from collections import defaultdict, deque
import time
from alerts import send_alert


class MultiSignalStrategy:

    def __init__(self):

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.signal_history = {}
        self.last_direction = {}

        self.SIGNAL_COOLDOWN = 900

        self.candidates = []
        self.last_rank_sent = 0

        # ✅ reversal tracking
        self.active_trades = {}
        self.completed_trades = set()

    # =========================
    # BASIC HELPERS
    # =========================

    def already_sent_recent(self, symbol, tag):
        key = f"{symbol}_{tag}"
        return key in self.signal_history and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN

    def is_volume_increasing(self, symbol):
        vols = list(self.volume_history[symbol])
        return len(vols) >= 3 and vols[-1] > vols[-2] > vols[-3]

    # =========================
    # ✅ CANDLE PATTERNS
    # =========================

    def bullish_engulfing(self, prices):
        if len(prices) < 4:
            return False
        return prices[-2] < prices[-3] and prices[-1] > prices[-2] and prices[-1] > prices[-3]

    def hammer_pattern(self, prices):
        if len(prices) < 3:
            return False
        body = abs(prices[-1] - prices[-2])
        wick = abs(prices[-2] - prices[-3])
        return wick > body * 1.5 and prices[-1] > prices[-2]

    def strong_reversal(self, prices):
        if len(prices) < 4:
            return False
        return (prices[-1] - prices[-2]) > abs(prices[-2] - prices[-3])

    def candle_pattern_confirm(self, prices):
        return (
            self.bullish_engulfing(prices) or
            self.hammer_pattern(prices) or
            self.strong_reversal(prices)
        )

    # =========================
    # ✅ REVERSAL STRATEGY
    # =========================

    def volume_spike(self, symbol):
        vols = list(self.volume_history[symbol])
        if len(vols) < 5:
            return False
        avg = sum(vols[:-1]) / (len(vols)-1)
        return vols[-1] > avg * 1.5

    def pullback_reversal(self, symbol, prices):
        if len(prices) < 12:
            return False
        if not prices[-5] > prices[-10]:
            return False
        if not prices[-2] < prices[-3]:
            return False
        if not self.candle_pattern_confirm(prices):
            return False
        if not self.volume_spike(symbol):
            return False
        return True

    # ✅ SL + Target
    def get_reversal_sl_target(self, prices):

        swing_low = min(prices[-5:])
        entry = prices[-1]

        sl = swing_low * 0.995
        risk = entry - sl
        target = entry + risk * 1.8

        return entry, sl, target

    # ✅ EXIT TRACKING
    def track_reversal_exit(self, symbol, price):

        if symbol not in self.active_trades:
            return

        trade = self.active_trades[symbol]

        if price >= trade["target"]:
            send_alert(f"""
✅ TARGET HIT ✅

{symbol}
🎯 ₹{round(trade['target'],2)}
""")
            self.completed_trades.add(symbol)
            del self.active_trades[symbol]

        elif price <= trade["sl"]:
            send_alert(f"""
❌ STOPLOSS HIT ❌

{symbol}
🛑 ₹{round(trade['sl'],2)}
""")
            self.completed_trades.add(symbol)
            del self.active_trades[symbol]

    # =========================
    # ✅ MAIN UPDATE
    # =========================

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume < 8000:
            return

        self.track_reversal_exit(symbol, price)

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(self.price_history[symbol])

        if len(prices) < 20:
            return

        # ✅ RESET logic
        if symbol in self.completed_trades:
            if prices[-1] > prices[-5]:
                self.completed_trades.remove(symbol)

        # =========================
        # ✅ REVERSAL PULLBACK
        # =========================
        if self.pullback_reversal(symbol, prices):

            if symbol not in self.active_trades and symbol not in self.completed_trades:

                entry, sl, target = self.get_reversal_sl_target(prices)

                send_alert(f"""
📉 REVERSAL PULLBACK BUY 📈

{symbol}

💰 Entry: ₹{round(entry,2)}
🛑 SL: ₹{round(sl,2)}
🎯 Target: ₹{round(target,2)}
""")

                self.active_trades[symbol] = {
                    "entry": entry,
                    "sl": sl,
                    "target": target
                }

        # =========================
        # ✅ MOMENTUM (instant/top)
        # =========================

        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        direction = "BUY" if m1 > 0 else "SELL"

        if not self.is_volume_increasing(symbol):
            return

        score = int(abs(m5) * 5)

        # ✅ INSTANT
        if score >= 22 and not self.already_sent_recent(symbol, direction):

            send_alert(f"""
🔥 INSTANT TRADE 🔥

{symbol} → {direction}
₹{round(price,2)}

⭐ Score: {score}
""")

            self.signal_history[f"{symbol}_{direction}"] = time.time()
            return

        # ✅ STORE
        if score > 18:
            self.candidates.append({
                "symbol": symbol,
                "direction": direction,
                "price": price,
                "score": score
            })

    # =========================
    # ✅ TOP TRADE WITH PATTERN
    # =========================

    def confirm_5m(self, prices, direction):
        if len(prices) < 3:
            return False
        if direction == "BUY":
            return prices[-1] > prices[-2] > prices[-3]
        return prices[-1] < prices[-2] < prices[-3]

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

            prices = list(self.price_history[symbol])

            # ✅ 5M CONFIRM
            if not self.confirm_5m(prices, direction):
                continue

            # ✅ CANDLE PATTERN
            if not self.candle_pattern_confirm(prices):
                continue

            if self.already_sent_recent(symbol, direction):
                continue

            send_alert(f"""
✅ CONFIRMED TOP TRADE ✅

{symbol} → {direction}
₹{round(price,2)}

⭐ Score: {score}

✅ 5M Confirmed
✅ Candle Pattern ✅🔥
""")

            self.signal_history[f"{symbol}_{direction}"] = time.time()

        self.candidates.clear()
        self.last_rank_sent = time.time()