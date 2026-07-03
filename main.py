import requests
import time
import traceback

from mapping import MAPPING
from config import ACCESS_TOKEN
from alerts import send_alert

from strategy import (
    MultiSignalStrategy,
    PullbackStrategy
)

multi_strategy = MultiSignalStrategy()
pullback_strategy = PullbackStrategy()

print("🚀 Bot running ✅")
send_alert("🤖 BOT STARTED ✅")


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
                timeout=5
            )

            data = res.json()

            for instrument_key, v in data.get("data", {}).items():

                prices[instrument_key] = {
                    "price": v.get("last_price"),
                    "volume": v.get("volume", 0)
                }

        except Exception as e:
            print("Batch error:", e)

    return prices


while True:

    try:

        print(f"📋 Mapping Count: {len(MAPPING)}")

        prices = get_prices_batch(MAPPING)

        print(f"✅ API Returned: {len(prices)}")

        for instrument_key, d in prices.items():

            symbol = next(
                (
                    k.replace("NSE_EQ:", "")
                    for k, v in MAPPING.items()
                    if v == instrument_key
                ),
                instrument_key
            )

            price = d.get("price")
            volume = d.get("volume", 0)

            if price is None:
                continue

            # ✅ Original Strategy
            multi_strategy.update(
                symbol,
                price,
                volume
            )

            # ✅ Pullback Strategy
            pullback_strategy.update(
                symbol,
                price,
                volume
            )

        # ✅ Top Ranked Signals
        multi_strategy.process_top_signals()

        print(
            f"📊 Scanned {len(prices)} Stocks | {time.strftime('%H:%M:%S')}"
        )

    except Exception:

        print(
            "❌ ERROR\n",
            traceback.format_exc()
        )

    # ✅ Wait before next scan
    time.sleep(15)