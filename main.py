import requests
import time
import traceback

from strategy import MultiSignalStrategy
from config import ACCESS_TOKEN
from mapping import MAPPING
from alerts import send_alert

strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")
send_alert("🤖 BOT STARTED ✅")

last_prices = {}
scan_cycle = 0


def get_prices_batch(mapping):

    url = "https://api.upstox.com/v2/market-quote/quotes"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

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

            for _, value in data.get("data", {}).items():

                symbol = value.get("symbol") or value.get("instrument_key")

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

        prices = get_prices_batch(MAPPING)

        for symbol, data in prices.items():
            strategy.update(symbol, data["price"], data["volume"])

        print(f"📊 Cycle {scan_cycle} | Stocks: {len(prices)} ✅")

    except Exception:
        print(traceback.format_exc())

    time.sleep(5)