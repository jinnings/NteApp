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

    def already_sent_recent(self, symbol, direction):
        key = f"{symbol}_{direction}"
        return key in self.signal_history and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN

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
        return prices[-1] < prices[-2] < prices[-3]

    def is_breakout(self, prices, direction):
        if len(prices) < 10:
            return False
        if direction == "BUY":
            return prices[-1] > max(prices[-10:-1])
        return prices[-1] < min(prices[-10:-1])

    def vwap_trend(self, price, vwap, direction):
        return price > vwap if direction == "BUY" else price < vwap

    # ✅ ENTRY IMPROVEMENT FUNCTIONS

    def breakout_hold(self, prices, direction):
        if len(prices) < 5:
            return False
        if direction == "BUY":
            return prices[-1] >= prices[-2]
        return prices[-1] <= prices[-2]

    def not_overextended(self, prices):
        move = abs(prices[-1] - prices[-5])
        return move < (prices[-1] * 0.02)

    def strong_pullback_entry(self, prices, direction):

        if len(prices) < 6:
            return False

        if direction == "BUY":
            return (
                prices[-3] > prices[-4] and  # up move
                prices[-2] < prices[-3] and  # pullback
                prices[-1] > prices[-2]      # bounce ✅
            )

        if direction == "SELL":
            return (
                prices[-3] < prices[-4] and
                prices[-2] > prices[-3] and
                prices[-1] < prices[-2]
            )

        return False

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

        # ✅ Trend
        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        dir1 = "BUY" if m1 > 0 else "SELL"
        dir5 = "BUY" if m5 > 0 else "SELL"

        if dir1 != dir5:
            return

        direction = dir1

        # ✅ Core filters
        if not self.vwap_trend(price, vwap, direction):
            return

        if not self.is_breakout(prices, direction):
            return

        if not self.is_volume_increasing(symbol):
            return

        if not self.confirm_candle(prices, direction):
            return

        # ✅ NEW ENTRY TIMING LOGIC 🔥
        if not self.breakout_hold(prices, direction):
            return

        if not self.not_overextended(prices):
            return

        if not self.strong_pullback_entry(prices, direction):
            return

        if self.already_sent_recent(symbol, direction):
            return

        prev_dir = self.last_direction.get(symbol)
        if prev_dir and prev_dir != direction:
            return

        day_change = self.get_day_change(symbol, price)
        if abs(day_change) < 0.1:
            return

        score = self.calculate_score(price, vwap, day_change, m5)

        # ✅ Instant trade
        if score >= 22:

            message = f"""
🔥 INSTANT TRADE 🔥
{symbol} → {direction}
₹{round(price,2)}
⭐ Score: {score}
"""

            send_alert(message)

            self.signal_history[f"{symbol}_{direction}"] = time.time()
            self.last_direction[symbol] = direction
            return

        # ✅ Store strong only
        if score > 18:
            self.candidates.append({
                "symbol": symbol,
                "direction": direction,
                "price": price,
                "score": score
            })

    def process_top_signals(self):

        if time.time() - self.last_rank_sent < 60:
            return

        if not self.candidates:
            return

        top = sorted(self.candidates, key=lambda x: x["score"], reverse=True)[:3]

        for t in top:

            symbol = t["symbol"]
            direction = t["direction"]
            price = t["price"]
            score = t["score"]

            if self.already_sent_recent(symbol, direction):
                continue

            message = f"""
🔥 TOP TRADE 🔥
{symbol} → {direction}
₹{round(price,2)}
⭐ Score: {score}
"""

            send_alert(message)

            self.signal_history[f"{symbol}_{direction}"] = time.time()
            self.last_direction[symbol] = direction

        self.candidates.clear()
        self.last_rank_sent = time.time()