from collections import defaultdict, deque
import time
from alerts import send_alert
import pickle
import os


class MultiSignalStrategy:
    def __init__(self):

        self.filename = "price_data.pkl"

        if os.path.exists(self.filename):
            try:
                with open(self.filename, "rb") as f:
                    self.price_history = pickle.load(f)
                print("✅ Loaded previous data")
            except Exception:
                print("⚠️ Corrupted file — starting fresh")
                self.price_history = defaultdict(lambda: deque(maxlen=100))
        else:
            self.price_history = defaultdict(lambda: deque(maxlen=100))

        self.volume_history = defaultdict(lambda: deque(maxlen=20))
        self.last_alert_time = defaultdict(float)

        self.COOLDOWN = 180
        self.BREAKOUT_LOOKBACK = 20

    def save_data(self):
        try:
            with open(self.filename, "wb") as f:
                pickle.dump(self.price_history, f)
        except Exception as e:
            print("Save error:", e)

    def price_change_percent(self, prices):
        if len(prices) < 5:
            return 0
        return ((prices[-1] - prices[-5]) / prices[-5]) * 100

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50

        gains, losses = 0, 0
        for i in range(-period, 0):
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
        if len(prices) < 3:
            return 0
        return prices[-1] - prices[-3]

    def breakout_levels(self, prices):
        recent = list(prices)[-self.BREAKOUT_LOOKBACK:]
        return max(recent), min(recent)

    def volume_spike(self, symbol, volume):
        self.volume_history[symbol].append(volume)
        vols = self.volume_history[symbol]

        if len(vols) < 5:
            return False

        avg_vol = sum(list(vols)[-5:]) / 5
        return volume > avg_vol * 2.5

    # ✅ Trend detection
    def is_uptrend(self, prices):
        if len(prices) < 6:
            return False
        return prices[-1] > prices[-2] > prices[-3] and prices[-3] > prices[-5]

    def is_downtrend(self, prices):
        if len(prices) < 6:
            return False
        return prices[-1] < prices[-2] < prices[-3] and prices[-3] < prices[-5]

    def update(self, symbol, price, volume):

        # ✅ ELITE FILTER
        if volume < 200000:
            return

        self.price_history[symbol].append(price)
        prices = self.price_history[symbol]

        # ✅ ignore tiny move
        if len(prices) > 1 and abs(price - prices[-2]) < 0.3:
            return

        now = time.time()

        if now - self.last_alert_time[symbol] < self.COOLDOWN:
            return

        if len(prices) < self.BREAKOUT_LOOKBACK:
            return

        rsi = self.calculate_rsi(prices)
        vwap = self.calculate_vwap(prices)
        momentum = self.momentum(prices)
        high, low = self.breakout_levels(prices)
        vol_spike = self.volume_spike(symbol, volume)
        change_pct = self.price_change_percent(prices)

        signals = []

        # ✅ strong move filter
        if change_pct < 0.8:
            return

        # ✅ MOMENTUM
        if abs(momentum) > 2 and price >= high * 0.998:
            if momentum > 0 and rsi > 60 and price > vwap:
                signals.append("⚡ MOMENTUM UP (STRONG)")
            elif momentum < 0 and rsi < 40 and price < vwap:
                signals.append("⚡ MOMENTUM DOWN (STRONG)")

        # ✅ BREAKOUT
        if price > high:
            signals.append("🔥 BREAKOUT UP")
        elif price < low:
            signals.append("🔥 BREAKOUT DOWN")

        # ✅ BUY / SELL
        if price > high and vol_spike and price > vwap and rsi > 60:
            signals.append("🟢 BUY SIGNAL")

        if price < low and vol_spike and price < vwap and rsi < 40:
            signals.append("🔴 SELL SIGNAL")

        # ✅ TREND CONTINUATION
        uptrend = self.is_uptrend(prices)
        downtrend = self.is_downtrend(prices)

        recent_high = max(list(prices)[-6:])
        recent_low = min(list(prices)[-6:])
        pullback = price < recent_high and price > recent_low

        if uptrend and pullback:
            if price > vwap and rsi > 55 and momentum > 0:
                signals.append("📈 TREND CONTINUATION BUY")

        if downtrend and pullback:
            if price < vwap and rsi < 45 and momentum < 0:
                signals.append("📉 TREND CONTINUATION SELL")

        # ✅ ✅ SCORING SYSTEM
        score = 0

        if "⚡ MOMENTUM UP (STRONG)" in signals:
            score += 10
        if "🔥 BREAKOUT UP" in signals:
            score += 10
        if "🟢 BUY SIGNAL" in signals:
            score += 15
        if "📈 TREND CONTINUATION BUY" in signals:
            score += 5

        # ✅ ✅ RATING
        if score >= 30:
            rating = "🔥 VERY HIGH"
        elif score >= 20:
            rating = "✅ HIGH"
        elif score >= 10:
            rating = "⚠️ MEDIUM"
        else:
            rating = "❌ LOW"

        # ✅ ✅ FINAL OUTPUT
        if signals and score >= 10:
            msg = f"""
📊 {symbol}
💰 ₹{price}

{chr(10).join(signals)}

⭐ Score: {score}/40
📊 Rating: {rating}
"""
            print(msg)
            send_alert(msg)

            self.last_alert_time[symbol] = now

        # ✅ save periodically
        if int(time.time()) % 10 == 0:
            self.save_data()
