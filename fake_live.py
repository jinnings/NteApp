import time
import random
from strategy import BreakoutAlert

strategy = BreakoutAlert()

symbol = "NSE_EQ|RELIANCE"

price = 2500  # starting price

print("🚀 Starting FAKE LIVE market...\n")

while True:
    # Simulate price movement
    price += random.uniform(-1, 2)  # slight upward bias

    # Simulate volume spike occasionally
    volume = random.randint(1000, 5000)

    # Send data to strategy (just like real market)
    strategy.update(symbol, round(price, 2), volume)

    # Print live feed
    print(f"{symbol} | Price: {round(price, 2)} | Volume: {volume}")

    time.sleep(1)  # 1 second = live tick
