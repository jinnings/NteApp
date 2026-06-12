from collections import defaultdict, deque
import time
from alerts import send_alert


class MultiSignalStrategy:
    def __init__(self):

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.last_sent_time = {}
        self.sent_priority = {}

        self.day_open = {}
        self.COOLDOWN = 120

    def can_send(self, symbol, priority):
        now = time.time()

        if symbol in self.last_sent_time:
            if now - self.last_sent_time[symbol] < self.COOLDOWN:
                if self.sent_priority.get(symbol, 0) >= priority:
                    return False
            else:
                self.sent_priority[symbol] = 0

        self.last_sent_time[symbol] = now
        self.sent_priority[symbol] = priority

        return True

    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price
        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume < 50000:
            return

        self.price_history[symbol].append(price)
        prices = list(self.price_history[symbol])

        if len(prices) < 30:
            return

        vwap = sum(prices) / len(prices)
        momentum = prices[-1] - prices[-3]
        day_change = self.get_day_change(symbol, price)

        # ✅ MOMENTUM
        if day_change > 1 and price > vwap:
            if self.can_send(symbol, 1):
                send_alert(f"""
🚀 MOMENTUM GAINER

{symbol} → ₹{price}
📈 +{round(day_change,2)}%
""")

        # ✅ PULLBACK
        if abs(price - vwap) / vwap < 0.005 and momentum > 0:
            if self.can_send(symbol, 2):
                send_alert(f"""
🎯 PULLBACK SETUP

{symbol} → ₹{price}
✅ Near VWAP
""")

        # ✅ RUNNERS
        if abs(day_change) >= 2:
            direction = "🟢 BUY" if day_change > 0 else "🔴 SELL"

            if self.can_send(symbol, 3):
                send_alert(f"""
📈 TODAY'S RUNNERS

{symbol} → {direction}
💰 ₹{price} ({round(day_change,2)}%)
""")

        # ✅ ELITE
        if abs(day_change) > 2 and abs(momentum) > 1.5:

            direction = "🟢 BUY" if momentum > 0 else "🔴 SELL"
            score = int(abs(day_change) * 10)

            if self.can_send(symbol, 4):
                send_alert(f"""
🔥 TOP INTRADAY SETUPS 🔥

📊 {symbol} → {direction}

💰 Entry: ₹{price}
⭐ Score: {score}
""")