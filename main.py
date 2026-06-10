import requests
import time

from strategy import BreakoutAlert
from config import ACCESS_TOKEN
from stocks import get_top_20_stocks

strategy = BreakoutAlert()

STOCKS = get_top_20_stocks()


def convert_symbol_to_instrument(symbol):
    mapping = {
        "NSE_EQ:RELIANCE": "NSE_EQ|INE002A01018",
        "NSE_EQ:TCS": "NSE_EQ|INE467B01029",
        "NSE_EQ:HDFCBANK": "NSE_EQ|INE040A01034",
        "NSE_EQ:INFY": "NSE_EQ|INE009A01021",
        "NSE_EQ:ICICIBANK": "NSE_EQ|INE090A01021",
        "NSE_EQ:LT": "NSE_EQ|INE018A01030",
        "NSE_EQ:SBIN": "NSE_EQ|INE062A01020",
        "NSE_EQ:AXISBANK": "NSE_EQ|INE238A01034",
        "NSE_EQ:ITC": "NSE_EQ|INE154A01025",
        "NSE_EQ:KOTAKBANK": "NSE_EQ|INE237A01028",
        "NSE_EQ:HINDUNILVR": "NSE_EQ|INE030A01027",
       "NSE_EQ:BAJFINANCE": "NSE_EQ|INE918I01026",
        "NSE_EQ:ASIANPAINT": "NSE_EQ|INE021A01026",
        "NSE_EQ:MARUTI": "NSE_EQ|INE585B01010",
        "NSE_EQ:TITAN": "NSE_EQ|INE280A01028",
        "NSE_EQ:WIPRO": "NSE_EQ|INE075A01022",
        "NSE_EQ:ULTRACEMCO": "NSE_EQ|INE481G01011",
        "NSE_EQ:ADANIENT": "NSE_EQ|INE423A01024",
        "NSE_EQ:NTPC": "NSE_EQ|INE733E01010",
        "NSE_EQ:POWERGRID": "NSE_EQ|INE752E01010"
    }

    return mapping.get(symbol)


def get_prices():
    url = "https://api.upstox.com/v2/market-quote/ltp"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    prices = {}

    for symbol in STOCKS:
        instrument_key = convert_symbol_to_instrument(symbol)

        if not instrument_key:
            print(f"⚠️ No mapping for {symbol}")
            continue

        try:
            res = requests.get(url, headers=headers, params={
                "instrument_key": instrument_key
            })

            data = res.json()

            if "data" in data and symbol in data["data"]:
                price = data["data"][symbol]["last_price"]
                prices[symbol] = price
            else:
                print(f"⚠️ No data for {symbol}")

        except Exception as e:
            print(f"❌ Error for {symbol}:", e)

    return prices

print("🚀 Starting MULTI-STOCK BOT (20 stocks)...")

while True:
    prices = get_prices()

    for symbol, price in prices.items():
        print(f"✅ {symbol} PRICE: {price}")

        # ✅ Feed into strategy
        strategy.update(symbol, price, 1)

    time.sleep(2)