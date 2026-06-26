from collections import defaultdict, deque
import time
from alerts import send_alert


class MultiSignalStrategy:
    def __init__(self):

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.last_sent_time = {}
        self.last_direction = {}

        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 900  # 15 min

        self.day_open = {}

        # ✅ ranking
        self.candidates = []
        self.last_rank_sent = 0


    # ✅ SL/Target
    def get_trade_levels(self, price, direction, prices):

        recent = prices[-10:]

        if direction == "BUY":
            stoploss = min(recent)
            risk = max(price - stoploss, price * 0.003)
            target = price + (risk * 2)

        else:
            stoploss = max(recent)
            risk = max(stoploss - price, price * 0.003)
            target = price - (risk * 2)

        return round(stoploss, 2), round(target, 2)


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
        return prices[-1] > prices[-2] > prices[-3] if direction == "BUY" else prices[-1] < prices[-2] < prices[-3]


    def is_pullback(self, prices, direction):
        if len(prices) < 6:
            return False
        return prices[-5] > prices[-3] and prices[-1] > prices[-2] if direction == "BUY" else prices[-5] < prices[-3] and prices[-1] < prices[-2]


    def is_breakout(self, prices, direction):
        if len(prices) < 10:
            return False
        return prices[-1] > max(prices[-10:-1]) if direction == "BUY" else prices[-1] < min(prices[-10:-1])


    def vwap_trend(self, price, vwap, direction):
        return price > vwap if direction == "BUY" else price < vwap


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

        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        dir1 = "BUY" if m1 > 0 else "SELL"
        dir5 = "BUY" if m5 > 0 else "SELL"

        if dir1 != dir5:
            return

        direction = dir1

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

        score = self.calculate_score(price, vwap, day_change, m5)

        # ✅ INSTANT TRADE
        if score >= 22:

            sl, tgt = self.get_trade_levels(price, direction, prices)

            message = f"""
🔥 INSTANT TRADE 🔥
{symbol} → {direction}
₹{round(price,2)}

🎯 Target: ₹{tgt}
🛑 Stoploss: ₹{sl}

⭐ Score: {score}
"""

            send_alert(message, symbol, direction, price, sl, tgt, "INSTANT")

            self.signal_history[f"{symbol}_{direction}"] = time.time()
            self.last_direction[symbol] = direction
            return


        # ✅ store candidates
        if score >= 15:
            self.candidates.append({
                "symbol": symbol,
                "direction": direction,
                "price": price,
                "score": score
            })

        # ✅ IMPORTANT: run ranking engine
        self.process_top_signals()


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
₹{round(price,2)}

🎯 Target: ₹{tgt}
🛑 Stoploss: ₹{sl}

⭐ Score: {score}
"""

            send_alert(message, symbol, direction, price, sl, tgt, "TOP")

            self.signal_history[f"{symbol}_{direction}"] = time.time()
            self.last_direction[symbol] = direction

        self.candidates.clear()
        self.last_rank_sent = time.time()


# ✅ JINNING STRATEGY (unchanged)
class JinningEffectStrategy:
    def __init__(self):
        self.close_history = defaultdict(lambda: deque(maxlen=150))
        self.volume_history = defaultdict(lambda: deque(maxlen=10))
        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 1800

    def already_sent_recent(self, symbol):
        return symbol in self.signal_history and time.time() - self.signal_history[symbol] < self.SIGNAL_COOLDOWN

    def update_daily(self, symbol, close_price, volume):

        if not symbol or close_price is None or volume is None:
            return

        self.close_history[symbol].append(close_price)
        self.volume_history[symbol].append(volume)

        closes = list(self.close_history[symbol])
        volumes = list(self.volume_history[symbol])

        if len(closes) < 130:
            return

        if max(closes[-5:]) <= max(closes[-126:-6]) * 1.05:
            return

        if len(volumes) < 6:
            return

        if volumes[-1] <= sum(volumes[-6:-1]) / 5:
            return

        if closes[-1] <= closes[-2]:
            return

        if self.already_sent_recent(symbol):
            return

        message = f"""
🔥 JINNING EFFECT 🔥
{symbol} → BUY
₹{round(close_price, 2)}
"""

        send_alert(message)
        self.signal_history[symbol] = time.time()