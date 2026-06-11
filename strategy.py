from collections import defaultdict, deque
import time
from alerts import send_alert
import pickle
import os
import numpy as np


class MultiSignalStrategy:
    def __init__(self):

        self.filename = "price_data.pkl"

        if os.path.exists(self.filename):
            try:
                with open(self.filename, "rb") as f:
                    self.price_history = pickle.load(f)
            except:
                self.price_history = defaultdict(lambda: deque(maxlen=100))
        else:
            self.price_history = defaultdict(lambda: deque(maxlen=100))

        self.volume_history = defaultdict(lambda: deque(maxlen=20))
        self.last_alert_time = defaultdict(float)
        self.live_candidates = []

        # ✅ runners
        self.day_open = {}
        self.runners = []
        self.runner_alert_time = 0

        self.COOLDOWN = 120
        self.BREAKOUT_LOOKBACK = 20

    def calculate_rsi(self, prices):
        if len(prices) < 15:
            return 50
        gains = losses = 0
        for i in range(-14, 0):
            diff = prices[i] - prices[i - 1]
            if diff > 0:
                gains += diff
            else:
                losses += abs(diff)
        if losses == 0:
            return 100
        rs = gains / losses
        return 100 - (100 / (1 + rs))

    def calculate_vwap(self, prices):
        return sum(prices) / len(prices)

    def momentum(self, prices):
        return prices[-1] - prices[-3] if len(prices) >= 3 else 0

    def breakout_levels(self, prices):
        recent = list(prices)[-20:]
        return max(recent), min(recent)

    def volume_spike(self, symbol, volume):
        self.volume_history[symbol].append(volume)
        vols = self.volume_history[symbol]
        if len(vols) < 5:
            return False
        avg = sum(list(vols)[-5:]) / 5
        return volume > avg * 1.5

    def calculate_macd(self, prices):
        if len(prices) < 26:
            return 0, 0
        ema12 = np.mean(prices[-12:])
        ema26 = np.mean(prices[-26:])
        macd = ema12 - ema26
        signal = np.mean(prices[-9:])
        return macd, signal

    def calculate_bollinger(self, prices):
        if len(prices) < 20:
            return 0, 0, 0
        ma = np.mean(prices[-20:])
        std = np.std(prices[-20:])
        upper = ma + 2 * std
        lower = ma - 2 * std
        return upper, ma, lower

    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price
        op = self.day_open[symbol]
        return ((price - op) / op) * 100 if op else 0

    # ✅ ✅ PULLBACK ENTRY LOGIC
    def is_pullback_entry(self, direction, price, vwap, mid, momentum):

        if direction == "BUY":
            near_vwap = abs(price - vwap) / vwap < 0.005
            near_mid = abs(price - mid) / mid < 0.005

            if not (near_vwap or near_mid):
                return False

            if momentum <= 0:
                return False

        elif direction == "SELL":
            near_vwap = abs(price - vwap) / vwap < 0.005
            near_mid = abs(price - mid) / mid < 0.005

            if not (near_vwap or near_mid):
                return False

            if momentum >= 0:
                return False

        return True

    def update(self, symbol, price, volume):

        if not symbol or price is None:
            return
        if volume < 50000:
            return

        self.price_history[symbol].append(price)
        prices = self.price_history[symbol]

        if len(prices) < 30:
            return

        now = time.time()
        if now - self.last_alert_time[symbol] < self.COOLDOWN:
            return

        rsi = self.calculate_rsi(prices)
        vwap = self.calculate_vwap(prices)
        momentum = self.momentum(prices)
        high, low = self.breakout_levels(prices)
        vol_spike = self.volume_spike(symbol, volume)
        macd, macd_signal = self.calculate_macd(prices)
        upper, mid, lower = self.calculate_bollinger(prices)

        # ✅ ✅ RUNNERS WITH PULLBACK
        day_change = self.get_day_change(symbol, price)

        if abs(day_change) >= 4:
            direction_runner = "BUY" if day_change > 0 else "SELL"

            if self.is_pullback_entry(direction_runner, price, vwap, mid, momentum):
                self.runners.append({
                    "symbol": symbol,
                    "price": round(price, 2),
                    "change": round(day_change, 2),
                    "direction": direction_runner
                })

        # ✅ ELITE SIGNAL STRATEGY
        direction = None
        score = 0

        if price >= high * 0.998:
            if rsi > 60: score += 8
            if price > vwap: score += 5
            if vol_spike: score += 10
            if momentum > 2: score += 8
            if macd > macd_signal: score += 7
            if price > upper: score += 7
            if score >= 25:
                direction = "BUY"

        elif price <= low * 1.002:
            if rsi < 40: score += 8
            if price < vwap: score += 5
            if vol_spike: score += 10
            if momentum < -2: score += 8
            if macd < macd_signal: score += 7
            if price < lower: score += 7
            if score >= 25:
                direction = "SELL"

        # ✅ ONLY HIGH QUALITY
        if direction is None or score < 30:
            return

        if direction == "BUY":
            entry, sl = price, low
            target = entry + (entry - sl) * 2
        else:
            entry, sl = price, high
            target = entry - (sl - entry) * 2

        rating = "🔥 VERY HIGH" if score >= 40 else "✅ HIGH"

        msg = f"""
🚨 ELITE TRADE SIGNAL 🚨

📊 {symbol} ({direction})

💰 Entry: ₹{round(entry,2)}
❌ SL: ₹{round(sl,2)}
🎯 Target: ₹{round(target,2)}

⭐ Score: {score}
📊 {rating}
"""
        send_alert(msg)

        self.live_candidates.append({
            "symbol": symbol,
            "price": round(entry, 2),
            "sl": round(sl, 2),
            "target": round(target, 2),
            "score": score,
            "rating": rating,
            "direction": direction
        })

        self.last_alert_time[symbol] = now

    def get_top_stocks(self):
        if not self.live_candidates:
            return []
        sorted_list = sorted(self.live_candidates, key=lambda x: x["score"], reverse=True)
        self.live_candidates = []
        return sorted_list[:3]

    def get_runners(self):
        if not self.runners:
            return []
        unique = {r["symbol"]: r for r in self.runners}
        result = sorted(unique.values(), key=lambda x: abs(x["change"]), reverse=True)
        self.runners = []
        return result[:5]