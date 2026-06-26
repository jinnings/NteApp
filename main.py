import requests
import time
import json
import threading
import random

from flask import Flask, jsonify
from alerts import send_alert
from config import MODE, ACCESS_TOKEN

# ✅ LIVE imports (always loaded — no comments needed)
from strategy import MultiSignalStrategy
from mapping import MAPPING

strategy = MultiSignalStrategy()

app = Flask(__name__, static_folder=".")

print("🚀 Bot running ✅")
send_alert("🤖 BOT STARTED ✅")


# ✅ HOME
@app.route("/")
def home():
    return app.send_static_file("dashboard.html")


# ✅ API
@app.route("/api/alerts")
def get_alerts():
    try:
        with open("alerts_log.json", "r") as f:
            data = json.load(f)
        return jsonify(list(reversed(data)))
    except:
        return jsonify([])


# ✅ ✅ FAKE ALERT GENERATOR
def generate_test_alerts():
    symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "INFY"]
    strategies = ["BREAKOUT", "SCALPING", "REVERSAL"]

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
            strategy_name = random.choice(strategies)
            direction = random.choice(["BUY", "SELL"])

            price = base_prices[symbol] + random.randint(-100, 100)

            if direction == "BUY":
                sl = price - random.randint(10, 80)
                target = price + random.randint(20, 150)
            else:
                sl = price + random.randint(10, 80)
                target = price - random.randint(20, 150)

            message = f"""{symbol} {direction} ({strategy_name})
Entry: {price}
SL: {sl}
Target: {target}"""

            send_alert(message, symbol, direction, price, sl, target, strategy_name)

        except Exception as e:
            print("Test Error:", e)

        time.sleep(5)


# ✅ ✅ LIVE MARKET PRICE
def get_prices_batch():
    url = "https://api.upstox.com/v2/market-quote/quotes"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    params = {
        "instrument_key": ",".join(MAPPING.values())
    }

    try:
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
    except:
        return {}

    prices = {}

    if "data" in data:
        for symbol, key in MAPPING.items():
            try:
                item = data["data"][key]
                prices[symbol] = item["last_price"]
            except:
                continue

    return prices


# ✅ ✅ PRICE SWITCH (AUTO BY CONFIG)
def get_prices():
    if MODE == "LIVE":
        return get_prices_batch()
    else:
        return {
            "NIFTY": random.randint(23400, 23600),
            "BANKNIFTY": random.randint(51800, 52200),
            "RELIANCE": random.randint(2950, 3050),
            "TCS": random.randint(3700, 3900),
            "INFY": random.randint(1450, 1600),
        }


# ✅ ✅ REAL BOT (always available)
def run_bot():
    print("📈 LIVE BOT STARTED")

    while True:
        try:
            prices = get_prices_batch()

            for symbol, price in prices.items():
                strategy.update(symbol, price, 0)

        except Exception as e:
            print("Bot Error:", e)

        time.sleep(2)


# ✅ ✅ TRADE STATUS TRACKER
def update_trade_status():
    while True:
        try:
            try:
                with open("alerts_log.json", "r") as f:
                    alerts = json.load(f)
            except:
                alerts = []

            prices = get_prices()

            updated = False

            for alert in alerts:
                if alert.get("status") != "OPEN":
                    continue

                symbol = alert.get("symbol")
                direction = alert.get("direction")
                target = alert.get("target")
                sl = alert.get("sl")

                if symbol not in prices:
                    continue

                current_price = prices[symbol]

                if direction == "BUY":
                    if current_price >= target:
                        alert["status"] = "TARGET HIT ✅"
                        alert["timestamp"] = time.time()
                        updated = True
                    elif current_price <= sl:
                        alert["status"] = "SL HIT ❌"
                        alert["timestamp"] = time.time()
                        updated = True

                elif direction == "SELL":
                    if current_price <= target:
                        alert["status"] = "TARGET HIT ✅"
                        alert["timestamp"] = time.time()
                        updated = True
                    elif current_price >= sl:
                        alert["status"] = "SL HIT ❌"
                        alert["timestamp"] = time.time()
                        updated = True

            if updated:
                with open("alerts_log.json", "w") as f:
                    json.dump(alerts, f, indent=2)

        except Exception as e:
            print("Status error:", e)

        time.sleep(3)


# ✅ ✅ START SYSTEM (NO COMMENTING EVER)
def start_system():
    if MODE == "LIVE":
        print("📈 LIVE MODE ENABLED")
        threading.Thread(target=run_bot, daemon=True).start()
    else:
        print("🧪 TEST MODE ENABLED")
        threading.Thread(target=generate_test_alerts, daemon=True).start()


# ✅ ✅ MAIN
if __name__ == "__main__":
    start_system()

    threading.Thread(target=update_trade_status, daemon=True).start()

    app.run(host="0.0.0.0", port=5000)
