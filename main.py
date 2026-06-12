import requests
import time
import traceback

from strategy import MultiSignalStrategy
from mapping import MAPPING
from config import ACCESS_TOKEN
from alerts import send_alert

strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")
send_alert("🤖 BOT STARTED ✅")


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


while True:
    try:
        prices = get_prices_batch(MAPPING)

        for symbol, d in prices.items():
            strategy.update(symbol, d["price"], d["volume"])

        print(f"📊 Scanned: {len(prices)} stocks")

    except Exception:
        print(traceback.format_exc())

    time.sleep(5)