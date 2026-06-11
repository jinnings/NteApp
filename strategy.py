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
            except:
                print("⚠️ Corrupted file — starting fresh")
                self.price_history = defaultdict(lambda: deque(maxlen=100))
        else:
            self.price_history = defaultdict(lambda: deque(maxlen=100))

        self.volume_history = defaultdict(lambda: deque(maxlen=20))
        self.last_alert_time = defaultdict(float)
        self.live_candidates = []

        self.COOLDOWN = 120
        self.BREAKOUT_LOOKBACK = 20

    def save_data(self):
        try:
            with open(self.filename, "wb") as f:
                pickle.dump(self.price_history, f)
        except Exception as e:
            print("Save error:", e)

    def calculate_rsi(self, prices):
        if len(prices) < 15:
            return 50
        gains, losses = 0, 0
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
        if len(prices) < 3:
            return 0
        return prices[-1] - prices[-3]

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

    def update(self, symbol, price, volume):

        if not symbol or price is None:
            return

        if volume < 50000:
            return

        self.price_history[symbol].append(price)
        prices = self.price_history[symbol]

        if len(prices) < 20:
            return

        now = time.time()
        if now - self.last_alert_time[symbol] < self.COOLDOWN:
            return

        rsi = self.calculate_rsi(prices)
        vwap = self.calculate_vwap(prices)
        momentum = self.momentum(prices)
        high, low = self.breakout_levels(prices)
        vol_spike = self.volume_spike(symbol, volume)

        direction = None
        score = 0

        if price >= high * 0.998:
            if (rsi > 55 and price > vwap) or vol_spike:
                direction = "BUY"
                score += 20

        elif price <= low * 1.002:
            if (rsi < 45 and price < vwap) or vol_spike:
                direction = "SELL"
                score += 20

        if abs(momentum) > 2:
            score += 10

        if direction is None:
            return

        if direction == "BUY":
            entry = price
            sl = low
            target = entry + (entry - sl) * 2
        else:
            entry = price
            sl = high
            target = entry - (sl - entry) * 2

        rating = "🔥 VERY HIGH" if score >= 30 else "✅ HIGH"

        msg = f"""
🚨 LIVE TRADE SIGNAL 🚨

📊 {symbol} ({direction})

💰 Entry: ₹{round(entry,2)}
❌ SL: ₹{round(sl,2)}
🎯 Target: ₹{round(target,2)}

⭐ Score: {score}
📊 {rating}
"""
        print(msg)
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

        if int(time.time()) % 10 == 0:
            self.save_data()

    def get_top_stocks(self):
        if not self.live_candidates:
            return []

        sorted_list = sorted(
            self.live_candidates,
            key=lambda x: x["score"],
            reverse=True
        )

        self.live_candidates = []
        return sorted_list[:3]