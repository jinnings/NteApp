import requests
import time

from strategy import MultiSignalStrategy
from config import ACCESS_TOKEN
from mapping import CORE_MAPPING, MOMENTUM_MAPPING
from alerts import send_alert

strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")

last_scan_alert = 0
last_prices = {}
scan_cycle = 0


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
                params={"instrument_key": ",".join(batch)},
                timeout=5
            )
            data = res.json()

            if "data" not in data:
                continue

            for _, value in data["data"].items():
                symbol = value.get("symbol")

                if not symbol:
                    continue

                prices[symbol] = {
                    "price": value.get("last_price"),
                    "volume": value.get("volume", 0)
                }

        except Exception as e:
            print("Batch error:", e)

    return prices


while True:
    try:
        scan_cycle += 1

        # ✅ CORE stocks
        prices = get_prices_batch(CORE_MAPPING)

        # ✅ MOMENTUM every 3rd cycle
        if scan_cycle % 3 == 0:
            prices.update(get_prices_batch(MOMENTUM_MAPPING))

        # ✅ fallback
        if not prices:
            prices = last_prices
        else:
            last_prices = prices

        # ✅ strategy update
        for symbol, data in prices.items():
            strategy.update(symbol, data["price"], data["volume"])

        # ✅ TIME (IMPORTANT)
        now = time.time()

        # ✅ ✅ RUNNERS ALERT (FIXED PLACEMENT)
        if now - strategy.runner_alert_time > 120:

            runners = strategy.get_runners()

            if runners:
                msg = "📈 TODAY'S RUNNERS (PULLBACK ENTRY ✅)\n\n"

                for i, stock in enumerate(runners, 1):
                    arrow = "🟢 BUY" if stock["direction"] == "BUY" else "🔴 SELL"

                    msg += (
                        f"{i}. {stock['symbol']}\n"
                        f"{arrow} | Pullback ₹{stock['price']}\n"
                        f"Change: {stock['change']}%\n\n"
                    )

                send_alert(msg)
            else:
                print("No pullback runners")

            strategy.runner_alert_time = now

        # ✅ 5-min summary
        if now - last_scan_alert > 300:

            top = strategy.get_top_stocks()

            if top:
                msg = "🔥 TOP INTRADAY SETUPS 🔥\n\n"

                for i, s in enumerate(top, 1):
                    msg += (
                        f"{i}. {s['symbol']} ({s['direction']})\n"
                        f"Entry: ₹{s['price']}\n"
                        f"SL: ₹{s['sl']}\n"
                        f"Target: ₹{s['target']}\n"
                        f"{s['rating']} ⭐{s['score']}\n\n"
                    )
            else:
                msg = "⚠️ No strong setups found"

            send_alert(msg)
            last_scan_alert = now

        print(f"📊 Cycle {scan_cycle} | Stocks: {len(prices)}")

    except Exception as e:
        print("MAIN ERROR:", e)

    time.sleep(5)