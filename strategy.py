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

    # ✅ CONTROL
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

    # ✅ DAY CHANGE
    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price

        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

    # ✅ VOLUME SPIKE
    def volume_spike(self, symbol, volume):
        self.volume_history[symbol].append(volume)
        vols = list(self.volume_history[symbol])

        if len(vols) < 5:
            return False

        avg = sum(vols[-5:]) / 5
        return volume > avg * 1.5

    # ✅ SCORE
    def calculate_score(self, price, vwap, day_change, momentum, vol_spike):

        score = 0

        score += min(abs(day_change) * 5, 20)

        if abs(momentum) > 1:
            score += min(abs(momentum) * 5, 10)

        if price > vwap:
            score += 10
        else:
            score += 5

        if vol_spike:
            score += 15

        return int(score)

    # ✅ MAIN LOGIC
    def update(self, symbol, price, volume):

        if not symbol or price is None or volume < 20000:
            return

        self.price_history[symbol].append(price)
        prices = list(self.price_history[symbol])

        if len(prices) < 30:
            return

        vwap = sum(prices) / len(prices)
        momentum = prices[-1] - prices[-3]
        day_change = self.get_day_change(symbol, price)
        vol_spike = self.volume_spike(symbol, volume)

        score = self.calculate_score(price, vwap, day_change, momentum, vol_spike)

        # ✅ KEY FIX: 30 threshold
        if score >= 30:

            direction = "🟢 BUY" if momentum > 0 else "🔴 SELL"
            confidence = "🔥 STRONG" if score >= 40 else "✅ GOOD"

            if self.can_send(symbol, 4):

                send_alert(f"""
🔥 TOP INTRADAY SETUPS 🔥

📊 {symbol} → {direction}

💰 Entry: ₹{round(price,2)}

⭐ Score: {score} | {confidence}
📈 Momentum: {round(momentum,2)}
📊 Change: {round(day_change,2)}%
""")