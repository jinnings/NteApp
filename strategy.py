from collections import defaultdict, deque
import threading
import time
from alerts import send_alert


# =========================
# ✅ MULTI SIGNAL STRATEGY
# =========================

class MultiSignalStrategy:

    def __init__(self):

        self.price_history  = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=100))

        self.last_direction = {}

        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 1800  # 30 min — increased from 15 min

        self.day_open = {}

        self.candidates     = []
        self.last_rank_sent = 0

        self._lock = threading.Lock()

        self.MAX_CANDIDATE_AGE = 30

        # EMA state — stores last computed EMA per symbol
        self.ema_state = {}

    def already_sent_recent(self, symbol, direction):

        key = f"{symbol}_{direction}"

        return (
            key in self.signal_history
            and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN
        )

    def get_day_change(self, symbol, price):

        if symbol not in self.day_open:
            self.day_open[symbol] = price

        open_price = self.day_open[symbol]

        if open_price == 0:
            return 0.0

        return ((price - open_price) / open_price) * 100

    def is_volume_increasing(self, symbol):

        vols = list(self.volume_history[symbol])

        return (
            len(vols) >= 3
            and vols[-1] > vols[-2] > vols[-3]
        )

    def confirm_candle(self, prices, direction):

        if len(prices) < 5:
            return False

        if direction == "BUY":
            return prices[-1] > prices[-2] > prices[-3]

        return prices[-1] < prices[-2] < prices[-3]

    def is_breakout(self, prices, direction):

        if len(prices) < 10:
            return False

        if direction == "BUY":
            return prices[-1] > max(prices[-10:-1])

        return prices[-1] < min(prices[-10:-1])

    def is_pullback(self, prices, direction):

        if len(prices) < 6:
            return False

        if direction == "BUY":
            return (
                prices[-5] > prices[-3]
                and prices[-1] > prices[-2]
            )

        return (
            prices[-5] < prices[-3]
            and prices[-1] < prices[-2]
        )

    def compute_ema(self, symbol, price):
        """
        Incremental EMA — O(1) per tick.
        EMA = price * k + prev_ema * (1 - k)
        k = 2 / (period + 1)
        Seeds all EMAs with first price on first call.
        Returns (ema5, ema10, ema20).
        """

        k5  = 2 / (5  + 1)   # 0.3333
        k10 = 2 / (10 + 1)   # 0.1818
        k20 = 2 / (20 + 1)   # 0.0952

        if symbol not in self.ema_state:
            self.ema_state[symbol] = {
                "ema5":  price,
                "ema10": price,
                "ema20": price,
            }
        else:
            prev = self.ema_state[symbol]
            self.ema_state[symbol] = {
                "ema5":  price * k5  + prev["ema5"]  * (1 - k5),
                "ema10": price * k10 + prev["ema10"] * (1 - k10),
                "ema20": price * k20 + prev["ema20"] * (1 - k20),
            }

        s = self.ema_state[symbol]
        return s["ema5"], s["ema10"], s["ema20"]

    def ema_direction(self, ema5, ema10, ema20, direction):
        """
        Full EMA stack alignment.
        BUY  → EMA5 > EMA10 > EMA20  (bullish stack)
        SELL → EMA5 < EMA10 < EMA20  (bearish stack)
        """

        if direction == "BUY":
            return ema5 > ema10 > ema20

        return ema5 < ema10 < ema20

    def ema_crossover(self, ema5, ema10, direction):
        """
        EMA5 / EMA10 crossover gate.
        BUY  → EMA5 > EMA10  (golden cross)
        SELL → EMA5 < EMA10  (death cross)
        """

        if direction == "BUY":
            return ema5 > ema10

        return ema5 < ema10

    def vwap_trend(self, price, vwap, direction):

        if direction == "BUY":
            return price > vwap

        return price < vwap

    def trend_alignment(self, prices, direction):

        if len(prices) < 20:
            return False

        sma10 = sum(prices[-10:]) / 10
        sma20 = sum(prices[-20:]) / 20

        if direction == "BUY":
            return sma10 > sma20

        return sma10 < sma20

    def calculate_score(
        self,
        symbol,
        direction,
        price,
        vwap,
        day_change,
        m_fast,
        m_slow,
        acceleration,
        ema5,
        ema10,
        ema20
    ):

        score = 0

        # ── 1. Day change — max 15 pts ─────────────────────────────────
        score += min(abs(day_change) * 4, 15)

        # ── 2. ROC momentum — max 8 pts ────────────────────────────────
        if abs(m_fast) > 0.1:
            score += min(abs(m_fast) * 3, 4)

        if abs(m_slow) > 0.2:
            score += min(abs(m_slow) * 2, 4)

        # ── 3. Momentum Acceleration — max 6 pts ───────────────────────
        # Positive on BUY  = momentum speeding up
        # Negative on SELL = selling pressure increasing
        if direction == "BUY" and acceleration > 0:
            score += min(acceleration * 3, 6)
        elif direction == "SELL" and acceleration < 0:
            score += min(abs(acceleration) * 3, 6)

        # ── 4. VWAP distance bonus — max 12 pts ────────────────────────
        if vwap > 0:
            vwap_distance_pct = ((price - vwap) / vwap) * 100

            if direction == "BUY":
                if vwap_distance_pct > 0:
                    score += 8 + min(vwap_distance_pct * 2, 4)
                else:
                    score += 4
            else:
                if vwap_distance_pct < 0:
                    score += 8 + min(abs(vwap_distance_pct) * 2, 4)
                else:
                    score += 4
        else:
            score += 4

        # ── 5. EMA stack alignment — max 5 pts ─────────────────────────
        # Full stack (EMA5 > EMA10 > EMA20) = 5 pts
        # Partial crossover only            = 2 pts
        if self.ema_direction(ema5, ema10, ema20, direction):
            score += 5
        elif self.ema_crossover(ema5, ema10, direction):
            score += 2

        # ── 6. SMA trend alignment — max 3 pts ─────────────────────────
        prices = list(self.price_history[symbol])

        if self.trend_alignment(prices, direction):
            score += 3

        return int(score)

    def reset_daily(self):
        """Call this at market open every day."""

        with self._lock:
            self.day_open.clear()
            self.signal_history.clear()
            self.last_direction.clear()
            self.candidates.clear()
            self.ema_state.clear()
            self.last_rank_sent = 0

    def update(self, symbol, price, volume):

        if (
            not symbol
            or price is None
            or volume is None
            or volume < 8000
        ):
            return

        with self._lock:

            self.price_history[symbol].append(price)
            self.volume_history[symbol].append(volume)

            prices  = list(self.price_history[symbol])
            volumes = list(self.volume_history[symbol])

            if len(prices) < 20:
                return

            # VWAP — aligned length
            length         = min(len(prices), len(volumes))
            recent_prices  = prices[-length:]
            recent_volumes = volumes[-length:]

            vol_sum = sum(recent_volumes)
            if vol_sum == 0:
                return

            vwap = sum(
                p * v for p, v in zip(recent_prices, recent_volumes)
            ) / vol_sum

            # ROC — Percentage Rate of Change
            base_fast = prices[-3]
            base_slow = prices[-10]

            if base_fast == 0 or base_slow == 0:
                return

            m_fast = ((prices[-1] - base_fast) / base_fast) * 100
            m_slow = ((prices[-1] - base_slow) / base_slow) * 100

            if m_fast == 0 or m_slow == 0:
                return

            # Momentum Acceleration
            acceleration = m_fast - m_slow

            # EMA5 / EMA10 / EMA20
            ema5, ema10, ema20 = self.compute_ema(symbol, price)

            dir1 = "BUY" if m_fast > 0 else "SELL"
            dir5 = "BUY" if m_slow > 0 else "SELL"

            if dir1 != dir5:
                return

            direction = dir1

            if self.already_sent_recent(symbol, direction):
                return

            prev_dir = self.last_direction.get(symbol)
            if prev_dir and prev_dir != direction:
                return

            day_change = self.get_day_change(symbol, price)
            if abs(day_change) < 0.1:
                return

            score = self.calculate_score(
                symbol, direction, price, vwap,
                day_change, m_fast, m_slow, acceleration,
                ema5, ema10, ema20
            )

            # ── Shared indicator flags ────────────────────────────────
            vol_inc       = self.is_volume_increasing(symbol)
            ema_full      = (ema5 > ema10 > ema20)  # full bullish stack
            ema_partial   = (ema5 > ema10)           # partial crossover
            ema_neutral   = (ema5 >= ema10)          # flat or just touching
            above_vwap    = (price > vwap)
            at_vwap       = (price >= vwap)          # at or above

            # volume neutral = last bar not lower than previous
            vols = list(self.volume_history[symbol])
            vol_neutral = (len(vols) >= 2 and vols[-1] >= vols[-2])

            # ════════════════════════════════════════════════════════════
            # TIER 1 — HIGH CONFIDENCE
            # ────────────────────────────────────────────────────────────
            # ROC Fast     > 0.50%
            # ROC Slow     > 0.30%
            # Acceleration > 0.20%
            # EMA5 > EMA10 > EMA20   full bullish stack
            # Price > VWAP
            # Volume Increasing      3 rising bars
            # ════════════════════════════════════════════════════════════
            is_high = (
                m_fast       > 0.50
                and m_slow       > 0.30
                and acceleration > 0.20
                and ema_full
                and above_vwap
                and vol_inc
            )

            # ════════════════════════════════════════════════════════════
            # TIER 2 — MEDIUM CONFIDENCE
            # ────────────────────────────────────────────────────────────
            # ROC Fast     > 0.20%
            # ROC Slow     > 0.10%
            # Acceleration > 0.05%
            # EMA5 > EMA10           partial crossover
            # Price > VWAP
            # Volume Increasing
            # ════════════════════════════════════════════════════════════
            is_medium = (
                not is_high
                and m_fast       > 0.20
                and m_slow       > 0.10
                and acceleration > 0.05
                and ema_partial
                and above_vwap
                and vol_inc
            )

            # ════════════════════════════════════════════════════════════
            # TIER 3 — LOW CONFIDENCE
            # ────────────────────────────────────────────────────────────
            # ROC Fast     > 0.05%
            # ROC Slow     > 0%
            # Acceleration > 0
            # EMA5 >= EMA10          flat or just crossing
            # Price >= VWAP          at or above fair value
            # Volume Neutral or Slightly Increasing
            # ════════════════════════════════════════════════════════════
            is_low = (
                not is_high
                and not is_medium
                and m_fast       > 0.05
                and m_slow       > 0.0
                and acceleration > 0.0
                and ema_neutral
                and at_vwap
                and vol_neutral
            )

            # No tier matched — drop
            if not is_high and not is_medium and not is_low:
                return

            # ── Build message based on tier ──────────────────────────
            if is_high:
                header    = "🚀 HIGH CONFIDENCE TRADE 🚀"
                ema_line  = "📊 EMA5 > EMA10 > EMA20  ✅ (Full Stack)"
                vwap_line = f"💧 Price > VWAP ({round(vwap, 2)})  ✅"
                vol_line  = "📦 Volume Increasing  ✅"

            elif is_medium:
                header    = "🟡 MEDIUM CONFIDENCE TRADE 🟡"
                ema_line  = "📊 EMA5 > EMA10  ✅ (Partial Crossover)"
                vwap_line = f"💧 Price > VWAP ({round(vwap, 2)})  ✅"
                vol_line  = "📦 Volume Increasing  ✅"

            else:
                header    = "🔵 LOW CONFIDENCE TRADE 🔵"
                ema_line  = "📊 EMA5 >= EMA10  ⚠️ (Neutral / Early Cross)"
                vwap_line = f"💧 Price >= VWAP ({round(vwap, 2)})  ⚠️"
                vol_line  = "📦 Volume Neutral / Slight Increase  ⚠️"

            message = (
                f"\n{header}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{symbol} → {direction}\n"
                f"₹{round(price, 2)}\n"
                f"⭐ Score        : {score}\n"
                f"📈 ROC Fast     : {round(m_fast, 3)}%\n"
                f"📈 ROC Slow     : {round(m_slow, 3)}%\n"
                f"⚡ Acceleration : {round(acceleration, 3)}%\n"
                f"{ema_line}\n"
                f"📊 EMA5  : {round(ema5, 2)}\n"
                f"📊 EMA10 : {round(ema10, 2)}\n"
                f"📊 EMA20 : {round(ema20, 2)}\n"
                f"{vwap_line}\n"
                f"{vol_line}\n"
                f"📅 Day Change : {round(day_change, 2)}%\n"
            )

            try:
                send_alert(message)
            finally:
                self.signal_history[f"{symbol}_{direction}"] = time.time()
                self.last_direction[symbol] = direction

    def process_top_signals(self):

        if time.time() - self.last_rank_sent < 60:
            return

        with self._lock:

            if not self.candidates:
                return

            now = time.time()

            fresh = [
                c for c in self.candidates
                if now - c["timestamp"] < self.MAX_CANDIDATE_AGE
            ]

            if not fresh:
                self.candidates.clear()
                self.last_rank_sent = now
                return

            top = sorted(
                fresh,
                key=lambda x: x["score"],
                reverse=True
            )[:3]

            for t in top:

                symbol    = t["symbol"]
                direction = t["direction"]
                price     = t["price"]
                score     = t["score"]

                if self.already_sent_recent(symbol, direction):
                    continue

                message = (
                    f"\n🔥 TOP TRADE 🔥\n"
                    f"{symbol} → {direction}\n"
                    f"₹{round(price, 2)}\n"
                    f"⭐ Score: {score}\n"
                    f"(Queued signal — price may have moved)\n"
                )

                try:
                    send_alert(message)
                finally:
                    self.signal_history[f"{symbol}_{direction}"] = now
                    self.last_direction[symbol] = direction

            self.candidates.clear()
            self.last_rank_sent = now


