import os
import json
import requests
import psycopg2
from datetime import datetime, timezone, timedelta
from psycopg2.extras import RealDictCursor
from pywebpush import webpush, WebPushException

from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# =========================
# 環境変数
# =========================
DATABASE_URL = os.environ.get("DATABASE_URL")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:test@example.com")
CRON_SECRET_KEY = os.environ.get("CRON_SECRET_KEY", "")

# =========================
# 日本時間
# =========================
JST = timezone(timedelta(hours=9))

def now_jst():
    return datetime.now(JST)

# =========================
# エリア
# =========================
AREAS = {
    "koto": {
        "name": "東京・江東区",
        "code": "13108"
    },
    "omotesando": {
        "name": "表参道",
        "code": "13113"
    }
}

PRESSURE_LEVEL = {
    "0": "通常",
    "1": "通常",
    "2": "やや注意",
    "3": "注意",
    "4": "警戒",
}

WEATHER = {
    "100": "☀️",
    "101": "🌤️",
    "102": "🌦️",
    "103": "🌦️",
    "200": "☁️",
    "201": "🌥️",
    "202": "🌧️",
    "203": "🌧️",
    "300": "☂️",
    "301": "🌧️",
    "302": "☔",
    "303": "☔",
    "400": "☃️",
}

# =========================
# DB
# =========================
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL が設定されていません")
    return psycopg2.connect(DATABASE_URL)


def init_notify_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS kiatsu_notifications (
            notification_key TEXT PRIMARY KEY,
            sent_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    conn.commit()
    conn.close()


# =========================
# スマホ通知
# =========================
def notify_all_devices_custom(title, body, url="/"):
    if not VAPID_PRIVATE_KEY:
        print("VAPID_PRIVATE_KEY が未設定です")
        return

    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id, subscription FROM push_subscriptions;")
    subs = cur.fetchall()

    payload = {
        "title": title,
        "body": body,
        "url": url
    }

    expired_ids = []

    for sub in subs:
        try:
            webpush(
                subscription_info=sub["subscription"],
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
        except WebPushException as e:
            if getattr(e.response, "status_code", None) in [404, 410]:
                expired_ids.append(sub["id"])
        except Exception as e:
            print("通知失敗:", e)

    for sid in expired_ids:
        cur.execute("DELETE FROM push_subscriptions WHERE id = %s;", (sid,))

    conn.commit()
    conn.close()


def already_sent(notification_key):
    init_notify_db()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT notification_key
        FROM kiatsu_notifications
        WHERE notification_key = %s;
    """, (notification_key,))

    exists = cur.fetchone() is not None

    if not exists:
        cur.execute("""
            INSERT INTO kiatsu_notifications (notification_key)
            VALUES (%s);
        """, (notification_key,))

    conn.commit()
    conn.close()

    return exists


# =========================
# 気圧データ取得
# =========================
def fetch_kiatsu(city_code):
    api_url = f"https://zutool.jp/api/getweatherstatus/{city_code}"
    res = requests.get(api_url, timeout=10)
    res.raise_for_status()
    return res.json()


# =========================
# 通常画面
# =========================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/kiatsu")
def api_kiatsu():
    area_key = request.args.get("area", "koto")

    if area_key not in AREAS:
        area_key = "koto"

    area = AREAS[area_key]
    data = fetch_kiatsu(area["code"])

    today_items = data.get("today", [])
    tomorrow_items = data.get("tommorow", data.get("tomorrow", []))

    now_hour = now_jst().hour
    start_hour = max(0, now_hour - 2)

    combined = []

    # 今日：今の2時間前〜
    for item in today_items:
        try:
            hour = int(item.get("time", 0))
            if hour >= start_hour:
                combined.append({
                    "label": f"{hour}時",
                    "item": item
                })
        except:
            pass

    # 明日：0〜5時
    for item in tomorrow_items:
        try:
            hour = int(item.get("time", 0))
            if 0 <= hour <= 5:
                combined.append({
                    "label": f"明日 {hour}時",
                    "item": item
                })
        except:
            pass

    filtered = []

    for row in combined:
        item = row["item"]
        level_code = str(item.get("pressure_level", ""))

        filtered.append({
            "hour": row["label"],
            "weather": WEATHER.get(str(item.get("weather")), "？"),
            "temp": item.get("temp", "-"),
            "pressure": item.get("pressure", "-"),
            "level_code": level_code
        })

    levels = [x["level_code"] for x in filtered]

    if "4" in levels:
        summary = "気圧かなり危険。無理しないで"
        status = "danger"
    elif "3" in levels:
        summary = "気圧注意。頭痛・だるさに注意"
        status = "warning"
    elif "2" in levels:
        summary = "少し気圧変化あり。様子見しよう"
        status = "caution"
    else:
        summary = "比較的安定してそう"
        status = "normal"

    return jsonify({
        "area": area_key,
        "city": area["name"],
        "updated": now_jst().strftime("%m/%d %H:%M 更新"),
        "summary": summary,
        "status": status,
        "items": filtered
    })


# =========================
# 無料cron用通知URL
# =========================
@app.route("/notify-kiatsu")
def notify_kiatsu():
    key = request.args.get("key", "")

    if not CRON_SECRET_KEY or key != CRON_SECRET_KEY:
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 401

    now = now_jst()
    notified = []

    for area_key, area in AREAS.items():
        try:
            data = fetch_kiatsu(area["code"])
            today_items = data.get("today", [])

            for i in range(len(today_items) - 1):
                current = today_items[i]
                nxt = today_items[i + 1]

                try:
                    target_hour = int(nxt.get("time", 0))
                    before_level = str(current.get("pressure_level", ""))
                    next_level = str(nxt.get("pressure_level", ""))

                    target_time = now.replace(
                        hour=target_hour,
                        minute=0,
                        second=0,
                        microsecond=0
                    )

                    diff_seconds = (target_time - now).total_seconds()

                    # 30分以内じゃなければスキップ
                    if not (0 < diff_seconds <= 1800):
                        continue

                    message = None

                    # 平常 → やや注意
                    if before_level in ["0", "1"] and next_level == "2":
                        message = f"{area['name']}：あと30分以内に気圧が黄色になります"

                    # やや注意 → 注意
                    elif before_level == "2" and next_level == "3":
                        message = f"{area['name']}：あと30分以内に気圧が赤になります⚠️"

                    if not message:
                        continue

                    notification_key = (
                        f"{area_key}-"
                        f"{now.strftime('%Y%m%d')}-"
                        f"{target_hour}-"
                        f"{before_level}-"
                        f"{next_level}"
                    )

                    if already_sent(notification_key):
                        print("通知済み:", notification_key)
                        continue

                    notify_all_devices_custom(
                        title="気圧どうかな？",
                        body=message,
                        url="/"
                    )

                    notified.append({
                        "area": area["name"],
                        "hour": target_hour,
                        "from": before_level,
                        "to": next_level,
                        "message": message
                    })

                except Exception as e:
                    print("時間チェック失敗:", e)

        except Exception as e:
            print("エリアチェック失敗:", area["name"], e)

    return jsonify({
        "ok": True,
        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "notified": notified,
        "count": len(notified)
    })


# =========================
# 起動
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)