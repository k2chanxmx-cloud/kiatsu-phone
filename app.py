from flask import Flask, render_template, jsonify
import requests
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# =========================
# 時間（日本時間固定）
# =========================
JST = timezone(timedelta(hours=9))

def now_jst():
    return datetime.now(JST)

# =========================
# 設定
# =========================
CITY_CODE = "13108"
CITY_NAME = "東京・江東区"
API_URL = f"https://zutool.jp/api/getweatherstatus/{CITY_CODE}"

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
# 画面
# =========================
@app.route("/")
def index():
    return render_template("index.html")

# =========================
# API
# =========================
@app.route("/api/kiatsu")
def api_kiatsu():
    res = requests.get(API_URL, timeout=10)
    res.raise_for_status()
    data = res.json()

    items = data.get("today", data.get("weather", []))

    # ⭐ 日本時間で判定
    now_hour = now_jst().hour
    start_hour = max(0, now_hour - 2)

    filtered = []
    for item in items:
        try:
            hour = int(item.get("time", 0))
            if hour >= start_hour:
                level_code = str(item.get("pressure_level", ""))
                filtered.append({
                    "hour": hour,
                    "weather": WEATHER.get(str(item.get("weather")), "？"),
                    "temp": item.get("temp", "-"),
                    "pressure": item.get("pressure", "-"),
                    "level": PRESSURE_LEVEL.get(level_code, "不明"),
                    "level_code": level_code,
                    "bad": level_code in ["3", "4"]
                })
        except:
            pass

    # サマリー判定
    levels = [x["level_code"] for x in filtered]

    if "4" in levels:
        summary = "今日は気圧かなり危険。無理しないで"
        status = "danger"
    elif "3" in levels:
        summary = "今日は気圧注意。頭痛・だるさに注意"
        status = "warning"
    elif "2" in levels:
        summary = "少し気圧変化あり。様子見しよう"
        status = "caution"
    else:
        summary = "今日は比較的安定してそう"
        status = "normal"

    return jsonify({
        "city": CITY_NAME,
        "updated": now_jst().strftime("%m/%d %H:%M 更新"),
        "summary": summary,
        "status": status,
        "items": filtered
    })

# =========================
# 起動
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)