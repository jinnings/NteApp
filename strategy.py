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

        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 900  # 15 minutes

        self.day_open = {}
        self.COOLDOWN = 60

    def can_send(self, symbol, priority):
        now = time.time()

        if symbol in self.last_sent_time:
            if now - self.last_sent_time[symbol] < self.COOLDOWN:
                return False

        self.last_sent_time[symbol] = now
        self.sent_priority[symbol] = priority
        return True

    def already_sent_recent(self, symbol, direction):
        key = f"{symbol}_{direction}"
        now = time.time()

        if key in self.signal_history:
            if now - self.signal_history[key] < self.SIGNAL_COOLDOWN:
                return True

        return False

    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price

        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

    def is_volume_increasing(self, symbol):
        vols = list(self.volume_history[symbol])
        return len(vols) >= 3 and vols[-1] > vols[-2] > vols[-3]

    def confirm_candle(self, prices, direction):
        if len(prices) < 5:
            return False

        if direction == "BUY":
            return prices[-1] > prices[-2] > prices[-3]
        else:
            return prices[-1] < prices[-2] < prices[-3]

    def calculate_score(self, price, vwap, day_change, momentum):

        score = 0
        score += min(abs(day_change) * 4, 15)

        if abs(momentum) > 0.3:
            score += min(abs(momentum) * 4, 8)

        score += 8 if price > vwap else 4
        return int(score)

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume < 8000:
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(self.price_history[symbol])

        if len(prices) < 20:
            return

        vwap = sum(prices) / len(prices)

        # ✅ multi timeframe
        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        dir1 = "BUY" if m1 > 0 else "SELL"
        dir5 = "BUY" if m5 > 0 else "SELL"

        if dir1 != dir5:
            return

        direction = dir1

        day_change = self.get_day_change(symbol, price)
        if abs(day_change) < 0.1:
            return

        score = self.calculate_score(price, vwap, day_change, m5)
        if score < 15:
            return

        # ✅ filters
        if not self.is_volume_increasing(symbol):
            return

        if not self.confirm_candle(prices, direction):
            return

        if self.already_sent_recent(symbol, direction):
            return

        prev_dir = self.last_direction.get(symbol)
        if prev_dir and prev_dir != direction:
            return

        if not self.can_send(symbol, 4):
            return

        # ✅ save state
        self.last_direction[symbol] = direction
        self.signal_history[f"{symbol}_{direction}"] = time.time()

        message = f"""
🔥 TRADE ALERT 🔥

📊 {symbol} → {'🟢 BUY' if direction=='BUY' else '🔴 SELL'}

💰 Entry: ₹{round(price,2)}

⭐ Score: {score}
📈 1M: {round(m1,2)} | 5M: {round(m5,2)}
📊 Change: {round(day_change,2)}%

✅ Volume Rising
✅ Candle Confirmed
✅ No Repeat (15min)
"""

        send_alert(message)