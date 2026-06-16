from collections import defaultdict
import time
from alerts import send_alert


class MultiSignalStrategy:

    def __init__(self):

        # ✅ candle storage
        self.candles_5m = defaultdict(list)
        self.current_5m = {}

        self.candles_15m = defaultdict(list)
        self.current_15m = {}

        self.signal_history = {}
        self.candidates = []
        self.last_rank_sent = 0

        self.SIGNAL_COOLDOWN = 900

    # ======================
    # ✅ CANDLE BUILDING
    # ======================

    def build_candle(self, symbol, price, minutes, store, current):

        now = int(time.time() // 60)
        bucket = now // minutes

        if symbol not in current:
            current[symbol] = {
                "bucket": bucket,
                "open": price,
                "high": price,
                "low": price,
                "close": price
            }
            return

        candle = current[symbol]

        if candle["bucket"] == bucket:
            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price
        else:
            store[symbol].append(candle.copy())

            current[symbol] = {
                "bucket": bucket,
                "open": price,
                "high": price,
                "low": price,
                "close": price
            }

    def get_closes(self, candles):
        return [c["close"] for c in candles]

    # ======================
    # ✅ UTILS
    # ======================

    def already_sent_recent(self, symbol, tag):
        key = f"{symbol}_{tag}"
        return key in self.signal_history and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN

    def fibonacci(self, prices):
        high = max(prices[-10:])
        low = min(prices[-10:])
        diff = high - low

        return {
            "sl": high - diff * 0.618,
            "target": high + diff * 0.27
        }

    # ======================
    # ✅ TREND (15M)
    # ======================

    def trend_15m(self, closes):

        if len(closes) < 5:
            return None

        if closes[-1] > closes[-3]:
            return "BUY"

        if closes[-1] < closes[-3]:
            return "SELL"

        return None

    # ======================
    # ✅ PULLBACK
    # ======================

    def pullback_entry(self, closes, vwap):

        if len(closes) < 12:
            return False

        if not closes[-5] > closes[-10]:
            return False

        high = max(closes[-8:-3])
        low = closes[-2]

        pullback = (high - low) / high * 100

        if not (0.5 <= pullback <= 2.5):
            return False

        if abs(closes[-2] - vwap) > closes[-2] * 0.01:
            return False

        return closes[-1] > closes[-2]

    # ======================
    # ✅ BREAKOUT
    # ======================

    def breakout(self, closes):
        if len(closes) < 10:
            return False
        return closes[-1] > max(closes[-10:-1])

    # ======================
    # ✅ MAIN UPDATE
    # ======================

    def update(self, symbol, price, volume):

        if price is None:
            return

        # ✅ build candles
        self.build_candle(symbol, price, 5, self.candles_5m, self.current_5m)
        self.build_candle(symbol, price, 15, self.candles_15m, self.current_15m)

        closes_5 = self.get_closes(self.candles_5m[symbol])
        closes_15 = self.get_closes(self.candles_15m[symbol])

        if len(closes_5) < 15 or len(closes_15) < 5:
            return

        trend15 = self.trend_15m(closes_15)

        vwap = sum(closes_5) / len(closes_5)

        # ======================
        # ✅ PULLBACK STRATEGY
        # ======================

        if trend15 == "BUY":

            if self.pullback_entry(closes_5, vwap):

                if not self.already_sent_recent(symbol, "PULLBACK"):

                    fib = self.fibonacci(closes_5)

                    send_alert(f"""
📉 PULLBACK BUY (5M+15M) 📈

{symbol}

💰 Entry: ₹{round(closes_5[-1],2)}
🛑 SL: ₹{round(fib['sl'],2)}
🎯 Target: ₹{round(fib['target'],2)}

✅ 15M Trend UP
✅ VWAP Support
✅ Pullback + Bounce
""")

                    self.signal_history[f"{symbol}_PULLBACK"] = time.time()

        # ======================
        # ✅ BREAKOUT STRATEGY
        # ======================

        direction = "BUY"

        if trend15 != direction:
            return

        if not self.breakout(closes_5):
            return

        score = int(abs(closes_5[-1] - closes_5[-5]) * 2)

        fib = self.fibonacci(closes_5)

        entry = closes_5[-1]
        sl = fib["sl"]
        target = fib["target"]

        # ✅ instant trades
        if score >= 22 and not self.already_sent_recent(symbol, "BUY"):

            send_alert(f"""
🔥 INSTANT TRADE (5M+15M) 🔥

{symbol}

💰 Entry: ₹{round(entry,2)}
🛑 SL: ₹{round(sl,2)}
🎯 Target: ₹{round(target,2)}

⭐ Score: {score}
""")

            self.signal_history[f"{symbol}_BUY"] = time.time()
            return

        # ✅ ranking
        if score > 18:
            self.candidates.append({
                "symbol": symbol,
                "price": entry,
                "score": score,
                "sl": sl,
                "target": target
            })

    # ======================
    # ✅ TOP SIGNALS
    # ======================

    def process_top_signals(self):

        if time.time() - self.last_rank_sent < 60:
            return

        if not self.candidates:
            return

        top = sorted(self.candidates, key=lambda x: x["score"], reverse=True)[:3]

        for t in top:

            if self.already_sent_recent(t["symbol"], "TOP"):
                continue

            send_alert(f"""
🔥 TOP TRADE (5M+15M) 🔥

{t['symbol']}

💰 Entry: ₹{round(t['price'],2)}
🛑 SL: ₹{round(t['sl'],2)}
🎯 Target: ₹{round(t['target'],2)}

⭐ Score: {t['score']}
""")

            self.signal_history[f"{t['symbol']}_TOP"] = time.time()

        self.candidates.clear()
        self.last_rank_sent = time.time()