# =========================
# ✅ PULLBACK STRATEGY
# =========================

class PullbackStrategy:

    def __init__(self):

        self.price_history  = defaultdict(lambda: deque(maxlen=50))
        self.volume_history = defaultdict(lambda: deque(maxlen=50))

        self.day_open = {}
        self.day_high = {}

        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 2700  # 45 min — increased from 30 min

        self._lock = threading.Lock()

    def already_sent_recent(self, symbol):

        return (
            symbol in self.signal_history
            and time.time() - self.signal_history[symbol] < self.SIGNAL_COOLDOWN
        )

    def get_day_change(self, symbol, price):

        if symbol not in self.day_open:
            self.day_open[symbol] = price

        open_price = self.day_open[symbol]

        if open_price == 0:
            return 0.0

        return ((price - open_price) / open_price) * 100

    def volume_increasing(self, symbol):

        vols = list(self.volume_history[symbol])

        if len(vols) < 3:
            return False

        return vols[-1] > vols[-2] > vols[-3]

    def volume_spike(self, symbol):

        vols = list(self.volume_history[symbol])

        if len(vols) < 6:
            return False

        avg_vol = sum(vols[-6:-1]) / 5

        # Raised from 1.5x to 2.0x — only genuine volume surges
        return vols[-1] > avg_vol * 2.0

    def strong_buying(self, prices):

        if len(prices) < 6:
            return False

        if prices[-6] == 0:
            return False

        move = ((prices[-1] - prices[-6]) / prices[-6]) * 100

        return move > 1

    def bullish_candle(self, prices):

        if len(prices) < 2:
            return False

        if prices[-2] == 0:
            return False

        candle_move = ((prices[-1] - prices[-2]) / prices[-2]) * 100

        return candle_move > 0.5

    def break_previous_high(self, prices):

        if len(prices) < 2:
            return False

        return prices[-1] > prices[-2]

    def break_resistance(self, prices):

        if len(prices) < 20:
            return False

        resistance = max(prices[-20:-1])

        return prices[-1] > resistance

    def pullback_recovery(self, prices):

        if len(prices) < 10:
            return False

        slice_high = prices[-10:-4]
        slice_low  = prices[-4:-1]

        if not slice_high or not slice_low:
            return False

        swing_high   = max(slice_high)
        pullback_low = min(slice_low)

        if swing_high == 0:
            return False

        retracement = ((swing_high - pullback_low) / swing_high) * 100

        if retracement > 10:
            return False

        return prices[-1] > prices[-2]

    def near_day_high(self, symbol, price):

        day_high = self.day_high.get(symbol, price)

        return price >= day_high * 0.97

    def reset_daily(self):
        """Call this at market open every day."""

        with self._lock:
            self.day_open.clear()
            self.day_high.clear()
            self.signal_history.clear()

    def update(self, symbol, price, volume):

        if (
            not symbol
            or price is None
            or volume is None
        ):
            return

        with self._lock:

            self.price_history[symbol].append(price)
            self.volume_history[symbol].append(volume)

            if symbol not in self.day_open:
                self.day_open[symbol] = price

            if symbol not in self.day_high:
                self.day_high[symbol] = price
            else:
                self.day_high[symbol] = max(self.day_high[symbol], price)

            prices = list(self.price_history[symbol])

            if len(prices) < 20:
                return

            day_change = self.get_day_change(symbol, price)

            # Raised from 4% to 5% — filters weaker moves
            if day_change < 5:
                return

            if self.already_sent_recent(symbol):
                return

            if not self.volume_increasing(symbol):
                return

            if not self.volume_spike(symbol):
                return

            if not self.strong_buying(prices):
                return

            if not self.bullish_candle(prices):
                return

            if not self.break_previous_high(prices):
                return

            if not self.pullback_recovery(prices):
                return

            breakout  = self.break_resistance(prices)
            near_high = self.near_day_high(symbol, price)

            if not breakout and not near_high:
                return

            signal_type = "BREAKOUT" if breakout else "PULLBACK READY"

            message = (
                f"\n🔥 PULLBACK STRATEGY 🔥\n\n"
                f"{symbol} → BUY\n\n"
                f"₹{round(price, 2)}\n\n"
                f"Type       : {signal_type}\n"
                f"Day Change : {round(day_change, 2)}%\n\n"
                f"✅ Strong Buying\n"
                f"✅ Volume Increasing\n"
                f"✅ Volume Spike\n"
                f"✅ Pullback Recovery\n"
                f"✅ Bullish Candle\n"
                f"✅ Previous High Break\n"
                f"✅ Near Day High / Resistance Break\n"
            )

            try:
                send_alert(message)
            finally:
                self.signal_history[symbol] = time.time()


