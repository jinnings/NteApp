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

        # ✅ smart control
        self.last_sent_time = {}
        self.sent_priority = {}

        self.day_open = {}
        self.COOLDOWN = 120

    # ---------------- INDICATORS ---------------- #

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

        return ma + 2 * std, ma, ma - 2 * std

    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price

        op = self.day_open[symbol]
        return ((price - op) / op) * 100 if op else 0

    # ---------------- PRIORITY CONTROL ---------------- #

    def can_send(self, symbol, priority):
        now = time.time()

        if symbol in self.last_sent_time:
            if now - self.last_sent_time[symbol] < self.COOLDOWN:
                if self.sent_priority.get(symbol, 0) >= priority:
                    return False

        self.last_sent_time[symbol] = now
        self.sent_priority[symbol] = priority

        return True

    # ---------------- MAIN UPDATE ---------------- #

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume < 50000:
            return

        self.price_history[symbol].append(price)
        prices = self.price_history[symbol]

        if len(prices) < 30:
            return

        rsi = self.calculate_rsi(prices)
        vwap = self.calculate_vwap(prices)
        momentum = self.momentum(prices)
        high, low = self.breakout_levels(prices)
        vol_spike = self.volume_spike(symbol, volume)
        macd, macd_signal = self.calculate_macd(prices)
        upper, mid, lower = self.calculate_bollinger(prices)

        day_change = self.get_day_change(symbol, price)

        # ✅ 🚀 MOMENTUM (LOW PRIORITY)
        if day_change > 3 and price > vwap:
            if self.can_send(symbol, 1):
                send_alert(f"""
🚀 MOMENTUM GAINER

{symbol} → ₹{round(price,2)}
📈 +{round(day_change,2)}%

⚡ Strong move starting
""")

        # ✅ 🎯 PULLBACK
        near_vwap = abs(price - vwap) / vwap < 0.005
        if day_change > 3 and near_vwap and momentum > 0:
            if self.can_send(symbol, 2):
                send_alert(f"""
🎯 PULLBACK SETUP

{symbol} → ₹{round(price,2)}

📉 Near VWAP
✅ Safe Entry Zone
""")

        # ✅ 📈 RUNNERS
        if abs(day_change) >= 4:
            direction = "BUY" if day_change > 0 else "SELL"

            if self.can_send(symbol, 3):
                send_alert(f"""
📈 TODAY'S RUNNERS

{symbol} → {'🟢 BUY' if direction == 'BUY' else '🔴 SELL'}
💰 ₹{round(price,2)} (+{round(day_change,2)}%)

✅ Strong Trend | Pullback Entry
""")

        # ✅ 🔥 ELITE SIGNAL
        direction = None
        score = 0

        if price >= high * 0.998:
            if rsi > 60: score += 8
            if price > vwap: score += 5
            if vol_spike: score += 10
            if momentum > 2: score += 8
            if macd > macd_signal: score += 7
            if price > upper: score += 7

            if score >= 35:
                direction = "BUY"

        elif price <= low * 1.002:
            if rsi < 40: score += 8
            if price < vwap: score += 5
            if vol_spike: score += 10
            if momentum < -2: score += 8
            if macd < macd_signal: score += 7
            if price < lower: score += 7

            if score >= 35:
                direction = "SELL"

        if direction:
            confidence = "🔥 STRONG" if score >= 40 else "✅ MEDIUM"
            trend = "Momentum Breakout" if direction == "BUY" else "Breakdown"

            if self.can_send(symbol, 4):
                send_alert(f"""
🔥 TOP INTRADAY SETUPS 🔥

📊 {symbol} → {'🟢 BUY' if direction == 'BUY' else '🔴 SELL'}

💰 Entry: ₹{round(price,2)}
🎯 Quick Move Expected

⭐ Score: {score} | {confidence}
📈 Trend: {trend}
""")