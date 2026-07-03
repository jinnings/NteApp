from collections import defaultdict, deque
import time
from alerts import send_alert





# =========================
# ✅ ORIGINAL STRATEGY
# =========================
class MultiSignalStrategy:
    def __init__(self):

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.last_sent_time = {}
        self.last_direction = {}

        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 900  # 15 min

        self.day_open = {}
        self.COOLDOWN = 60

        # ✅ ranking storage
        self.candidates = []
        self.last_rank_sent = 0

def already_sent_recent(self, symbol, direction):
    key = f"{symbol}_{direction}"
    return (
        key in self.signal_history
        and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN
    )


    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price
        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

def is_volume_increasing(self, symbol):
    vols = list(self.volume_history[symbol])
    return (
        len(vols) >= 3
        and vols[-1] > vols[-2] > vols[-3]
    )

    def confirm_candle(self, prices, direction):
        if len(prices) < 5:
            return False
        if direction == "BUY":
            return prices[-1] > prices[-2] > prices[-3]
        else:
            return prices[-1] < prices[-2] < prices[-3]

    def is_pullback(self, prices, direction):
        if len(prices) < 6:
            return False
        if direction == "BUY":
            return prices[-5] > prices[-3] and prices[-1] > prices[-2]
        else:
            return prices[-5] < prices[-3] and prices[-1] < prices[-2]

    def is_breakout(self, prices, direction):
        if len(prices) < 10:
            return False
        if direction == "BUY":
            return prices[-1] > max(prices[-10:-1])
        else:
            return prices[-1] < min(prices[-10:-1])

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

        # ✅ INSTANT SIGNAL
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

        # ✅ STORE FOR RANKING
        if score >= 19:
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


# =========================
# ✅ PULLBACK STRATEGY
# =========================
class PullbackStrategy:

    def __init__(self):

        self.price_history = defaultdict(lambda: deque(maxlen=50))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.day_open = {}
        self.day_high = {}

        self.signal_history = {}

        self.SIGNAL_COOLDOWN = 1800

    def already_sent_recent(self, symbol):

        return (
            symbol in self.signal_history
            and time.time() - self.signal_history[symbol]
            < self.SIGNAL_COOLDOWN
        )

    def get_day_change(self, symbol, price):

        if symbol not in self.day_open:
            self.day_open[symbol] = price

        return (
            (price - self.day_open[symbol])
            / self.day_open[symbol]
        ) * 100

    def volume_increasing(self, symbol):

        vols = list(self.volume_history[symbol])

        if len(vols) < 3:
            return False

        return vols[-1] > vols[-2] > vols[-3]

    def volume_spike(self, symbol):

        vols = list(self.volume_history[symbol])

        if len(vols) < 6:
            return False

        avg_vol = sum(vols[-6:-1]) / 5

        return vols[-1] > avg_vol * 1.5

    def strong_buying(self, prices):

        if len(prices) < 6:
            return False

        move = (
            (prices[-1] - prices[-6])
            / prices[-6]
        ) * 100

        return move > 1

    def bullish_candle(self, prices):

        if len(prices) < 2:
            return False

        candle_move = (
            (prices[-1] - prices[-2])
            / prices[-2]
        ) * 100

        return candle_move > 0.5

    def break_previous_high(self, prices):

        if len(prices) < 2:
            return False

        return prices[-1] > prices[-2]

    def break_resistance(self, prices):

        if len(prices) < 20:
            return False

        resistance = max(prices[-20:-1])

        return prices[-1] > resistance

    def pullback_recovery(self, prices):

        if len(prices) < 10:
            return False

        swing_high = max(prices[-10:-4])

        pullback_low = min(prices[-4:-1])

        retracement = (
            (swing_high - pullback_low)
            / swing_high
        ) * 100

        if retracement > 10:
            return False

        return prices[-1] > prices[-2]

    def near_day_high(self, symbol, price):

        day_high = self.day_high.get(symbol, price)

        return price >= day_high * 0.97

    def update(self, symbol, price, volume):

        if (
            not symbol
            or price is None
            or volume is None
        ):
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        if symbol not in self.day_open:
            self.day_open[symbol] = price

        if symbol not in self.day_high:
            self.day_high[symbol] = price
        else:
            self.day_high[symbol] = max(
                self.day_high[symbol],
                price
            )

        prices = list(self.price_history[symbol])

        if len(prices) < 20:
            return

        day_change = self.get_day_change(
            symbol,
            price
        )

        if day_change < 4:
            return

        if self.already_sent_recent(symbol):
            return

        if not self.volume_increasing(symbol):
            return

        if not self.volume_spike(symbol):
            return

        if not self.strong_buying(prices):
            return

        if not self.bullish_candle(prices):
            return

        if not self.break_previous_high(prices):
            return

        if not self.pullback_recovery(prices):
            return

        breakout = self.break_resistance(prices)
        near_high = self.near_day_high(symbol, price)

        if not breakout and not near_high:
            return

        signal_type = (
            "BREAKOUT"
            if breakout
            else "PULLBACK READY"
        )

        message = f"""
🔥 PULLBACK STRATEGY 🔥

{symbol} → BUY

₹{round(price, 2)}

Type : {signal_type}
Day Change : {round(day_change, 2)}%

✅ Strong Buying
✅ Volume Increasing
✅ Volume Spike
✅ Pullback Recovery
✅ Bullish Candle
✅ Previous High Break
✅ Near Day High / Resistance Break
"""

        send_alert(message)

        self.signal_history[symbol] = time.time()

# =========================
# ✅ NEW STRATEGY (SEPARATE)
# =========================
class JinningEffectStrategy:
    def __init__(self):
        self.close_history = defaultdict(lambda: deque(maxlen=150))
        self.volume_history = defaultdict(lambda: deque(maxlen=10))

        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 1800  # 30 min

    def already_sent_recent(self, symbol):
        return symbol in self.signal_history and time.time() - self.signal_history[symbol] < self.SIGNAL_COOLDOWN

    def update_daily(self, symbol, close_price, volume):

        if not symbol or close_price is None or volume is None:
            return

        self.close_history[symbol].append(close_price)
        self.volume_history[symbol].append(volume)

        closes = list(self.close_history[symbol])
        volumes = list(self.volume_history[symbol])

        # Need enough history
        if len(closes) < 130:
            return

        # ✅ CONDITION 1 (Breakout)
        recent_5_max = max(closes[-5:])
        past_120_max = max(closes[-126:-6])

        if recent_5_max <= past_120_max * 1.05:
            return

        # ✅ CONDITION 2 (Volume surge)
        if len(volumes) < 6:
            return

        avg_5_volume = sum(volumes[-6:-1]) / 5
        current_volume = volumes[-1]

        if current_volume <= avg_5_volume:
            return

        # ✅ CONDITION 3 (Close > previous)
        if closes[-1] <= closes[-2]:
            return

        if self.already_sent_recent(symbol):
            return

        # ✅ SIGNAL
        message = f"""
🔥 JINNING EFFECT 🔥
{symbol} → BUY
₹{round(close_price, 2)}

✅ 5-Day Breakout > 120D + 5%
✅ Volume > 5D Avg
✅ Strong Closing
"""

        send_alert(message)
        self.signal_history[symbol] = time.time()