# =========================
# ✅ JINNING EFFECT STRATEGY
# =========================

class JinningEffectStrategy:

    def __init__(self):

        self.close_history  = defaultdict(lambda: deque(maxlen=150))
        self.volume_history = defaultdict(lambda: deque(maxlen=150))

        self.signal_history  = {}
        self.SIGNAL_COOLDOWN = 3600  # 60 min — increased from 30 min

        self._lock = threading.Lock()

    def already_sent_recent(self, symbol):

        return (
            symbol in self.signal_history
            and time.time() - self.signal_history[symbol] < self.SIGNAL_COOLDOWN
        )

    def reset_daily(self):
        """Call this at market open every day."""

        with self._lock:
            self.signal_history.clear()

    def update_daily(self, symbol, close_price, volume):

        if not symbol or close_price is None or volume is None:
            return

        with self._lock:

            self.close_history[symbol].append(close_price)
            self.volume_history[symbol].append(volume)

            closes  = list(self.close_history[symbol])
            volumes = list(self.volume_history[symbol])

            if len(closes) < 130:
                return

            # CONDITION 1 — 5-day high > 120-day high + 5%
            recent_5_max = max(closes[-5:])
            past_120_max = max(closes[-126:-6])

            if past_120_max == 0:
                return

            if recent_5_max <= past_120_max * 1.05:
                return

            # CONDITION 2 — current volume > 5-day average
            if len(volumes) < 6:
                return

            avg_5_volume   = sum(volumes[-6:-1]) / 5
            current_volume = volumes[-1]

            if avg_5_volume == 0:
                return

            if current_volume <= avg_5_volume:
                return

            # CONDITION 3 — today closed higher than yesterday
            if closes[-1] <= closes[-2]:
                return

            if self.already_sent_recent(symbol):
                return

            message = (
                f"\n🔥 JINNING EFFECT 🔥\n"
                f"{symbol} → BUY\n"
                f"₹{round(close_price, 2)}\n\n"
                f"✅ 5-Day Breakout > 120D + 5%\n"
                f"✅ Volume > 5D Avg\n"
                f"✅ Strong Closing\n"
            )

            try:
                send_alert(message)
            finally:
                self.signal_history[symbol] = time.time()