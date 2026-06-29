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


    # ✅ MARKET STATE (NEW)
    def get_market_state(self, prices):
        if len(prices) < 20:
            return "NORMAL"

        range_val = max(prices[-15:]) - min(prices[-15:])
        volatility = range_val / prices[-1]

        if volatility < 0.003:
            return "LOW"
        elif volatility > 0.01:
            return "HIGH"
        else:
            return "NORMAL"


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


    # ✅ STRUCTURE
    def confirm_candle(self, prices, direction):
        if len(prices) < 5:
            return False
        return prices[-1] > prices[-2] > prices[-3] if direction == "BUY" else prices[-1] < prices[-2] < prices[-3]


    # ✅ PULLBACK
    def is_pullback(self, prices, direction):
        if len(prices) < 6:
            return False
        return prices[-5] > prices[-3] and prices[-1] > prices[-2] if direction == "BUY" else prices[-5] < prices[-3] and prices[-1] < prices[-2]


    # ✅ ✅ ADAPTIVE BREAKOUT
    def is_breakout(self, prices, direction):

        if len(prices) < 12:
            return False

        state = self.get_market_state(prices)

        prev_high = max(prices[-11:-2])
        prev_low = min(prices[-11:-2])
        current = prices[-1]

        # ✅ Adaptive threshold
        if state == "LOW":
            threshold = current * 0.0005
        elif state == "HIGH":
            threshold = current * 0.0015
        else:
            threshold = current * 0.0008

        if direction == "BUY":
            if current <= prev_high:
                return False
            if current - prev_high < threshold:
                return False
            if current < prices[-2]:
                return False
            if prices[-2] < prices[-3]:
                return False
            return True

        else:
            if current >= prev_low:
                return False
            if prev_low - current < threshold:
                return False
            if current > prices[-2]:
                return False
            if prices[-2] > prices[-3]:
                return False
            return True


    # ✅ VWAP
    def vwap_trend(self, price, vwap, direction):
        return price > vwap if direction == "BUY" else price < vwap


    # ✅ SCORE (UNCHANGED)
    def calculate_score(self, price, vwap, day_change, momentum):
        score = 0

        score += min(abs(day_change) * 4, 15)

        if abs(momentum) > 0.3:
            score += min(abs(momentum) * 4, 8)

        score += 8 if price > vwap else 4

        return int(score)


    # ✅ ✅ ADAPTIVE TREND
    def is_strong_trend(self, prices, direction):
        if len(prices) < 15:
            return False

        state = self.get_market_state(prices)
        move = prices[-1] - prices[-15]

        if state == "LOW":
            threshold = 0.0015
        elif state == "HIGH":
            threshold = 0.005
        else:
            threshold = 0.0025

        if direction == "BUY":
            return move > prices[-1] * threshold
        else:
            return move < -(prices[-1] * threshold)


    # ✅ ✅ ADAPTIVE SIDEWAYS
    def is_sideways(self, prices):
        if len(prices) < 10:
            return False

        state = self.get_market_state(prices)

        high = max(prices[-10:])
        low = min(prices[-10:])
        range_pct = (high - low) / prices[-1]

        if state == "LOW":
            return range_pct < 0.002
        elif state == "HIGH":
            return False
        else:
            return range_pct < 0.0035


    # ✅ ✅ ADAPTIVE LIQUIDITY TRAP
    def is_liquidity_trap(self, prices, direction):
        if len(prices) < 6:
            return False

        state = self.get_market_state(prices)
        spike = abs(prices[-2] - prices[-4])

        if state == "LOW":
            spike_threshold = prices[-1] * 0.003
        elif state == "HIGH":
            spike_threshold = prices[-1] * 0.0015
        else:
            spike_threshold = prices[-1] * 0.002

        if spike < spike_threshold:
            return False

        if direction == "BUY":
            return prices[-1] < prices[-2]
        else:
            return prices[-1] > prices[-2]


    # ✅ ✅ MAIN ENGINE
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

        # ✅ EXISTING FILTER
        if not self.vwap_trend(price, vwap, direction):
            return

        # ✅ ✅ ADAPTIVE FILTERS
        if self.is_sideways(prices):
            return

        if not self.is_strong_trend(prices, direction):
            return

        if self.is_liquidity_trap(prices, direction):
            return

        # ✅ ORIGINAL FLOW
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

        if self.last_direction.get(symbol) == ("SELL" if direction == "BUY" else "BUY"):
            return

        day_change = self.get_day_change(symbol, price)
        if abs(day_change) < 0.1:
            return

        score = self.calculate_score(price, vwap, day_change, m5)

        sl, tgt = self.get_trade_levels(price, direction, prices)

        # ✅ INSTANT TRADE
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

        # ✅ TOP TRADE
        if score >= 15:
            self.candidates.append({
                "symbol": symbol,
                "direction": direction,
                "price": price,
                "score": score
            })

        self.process_top_signals()


    # ✅ RANKING ENGINE
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