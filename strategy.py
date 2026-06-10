from collections import defaultdict, deque
import time
from alerts import send_alert


class MultiSignalStrategy:
    def __init__(self):
        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.last_alert_time = defaultdict(float)

        self.COOLDOWN = 60
        self.BREAKOUT_LOOKBACK = 20

    # ✅ RSI
    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50

        gains, losses = 0, 0
        for i in range(-period, 0):
            diff = prices[i] - prices[i - 1]
            if diff > 0:
                gains += diff
            else:
                losses += abs(diff)

        if losses == 0:
            return 100

        rs = gains / losses
        return 100 - (100 / (1 + rs))

    # ✅ VWAP
    def calculate_vwap(self, prices):
        return sum(prices) / len(prices)

    # ✅ Momentum
    def momentum(self, prices):
        if len(prices) < 3:
            return 0
        return prices[-1] - prices[-3]

    # ✅ Breakout levels
    def breakout_levels(self, prices):
        recent = list(prices)[-self.BREAKOUT_LOOKBACK:]
        return max(recent), min(recent)

    # ✅ Fake volume spike
    def volume_spike(self, prices):
        if len(prices) < 5:
            return False

        move = abs(prices[-1] - prices[-2])
        avg = sum(abs(prices[i] - prices[i - 1]) for i in range(-5, 0)) / 5

        return move > avg * 1.5

    # ✅ MAIN
    def update(self, symbol, price, volume):

        self.price_history[symbol].append(price)
        prices = self.price_history[symbol]

        # ✅ Noise filter
        if len(prices) > 1 and abs(price - prices[-2]) < 0.2:
            return

        now = time.time()

        # ✅ Cooldown (global per symbol)
        if now - self.last_alert_time[symbol] < self.COOLDOWN:
            return

        if len(prices) < self.BREAKOUT_LOOKBACK:
            return

        rsi = self.calculate_rsi(prices)
        vwap = self.calculate_vwap(prices)
        momentum = self.momentum(prices)
        high, low = self.breakout_levels(prices)
        vol_spike = self.volume_spike(prices)

        signals = []  # ✅ collect all signals

        # =========================
        # ⚡ MOMENTUM
        # =========================
        if abs(momentum) > 1:
            direction = "UP" if momentum > 0 else "DOWN"

            signals.append(
                f"⚡ MOMENTUM {direction}\n"
                f"Move: {round(momentum,2)}"
            )

        # =========================
        # 🔥 BREAKOUT
        # =========================
        if price > high:
            signals.append("🔥 BREAKOUT UP")
        elif price < low:
            signals.append("🔥 BREAKOUT DOWN")

        # =========================
        # 🟢🔴 INTRADAY SIGNAL
        # =========================

        # ✅ BUY
        if price > high and vol_spike:
            if price > vwap and rsi > 55 and momentum > 0:
                signals.append("🟢 BUY SIGNAL")

        # ✅ SELL
        if price < low and vol_spike:
            if price < vwap and rsi < 45 and momentum < 0:
                signals.append("🔴 SELL SIGNAL")

        # ✅ SEND IF ANY SIGNALS FOUND
        if signals:
            msg = f"""
📊 {symbol}
💰 Price: ₹{price}

{chr(10).join(signals)}

📈 RSI: {round(rsi,1)}
📊 VWAP: {round(vwap,2)}
"""
            print(msg)
            send_alert(msg)

            self.last_alert_time[symbol] = now