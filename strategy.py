from collections import defaultdict
import time
import pandas as pd
import os
from alerts import send_alert


class MultiSignalStrategy:

    def __init__(self):

        self.candles_5m = defaultdict(list)
        self.current_5m = {}

        self.candles_15m = defaultdict(list)
        self.current_15m = {}

        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 900

        self.trades = []
        self.excel_file = "trades.xlsx"

        # ✅ store volume history (FIXED)
        self.volume_history = defaultdict(list)

    # ✅ Candle builder
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

    def already_sent_recent(self, symbol, tag):
        key = f"{symbol}_{tag}"
        return key in self.signal_history and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN

    # ✅ Fibonacci
    def fibonacci(self, prices):
        high = max(prices[-10:])
        low = min(prices[-10:])
        diff = high - low

        return {
            "sl": high - diff * 0.618,
            "target": high + diff * 0.27
        }

    # ✅ Save trades
    def save_trade(self, symbol, strategy, entry, sl, target, score):

        trade = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "strategy": strategy,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "target": round(target, 2),
            "score": score
        }

        self.trades.append(trade)

        df = pd.DataFrame(self.trades)

        if os.path.exists(self.excel_file):
            old_df = pd.read_excel(self.excel_file)
            df = pd.concat([old_df, df]).drop_duplicates().reset_index(drop=True)

        df.to_excel(self.excel_file, index=False)

    # ✅ Trend
    def trend_15m(self, closes):
        if len(closes) < 5:
            return None

        if closes[-1] > closes[-3]:
            return "BUY"
        elif closes[-1] < closes[-3]:
            return "SELL"

        return None

    # ✅ Breakout
    def breakout(self, closes):
        if len(closes) < 10:
            return False
        return closes[-1] > max(closes[-10:-1]) and closes[-1] > closes[-2]

    # ✅ MAIN LOGIC
    def update(self, symbol, price, volume):

        if price is None:
            return

        # ✅ track volume history (NEW FIX)
        self.volume_history[symbol].append(volume)
        if len(self.volume_history[symbol]) > 20:
            self.volume_history[symbol].pop(0)

        self.build_candle(symbol, price, 5, self.candles_5m, self.current_5m)
        self.build_candle(symbol, price, 15, self.candles_15m, self.current_15m)

        closes_5 = self.get_closes(self.candles_5m[symbol])
        closes_15 = self.get_closes(self.candles_15m[symbol])

        if len(closes_5) < 15 or len(closes_15) < 5:
            return

        trend15 = self.trend_15m(closes_15)

        # =========================
        # 💥 VOLUME SPIKE SNIPER (FIXED ✅)
        # =========================
        if len(self.volume_history[symbol]) >= 10:
            avg_vol = sum(self.volume_history[symbol][-10:]) / 10

            if volume > avg_vol * 2 and trend15 == "BUY":

                if not self.already_sent_recent(symbol, "SNIPER"):

                    fib = self.fibonacci(closes_5)

                    send_alert(f"""
💥 VOLUME SPIKE SNIPER 💥

{symbol}

💰 Entry: ₹{round(closes_5[-1],2)}
🛑 SL: ₹{round(fib['sl'],2)}
🎯 Target: ₹{round(fib['target'],2)}

🚀 Volume spike detected
""")

                    self.signal_history[f"{symbol}_SNIPER"] = time.time()
                    self.save_trade(symbol, "SNIPER", closes_5[-1], fib["sl"], fib["target"], 25)

        # =========================
        # ⚡ SCALPING MODE
        # =========================
        price_jump = (closes_5[-1] - closes_5[-2]) / closes_5[-2] * 100

        if trend15 == "BUY" and price_jump > 0.3:

            if not self.already_sent_recent(symbol, "SCALP"):

                fib = self.fibonacci(closes_5)

                send_alert(f"""
⚡ SCALPING TRADE ⚡

{symbol}

💰 Entry: ₹{round(closes_5[-1],2)}
🛑 SL: ₹{round(fib['sl'],2)}
🎯 Target: ₹{round(fib['target'],2)}

⚡ Quick momentum move
""")

                self.signal_history[f"{symbol}_SCALP"] = time.time()
                self.save_trade(symbol, "SCALP", closes_5[-1], fib["sl"], fib["target"], 15)

        # =========================
        # 🚀 ELITE BREAKOUT
        # =========================
        if trend15 != "BUY":
            return

        if not self.breakout(closes_5):
            return

        # ✅ SMART SCORE
        momentum = (closes_5[-1] - closes_5[-5]) / closes_5[-5] * 100
        candle_strength = (closes_5[-1] - closes_5[-2]) / closes_5[-2] * 100
        volume_boost = min(volume / 100000, 10)

        score = int(momentum * 3 + candle_strength * 2 + volume_boost)

        if closes_5[-1] <= closes_5[-2]:
            return

        if (closes_5[-1] - closes_5[-2]) / closes_5[-2] < 0.2:
            return

        fib = self.fibonacci(closes_5)

        if score >= 20 and not self.already_sent_recent(symbol, "BUY"):

            send_alert(f"""
🚀 ELITE BREAKOUT 🚀

{symbol}

💰 Entry: ₹{round(closes_5[-1],2)}
🛑 SL: ₹{round(fib['sl'],2)}
🎯 Target: ₹{round(fib['target'],2)}

⭐ Score: {score}
""")

            self.signal_history[f"{symbol}_BUY"] = time.time()
            self.save_trade(symbol, "BREAKOUT", closes_5[-1], fib["sl"], fib["target"], score)