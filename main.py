import requests
import time

from strategy import MultiSignalStrategy
from config import ACCESS_TOKEN
from mapping import MAPPING
from alerts import send_alert

strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")

last_summary = 0
last_scan_alert = 0
last_prices = {}


def get_prices_batch():
    url = "https://api.upstox.com/v2/market-quote/quotes"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    prices = {}
    keys = list(MAPPING.values())
    BATCH_SIZE = 20

    for i in range(0, len(keys), BATCH_SIZE):
        batch = keys[i:i + BATCH_SIZE]

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
        prices = get_prices_batch()

        if not prices:
            prices = last_prices
        else:
            last_prices = prices

        for symbol, data in prices.items():
            strategy.update(symbol, data["price"], data["volume"])

        now = time.time()

        # ✅ 5‑MIN SUMMARY
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

        if now - last_summary > 60:
            print(f"📊 Running | {len(prices)} stocks ✅")
            last_summary = now

    except Exception as e:
        print("MAIN ERROR:", e)

    time.sleep(5)
