import requests
import time

from strategy import MultiSignalStrategy
from config import ACCESS_TOKEN
from mapping import MAPPING
from alerts import send_alert

# ✅ init
strategy = MultiSignalStrategy()

STOCKS = list(MAPPING.keys())

last_summary = 0
last_telegram = 0

# ✅ restart alert (only once)
send_alert("⚠️ Bot started / restarted ✅")


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


print("🚀 Bot running ✅")


while True:
    try:
        prices = get_prices()

        if not prices:
            print("⚠️ No data from API — retrying...")
            time.sleep(10)
            continue

        for symbol, price in prices.items():

            # ✅ Run strategy
            strategy.update(symbol, price, 1)

            # ✅ Print ONLY ZOMATO CMP (monitoring)
            if symbol == "NSE_EQ:ZOMATO":
                print(f"📊 ZOMATO CMP: ₹{price}")

        # ✅ Summary every 60 sec
        now = time.time()
        if now - last_summary > 60:
            print(f"📊 Running | {len(prices)} stocks ✅")

            if "NSE_EQ:ZOMATO" in prices:
                print(f"📊 ZOMATO CMP: ₹{prices['NSE_EQ:ZOMATO']}")

            last_summary = now

        # ✅ Telegram heartbeat every 5 minutes
        if now - last_telegram > 300:
            send_alert(f"📊 Bot running | {len(prices)} stocks ✅")
            last_telegram = now

    except Exception as e:
        print("❌ ERROR:", e)
        time.sleep(5)

    time.sleep(6)