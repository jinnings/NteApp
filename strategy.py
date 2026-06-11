from collections import defaultdict, deque
import time
from alerts import send_alert
import pickle
import os


class MultiSignalStrategy:
    def __init__(self):

        self.filename = "price_data.pkl"

        # ✅ safe load
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

        self.COOLDOWN = 60
        self.BREAKOUT_LOOKBACK = 20

    # ✅ safe save (atomic)
    def save_data(self):
        temp_file = self.filename + ".tmp"
        try:
            with open(temp_file, "wb") as f:
                pickle.dump(self.price_history, f)
            os.replace(temp_file, self.filename)
        except Exception as e:
            print("Save error:", e)

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

    # ✅ REAL volume spike
    def volume_spike(self, symbol, volume):

        self.volume_history[symbol].append(volume)
        vols = self.volume_history[symbol]

        if len(vols) < 5:
            return False

        avg_vol = sum(list(vols)[-5:]) / 5
        return volume > avg_vol * 2

    def update(self, symbol, price, volume):

        self.price_history[symbol].append(price)
        prices = self.price_history[symbol]

        if len(prices) > 1 and abs(price - prices[-2]) < 0.2:
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

        signals = []

        # ✅ filtered momentum
        if abs(momentum) > 1.2:
            if abs(price - high) <= 1 or abs(price - low) <= 1:
                if momentum > 0 and rsi > 55 and price > vwap:
                    signals.append("⚡ MOMENTUM UP (STRONG)")
                elif momentum < 0 and rsi < 45 and price < vwap:
                    signals.append("⚡ MOMENTUM DOWN (STRONG)")

        # ✅ breakout
        if price > high:
            signals.append("🔥 BREAKOUT UP")
        elif price < low:
            signals.append("🔥 BREAKOUT DOWN")

        # ✅ BUY / SELL with volume confirmation
        if price > high and vol_spike:
            if price > vwap and rsi > 55 and momentum > 0:
                signals.append("🟢 BUY SIGNAL")

        if price < low and vol_spike:
            if price < vwap and rsi < 45 and momentum < 0:
                signals.append("🔴 SELL SIGNAL")

        if signals:
            msg = f"""
📊 {symbol}
💰 ₹{price}

{chr(10).join(signals)}

📈 RSI: {round(rsi,1)}
📊 VWAP: {round(vwap,2)}
📦 Volume: {volume}
"""
            print(msg)
            send_alert(msg)

            self.last_alert_time[symbol] = now

        # ✅ save periodically
        if int(time.time()) % 10 == 0:
            self.save_data()