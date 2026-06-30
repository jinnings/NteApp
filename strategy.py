from collections import defaultdict, deque
from alerts import send_alert, get_ist_time


class MultiSignalStrategy:

    def __init__(self):
        self.strategy_name = "STB (NteScalping PRO)"

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

    # ✅ RELAXED HTF FILTER (used only after warmup)
    def passes_htf_filter(self, symbol):
        data = self.daily_data[symbol]
        closes = list(data["close"])
        volumes = list(data["volume"])

        if len(closes) < 40:
            return False

        if max(closes[-5:]) <= max(closes[:-6]) * 1.02:
            return False

        if volumes[-1] < (sum(volumes[-5:]) / 5) * 0.9:
            return False

        if closes[-1] <= closes[-2]:
            return False

        return True

    # ✅ SUPPORT FUNCTIONS
    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price
        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

    def get_trade_levels(self, price, direction, prices):
        recent = prices[-8:]

        if direction == "BUY":
            sl = min(recent)
            risk = max(price - sl, price * 0.0025)
            target = price + (risk * 2)
        else:
            sl = max(recent)
            risk = max(sl - price, price * 0.0025)
            target = price - (risk * 2)

        return round(sl, 2), round(target, 2)

    # ✅ SCORE SYSTEM
    def calculate_score(self, price, vwap, day_change, momentum):
        score = 0

        score += min(abs(day_change) * 3, 12)

        if abs(momentum) > 0.0015:
            score += min(abs(momentum) * 200, 10)

        score += 8 if price > vwap else 4

        return int(score)

    # ✅ CONFIDENCE
    def calculate_confidence(self, score, day_change, momentum):
        confidence = 50
        confidence += score * 1.2
        confidence += min(abs(day_change) * 2, 10)
        confidence += min(abs(momentum) * 200, 10)
        return min(int(confidence), 100)

    # ✅ TREND
    def get_trend(self, prices):
        move = abs(prices[-1] - prices[-10]) / prices[-10]
        return "STRONG" if move > 0.003 else "MEDIUM"

    # ✅ RISK
    def get_risk(self, price, sl, confidence, trend):
        pct = abs(price - sl) / price

        if pct < 0.003:
            risk = "LOW"
        elif pct < 0.006:
            risk = "MEDIUM"
        else:
            risk = "HIGH"

        if confidence >= 85 and trend == "STRONG":
            risk = "LOW"
        elif confidence < 60:
            risk = "HIGH"

        return risk

    # ✅ MAIN ENGINE
    def update(self, symbol, price, volume):

        # ✅ LOWERED VOLUME FILTER
        if volume < 1500:
            print(f"{symbol}: Volume failed ({volume})")
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(self.price_history[symbol])
        price_len = len(prices)

        print(f"{symbol}: Prices stored = {price_len}")

        # ✅ QUICK START (warmup mode)
        if price_len < 8:
            print(f"{symbol}: Waiting for minimum data")
            return

        vwap = sum(prices) / len(prices)

        # ✅ % MOMENTUM
        m1 = (prices[-1] - prices[-3]) / prices[-3]
        m5 = (prices[-1] - prices[-6]) / prices[-6]

        direction = "BUY" if m1 > 0 else "SELL"

        day_change = self.get_day_change(symbol, price)

        # ✅ WARMUP MODE (FAST SIGNALS)
        if price_len < 15:
            score = self.calculate_score(price, vwap, day_change, m5)

            if score < 8:
                print(f"{symbol}: Warmup score too low ({score})")
                return
        else:
            # ✅ APPLY FULL FILTER AFTER DATA BUILDS
            if not self.passes_htf_filter(symbol):
                print(f"{symbol}: HTF failed")
                return

            score = self.calculate_score(price, vwap, day_change, m5)

            if score < 10:
                print(f"{symbol}: Score too low ({score})")
                return

        sl, tgt = self.get_trade_levels(price, direction, prices)

        confidence = self.calculate_confidence(score, day_change, m5)
        trend = self.get_trend(prices)
        risk = self.get_risk(price, sl, confidence, trend)

        # ✅ TRADE TYPE
        if score >= 20 and risk == "LOW":
            trade_type = "🔥 INSTANT PREMIUM"
        elif score >= 20:
            trade_type = "🔥 INSTANT TRADE"
        else:
            trade_type = "🔥 TOP TRADE"

        message = f"""
{trade_type}
Strategy: {self.strategy_name}

{symbol} → {direction}
Time: {get_ist_time()}

Entry: ₹{round(price, 2)}
SL: ₹{sl}
Target: ₹{tgt}

⭐ Score: {score}
📊 Confidence: {confidence}%
📈 Trend: {trend}
⚠️ Risk: {risk}
"""

        print(f"{symbol}: ✅ SIGNAL ({direction}) Score={score}")

        send_alert(
            message,
            symbol,
            direction,
            price,
            sl,
            tgt,
            self.strategy_name,
            confidence,
            trend,
            risk
        )