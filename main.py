import requests
import time

from strategy import MultiSignalStrategy
from config import ACCESS_TOKEN
from mapping import MAPPING

strategy = MultiSignalStrategy()

STOCKS = list(MAPPING.keys())

last_summary = 0

print("🚀 Bot running ✅")


def get_prices():
    url = "https://api.upstox.com/v2/market-quote/ltp"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    prices = {}

    for symbol in STOCKS:
        instrument_key = MAPPING.get(symbol)

        try:
            res = requests.get(
                url,
                headers=headers,
                params={"instrument_key": instrument_key}
            )

            data = res.json()

            if "data" in data and symbol in data["data"]:
                prices[symbol] = data["data"][symbol]["last_price"]

        except:
            continue

    return prices


while True:
    try:
        prices = get_prices()

        if not prices:
            print("⚠️ API returned no data — continuing...")

        for symbol, price in prices.items():
            strategy.update(symbol, price, 1)

            # ✅ monitor one stock
            if symbol == "NSE_EQ:ZOMATO":
                print(f"📊 ZOMATO CMP: ₹{price}")

        now = time.time()

        if now - last_summary > 60:
            print(f"📊 Running | {len(prices)} stocks ✅")
            last_summary = now

    except Exception as e:
        print("❌ ERROR:", e)

    time.sleep(6)