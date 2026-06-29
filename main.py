import requests
import time
import json
import threading
import random
import traceback

from flask import Flask, jsonify

from alerts import send_alert, get_ist_time
from config import MODE, ACCESS_TOKEN
from strategy import MultiSignalStrategy
from mapping import MAPPING

# ✅ INIT
strategy = MultiSignalStrategy()
app = Flask(__name__, static_folder=".")


print("🚀 Bot running ✅")
send_alert(f"🤖 BOT STARTED ✅\nTime: {get_ist_time()}")


# ==============================
# ✅ DASHBOARD ROUTES
# ==============================

@app.route("/")
def home():
    return app.send_static_file("dashboard.html")


@app.route("/api/alerts")
def get_alerts():
    try:
        with open("alerts_log.json", "r") as f:
            data = json.load(f)
    except:
        data = []

    return jsonify(data)


# ==============================
# ✅ MARKET DATA
# ==============================

def get_prices_batch(mapping):
    url = "https://api.upstox.com/v2/market-quote/quotes"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    prices = {}

    keys = list(mapping.values())

    for i in range(0, len(keys), 20):
        batch = keys[i:i+20]

        try:
            res = requests.get(
                url,
                headers=headers,
                params={"instrument_key": ",".join(batch)},
                timeout=5
            )

            data = res.json()

            for _, v in data.get("data", {}).items():
                symbol = v.get("symbol") or v.get("instrument_key")
                if not symbol:
                    continue

                prices[symbol] = {
                    "price": v.get("last_price"),
                    "volume": v.get("volume", 0)
                }

        except Exception as e:
            print("Batch error:", e)

    return prices


# ==============================
# ✅ LIVE BOT
# ==============================

def run_bot():
    print("📈 LIVE MODE STARTED")

    while True:
        try:
            prices = get_prices_batch(MAPPING)

            for symbol, d in prices.items():
                strategy.update(symbol, d["price"], d["volume"])

            print(f"📊 Scanned: {len(prices)} stocks")

        except Exception:
            print(traceback.format_exc())

        time.sleep(5)


# ==============================
# ✅ TEST BOT
# ==============================

def generate_test_alerts():

    symbols = ["RELIANCE", "TCS", "INFY"]
    print("🧪 TEST MODE STARTED")

    while True:
        symbol = random.choice(symbols)
        direction = random.choice(["BUY", "SELL"])

        price = random.randint(1000, 3000)

        if direction == "BUY":
            sl = price - 20
            target = price + 40
        else:
            sl = price + 20
            target = price - 40

        confidence = random.randint(60, 95)
        trend = random.choice(["STRONG", "MEDIUM"])
        risk = random.choice(["LOW", "MEDIUM", "HIGH"])

        message = f"""
🔥 TRADE ALERT 🔥

{symbol} → {direction}
Time: {get_ist_time()}

Entry: ₹{price}
SL: ₹{sl}
Target: ₹{target}

📊 Confidence: {confidence}%
📈 Trend: {trend}
⚠️ Risk: {risk}
"""

        send_alert(
            message,
            symbol,
            direction,
            price,
            sl,
            target,
            "TEST",
            confidence,
            trend,
            risk
        )

        time.sleep(5)


# ==============================
# ✅ START APP + BOT
# ==============================

if __name__ == "__main__":

    if MODE == "LIVE":
        threading.Thread(target=run_bot, daemon=True).start()
    else:
        threading.Thread(target=generate_test_alerts, daemon=True).start()

    app.run(host="0.0.0.0", port=5000)
