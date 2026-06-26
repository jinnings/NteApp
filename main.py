import requests
import time
import json
import threading
import random
import traceback

from flask import Flask, jsonify
from alerts import send_alert
from config import MODE, ACCESS_TOKEN

from strategy import MultiSignalStrategy
from mapping import MAPPING

strategy = MultiSignalStrategy()

app = Flask(__name__, static_folder=".")

# ✅ GLOBAL STATS (WITH SESSION TIME)
stats = {
    "scanned": 0,
    "open_trades": 0,
    "closed_trades": 0,
    "pnl": 0,
    "start_time": time.time()
}

print("🚀 Bot running ✅")
send_alert("🤖 BOT STARTED ✅")


@app.route("/")
def home():
    return app.send_static_file("dashboard.html")


@app.route("/api/alerts")
def get_alerts():
    try:
        with open("alerts_log.json", "r") as f:
            data = json.load(f)
        return jsonify(list(reversed(data)))
    except:
        return jsonify([])


@app.route("/api/stats")
def get_stats():
    return jsonify(stats)


# ✅ RESET (SESSION BASED)
@app.route("/api/reset", methods=["POST"])
def reset_stats():
    global stats

    stats = {
        "scanned": 0,
        "open_trades": 0,
        "closed_trades": 0,
        "pnl": 0,
        "start_time": time.time()  # ✅ key fix
    }

    print("🔄 SESSION RESET ✅")

    return jsonify({"status": "reset success"})


# ✅ ORIGINAL WORKING FETCH (UNCHANGED ✅)
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


# ✅ LIVE BOT
def run_bot():
    print("📈 LIVE MODE STARTED")

    while True:
        try:
            prices = get_prices_batch(MAPPING)

            for symbol, d in prices.items():
                strategy.update(symbol, d["price"], d["volume"])

            strategy.process_top_signals()

            stats["scanned"] = len(prices)

            print(f"📊 Scanned: {len(prices)} stocks")

        except Exception:
            print(traceback.format_exc())

        time.sleep(5)


# ✅ TEST MODE
def generate_test_alerts():
    symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "INFY"]
    strategies = ["BREAKOUT", "SCALPING", "REVERSAL"]

    print("🧪 TEST MODE STARTED")

    while True:
        symbol = random.choice(symbols)
        strategy_name = random.choice(strategies)
        direction = random.choice(["BUY", "SELL"])

        price = random.randint(1000, 5000)

        send_alert(
            f"{symbol} {direction}",
            symbol,
            direction,
            price,
            price - 20,
            price + 40,
            strategy_name
        )

        time.sleep(5)


# ✅ PRICE SOURCE
def get_prices_for_status():
    if MODE == "LIVE":
        real = get_prices_batch(MAPPING)
        return {k: v["price"] for k, v in real.items()}
    return {}


# ✅ ✅ FIXED TRADE STATUS (SESSION BASED ✅)
def update_trade_status():
    while True:
        try:
            try:
                with open("alerts_log.json", "r") as f:
                    alerts = json.load(f)
            except:
                alerts = []

            prices = get_prices_for_status()

            open_count = 0
            closed_count = 0
            total_pnl = 0

            session_start = stats.get("start_time", 0)

            for alert in alerts:
                try:
                    alert_time = time.mktime(
                        time.strptime(alert.get("time"), "%Y-%m-%d %H:%M:%S")
                    )
                except:
                    continue

                # ✅ ONLY CURRENT SESSION
                if alert_time < session_start:
                    continue

                if alert.get("status") == "OPEN":
                    open_count += 1

                    symbol = alert.get("symbol")
                    direction = alert.get("direction")
                    entry = alert.get("entry")
                    target = alert.get("target")
                    sl = alert.get("sl")

                    if symbol not in prices:
                        continue

                    current_price = prices[symbol]

                    if direction == "BUY":
                        if current_price >= target:
                            alert["status"] = "TARGET HIT ✅"
                            alert["pnl"] = round(target - entry, 2)

                        elif current_price <= sl:
                            alert["status"] = "SL HIT ❌"
                            alert["pnl"] = round(sl - entry, 2)

                    elif direction == "SELL":
                        if current_price <= target:
                            alert["status"] = "TARGET HIT ✅"
                            alert["pnl"] = round(entry - target, 2)

                        elif current_price >= sl:
                            alert["status"] = "SL HIT ❌"
                            alert["pnl"] = round(entry - sl, 2)

                else:
                    closed_count += 1
                    total_pnl += alert.get("pnl", 0)

            stats["open_trades"] = open_count
            stats["closed_trades"] = closed_count
            stats["pnl"] = round(total_pnl, 2)

            with open("alerts_log.json", "w") as f:
                json.dump(alerts, f, indent=2)

        except Exception as e:
            print("Status error:", e)

        time.sleep(3)


# ✅ START SYSTEM
if __name__ == "__main__":

    if MODE == "LIVE":
        threading.Thread(target=run_bot, daemon=True).start()
    else:
        threading.Thread(target=generate_test_alerts, daemon=True).start()

    threading.Thread(target=update_trade_status, daemon=True).start()

    app.run(host="0.0.0.0", port=5000)