import requests
import time
import json
import threading
import random
import datetime

from flask import Flask, jsonify
from strategy import MultiSignalStrategy
from mapping import MAPPING
from config import ACCESS_TOKEN
from alerts import send_alert

# ✅ Flask
app = Flask(__name__, static_folder=".")

strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")
send_alert("🤖 BOT STARTED ✅")


# ✅ ✅ HOME (no 404)
@app.route("/")
def home():
    return app.send_static_file("dashboard.html")


# ✅ ✅ API
@app.route("/api/alerts")
def get_alerts():
    try:
        with open("alerts_log.json", "r") as f:
            data = json.load(f)
        return jsonify(list(reversed(data)))
    except:
        return jsonify([])


# ✅ ✅ SAFE REQUEST
def safe_request(url, headers, params):
    for _ in range(3):
        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                return res.json()
        except:
            time.sleep(1)
    return None


# ✅ ✅ FETCH REAL MARKET DATA
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


# ✅ ✅ REAL BOT
def run_bot():
    print("📈 LIVE MODE STARTED")

    while True:
        try:
            prices = get_prices_batch(MAPPING)

            for symbol, (price, volume) in prices.items():
                strategy.update(symbol, price, volume)

        except Exception as e:
            print("Bot Error:", e)

        time.sleep(2)


# ✅ ✅ FAKE ALERT GENERATOR
def generate_test_alerts():
    symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "INFY"]
    base_prices = {
        "NIFTY": 23500,
        "BANKNIFTY": 52000,
        "RELIANCE": 3000,
        "TCS": 3800,
        "INFY": 1500
    }

    print("🧪 TEST MODE STARTED")

    while True:
        try:
            symbol = random.choice(symbols)

            direction = random.choices(
                ["BUY", "SELL"],
                weights=[0.6, 0.4]
            )[0]

            price = base_prices[symbol] + random.randint(-100, 100)

            if direction == "BUY":
                sl = price - random.randint(10, 80)
                target = price + random.randint(20, 150)
            else:
                sl = price + random.randint(10, 80)
                target = price - random.randint(20, 150)

            message = f"""{symbol} {direction} at {price}
SL: {sl}
Target: {target}"""

            send_alert(message)

        except Exception as e:
            print("Test Error:", e)

        time.sleep(5)


# ✅ ✅ AUTO SWITCH LOGIC
def is_market_open():
    now = datetime.datetime.now()

    # ✅ Weekdays only
    if now.weekday() >= 5:
        return False

    # ✅ Indian market time: 9:15 AM to 3:30 PM
    market_start = now.replace(hour=9, minute=15, second=0)
    market_end = now.replace(hour=15, minute=30, second=0)

    return market_start <= now <= market_end


# ✅ ✅ MODE MANAGER
def start_system():
    if is_market_open():
        threading.Thread(target=run_bot, daemon=True).start()
    else:
        threading.Thread(target=generate_test_alerts, daemon=True).start()


# ✅ ✅ START
if __name__ == "__main__":
    start_system()
    app.run(host="0.0.0.0", port=5000)