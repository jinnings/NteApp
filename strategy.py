from collections import defaultdict, deque
import threading
import time
from alerts import send_alert


# =========================
# ✅ MULTI SIGNAL STRATEGY
# =========================

class MultiSignalStrategy:

    def __init__(self):

        # FIX #2 — matched maxlen so price[i] aligns with volume[i]
        self.price_history  = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=100))

        self.last_direction = {}

        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 900  # 15 min

        self.day_open = {}

        self.candidates     = []
        self.last_rank_sent = 0

        # FIX #15 — thread safety lock
        self._lock = threading.Lock()

        # FIX #11 — max age for candidates (seconds)
        self.MAX_CANDIDATE_AGE = 30

        # EMA state — stores last computed EMA per symbol
        # key: symbol  value: {"ema5": float, "ema10": float, "ema20": float}
        self.ema_state = {}

        # Debug mode — set True to print why each signal is dropped
        self.debug = True

    # ------------------------------------------------------------------

    def already_sent_recent(self, symbol, direction):

        key = f"{symbol}_{direction}"

        return (
            key in self.signal_history
            and time.time() - self.signal_history[key] < self.SIGNAL_COOLDOWN
        )

    # ------------------------------------------------------------------

    def get_day_change(self, symbol, price):

        if symbol not in self.day_open:
            self.day_open[symbol] = price

        open_price = self.day_open[symbol]

        # FIX #3 — division by zero guard
        if open_price == 0:
            return 0.0

        return ((price - open_price) / open_price) * 100

    # ------------------------------------------------------------------

    def is_volume_increasing(self, symbol):

        vols = list(self.volume_history[symbol])

        return (
            len(vols) >= 3
            and vols[-1] > vols[-2] > vols[-3]
        )

    # ------------------------------------------------------------------

    def confirm_candle(self, prices, direction):

        if len(prices) < 5:
            return False

        if direction == "BUY":
            return prices[-1] > prices[-2] > prices[-3]

        return prices[-1] < prices[-2] < prices[-3]

    # ------------------------------------------------------------------

    def is_breakout(self, prices, direction):

        if len(prices) < 10:
            return False

        if direction == "BUY":
            return prices[-1] > max(prices[-10:-1])

        return prices[-1] < min(prices[-10:-1])

    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------

    def compute_ema(self, symbol, price):
        """
        Incremental EMA calculation — O(1) per tick.
        EMA = price * k  +  prev_ema * (1 - k)
        where k = 2 / (period + 1)

        Returns (ema5, ema10, ema20) tuple.
        On first call seeds all EMAs with current price.
        """

        k5  = 2 / (5  + 1)   # 0.3333
        k10 = 2 / (10 + 1)   # 0.1818
        k20 = 2 / (20 + 1)   # 0.0952

        if symbol not in self.ema_state:
            # Seed: first price initialises all three EMAs
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

    # ------------------------------------------------------------------

    def ema_direction(self, ema5, ema10, ema20, direction):
        """
        EMA stack alignment check.
        BUY  → EMA5 > EMA10 > EMA20  (bullish stack)
        SELL → EMA5 < EMA10 < EMA20  (bearish stack)
        """

        if direction == "BUY":
            return ema5 > ema10 > ema20

        return ema5 < ema10 < ema20

    # ------------------------------------------------------------------

    def ema_crossover(self, ema5, ema10, direction):
        """
        EMA5 / EMA10 crossover signal.
        BUY  → EMA5 crossed above EMA10 (golden cross)
        SELL → EMA5 crossed below EMA10 (death cross)
        """

        if direction == "BUY":
            return ema5 > ema10

        return ema5 < ema10

    # ------------------------------------------------------------------

    def vwap_trend(self, price, vwap, direction):

        if direction == "BUY":
            return price > vwap

        return price < vwap

    # ------------------------------------------------------------------

    def trend_alignment(self, prices, direction):

        if len(prices) < 20:
            return False

        sma10 = sum(prices[-10:]) / 10
        sma20 = sum(prices[-20:]) / 20

        if direction == "BUY":
            return sma10 > sma20

        return sma10 < sma20

    # ------------------------------------------------------------------

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
        # m_fast: short-term % move  (e.g. 0.5% → 1.5 pts)
        # m_slow: medium-term % move (e.g. 1.0% → 2.0 pts)
        if abs(m_fast) > 0.1:
            score += min(abs(m_fast) * 3, 4)

        if abs(m_slow) > 0.2:
            score += min(abs(m_slow) * 2, 4)

        # ── 3. Momentum Acceleration — max 6 pts ───────────────────────
        # acceleration = m_fast - m_slow
        # Positive acceleration on BUY = momentum is speeding up
        # Negative acceleration on SELL = selling pressure increasing
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
        # Full stack aligned (EMA5 > EMA10 > EMA20 for BUY) = 5 pts
        # Partial (only EMA5 > EMA10 crossover)              = 2 pts
        if self.ema_direction(ema5, ema10, ema20, direction):
            score += 5
        elif self.ema_crossover(ema5, ema10, direction):
            score += 2

        # ── 6. SMA trend alignment — max 3 pts ─────────────────────────
        prices = list(self.price_history[symbol])

        if self.trend_alignment(prices, direction):
            score += 3

        return int(score)

    # ------------------------------------------------------------------

    def reset_daily(self):
        """FIX #10 — Call this at market open every day."""

        with self._lock:
            self.day_open.clear()
            self.signal_history.clear()
            self.last_direction.clear()
            self.candidates.clear()
            self.ema_state.clear()
            self.last_rank_sent = 0

    # ------------------------------------------------------------------

    def _dbg(self, symbol, reason):
        """Print drop reason when debug=True."""
        if self.debug:
            print(f"[FILTER DROP] {symbol} — {reason}")

    # ------------------------------------------------------------------

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume is None:
            return

        if volume < 8000:
            self._dbg(symbol, f"volume too low: {volume} < 8000")
            return

        with self._lock:

            self.price_history[symbol].append(price)
            self.volume_history[symbol].append(volume)

            prices  = list(self.price_history[symbol])
            volumes = list(self.volume_history[symbol])

            if len(prices) < 20:
                self._dbg(symbol, f"warming up: {len(prices)}/20 prices")
                return

            # VWAP
            length         = min(len(prices), len(volumes))
            recent_prices  = prices[-length:]
            recent_volumes = volumes[-length:]

            vol_sum = sum(recent_volumes)
            if vol_sum == 0:
                self._dbg(symbol, "vol_sum is zero")
                return

            vwap = sum(
                p * v for p, v in zip(recent_prices, recent_volumes)
            ) / vol_sum

            # ROC
            base_fast = prices[-3]
            base_slow = prices[-10]

            if base_fast == 0 or base_slow == 0:
                self._dbg(symbol, "base price is zero")
                return

            m_fast = ((prices[-1] - base_fast) / base_fast) * 100
            m_slow = ((prices[-1] - base_slow) / base_slow) * 100

            # Momentum Acceleration
            acceleration = m_fast - m_slow

            # EMA
            ema5, ema10, ema20 = self.compute_ema(symbol, price)

            # Direction
            dir1 = "BUY" if m_fast > 0 else "SELL"
            dir5 = "BUY" if m_slow > 0 else "SELL"

            if dir1 != dir5:
                self._dbg(symbol, f"direction conflict: fast={dir1} slow={dir5}")
                return

            direction = dir1

            # Cooldown
            if self.already_sent_recent(symbol, direction):
                self._dbg(symbol, "cooldown active")
                return

            # Direction flip
            prev_dir = self.last_direction.get(symbol)
            if prev_dir and prev_dir != direction:
                self._dbg(symbol, f"direction flip: was {prev_dir} now {direction}")
                return

            # Day change
            day_change = self.get_day_change(symbol, price)
            if abs(day_change) < 0.1:
                self._dbg(symbol, f"day_change too small: {round(day_change,3)}%")
                return

            score = self.calculate_score(
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
            )

            # ════════════════════════════════════════════════════════════
            # CONFIDENCE TIER DETECTION
            # ════════════════════════════════════════════════════════════
            #
            # HIGH CONFIDENCE (Blind Trade) — ALL 6 conditions must pass:
            #   ROC Fast     > 1.0%   (strong short momentum)
            #   ROC Slow     > 0.7%   (strong medium momentum)
            #   Acceleration > 0.5%   (momentum clearly speeding up)
            #   EMA5 > EMA10 > EMA20  (full bullish EMA stack)
            #   Price > VWAP          (above fair value)
            #   Volume increasing     (3 consecutive rising bars)
            #
            # MEDIUM CONFIDENCE — ALL 6 conditions must pass:
            #   ROC Fast     > 0.5%
            #   ROC Slow     > 0.3%
            #   Acceleration > 0.2%
            #   EMA5 > EMA10 > EMA20
            #   Price > VWAP
            #   Volume increasing
            #
            # ════════════════════════════════════════════════════════════

            vol_increasing   = self.is_volume_increasing(symbol)
            ema_stack_ok     = (ema5 > ema10 > ema20)
            price_above_vwap = (price > vwap)

            # Live debug print every tick
            if self.debug:
                print(
                    f"[LIVE] {symbol} | dir={direction} | "
                    f"mf={round(m_fast,3)}% ms={round(m_slow,3)}% "
                    f"acc={round(acceleration,3)}% | "
                    f"ema_ok={ema_stack_ok} pvwap={price_above_vwap} "
                    f"vol_inc={vol_increasing} | score={score}"
                )

            # HIGH CONFIDENCE
            is_high_confidence = (
                m_fast       > 1.0
                and m_slow       > 0.7
                and acceleration > 0.5
                and ema_stack_ok
                and price_above_vwap
                and vol_increasing
            )

            # MEDIUM CONFIDENCE
            is_medium_confidence = (
                m_fast       > 0.5
                and m_slow       > 0.3
                and acceleration > 0.2
                and ema_stack_ok
                and price_above_vwap
                and vol_increasing
            )

            if not is_medium_confidence:
                self._dbg(
                    symbol,
                    f"confidence failed | "
                    f"mf={round(m_fast,3)} ms={round(m_slow,3)} "
                    f"acc={round(acceleration,3)} "
                    f"ema={ema_stack_ok} vwap={price_above_vwap} "
                    f"vol={vol_increasing}"
                )
                return

            # ── Build and send alert based on tier ───────────────────
            if is_high_confidence:

                message = (
                    f"\n🚀 HIGH CONFIDENCE TRADE 🚀\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{symbol} → {direction}\n"
                    f"₹{round(price, 2)}\n"
                    f"⭐ Score        : {score}\n"
                    f"📈 ROC Fast     : {round(m_fast, 3)}%  ✅ (>1.0%)\n"
                    f"📈 ROC Slow     : {round(m_slow, 3)}%  ✅ (>0.7%)\n"
                    f"⚡ Acceleration : {round(acceleration, 3)}%  ✅ (>0.5%)\n"
                    f"📊 EMA5 > EMA10 > EMA20  ✅\n"
                    f"📊 EMA5  : {round(ema5, 2)}\n"
                    f"📊 EMA10 : {round(ema10, 2)}\n"
                    f"📊 EMA20 : {round(ema20, 2)}\n"
                    f"💧 Price > VWAP  ✅\n"
                    f"📦 Volume Increasing  ✅\n"
                )

                try:
                    send_alert(message)
                finally:
                    self.signal_history[f"{symbol}_{direction}"] = time.time()
                    self.last_direction[symbol] = direction

            else:

                # Medium confidence — queue as candidate for TOP TRADE
                message = (
                    f"\n🟡 MEDIUM CONFIDENCE TRADE 🟡\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{symbol} → {direction}\n"
                    f"₹{round(price, 2)}\n"
                    f"⭐ Score        : {score}\n"
                    f"📈 ROC Fast     : {round(m_fast, 3)}%  ✅ (>0.5%)\n"
                    f"📈 ROC Slow     : {round(m_slow, 3)}%  ✅ (>0.3%)\n"
                    f"⚡ Acceleration : {round(acceleration, 3)}%  ✅ (>0.2%)\n"
                    f"📊 EMA5 > EMA10 > EMA20  ✅\n"
                    f"📊 EMA5  : {round(ema5, 2)}\n"
                    f"📊 EMA10 : {round(ema10, 2)}\n"
                    f"📊 EMA20 : {round(ema20, 2)}\n"
                    f"💧 Price > VWAP  ✅\n"
                    f"📦 Volume Increasing  ✅\n"
                )

                try:
                    send_alert(message)
                finally:
                    self.signal_history[f"{symbol}_{direction}"] = time.time()
                    self.last_direction[symbol] = direction

    # ------------------------------------------------------------------

    def process_top_signals(self):

        if time.time() - self.last_rank_sent < 60:
            return

        with self._lock:

            if not self.candidates:
                return

            now = time.time()

            # FIX #11 — filter out stale candidates
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

                # FIX #16 — always record signal even if send_alert fails
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
        self.SIGNAL_COOLDOWN = 1800  # 30 min

        # FIX #15 — thread safety lock
        self._lock = threading.Lock()

    # ------------------------------------------------------------------

    def already_sent_recent(self, symbol):

        return (
            symbol in self.signal_history
            and time.time() - self.signal_history[symbol] < self.SIGNAL_COOLDOWN
        )

    # ------------------------------------------------------------------

    def get_day_change(self, symbol, price):

        if symbol not in self.day_open:
            self.day_open[symbol] = price

        open_price = self.day_open[symbol]

        # FIX #3 — division by zero guard
        if open_price == 0:
            return 0.0

        return ((price - open_price) / open_price) * 100

    # ------------------------------------------------------------------

    def volume_increasing(self, symbol):

        vols = list(self.volume_history[symbol])

        if len(vols) < 3:
            return False

        return vols[-1] > vols[-2] > vols[-3]

    # ------------------------------------------------------------------

    def volume_spike(self, symbol):

        vols = list(self.volume_history[symbol])

        if len(vols) < 6:
            return False

        avg_vol = sum(vols[-6:-1]) / 5

        return vols[-1] > avg_vol * 1.5

    # ------------------------------------------------------------------

    def strong_buying(self, prices):

        if len(prices) < 6:
            return False

        # FIX #4 — division by zero guard
        if prices[-6] == 0:
            return False

        move = ((prices[-1] - prices[-6]) / prices[-6]) * 100

        return move > 1

    # ------------------------------------------------------------------

    def bullish_candle(self, prices):

        if len(prices) < 2:
            return False

        # FIX #4 — division by zero guard
        if prices[-2] == 0:
            return False

        candle_move = ((prices[-1] - prices[-2]) / prices[-2]) * 100

        return candle_move > 0.5

    # ------------------------------------------------------------------

    def break_previous_high(self, prices):

        if len(prices) < 2:
            return False

        return prices[-1] > prices[-2]

    # ------------------------------------------------------------------

    def break_resistance(self, prices):

        if len(prices) < 20:
            return False

        resistance = max(prices[-20:-1])

        return prices[-1] > resistance

    # ------------------------------------------------------------------

    def pullback_recovery(self, prices):

        if len(prices) < 10:
            return False

        # FIX #5 — guard against empty slices
        slice_high = prices[-10:-4]
        slice_low  = prices[-4:-1]

        if not slice_high or not slice_low:
            return False

        swing_high   = max(slice_high)
        pullback_low = min(slice_low)

        # FIX #3 — division by zero guard
        if swing_high == 0:
            return False

        retracement = ((swing_high - pullback_low) / swing_high) * 100

        if retracement > 10:
            return False

        return prices[-1] > prices[-2]

    # ------------------------------------------------------------------

    def near_day_high(self, symbol, price):

        day_high = self.day_high.get(symbol, price)

        return price >= day_high * 0.97

    # ------------------------------------------------------------------

    def reset_daily(self):
        """FIX #10 — Call this at market open every day."""

        with self._lock:
            self.day_open.clear()
            self.day_high.clear()
            self.signal_history.clear()

    # ------------------------------------------------------------------

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

            if day_change < 4:
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

            # FIX #16 — always record signal even if send_alert fails
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

        # FIX #6 — increased maxlen to match close_history
        self.volume_history = defaultdict(lambda: deque(maxlen=150))

        self.signal_history  = {}
        self.SIGNAL_COOLDOWN = 1800  # 30 min

        # FIX #15 — thread safety lock
        self._lock = threading.Lock()

    # ------------------------------------------------------------------

    def already_sent_recent(self, symbol):

        return (
            symbol in self.signal_history
            and time.time() - self.signal_history[symbol] < self.SIGNAL_COOLDOWN
        )

    # ------------------------------------------------------------------

    def reset_daily(self):
        """FIX #10 — Call this at market open every day."""

        with self._lock:
            self.signal_history.clear()

    # ------------------------------------------------------------------

    def update_daily(self, symbol, close_price, volume):

        if not symbol or close_price is None or volume is None:
            return

        with self._lock:

            self.close_history[symbol].append(close_price)
            self.volume_history[symbol].append(volume)

            closes  = list(self.close_history[symbol])
            volumes = list(self.volume_history[symbol])

            # Need enough history
            if len(closes) < 130:
                return

            # CONDITION 1 — 5-day high must be > 120-day high + 5%
            recent_5_max = max(closes[-5:])
            past_120_max = max(closes[-126:-6])

            if past_120_max == 0:
                return

            if recent_5_max <= past_120_max * 1.05:
                return

            # CONDITION 2 — current volume must exceed 5-day average
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

            # FIX #16 — always record signal even if send_alert fails
            try:
                send_alert(message)
            finally:
                self.signal_history[symbol] = time.time()
