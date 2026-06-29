from collections import defaultdict, deque
import time
from alerts import send_alert, get_ist_time


class MultiSignalStrategy:
    def __init__(self):

        self.strategy_name = "STB (NteScalping)"

        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=20))

        # ✅ HTF DATA
        self.daily_data = defaultdict(lambda: {
            "close": deque(maxlen=130),
            "volume": deque(maxlen=10)
        })

        self.signal_history = {}
        self.last_direction = {}
        self.SIGNAL_COOLDOWN = 900

        self.day_open = {}

        self.candidates = []
        self.last_rank_sent = 0

    # ==============================
    # ✅ DAILY UPDATE
    # ==============================
    def update_daily(self, symbol, close, volume):
        self.daily_data[symbol]["close"].append(close)
        self.daily_data[symbol]["volume"].append(volume)

    # ==============================
    # ✅ HTF FILTER (IMAGE LOGIC)
    # ==============================
    def passes_htf_filter(self, symbol):

        data = self.daily_data[symbol]
        closes = list(data["close"])
        volumes = list(data["volume"])

        if len(closes) < 125 or len(volumes) < 5:
            return False

        recent_5_high = max(closes[-5:])
        old_120_high = max(closes[:-6])

        if recent_5_high <= old_120_high * 1.05:
            return False

        vol_sma = sum(volumes[-5:]) / 5
        if volumes[-1] <= vol_sma:
            return False

        if closes[-1] <= closes[-2]:
            return False

        return True

    # ==============================
    # ✅ CONFIDENCE
    # ==============================
    def calculate_confidence(self, score, day_change, momentum):
        confidence = 50
        confidence += score * 1.5
        confidence += min(abs(day_change) * 2, 10)
        confidence += min(abs(momentum) * 3, 10)
        return min(int(confidence), 100)

    # ==============================
    # ✅ TREND LABEL
    # ==============================
    def get_trend_label(self, prices):
        move = abs(prices[-1] - prices[-15])
        strength = move / prices[-1]

        if strength > 0.004:
            return "STRONG"
        return "MEDIUM"

    # ==============================
    # ✅ RISK LEVEL
    # ==============================
    def calculate_risk_level(self, price, sl, confidence, trend):
        risk_pct = abs(price - sl) / price

        if risk_pct < 0.004:
            risk = "LOW"
        elif risk_pct < 0.008:
            risk = "MEDIUM"
        else:
            risk = "HIGH"

        if confidence >= 85 and trend == "STRONG":
            risk = "LOW"
        elif confidence < 65:
            risk = "HIGH"

        return risk

    # ==============================
    # ✅ SUPPORT FUNCTIONS
    # ==============================
    def vwap_trend(self, price, vwap, direction):
        return price > vwap if direction == "BUY" else price < vwap

    def is_volume_increasing(self, symbol):
        vols = list(self.volume_history[symbol])
        return len(vols) >= 3 and vols[-1] > vols[-2] > vols[-3]

    def confirm_candle(self, prices, direction):
        return prices[-1] > prices[-2] > prices[-3] if direction == "BUY" else prices[-1] < prices[-2] < prices[-3]

    def is_pullback(self, prices, direction):
        return prices[-5] > prices[-3] and prices[-1] > prices[-2] if direction == "BUY" else prices[-5] < prices[-3] and prices[-1] < prices[-2]

    def is_breakout(self, prices, direction):
        prev_high = max(prices[-11:-2])
        prev_low = min(prices[-11:-2])
        current = prices[-1]
        threshold = current * 0.0008

        if direction == "BUY":
            return current > prev_high and (current - prev_high) > threshold
        else:
            return current < prev_low and (prev_low - current) > threshold

    def is_strong_trend(self, prices, direction):
        move = prices[-1] - prices[-15]
        threshold = prices[-1] * 0.0025
        return move > threshold if direction == "BUY" else move < -threshold

    def is_sideways(self, prices):
        high = max(prices[-10:])
        low = min(prices[-10:])
        return (high - low) / prices[-1] < 0.0035

    def is_liquidity_trap(self, prices, direction):
        spike = abs(prices[-2] - prices[-4])
        if spike < prices[-1] * 0.002:
            return False
        return prices[-1] < prices[-2] if direction == "BUY" else prices[-1] > prices[-2]

    def get_trade_levels(self, price, direction, prices):
        recent = prices[-10:]
        if direction == "BUY":
            sl = min(recent)
            risk = max(price - sl, price * 0.003)
            target = price + (risk * 2)
        else:
            sl = max(recent)
            risk = max(sl - price, price * 0.003)
            target = price - (risk * 2)

        return round(sl, 2), round(target, 2)

    def calculate_score(self, price, vwap, day_change, momentum):
        score = 0
        score += min(abs(day_change) * 4, 15)
        if abs(momentum) > 0.3:
            score += min(abs(momentum) * 4, 8)
        score += 8 if price > vwap else 4
        return int(score)

    def get_day_change(self, symbol, price):
        if symbol not in self.day_open:
            self.day_open[symbol] = price
        return ((price - self.day_open[symbol]) / self.day_open[symbol]) * 100

    # ==============================
    # ✅ MAIN ENGINE
    # ==============================
    def update(self, symbol, price, volume):

        if not symbol or volume < 8000:
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(self.price_history[symbol])
        if len(prices) < 20:
            return

        # ✅ HTF FILTER
        if not self.passes_htf_filter(symbol):
            return

        vwap = sum(prices) / len(prices)

        m1 = prices[-1] - prices[-3]
        m5 = prices[-1] - prices[-10]

        direction = "BUY" if m1 > 0 else "SELL"

        if not self.vwap_trend(price, vwap, direction):
            return
        if self.is_sideways(prices):
            return
        if not self.is_strong_trend(prices, direction):
            return
        if self.is_liquidity_trap(prices, direction):
            return
        if not self.is_pullback(prices, direction):
            return
        if not self.is_breakout(prices, direction):
            return
        if not self.is_volume_increasing(symbol):
            return

        day_change = self.get_day_change(symbol, price)
        score = self.calculate_score(price, vwap, day_change, m5)

        sl, tgt = self.get_trade_levels(price, direction, prices)

        confidence = self.calculate_confidence(score, day_change, m5)
        trend = self.get_trend_label(prices)
        risk = self.calculate_risk_level(price, sl, confidence, trend)

        # ✅ INSTANT TRADE
        if score >= 22:
            message = f"""
🔥 INSTANT TRADE 🔥
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
            send_alert(message, symbol, direction, price, sl, tgt, self.strategy_name)
            return

        # ✅ TOP TRADE
        if score >= 15:
            message = f"""
🔥 TOP TRADE 🔥
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
            send_alert(message, symbol, direction, price, sl, tgt, self.strategy_name)
``