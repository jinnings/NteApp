from collections import defaultdict, deque
import time
from alerts import send_alert


class MultiSignalStrategy:
    def __init__(self):

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.last_sent_time = {}
        self.sent_priority = {}
        self.last_direction = {}

        self.day_open = {}
        self.COOLDOWN = 60

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
        return volume > avg * 1.3

    def calculate_score(self, price, vwap, day_change, momentum, vol_spike):

        score = 0
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

        if len(prices) < 20:
            return

        vwap = sum(prices) / len(prices)

        # ✅ multi-timeframe
        momentum_1m = prices[-1] - prices[-3]
        momentum_5m = prices[-1] - prices[-10]

        dir_1m = "BUY" if momentum_1m > 0 else "SELL"
        dir_5m = "BUY" if momentum_5m > 0 else "SELL"

        # ✅ confirmation
        if dir_1m != dir_5m:
            return

        direction = dir_1m

        day_change = self.get_day_change(symbol, price)

        if abs(day_change) < 0.1:
            return

        vol_spike = self.volume_spike(symbol, volume)

        score = self.calculate_score(price, vwap, day_change, momentum_5m, vol_spike)

        if score >= 15:

            # ✅ prevent flip
            prev_dir = self.last_direction.get(symbol)
            if prev_dir and prev_dir != direction:
                return

            confidence = "🔥 STRONG" if score >= 22 else "✅ GOOD"

            if self.can_send(symbol, 4):

                self.last_direction[symbol] = direction

                send_alert(f"""
🔥 TOP INTRADAY SETUPS 🔥

📊 {symbol} → {'🟢 BUY' if direction=='BUY' else '🔴 SELL'}

💰 Entry: ₹{round(price,2)}

⭐ Score: {score} | {confidence}
📈 1M: {round(momentum_1m,2)} | 5M: {round(momentum_5m,2)}
📊 Change: {round(day_change,2)}%
""")