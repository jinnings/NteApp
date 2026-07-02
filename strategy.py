from collections import defaultdict, deque
from datetime import datetime

from alerts import send_alert, get_ist_time


class MultiSignalStrategy:

    def __init__(self):

        self.strategy_name = "STB (NteScalping PROFIT)"

        self.price_history = defaultdict(
            lambda: deque(maxlen=100)
        )

        self.volume_history = defaultdict(
            lambda: deque(maxlen=20)
        )

        self.day_open = {}

        self.market_trend = "SIDEWAYS"
        self.market_breadth = 0

        self.last_signal = {}

    # =====================================================
    # MARKET SETTINGS
    # =====================================================

    def set_market_trend(self, trend):
        self.market_trend = trend

    def set_market_breadth(self, breadth):
        self.market_breadth = breadth

    # =====================================================
    # OPEN/CLOSE TIME FILTER
    # =====================================================

    def market_time_filter(self):

        now = datetime.now()

        minute_of_day = now.hour * 60 + now.minute

        market_open = 9 * 60 + 15
        market_close = 15 * 60 + 30

        # First 5 mins
        if minute_of_day < market_open + 5:
            return False

        # Last 15 mins
        if minute_of_day > market_close - 15:
            return False

        return True

    # =====================================================
    # DAY CHANGE
    # =====================================================

    def get_day_change(self, symbol, price):

        if symbol not in self.day_open:
            self.day_open[symbol] = price

        return (
            (price - self.day_open[symbol])
            / self.day_open[symbol]
        ) * 100

    # =====================================================
    # VWAP
    # =====================================================

    def calculate_vwap(self, prices, volumes):

        total_pv = sum(
            p * v for p, v in zip(prices, volumes)
        )

        total_vol = sum(volumes)

        if total_vol == 0:
            return prices[-1]

        return total_pv / total_vol

    # =====================================================
    # EMA 20
    # =====================================================

    def calculate_ema(self, prices, period=20):

        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)

        ema = sum(prices[:period]) / period

        for price in prices[period:]:
            ema = ((price - ema) * multiplier) + ema

        return ema

    # =====================================================
    # RSI 14
    # =====================================================

    def calculate_rsi(self, prices, period=14):

        if len(prices) < period + 1:
            return 50

        gains = []
        losses = []

        for i in range(1, period + 1):

            change = prices[-i] - prices[-i - 1]

            if change > 0:
                gains.append(change)
            else:
                losses.append(abs(change))

        avg_gain = sum(gains) / period if gains else 0.0001
        avg_loss = sum(losses) / period if losses else 0.0001

        rs = avg_gain / avg_loss

        return 100 - (100 / (1 + rs))

    # =====================================================
    # ATR
    # =====================================================

    def calculate_atr(self, prices, period=14):

        if len(prices) < period + 1:
            return None

        trs = []

        for i in range(-period, -1):

            tr = abs(
                prices[i] - prices[i - 1]
            )

            trs.append(tr)

        return sum(trs) / len(trs)

    # =====================================================
    # TREND
    # =====================================================

    def get_trend(self, prices):

        if len(prices) < 10:
            return "MEDIUM"

        move = (
            prices[-1] - prices[-10]
        ) / prices[-10]

        if abs(move) > 0.008:
            return "STRONG"

        if abs(move) > 0.004:
            return "MEDIUM"

        return "WEAK"

    # =====================================================
    # VOLUME SPIKE
    # =====================================================

    def has_volume_spike(self, volumes):

        if len(volumes) < 6:
            return False

        avg_volume = sum(
            volumes[-6:-1]
        ) / 5

        return volumes[-1] > avg_volume * 1.3

    # =====================================================
    # SCORE
    # =====================================================

    def calculate_score(
        self,
        price,
        vwap,
        ema20,
        rsi,
        day_change,
        momentum,
        direction
    ):

        score = 0

        # Day strength
        score += min(
            abs(day_change) * 3,
            12
        )

        # Momentum
        score += min(
            abs(momentum) * 250,
            12
        )

        # VWAP
        if direction == "BUY":
            score += 10 if price > vwap else 0
        else:
            score += 10 if price < vwap else 0

        # EMA
        if direction == "BUY":
            score += 8 if price > ema20 else 0
        else:
            score += 8 if price < ema20 else 0

        # RSI
        if direction == "BUY" and rsi > 60:
            score += 5

        if direction == "SELL" and rsi < 40:
            score += 5

        return int(score)

    # =====================================================
    # CONFIDENCE
    # =====================================================

    def calculate_confidence(
        self,
        score,
        day_change,
        momentum
    ):

        confidence = 50

        confidence += score * 1.2

        confidence += min(
            abs(day_change) * 2,
            10
        )

        confidence += min(
            abs(momentum) * 200,
            10
        )

        return min(
            int(confidence),
            100
        )

    # =====================================================
    # MARKET BIAS
    # =====================================================

    def market_bias(self, direction):

        if self.market_trend == "SIDEWAYS":
            return "FREE"

        if (
            self.market_trend == "UP"
            and direction == "BUY"
        ):
            return "STRONG"

        if (
            self.market_trend == "DOWN"
            and direction == "SELL"
        ):
            return "STRONG"

        return "WEAK"

    # =====================================================
    # ATR STOPLOSS
    # =====================================================

    def get_trade_levels(
        self,
        price,
        direction,
        prices
    ):

        atr = self.calculate_atr(prices)

        if atr is None:
            atr = price * 0.003

        if direction == "BUY":

            sl = price - (atr * 1.5)
            target = price + (atr * 3)

        else:

            sl = price + (atr * 1.5)
            target = price - (atr * 3)

        return round(sl, 2), round(target, 2)

    # =====================================================
    # RISK
    # =====================================================

    def get_risk(
        self,
        price,
        sl
    ):

        pct = abs(price - sl) / price

        if pct < 0.005:
            return "LOW"

        if pct < 0.01:
            return "MEDIUM"

        return "HIGH"

    # =====================================================
    # MAIN ENGINE
    # =====================================================

    def update(
        self,
        symbol,
        price,
        volume
    ):

        if not self.market_time_filter():
            return

        if volume < 1500:
            return

        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)

        prices = list(
            self.price_history[symbol]
        )

        volumes = list(
            self.volume_history[symbol]
        )

        if len(prices) < 20:
            return

        # ------------------------
        # CALCULATIONS
        # ------------------------

        vwap = self.calculate_vwap(
            prices,
            volumes
        )

        ema20 = self.calculate_ema(
            prices,
            20
        )

        rsi = self.calculate_rsi(
            prices,
            14
        )

        if ema20 is None:
            return

        m1 = (
            prices[-1] - prices[-3]
        ) / prices[-3]

        m5 = (
            prices[-1] - prices[-6]
        ) / prices[-6]

        # ------------------------
        # DIRECTION
        # ------------------------

        if m1 > 0:
            direction = "BUY"

        elif m1 < 0:
            direction = "SELL"

        else:
            return

        # ------------------------
        # MARKET TREND FILTER
        # ------------------------

        if (
            self.market_trend == "UP"
            and direction == "SELL"
        ):
            return

        if (
            self.market_trend == "DOWN"
            and direction == "BUY"
        ):
            return

        # ------------------------
        # MARKET BREADTH
        # ------------------------

        if (
            direction == "BUY"
            and self.market_breadth < 0
        ):
            return

        if (
            direction == "SELL"
            and self.market_breadth > 0
        ):
            return

        # ------------------------
        # VWAP FILTER
        # ------------------------

        if direction == "BUY" and price < vwap:
            return

        if direction == "SELL" and price > vwap:
            return

        # ------------------------
        # EMA FILTER
        # ------------------------

        if direction == "BUY" and price < ema20:
            return

        if direction == "SELL" and price > ema20:
            return

        # ------------------------
        # RSI FILTER
        # ------------------------

        if direction == "BUY" and rsi < 55:
            return

        if direction == "SELL" and rsi > 45:
            return

        # ------------------------
        # VOLUME FILTER
        # ------------------------

        if not self.has_volume_spike(volumes):
            return

        day_change = self.get_day_change(
            symbol,
            price
        )

        score = self.calculate_score(
            price,
            vwap,
            ema20,
            rsi,
            day_change,
            m5,
            direction
        )

        bias = self.market_bias(
            direction
        )

        if bias == "STRONG":
            score += 3

        elif bias == "FREE":
            score += 1

        if score < 20:
            return

        confidence = self.calculate_confidence(
            score,
            day_change,
            m5
        )

        if confidence < 75:
            return

        trend = self.get_trend(
            prices
        )

        if trend == "WEAK":
            return

        sl, tgt = self.get_trade_levels(
            price,
            direction,
            prices
        )

        risk = self.get_risk(
            price,
            sl
        )

        # ------------------------
        # DUPLICATE FILTER
        # ------------------------

        key = f"{symbol}_{direction}"

        if key in self.last_signal:

            previous = self.last_signal[key]

            move = abs(
                price - previous
            ) / previous

            if move < 0.002:
                return

        self.last_signal[key] = price

        # ------------------------
        # TRADE TYPE
        # ------------------------

        if score >= 30 and risk == "LOW":
            trade_type = "🔥 PREMIUM"

        elif score >= 24:
            trade_type = "🔥 STRONG"

        else:
            trade_type = "⚡ NORMAL"

        # ------------------------
        # MESSAGE
        # ------------------------

        message = f"""
{trade_type}

Strategy: {self.strategy_name}

{symbol} → {direction}
Time: {get_ist_time()}

Entry: ₹{round(price,2)}
SL: ₹{round(sl,2)}
Target: ₹{round(tgt,2)}

⭐ Score: {score}
📊 Confidence: {confidence}%
📈 Trend: {trend}
📉 RSI: {round(rsi,1)}
📍 VWAP: {round(vwap,2)}
📊 EMA20: {round(ema20,2)}
⚠️ Risk: {risk}
"""

        print(
            f"{symbol}: ✅ {direction} "
            f"Score={score} "
            f"Confidence={confidence}%"
        )

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