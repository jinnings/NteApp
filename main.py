import requests
import time
import json
import threading
import os

from flask import Flask, jsonify, send_from_directory

from strategy import MultiSignalStrategy
from mapping import MAPPING
from config import ACCESS_TOKEN
from alerts import send_alert

# ✅ Flask setup
app = Flask(__name__)
strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")
send_alert("🤖 BOT STARTED ✅")


# ✅ ✅ HOME ROUTE (FIXES YOUR 404 ERROR)
@app.route("/")
def home():
    return send_from_directory(os.getcwd(), "dashboard.html")


# ✅ API ENDPOINT
@app.route("/api/alerts")
def get_alerts():
    try:
        with open("alerts_log.json", "r") as f:
            data = json.load(f)

        return jsonify(list(reversed(data)))  # newest first
    except:
        return jsonify([])


# ✅ SAFE REQUEST (retry)
def safe_request(url, headers, params):
    for _ in range(3):
        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                return res.json()
        except:
            time.sleep(1)
    return None


# ✅ FETCH MARKET DATA
def get_prices_batch(mapping):
    url = "https://api.upstox.com/v2/market-quote/quotes"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    params = {
        "instrument_key": ",".join(mapping.values())
    }

    data = safe_request(url, headers, params)

    prices = {}

    if data and "data" in data:
        for symbol, key in mapping.items():
            try:
                item = data["data"][key]
                price = item["last_price"]
                volume = item.get("volume", 0)

                prices[symbol] = (price, volume)
            except:
                continue

    return prices


# ✅ BOT LOOP
def run_bot():
    while True:
        try:
            prices = get_prices_batch(MAPPING)

            for symbol, (price, volume) in prices.items():
                strategy.update(symbol, price, volume)

        except Exception as e:
            print("Bot Error:", e)

        time.sleep(2)


# ✅ START EVERYTHING
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

    app.run(host="0.0.0.0", port=5000)