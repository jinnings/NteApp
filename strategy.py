from collections import defaultdict, deque
import time
from alerts import send_alert, get_ist_time


class MultiSignalStrategy:
    def __init__(self):

        self.strategy_name = "STB (NteScalping)"

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.daily_data = defaultdict(lambda: {
            "close": deque(maxlen=130),
            "volume": deque(maxlen=10)
        })

        self.day_open = {}

    # ✅ DAILY DATA
    def update_daily(self, symbol, close, volume):
        self.daily_data[symbol]["close"].append(close)
        self.daily_data[symbol]["volume"].append(volume)

    # ✅ HTF FILTER
    def passes_htf_filter(self, symbol):
        data = self.daily_data[symbol]
        closes = list(data["close"])
        volumes = list(data["volume"])

        if len(closes) < 125 or len(volumes) < 5:
            return False

        if max(closes[-5:]) <= max(closes[:-6]) * 1.05:
            return False

        if volumes[-1] <= sum(volumes[-5:]) / 5:
            return False

        if closes[-1] <= closes[-2]:
            return False

        return True

    # ✅ SUPPORT
    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price
        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

    def get_trade_levels(self, price, direction, prices):
        recent = prices[-10:]
        if direction == "BUY":
            sl = min(recent)
            risk = max(price - sl, price * 0.003)
            target = price + risk * 2
        else:
            sl = max(recent)
            risk = max(sl - price, price * 0.003)
            target = price - risk * 2
        return round(sl, 2), round(target, 2)

    # ✅ EXTRA METRICS
    def calculate_score(self, price, vwap, day_change, momentum):
        score = min(abs(day_change) * 4, 15)
        if abs(momentum) > 0.3:
            score += min(abs(momentum) * 4, 8)
        score += 8 if price > vwap else 4
        return int(score)

    def calculate_confidence(self, score, day_change, momentum):
        return min(int(50 + score * 1.5 + abs(day_change)*2 + abs(momentum)*3), 100)

    def get_trend(self, prices):
        move = abs(prices[-1] - prices[-15]) / prices[-1]
        return "STRONG" if move > 0.004 else "MEDIUM"

    def get_risk(self, price, sl, confidence, trend):
        pct = abs(price - sl) / price
        if pct < 0.004:
            risk = "LOW"
        elif pct < 0.008:
            risk = "MEDIUM"
        else:
            risk = "HIGH"

        if confidence > 85 and trend == "STRONG":
            risk = "LOW"
        if confidence < 65:
            risk = "HIGH"

        return risk

    # ✅ MAIN ENGINE
    def update(self, symbol, price, volume):

        if volume < 8000:
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(self.price_history[symbol])
        if len(prices) < 20:
            return

        if not self.passes_htf_filter(symbol):
            return

        vwap = sum(prices) / len(prices)
        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        direction = "BUY" if m1 > 0 else "SELL"

        day_change = self.get_day_change(symbol, price)
        score = self.calculate_score(price, vwap, day_change, m5)

        sl, tgt = self.get_trade_levels(price, direction, prices)

        confidence = self.calculate_confidence(score, day_change, m5)
        trend = self.get_trend(prices)
        risk = self.get_risk(price, sl, confidence, trend)

        message = f"""
🔥 TRADE ALERT 🔥
Strategy: {self.strategy_name}

{symbol} → {direction}
Time: {get_ist_time()}

Entry: ₹{price}
SL: ₹{sl}
Target: ₹{tgt}

⭐ Score: {score}
📊 Confidence: {confidence}%
📈 Trend: {trend}
⚠️ Risk: {risk}
"""

        send_alert(message, symbol, direction, price, sl, tgt,
                   self.strategy_name, confidence, trend, risk)