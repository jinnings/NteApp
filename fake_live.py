import time
import random

from alerts import send_alert

print("🚀 Fake Live Price Sender ✅")

symbols = ["RELIANCE", "TCS", "INFY"]

base_prices = {
    "RELIANCE": 2850,
    "TCS": 3900,
    "INFY": 1500
}

current_prices = base_prices.copy()

# ✅ simulate price
def generate_price(symbol):
    last_price = current_prices[symbol]

    move = random.uniform(-5, 5)   # movement
    new_price = last_price + move

    if new_price <= 0:
        new_price = last_price

    current_prices[symbol] = round(new_price, 2)
    return current_prices[symbol]


# ✅ timer to avoid spamming
last_send_time = 0

while True:
    try:
        msg = ""

        for symbol in symbols:
            price = generate_price(symbol)

            print(f"{symbol} → ₹{price}")

            # ✅ build telegram message
            msg += f"{symbol} → ₹{price}\n"

        now = time.time()

        # ✅ send every 20 seconds
        if now - last_send_time > 20:
            send_alert(msg)
            print("✅ Sent to Telegram\n")
            last_send_time = now

        print("--------------------------")

    except Exception as e:
        print("❌ ERROR:", e)

    time.sleep(5)