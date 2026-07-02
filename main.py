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


# ==============================
# ✅ INIT
# ==============================

strategy = MultiSignalStrategy()

app = Flask(
    __name__,
    static_folder="."
)

print("🚀 Bot running ✅")

send_alert(
    f"🤖 BOT STARTED ✅\nTime: {get_ist_time()}"
)


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

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    prices = {}

    keys = list(mapping.values())

    for i in range(0, len(keys), 20):

        batch = keys[i:i + 20]

        try:

            res = requests.get(
                url,
                headers=headers,
                params={
                    "instrument_key": ",".join(batch)
                },
                timeout=10
            )

            data = res.json()

            for _, v in data.get("data", {}).items():

                symbol = (
                    v.get("symbol")
                    or v.get("instrument_key")
                )

                if not symbol:
                    continue

                prices[symbol] = {
                    "price": v.get("last_price"),
                    "volume": v.get("volume", 0)
                }

        except Exception as e:

            print(
                f"❌ Batch Error : {e}"
            )

    return prices


# ==============================
# ✅ MARKET TREND
# ==============================

market_history = {}


def get_market_trend(prices):

    global market_history

    advances = 0
    declines = 0

    for symbol, data in prices.items():

        current_price = data.get("price")

        if current_price is None:
            continue

        previous_price = market_history.get(symbol)

        if previous_price is not None:

            if current_price > previous_price:
                advances += 1

            elif current_price < previous_price:
                declines += 1

        market_history[symbol] = current_price

    total = advances + declines

    if total == 0:
        return "SIDEWAYS"

    advance_ratio = advances / total

    if advance_ratio >= 0.60:
        return "UP"

    elif advance_ratio <= 0.40:
        return "DOWN"

    return "SIDEWAYS"


# ==============================
# ✅ LIVE BOT
# ==============================

def run_bot():

    print("📈 LIVE MODE STARTED")

    while True:

        start_time = time.time()

        try:

            prices = get_prices_batch(MAPPING)

            market_trend = get_market_trend(
                prices
            )

            strategy.set_market_trend(
                market_trend
            )

            for symbol, d in prices.items():

                try:

                    strategy.update(
                        symbol,
                        d["price"],
                        d["volume"]
                    )

                except Exception as e:

                    print(
                        f"⚠️ Strategy Error [{symbol}] : {e}"
                    )

            print(
                f"📊 {get_ist_time()} | "
                f"Market Trend: {market_trend} | "
                f"Scanned: {len(prices)} stocks"
            )

        except Exception:

            print(
                traceback.format_exc()
            )

        elapsed = time.time() - start_time

        sleep_time = max(
            0,
            60 - elapsed
        )

        print(
            f"⏳ Next scan in "
            f"{int(sleep_time)} sec"
        )

        time.sleep(sleep_time)


# ==============================
# ✅ TEST BOT
# ==============================

def generate_test_alerts():

    symbols = [
        "RELIANCE",
        "TCS",
        "INFY"
    ]

    print("🧪 TEST MODE STARTED")

    while True:

        symbol = random.choice(
            symbols
        )

        direction = random.choice(
            ["BUY", "SELL"]
        )

        price = random.randint(
            1000,
            3000
        )

        if direction == "BUY":

            sl = price - 20
            target = price + 40

        else:

            sl = price + 20
            target = price - 40

        confidence = random.randint(
            60,
            95
        )

        trend = random.choice(
            ["STRONG", "MEDIUM"]
        )

        risk = random.choice(
            ["LOW", "MEDIUM", "HIGH"]
        )

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

        threading.Thread(
            target=run_bot,
            daemon=True
        ).start()

    else:

        threading.Thread(
            target=generate_test_alerts,
            daemon=True
        ).start()

    app.run(
        host="0.0.0.0",
        port=5000
    )