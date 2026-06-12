import requests
import time
import traceback

from strategy import MultiSignalStrategy
from config import ACCESS_TOKEN
from mapping import CORE_MAPPING, MOMENTUM_MAPPING
from alerts import send_alert

strategy = MultiSignalStrategy()

print("🚀 Bot running ✅")

# ✅ START MESSAGE
send_alert(f"""
🤖 NteApp STARTED ✅

🕒 {time.strftime('%H:%M:%S')}
🚀 Trading system active
""")

last_prices = {}
scan_cycle = 0
nifty_sent = False

last_heartbeat = time.time()
last_error = ""
last_error_time = 0


# ✅ NIFTY SENTIMENT
def nifty_sentiment_message(open_price, current_price, prev_close=None):

    if not open_price or not current_price:
        return None

    change = ((current_price - open_price) / open_price) * 100

    trend = "📈 UP" if change > 0.5 else "📉 DOWN" if change < -0.5 else "➡️ FLAT"

    gap_msg = ""
    if prev_close:
        gap = ((open_price - prev_close) / prev_close) * 100
        gap_msg = f"📊 GAP {('UP' if gap > 0 else 'DOWN')} ({round(gap,2)}%)"

    return f"""
📊 NIFTY MARKET OPEN

{trend} ({round(change,2)}%)

{gap_msg}
"""


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


# ✅ MAIN LOOP
while True:
    try:
        scan_cycle += 1

        prices = get_prices_batch(CORE_MAPPING)

        if scan_cycle % 3 == 0:
            prices.update(get_prices_batch(MOMENTUM_MAPPING))

        if not prices:
            prices = last_prices
        else:
            last_prices = prices

        # ✅ NIFTY MESSAGE
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
                    nifty_sent = True

        # ✅ STRATEGY
        for symbol, data in prices.items():
            strategy.update(symbol, data["price"], data["volume"])

        # ✅ HEARTBEAT
        if time.time() - last_heartbeat > 3600:
            send_alert(f"""
🤖 BOT STATUS ✅

⏳ Still scanning...
📊 Stocks: {len(prices)}
🕒 {time.strftime('%H:%M:%S')}
""")
            last_heartbeat = time.time()

        print(f"📊 Cycle {scan_cycle} | Stocks: {len(prices)}")

    except Exception:

        error_text = traceback.format_exc()
        now = time.time()

        if error_text != last_error or now - last_error_time > 60:

            msg = f"""
❌ BOT ERROR 🚨

🕒 {time.strftime('%H:%M:%S')}

{error_text}
"""

            print(msg)

            try:
                send_alert(msg)
            except:
                print("Telegram failed")

            last_error = error_text
            last_error_time = now

        time.sleep(5)

    time.sleep(5)