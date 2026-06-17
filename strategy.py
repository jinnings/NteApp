from collections import defaultdict, deque
import time
import pandas as pd
import os


class MultiSignalStrategy:

    def __init__(self):

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.signal_history = {}

        self.SIGNAL_COOLDOWN = 900

        self.candidates = []
        self.last_rank_sent = 0

        # ✅ reversal tracking
        self.active_trades = {}
        self.completed_trades = set()

        self.file = "trade_log.xlsx"

    # =========================
    # ✅ LOGGING FUNCTION
    # =========================

    def log_to_excel(self, symbol, strategy, entry, sl=0, target=0, status="ENTRY"):

        row = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "strategy": strategy,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "target": round(target, 2),
            "status": status
        }

        df_new = pd.DataFrame([row])

        if os.path.exists(self.file):
            df_old = pd.read_excel(self.file)
            df = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df = df_new

        df.to_excel(self.file, index=False, engine="openpyxl")

    # =========================
    # HELPERS
    # =========================

    def already_sent_recent(self, symbol, tag):
        key = f"{symbol}_{tag}"
        return key in self.signal_history and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN

    def is_volume_increasing(self, symbol):
        vols = list(self.volume_history[symbol])
        return len(vols) >= 3 and vols[-1] > vols[-2] > vols[-3]

    def volume_spike(self, symbol):
        vols = list(self.volume_history[symbol])
        if len(vols) < 5:
            return False
        avg = sum(vols[:-1]) / (len(vols) - 1)
        return vols[-1] > avg * 1.5

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

    def candle_pattern_confirm(self, prices):
        return self.bullish_engulfing(prices) or self.hammer_pattern(prices)

    # =========================
    # ✅ REVERSAL STRATEGY
    # =========================

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

    def get_reversal_sl_target(self, prices):

        swing_low = min(prices[-5:])
        entry = prices[-1]

        sl = swing_low * 0.995
        risk = entry - sl
        target = entry + risk * 1.8

        return entry, sl, target

    # =========================
    # ✅ EXIT TRACKING
    # =========================

    def track_reversal_exit(self, symbol, price):

        if symbol not in self.active_trades:
            return

        trade = self.active_trades[symbol]

        if price >= trade["target"]:

            self.log_to_excel(symbol, "REVERSAL",
                              trade["entry"], trade["sl"], trade["target"], "TARGET HIT")

            self.completed_trades.add(symbol)
            del self.active_trades[symbol]

        elif price <= trade["sl"]:

            self.log_to_excel(symbol, "REVERSAL",
                              trade["entry"], trade["sl"], trade["target"], "SL HIT")

            self.completed_trades.add(symbol)
            del self.active_trades[symbol]

    # =========================
    # ✅ MAIN LOGIC
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

        # ✅ reset
        if symbol in self.completed_trades and prices[-1] > prices[-5]:
            self.completed_trades.remove(symbol)

        # =========================
        # ✅ REVERSAL ENTRY
        # =========================

        if self.pullback_reversal(symbol, prices):

            if symbol not in self.active_trades and symbol not in self.completed_trades:

                entry, sl, target = self.get_reversal_sl_target(prices)

                self.log_to_excel(symbol, "REVERSAL", entry, sl, target)

                self.active_trades[symbol] = {
                    "entry": entry,
                    "sl": sl,
                    "target": target
                }

        # =========================
        # ✅ MOMENTUM
        # =========================

        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        direction = "BUY" if m1 > 0 else "SELL"

        if not self.is_volume_increasing(symbol):
            return

        score = int(abs(m5) * 5)

        # ✅ INSTANT
        if score >= 22 and not self.already_sent_recent(symbol, direction):

            self.log_to_excel(symbol, "INSTANT", price)

            self.signal_history[f"{symbol}_{direction}"] = time.time()
            return

        # ✅ STORE TOP
        if score > 18:
            self.candidates.append({
                "symbol": symbol,
                "direction": direction,
                "price": price,
                "score": score
            })

    # =========================
    # ✅ TOP TRADES
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

            if not self.confirm_5m(prices, direction):
                continue

            if not self.candle_pattern_confirm(prices):
                continue

            if self.already_sent_recent(symbol, direction):
                continue

            self.log_to_excel(symbol, "TOP", price)

            self.signal_history[f"{symbol}_{direction}"] = time.time()

        self.candidates.clear()
        self.last_rank_sent = time.time()