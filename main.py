import requests
import time

from strategy import MultiSignalStrategy
from config import ACCESS_TOKEN
from mapping import MAPPING

strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")

last_summary = 0
last_prices = {}


def get_prices_batch():
    url = "https://api.upstox.com/v2/market-quote/quotes"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/json"
    }

    prices = {}
    instrument_list = list(MAPPING.values())

    BATCH_SIZE = 20

    for i in range(0, len(instrument_list), BATCH_SIZE):
        batch = instrument_list[i:i + BATCH_SIZE]

        try:
            res = requests.get(
                url,
                headers=headers,
                params={"instrument_key": ",".join(batch)},
                timeout=5
            )

            # ✅ DEBUG (can remove later)
            print("\n----------------------")
            print("BATCH:", batch)
            print("STATUS CODE:", res.status_code)
            print("----------------------\n")

            if res.status_code != 200:
                print("❌ HTTP ERROR:", res.status_code, res.text)
                continue

            data = res.json()

            # ✅ API error check
            if data.get("status") == "error":
                print("❌ API ERROR:", data)
                continue

            if "data" not in data or not data["data"]:
                print("⚠️ Empty market data for batch")
                continue

            # ✅ ✅ FIX APPLIED HERE
            for instrument_key, value in data["data"].items():

                # ✅ use symbol from response directly
                symbol = value.get("symbol")   # e.g., NHPC, UPL

                prices[symbol] = {
                    "price": value.get("last_price"),
                    "volume": value.get("volume", 0)
                }

        except Exception as e:
            print("❌ Batch error:", e)

    return prices


while True:
    try:
        prices = get_prices_batch()

        # ✅ fallback logic
        if not prices:
            print("⚠️ API returned no data — using last values")
            prices = last_prices
        else:
            last_prices = prices

        # ✅ strategy update
        for symbol, data in prices.items():
            price = data["price"]
            volume = data["volume"]

            strategy.update(symbol, price, volume)

            # ✅ example tracking
            if symbol == "ZOMATO":  # <-- changed
                print(f"📊 ZOMATO CMP: ₹{price} | Vol: {volume}")

        now = time.time()

        if now - last_summary > 60:
            print(f"📊 Running | {len(prices)} stocks ✅")
            last_summary = now

    except Exception as e:
        print("❌ MAIN LOOP ERROR:", e)

    time.sleep(5)