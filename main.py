import requests
import time

from strategy import MultiSignalStrategy

strategy = MultiSignalStrategy()
from config import ACCESS_TOKEN
from mapping import MAPPING

# ✅ Init
strategy = MultiSignalStrategy()

strategy = MultiSignalStrategy()

# ✅ Use all stocks
STOCKS = list(MAPPING.keys())


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

        except Exception:
            continue

    return prices


print("🚀 Bot running ✅")

last_summary = 0

while True:
    try:
        prices = get_prices()

        for symbol, price in prices.items():
            strategy.update(symbol, price, 1)

        # ✅ Summary every 60 sec
        now = time.time()
        if now - last_summary > 60:
            print(f"📊 Running | {len(prices)} stocks ✅")
            last_summary = now

    except Exception as e:
        print("❌ ERROR:", e)

    # ✅ tuned for 40–60 stocks
    time.sleep(6)