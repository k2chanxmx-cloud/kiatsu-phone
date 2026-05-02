from flask import Flask, render_template, jsonify, request
import requests
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

JST = timezone(timedelta(hours=9))

def now_jst():
    return datetime.now(JST)

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

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/kiatsu")
def api_kiatsu():
    area_key = request.args.get("area", "koto")

    if area_key not in AREAS:
        area_key = "koto"

    area = AREAS[area_key]
    api_url = f"https://zutool.jp/api/getweatherstatus/{area['code']}"

    res = requests.get(api_url, timeout=10)
    res.raise_for_status()
    data = res.json()

    today_items = data.get("today", [])
    tomorrow_items = data.get("tommorow", data.get("tomorrow", []))

    now_hour = now_jst().hour
    start_hour = max(0, now_hour - 2)

    combined = []

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
            "level_code": level_code,
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)