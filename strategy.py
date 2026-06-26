from collections import defaultdict, deque
import time
from alerts import send_alert


class MultiSignalStrategy:
    def __init__(self):
        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.last_direction = {}
        self.signal_history = {}

        self.SIGNAL_COOLDOWN = 900

        self.day_open = {}
        self.candidates = []
        self.last_rank_sent = 0

    # ✅ REAL VWAP
    def calculate_vwap(self, prices, volumes):
        total_vol = sum(volumes)
        if total_vol == 0:
            return prices[-1]
        return sum(p * v for p, v in zip(prices, volumes)) / total_vol

    def get_trade_levels(self, price, direction, prices):
        recent = prices[-10:]

        if direction == "BUY":
            stoploss = min(recent[:-1])
            risk = max(price - stoploss, price * 0.003)
            target = price + (risk * 2)
        else:
            stoploss = max(recent[:-1])
            risk = max(stoploss - price, price * 0.003)
            target = price - (risk * 2)

        return round(stoploss, 2), round(target, 2)

    def already_sent_recent(self, symbol, direction):
        key = f"{symbol}_{direction}"
        return key in self.signal_history and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN

    def is_volume_increasing(self, symbol):
        vols = list(self.volume_history[symbol])
        return len(vols) >= 3 and vols[-1] > vols[-2] > vols[-3]

    def confirm_candle(self, prices, direction):
        if len(prices) < 5:
            return False
        return prices[-1] > prices[-2] > prices[-3] if direction == "BUY" else prices[-1] < prices[-2] < prices[-3]

    def is_pullback(self, prices, direction):
        if len(prices) < 6:
            return False
        return prices[-5] > prices[-3] if direction == "BUY" else prices[-5] < prices[-3]

    def is_breakout(self, prices, direction):
        if len(prices) < 10:
            return False
        return prices[-1] > max(prices[-10:-1]) if direction == "BUY" else prices[-1] < min(prices[-10:-1])

    def update(self, symbol, price, volume):
        if not symbol or price is None or volume < 8000:
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(self.price_history[symbol])
        volumes = list(self.volume_history[symbol])

        if len(prices) < 20:
            return

        vwap = self.calculate_vwap(prices, volumes)

        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        direction = "BUY" if m1 > 0 else "SELL"

        if (m1 > 0) != (m5 > 0):
            return

        if direction == "BUY" and price < vwap:
            return
        if direction == "SELL" and price > vwap:
            return

        if not self.is_pullback(prices, direction):
            return
        if not self.is_breakout(prices, direction):
            return
        if not self.is_volume_increasing(symbol):
            return
