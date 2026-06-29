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

        # ✅ ranking system
        self.candidates = []
        self.last_rank_sent = 0


    # ✅ SL / TARGET
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


    # ✅ DAY CHANGE
    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price
        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100


    # ✅ VOLUME TREND
    def is_volume_increasing(self, symbol):
        vols = list(self.volume_history[symbol])
        return len(vols) >= 3 and vols[-1] > vols[-2] > vols[-3]


    # ✅ STRUCTURE CONFIRM
    def confirm_candle(self, prices, direction):
        if len(prices) < 5:
            return False
        return prices[-1] > prices[-2] > prices[-3] if direction == "BUY" else prices[-1] < prices[-2] < prices[-3]


    # ✅ PULLBACK
    def is_pullback(self, prices, direction):
        if len(prices) < 6:
            return False
        return prices[-5] > prices[-3] and prices[-1] > prices[-2] if direction == "BUY" else prices[-5] < prices[-3] and prices[-1] < prices[-2]


    # ✅ BREAKOUT
    def is_breakout(self, prices, direction):
        if len(prices) < 10:
            return False
        return prices[-1] > max(prices[-10:-1]) if direction == "BUY" else prices[-1] < min(prices[-10:-1])


    # ✅ VWAP FILTER
    def vwap_trend(self, price, vwap, direction):
        return price > vwap if direction == "BUY" else price < vwap


    # ✅ ✅ ✅ ORIGINAL STRONG SCORE LOGIC
    def calculate_score(self, price, vwap, day_change, momentum):
        score = 0

        # 📊 Day move strength
        score += min(abs(day_change) * 4, 15)

        # ⚡ Momentum
        if abs(momentum) > 0.3:
            score += min(abs(momentum) * 4, 8)

        # 📈 VWAP bias
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

        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        dir1 = "BUY" if m1 > 0 else "SELL"
        dir5 = "BUY" if m5 > 0 else "SELL"

        if dir1 != dir5:
            return

        direction = dir1

        # ✅ Filters
        if not self.vwap_trend(price, vwap, direction):
            return

        if not self.is_pullback(prices, direction):
            return

        if not self.is_breakout(prices, direction):
            return

        if not self.is_volume_increasing(symbol):
            return

        if not self.confirm_candle(prices, direction):
            return

        if self.already_sent_recent(symbol, direction):
            return

        prev_dir = self.last_direction.get(symbol)
        if prev_dir and prev_dir != direction:
            return

        day_change = self.get_day_change(symbol, price)
        if abs(day_change) < 0.1:
            return

        # ✅ SCORE
        score = self.calculate_score(price, vwap, day_change, m5)

        sl, tgt = self.get_trade_levels(price, direction, prices)

        # ✅ ✅ INSTANT TRADE (HIGH SCORE)
        if score >= 22:
            message = f"""
🔥 INSTANT TRADE 🔥
{symbol} → {direction}
Time: {get_ist_time()}

Entry: ₹{round(price,2)}
SL: ₹{sl}
Target: ₹{tgt}

⭐ Score: {score}
"""
            send_alert(message, symbol, direction, price, sl, tgt, "INSTANT")

            self.signal_history[f"{symbol}_{direction}"] = time.time()
            self.last_direction[symbol] = direction
            return


        # ✅ MID SCORE → STORE
        if score >= 15:
            self.candidates.append({
                "symbol": symbol,
                "direction": direction,
                "price": price,
                "score": score
            })

        self.process_top_signals()


    # ✅ ✅ TOP SIGNAL RANKING
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

            prices = list(self.price_history[symbol])
            sl, tgt = self.get_trade_levels(price, direction, prices)

            message = f"""
🔥 TOP TRADE 🔥
{symbol} → {direction}
Time: {get_ist_time()}

Entry: ₹{round(price,2)}
SL: ₹{sl}
Target: ₹{tgt}

⭐ Score: {score}
"""

            send_alert(message, symbol, direction, price, sl, tgt, "TOP")

            self.signal_history[f"{symbol}_{direction}"] = time.time()
            self.last_direction[symbol] = direction

        self.candidates.clear()
        self.last_rank_sent = time.time()