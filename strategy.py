from collections import defaultdict, deque
import time
import pandas as pd
import os


class MultiSignalStrategy:

    def __init__(self):

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.signal_history = {}
        self.last_direction = {}

        self.SIGNAL_COOLDOWN = 900

        self.candidates = []
        self.last_rank_sent = 0

        self.active_trades = {}
        self.completed_trades = set()

        self.file = "trade_log.xlsx"

    # =========================
    # ✅ COLOR FUNCTION
    # =========================
    def color_text(self, text, color):

        colors = {
            "green": "\033[92m",
            "red": "\033[91m",
            "yellow": "\033[93m",
            "reset": "\033[0m"
        }

        return f"{colors[color]}{text}{colors['reset']}"

    # =========================
    # ✅ LOG TO EXCEL + PRINT
    # =========================

    def log_to_excel(self, symbol, strategy, entry, sl=0, target=0, status="ENTRY", score=0):

        row = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "strategy": strategy,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "target": round(target, 2),
            "status": status,
            "score": score
        }

        # ✅ COLOR LOGIC
        if score >= 22:
            header = self.color_text("🔥 HIGH SCORE TRADE 🔥", "green")
        else:
            header = "📊 TRADE SIGNAL"

        # ✅ CONSOLE OUTPUT
        print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{header}
⏰ {time.strftime("%H:%M:%S")}
📌 {symbol}
⚡ Strategy: {strategy}
⭐ Score: {score}
💰 Entry: ₹{entry}
🛑 SL: ₹{sl}
🎯 Target: ₹{target}
📍 Status: {status}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

        # ✅ SAVE TO EXCEL
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
        avg = sum(vols[:-1]) / (len(vols)-1)
        return vols[-1] > avg * 1.5

    # =========================
    # ✅ CANDLE PATTERN
    # =========================

    def candle_pattern(self, prices):
        if len(prices) < 4:
            return False

        return (
            prices[-1] > prices[-2] > prices[-3] or
            prices[-1] > prices[-3]
        )

    # =========================
    # ✅ REVERSAL
    # =========================

    def pullback_reversal(self, symbol, prices):
        if len(prices) < 12:
            return False

        if not prices[-5] > prices[-10]:
            return False

        if not prices[-2] < prices[-3]:
            return False

        if not self.candle_pattern(prices):
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

    def track_reversal_exit(self, symbol, price):

        if symbol not in self.active_trades:
            return

        trade = self.active_trades[symbol]

        if price >= trade["target"]:
            self.log_to_excel(symbol, "REVERSAL", trade["entry"], trade["sl"], trade["target"], "TARGET HIT")

            self.completed_trades.add(symbol)
            del self.active_trades[symbol]

        elif price <= trade["sl"]:
            self.log_to_excel(symbol, "REVERSAL", trade["entry"], trade["sl"], trade["target"], "SL HIT")

            self.completed_trades.add(symbol)
            del self.active_trades[symbol]

    # =========================
    # MAIN LOGIC
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

        # ✅ RESET
        if symbol in self.completed_trades and prices[-1] > prices[-5]:
            self.completed_trades.remove(symbol)

        # ✅ REVERSAL ENTRY
        if self.pullback_reversal(symbol, prices):

            if symbol not in self.active_trades and symbol not in self.completed_trades:

                entry, sl, target = self.get_reversal_sl_target(prices)

                self.log_to_excel(symbol, "REVERSAL", entry, sl, target)

                self.active_trades[symbol] = {
                    "entry": entry,
                    "sl": sl,
                    "target": target
                }

        # ✅ MOMENTUM
        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        direction = "BUY" if m1 > 0 else "SELL"

        if not self.is_volume_increasing(symbol):
            return

        score = int(abs(m5) * 5)

        # ✅ INSTANT (GREEN if high score)
        if score >= 22 and not self.already_sent_recent(symbol, direction):

            self.log_to_excel(symbol, "INSTANT", price, score=score)

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
    # ✅ TOP TRADES
    # =========================

    def confirm_5m(self, prices, direction):
        if len(prices) < 3:
            return False
        return prices[-1] > prices[-2] > prices[-3]

    def process_top_signals(self):

        if time.time() - self.last_rank_sent < 60:
            return

        if not self.candidates:
            return

        top = sorted(self.candidates, key=lambda x: x["score"], reverse=True)[:3]

        for t in top:

            prices = list(self.price_history[t["symbol"]])

            if not self.confirm_5m(prices, t["direction"]):
                continue

            if not self.candle_pattern(prices):
                continue

            self.log_to_excel(t["symbol"], "TOP", t["price"], score=t["score"])

        self.candidates.clear()
        self.last_rank_sent = time.time()