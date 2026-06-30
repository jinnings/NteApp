from collections import defaultdict, deque
from alerts import send_alert, get_ist_time


class MultiSignalStrategy:

    def __init__(self):
        self.strategy_name = "STB (NteScalping PROFIT)"

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        self.daily_data = defaultdict(lambda: {
            "close": deque(maxlen=130),
            "volume": deque(maxlen=10)
        })

        self.day_open = {}

        # ✅ YOU MUST UPDATE THIS FROM MAIN LOOP
        self.market_trend = "SIDEWAYS"  # "UP" / "DOWN"

    # ✅ SET MARKET TREND (CALL THIS FROM MAIN.PY)
    def set_market_trend(self, trend):
        self.market_trend = trend

    # ✅ DAILY DATA
    def update_daily(self, symbol, close, volume):
        self.daily_data[symbol]["close"].append(close)
        self.daily_data[symbol]["volume"].append(volume)

    # ✅ HTF FILTER
    def passes_htf_filter(self, symbol):
        data = self.daily_data[symbol]
        closes = list(data["close"])
        volumes = list(data["volume"])

        if len(closes) < 40:
            return False

        if max(closes[-5:]) <= max(closes[:-6]) * 1.02:
            return False

        if volumes[-1] < (sum(volumes[-5:]) / 5):
            return False

        return True

    # ✅ DAY CHANGE
    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price
        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

    # ✅ REAL VWAP (FIXED)
    def calculate_vwap(self, prices, volumes):
        total_pv = sum(p * v for p, v in zip(prices, volumes))
        total_vol = sum(volumes)
        return total_pv / total_vol if total_vol > 0 else prices[-1]

    # ✅ TRADE LEVELS
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

    # ✅ SCORE
    def calculate_score(self, price, vwap, day_change, momentum):
        score = 0

        score += min(abs(day_change) * 3, 12)

        if abs(momentum) > 0.0015:
            score += min(abs(momentum) * 200, 10)

        score += 10 if price > vwap else 2

        return int(score)

    # ✅ CONFIDENCE
    def calculate_confidence(self, score, day_change, momentum):
        confidence = 50
        confidence += score * 1.2
        confidence += min(abs(day_change) * 2, 10)
        confidence += min(abs(momentum) * 200, 10)
        return min(int(confidence), 100)

    # ✅ SAFE TREND
    def get_trend(self, prices):
        if len(prices) < 2:
            return "MEDIUM"

        base = prices[0] if len(prices) < 10 else prices[-10]

        if base == 0:
            return "MEDIUM"

        move = abs(prices[-1] - base) / base

        return "STRONG" if move > 0.003 else "MEDIUM"

    # ✅ MARKET FILTER (CRITICAL)
    def market_ok(self, direction):
        if self.market_trend == "UP" and direction == "BUY":
            return True
        if self.market_trend == "DOWN" and direction == "SELL":
            return True
        return False

    # ✅ VOLUME SPIKE FILTER
    def has_volume_spike(self, volumes):
        if len(volumes) < 5:
            return True  # allow in warmup

        avg = sum(volumes[-5:]) / 5
        return volumes[-1] > avg * 1.2

    # ✅ MAIN ENGINE
    def update(self, symbol, price, volume):

        if volume < 1500:
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(self.price_history[symbol])
        volumes = list(self.volume_history[symbol])

        price_len = len(prices)

        if price_len < 4:
            return

        # ✅ REAL VWAP
        vwap = self.calculate_vwap(prices, volumes)

        # ✅ MOMENTUM
        m1 = (prices[-1] - prices[-3]) / prices[-3] if price_len >= 3 else 0
        m5 = (prices[-1] - prices[-6]) / prices[-6] if price_len >= 6 else m1

        direction = "BUY" if m1 > 0 else "SELL"

        # ✅ MARKET FILTER
        if not self.market_ok(direction):
            print(f"{symbol}: Market filter blocked")
            return

        # ✅ VOLUME SPIKE
        if not self.has_volume_spike(volumes):
            print(f"{symbol}: No volume spike")
            return

        day_change = self.get_day_change(symbol, price)

        # ✅ HTF after warmup
        if price_len >= 15:
            if not self.passes_htf_filter(symbol):
                print(f"{symbol}: HTF failed")
                return

        score = self.calculate_score(price, vwap, day_change, m5)

        if score < 12:
            print(f"{symbol}: Score too low ({score})")
            return

        sl, tgt = self.get_trade_levels(price, direction, prices)
        confidence = self.calculate_confidence(score, day_change, m5)
        trend = self.get_trend(prices)
        risk = self.get_risk(price, sl, confidence, trend)

        # ✅ TRADE TYPE
        if score >= 22 and risk == "LOW":
            trade_type = "🔥 PREMIUM"
        elif score >= 18:
            trade_type = "🔥 STRONG"
        else:
            trade_type = "⚡ NORMAL"

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

        print(f"{symbol}: ✅ PROFIT SIGNAL ({direction}) Score={score}")

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