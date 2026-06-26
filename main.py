import requests
import time
import json
import threading
import random

from flask import Flask, jsonify
from alerts import send_alert
from config import MODE, ACCESS_TOKEN

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


# ✅ ALERTS API
@app.route("/api/alerts")
def get_alerts():
    try:
        with open("alerts_log.json", "r") as f:
            data = json.load(f)
        return jsonify(list(reversed(data)))
    except:
        return jsonify([])


# ✅ TEST MODE (fake alerts)
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
        symbol = random.choice(symbols)
        strategy_name = random.choice(strategies)
        direction = random.choice(["BUY", "SELL"])

        price = base_prices[symbol] + random.randint(-100, 100)
        volume = random.randint(10000, 50000)

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

        time.sleep(5)


# ✅ LIVE MARKET API
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
                price = item["last_price"]
                volume = item.get("volume", 0)

                prices[symbol] = (price, volume)
            except:
                continue

    return prices


# ✅ ✅ LIVE BOT (WITH SCAN PRINT LIKE OLD VERSION)
def run_bot():
    print("📈 LIVE BOT STARTED")

    while True:
        try:
            prices = get_prices_batch()

            # ✅ process all stocks
            for symbol, (price, volume) in prices.items():
                strategy.update(symbol, price, volume)

            # ✅ process ranked signals
            strategy.process_top_signals()

            # ✅ OLD STYLE OUTPUT ✅
            print(f"📊 Scanned: {len(prices)} stocks")

        except Exception as e:
            print("Bot Error:", e)

        time.sleep(2)


# ✅ PRICE SOURCE FOR STATUS
def get_prices_for_status():
    if MODE == "LIVE":
        real = get_prices_batch()
        return {k: v[0] for k, v in real.items()}
    else:
        return {
            "NIFTY": random.randint(23400, 23600),
            "BANKNIFTY": random.randint(51800, 52200),
            "RELIANCE": random.randint(2950, 3050),
            "TCS": random.randint(3700, 3900),
            "INFY": random.randint(1450, 1600),
        }


# ✅ TRADE STATUS TRACKER
def update_trade_status():
    while True:
        try:
            try:
                with open("alerts_log.json", "r") as f:
                    alerts = json.load(f)
            except:
                alerts = []

            prices = get_prices_for_status()

            updated = False

            for alert in alerts:
                if alert.get("status") != "OPEN":
                    continue

                symbol = alert.get("symbol")
                direction = alert.get("direction")

                if symbol not in prices:
                    continue

                current_price = prices[symbol]
                target = alert.get("target")
                sl = alert.get("sl")

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


# ✅ START SYSTEM
if __name__ == "__main__":

    if MODE == "LIVE":
        print("📈 LIVE MODE ENABLED")
        threading.Thread(target=run_bot, daemon=True).start()
    else:
        print("🧪 TEST MODE ENABLED")
        threading.Thread(target=generate_test_alerts, daemon=True).start()

    threading.Thread(target=update_trade_status, daemon=True).start()

    app.run(host="0.0.0.0", port=5000)
