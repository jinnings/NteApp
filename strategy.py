from collections import defaultdict, deque
import time
from alerts import send_alert


class BreakoutAlert:
    def __init__(self):
        self.last_price = defaultdict(float)
        self.prev_change = defaultdict(float)
        self.last_alert_time = defaultdict(float)
        self.price_history = defaultdict(lambda: deque(maxlen=20))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.COOLDOWN = 60
        self.MIN_MOVE = 0.15
        self.BREAKOUT_MOVE = 0.4
        self.VOLUME_MULTIPLIER = 1.5

    def calculate_rsi(self, prices):
        if len(prices) < 14:
            return 50

        gains = []
        losses = []

        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            if diff > 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))

        avg_gain = sum(gains[-14:]) / 14 if gains else 0
        avg_loss = sum(losses[-14:]) / 14 if losses else 0

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def update(self, symbol, price, volume):

        print(f"{symbol} | {price}")

        # ✅ store price & volume
        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        if self.last_price[symbol] == 0:
            self.last_price[symbol] = price
            return

        prev = self.last_price[symbol]
        change = price - prev
        now = time.time()

        # ✅ Noise filter
        if abs(change) < self.MIN_MOVE:
            self.last_price[symbol] = price
            return

        # ✅ Cooldown
        if now - self.last_alert_time[symbol] < self.COOLDOWN:
            self.last_price[symbol] = price
            return

        prev_change = self.prev_change[symbol]

        # ✅ Momentum confirmation
        if not ((prev_change > 0 and change > 0) or (prev_change < 0 and change < 0)):
            self.prev_change[symbol] = change
            self.last_price[symbol] = price
            return

        # ✅ Volume check
        avg_vol = sum(self.volume_history[symbol]) / max(len(self.volume_history[symbol]), 1)
        if volume < avg_vol * self.VOLUME_MULTIPLIER:
            return

        # ✅ RSI filter
        rsi = self.calculate_rsi(self.price_history[symbol])

        # ✅ Direction
        direction = "UP" if change > 0 else "DOWN"

        # =========================
        # 🔥 BREAKOUT SIGNAL
        # =========================
        if abs(change) > self.BREAKOUT_MOVE:

            # ✅ RSI filter conditions
            if direction == "UP" and rsi < 55:
                return
            if direction == "DOWN" and rsi > 45:
                return

            msg = (
                f"🔥 BREAKOUT {direction}\n"
                f"{symbol}\n"
                f"Price: {price}\n"
                f"Move: {round(change, 2)}\n"
                f"RSI: {round(rsi, 1)}\n"
                f"Volume Spike ✅"
            )

            print(msg)
            send_alert(msg)
            self.last_alert_time[symbol] = now

        # =========================
        # ⚡ MOMENTUM SIGNAL
        # =========================
        elif abs(change) > self.MIN_MOVE:

            msg = (
                f"⚡ MOMENTUM {direction}\n"
                f"{symbol}\n"
                f"Price: {price}\n"
                f"Move: {round(change, 2)}"
            )

            print(msg)
            send_alert(msg)
            self.last_alert_time[symbol] = now

        self.prev_change[symbol] = change
        self.last_price[symbol] = price