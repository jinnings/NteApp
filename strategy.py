from collections import defaultdict, deque
import time
from alerts import send_alert, get_ist_time


class MultiSignalStrategy:
    def __init__(self):
        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))
        self.signal_history = {}
        self.last_direction = {}
        self.SIGNAL_COOLDOWN = 900
        self.day_open = {}
        self.candidates = []
        self.last_rank_sent = 0

    def get_trade_levels(self, price, direction, prices):
        recent = prices[-10:]

        if direction == "BUY":
            sl = min(recent)
            risk = max(price - sl, price * 0.003)
            target = price + (risk * 2)
        else:
            sl = max(recent)
            risk = max(sl - price, price * 0.003)
            target = price - (risk * 2)

        return round(sl, 2), round(target, 2)

    def already_sent_recent(self, symbol, direction):
        key = f"{symbol}_{direction}"
        return key in self.signal_history and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume < 8000:
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(self.price_history[symbol])
        if len(prices) < 20:
            return

        vwap = sum(prices) / len(prices)

        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        direction = "BUY" if m1 > 0 else "SELL"

        if (m5 > 0 and direction == "SELL") or (m5 < 0 and direction == "BUY"):
            return

        score = int(abs(m5) * 2)

        if score < 10:
            return

        if self.already_sent_recent(symbol, direction):
            return

        sl, tgt = self.get_trade_levels(price, direction, prices)

        # ✅ IST INCLUDED
        message = f"""
🔥 TRADE SIGNAL 🔥
{symbol} → {direction}
Time: {get_ist_time()}

Entry: ₹{round(price,2)}
SL: ₹{sl}
Target: ₹{tgt}

⭐ Score: {score}
"""

        send_alert(message, symbol, direction, price, sl, tgt, "LIVE")

        self.signal_history[f"{symbol}_{direction}"] = time.time()