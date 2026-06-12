import requests
import time

from strategy import MultiSignalStrategy
from config import ACCESS_TOKEN
from mapping import CORE_MAPPING, MOMENTUM_MAPPING
from alerts import send_alert

strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")
send_alert("🤖 BOT STARTED ✅\n\n🚀 Trading system is now active")

last_prices = {}
scan_cycle = 0

# ✅ send only once
nifty_sent = False


# ✅ ✅ NIFTY SENTIMENT FUNCTION
def nifty_sentiment_message(open_price, current_price, prev_close=None):

    if not open_price or not current_price:
        return None

    change = ((current_price - open_price) / open_price) * 100

    if change > 0.5:
        trend = "📈 UP"
    elif change < -0.5:
        trend = "📉 DOWN"
    else:
        trend = "➡️ FLAT"

    gap_msg = ""
    if prev_close:
        gap = ((open_price - prev_close) / prev_close) * 100

        if gap > 0.5:
            gap_msg = f"📊 GAP UP (+{round(gap,2)}%)"
        elif gap < -0.5:
            gap_msg = f"📊 GAP DOWN ({round(gap,2)}%)"
        else:
            gap_msg = f"📊 FLAT OPEN ({round(gap,2)}%)"

    return f"""
📊 NIFTY MARKET OPEN

{trend} ({round(change,2)}%)

{gap_msg}
"""


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
                    "volume": value.get("volume", 0),
                    "open": value.get("ohlc", {}).get("open"),
                    "prev_close": value.get("ohlc", {}).get("close")
                }

        except Exception as e:
            print("Batch error:", e)

    return prices


while True:
    try:
        scan_cycle += 1

        # ✅ CORE stocks
        prices = get_prices_batch(CORE_MAPPING)

        # ✅ MOMENTUM stocks every 3 cycles
        if scan_cycle % 3 == 0:
            prices.update(get_prices_batch(MOMENTUM_MAPPING))

        # ✅ fallback
        if not prices:
            prices = last_prices
        else:
            last_prices = prices

        # ✅ ✅ NIFTY SENTIMENT (ONLY ONCE)
        if not nifty_sent:

            nifty = prices.get("NIFTY")

            if nifty:
                msg = nifty_sentiment_message(
                    nifty.get("open"),
                    nifty.get("price"),
                    nifty.get("prev_close")
                )

                if msg:
                    send_alert(msg)
                    print("✅ NIFTY sentiment sent")

                    nifty_sent = True

        # ✅ ✅ MAIN STRATEGY (ALL ALERTS INSIDE THIS)
        for symbol, data in prices.items():
            strategy.update(symbol, data["price"], data["volume"])

        print(f"📊 Cycle {scan_cycle} | Stocks: {len(prices)}")

    except Exception as e:
        print("MAIN ERROR:", e)

    time.sleep(5)