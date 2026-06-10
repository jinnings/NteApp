from collections import defaultdict, deque
import time
from alerts import send_alert


class BreakoutAlert:
    def __init__(self):
        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=100))

        self.last_alert_time = defaultdict(float)

        self.COOLDOWN = 60   # seconds
        self.BREAKOUT_LOOKBACK = 20
        self.VOLUME_MULTIPLIER = 1.5

    # ✅ RSI
    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50

        gains, losses = 0, 0

        for i in range(-period, 0):
            diff = prices[i] - prices[i-1]
            if diff > 0:
                gains += diff
            else:
                losses += abs(diff)

        if losses == 0:
            return 100

        rs = gains / losses
        return 100 - (100 / (1 + rs))

    # ✅ VWAP (approx using price only)
    def calculate_vwap(self, prices):
        return sum(prices) / len(prices) if prices else 0

    # ✅ Volume Spike
    def volume_spike(self, symbol, volume):
        vols = self.volume_history[symbol]
        if len(vols) < 10:
            return False

        avg_vol = sum(vols) / len(vols)
        return volume > avg_vol * self.VOLUME_MULTIPLIER

    # ✅ Breakout Detection
    def is_breakout(self, symbol, price):
        prices = self.price_history[symbol]

        if len(prices) < self.BREAKOUT_LOOKBACK:
            return False, None

        recent_high = max(list(prices)[-self.BREAKOUT_LOOKBACK:])
        recent_low = min(list(prices)[-self.BREAKOUT_LOOKBACK:])

        if price > recent_high:
            return True, "UP"

        if price < recent_low:
            return True, "DOWN"

        return False, None

    # ✅ Momentum
    def momentum(self, prices):
        if len(prices) < 3:
            return 0

        return prices[-1] - prices[-3]

    # ✅ MAIN FUNCTION
    def update(self, symbol, price, volume):

        print(f"{symbol} | {price}")

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        now = time.time()

        # ✅ Cooldown
        if now - self.last_alert_time[symbol] < self.COOLDOWN:
            return

        prices = self.price_history[symbol]

        # ✅ Indicators
        rsi = self.calculate_rsi(prices)
        vwap = self.calculate_vwap(prices)
        momentum = self.momentum(prices)
        breakout, direction = self.is_breakout(symbol, price)
        vol_spike = self.volume_spike(symbol, volume)

        # ✅ HYBRID LOGIC

        if breakout and vol_spike:

            # ✅ FILTERS
            if direction == "UP":
                if rsi < 55 or price < vwap:
                    return

            elif direction == "DOWN":
                if rsi > 45 or price > vwap:
                    return

            msg = (
                f"🔥 BREAKOUT {direction}\n"
                f"{symbol}\n"
                f"Price: {price}\n"
                f"RSI: {round(rsi, 1)}\n"
                f"VWAP: {round(vwap, 2)}\n"
                f"Momentum: {round(momentum, 2)}\n"
                f"Volume Spike ✅"
            )

            print(msg)
            send_alert(msg)

            self.last_alert_time[symbol] = now

        # ✅ OPTIONAL MOMENTUM SIGNAL
        elif abs(momentum) > 0.3:

            direction = "UP" if momentum > 0 else "DOWN"

            msg = (
                f"⚡ MOMENTUM {direction}\n"
                f"{symbol}\n"
                f"Price: {price}\n"
                f"Momentum: {round(momentum, 2)}"
            )

            print(msg)
            send_alert(msg)

            self.last_alert_time[symbol] = now
