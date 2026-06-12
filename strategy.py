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
        self.COOLDOWN = 60   # ✅ faster alerts

    def can_send(self, symbol, priority):
        now = time.time()

        if symbol in self.last_sent_time:
            if now - self.last_sent_time[symbol] < self.COOLDOWN:
                if self.sent_priority.get(symbol, 0) >= priority:
                    return False

        self.last_sent_time[symbol] = now
        self.sent_priority[symbol] = priority
        return True

    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price

        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

    def volume_spike(self, symbol, volume):
        self.volume_history[symbol].append(volume)

        vols = list(self.volume_history[symbol])
        if len(vols) < 5:
            return False

        avg = sum(vols[-5:]) / 5
        return volume > avg * 1.3   # ✅ easier trigger

    def calculate_score(self, price, vwap, day_change, momentum, vol_spike):

        score = 0

        # ✅ relaxed scoring
        score += min(abs(day_change) * 4, 15)

        if abs(momentum) > 0.3:
            score += min(abs(momentum) * 4, 8)

        if price > vwap:
            score += 8
        else:
            score += 4

        if vol_spike:
            score += 10

        return int(score)

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume < 8000:
            return

        self.price_history[symbol].append(price)
        prices = list(self.price_history[symbol])

        if len(prices) < 15:   # ✅ faster warmup
            return

        vwap = sum(prices) / len(prices)
        momentum = prices[-1] - prices[-2]  # ✅ faster momentum
        day_change = self.get_day_change(symbol, price)

        # ✅ VERY IMPORTANT: relaxed filter
        if abs(day_change) < 0.1:
            return

        vol_spike = self.volume_spike(symbol, volume)
        score = self.calculate_score(price, vwap, day_change, momentum, vol_spike)

        # ✅ BIG FIX: lower threshold
        if score >= 15:

            direction = "🟢 BUY" if momentum > 0 else "🔴 SELL"
            confidence = "🔥 STRONG" if score >= 22 else "✅ GOOD"

            if self.can_send(symbol, 4):

                send_alert(f"""
🔥 TOP INTRADAY SETUPS 🔥

📊 {symbol} → {direction}


💰 Entry: ₹{round(price,2)}

⭐ Score: {score} | {confidence}
📈 Momentum: {round(momentum,2)}
📊 Change: {round(day_change,2)}%
""")