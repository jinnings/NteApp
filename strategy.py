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
        """
        Calculates raw score out of 49, then normalises to 0-10.
        Components:
          1. Day change        - max 15 pts
          2. ROC Fast          - max  4 pts
          3. ROC Slow          - max  4 pts
          4. Acceleration      - max  6 pts
          5. VWAP distance     - max 12 pts
          6. EMA stack         - max  5 pts
          7. SMA trend         - max  3 pts
                               -----------
                         Total  max 49 pts  -> normalised to 10
        """

        raw = 0

        # 1. Day change - max 15 pts
        raw += min(abs(day_change) * 4, 15)

        # 2. ROC Fast - max 4 pts
        if abs(m_fast) > 0.1:
            raw += min(abs(m_fast) * 3, 4)

        # 3. ROC Slow - max 4 pts
        if abs(m_slow) > 0.2:
            raw += min(abs(m_slow) * 2, 4)

        # 4. Acceleration - max 6 pts
        if direction == "BUY" and acceleration > 0:
            raw += min(acceleration * 3, 6)
        elif direction == "SELL" and acceleration < 0:
            raw += min(abs(acceleration) * 3, 6)

        # 5. VWAP distance - max 12 pts
        if vwap > 0:
            vwap_distance_pct = ((price - vwap) / vwap) * 100
            if direction == "BUY":
                raw += (8 + min(vwap_distance_pct * 2, 4)) if vwap_distance_pct > 0 else 4
            else:
                raw += (8 + min(abs(vwap_distance_pct) * 2, 4)) if vwap_distance_pct < 0 else 4
        else:
            raw += 4

        # 6. EMA stack - max 5 pts
        if self.ema_direction(ema5, ema10, ema20, direction):
            raw += 5
        elif self.ema_crossover(ema5, ema10, direction):
            raw += 2

        # 7. SMA trend - max 3 pts
        prices = list(self.price_history[symbol])
        if self.trend_alignment(prices, direction):
            raw += 3

        # Normalise to 0-10  (max raw = 49)
        strength = round((raw / 49) * 10, 1)

        return strength

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

        if not symbol or price is None or volume is None:
            return

        # Minimum absolute volume gate
        if volume < 20000:
            print(f"[DROP] {symbol} | low abs volume {volume}")
            return

        with self._lock:

            self.price_history[symbol].append(price)
            self.volume_history[symbol].append(volume)

            prices  = list(self.price_history[symbol])
            volumes = list(self.volume_history[symbol])

            if len(prices) < 20:
                print(f"[DROP] {symbol} | warming up {len(prices)}/20")
                return

            # -- Relative Volume filter ------------------------------------------------
            # Current volume must be at least 30% of its own 10-bar average
            # --------------------------------------------------------------------------
            if len(volumes) >= 10:
                avg_vol = sum(volumes[-10:]) / 10
                if avg_vol > 0 and volume < avg_vol * 0.3:
                    print(f"[DROP] {symbol} | rel vol too low {volume} vs avg {round(avg_vol)}")
                    return

            # VWAP
            length         = min(len(prices), len(volumes))
            recent_prices  = prices[-length:]
            recent_volumes = volumes[-length:]
            vol_sum        = sum(recent_volumes)
            if vol_sum == 0:
                return

            vwap = sum(p * v for p, v in zip(recent_prices, recent_volumes)) / vol_sum

            # ROC
            base_fast = prices[-3]
            base_slow = prices[-10]
            if base_fast == 0 or base_slow == 0:
                return

            m_fast       = ((prices[-1] - base_fast) / base_fast) * 100
            m_slow       = ((prices[-1] - base_slow) / base_slow) * 100
            acceleration = m_fast - m_slow

            # EMA
            ema5, ema10, ema20 = self.compute_ema(symbol, price)

            # Direction
            dir_fast = "BUY" if m_fast > 0 else "SELL"
            dir_slow = "BUY" if m_slow > 0 else "SELL"

            # Use fast ROC as primary direction - slow conflict handled in tier conditions
            direction = dir_fast

            if self.already_sent_recent(symbol, direction):
                print(f"[DROP] {symbol} | cooldown active")
                return

            day_change = self.get_day_change(symbol, price)
            if abs(day_change) < 0.3:   # lowered - market may be flat/sideways
                print(f"[DROP] {symbol} | day_change {round(day_change,3)}% < 0.3%")
                return

            strength = self.calculate_score(
                symbol, direction, price, vwap,
                day_change, m_fast, m_slow, acceleration,
                ema5, ema10, ema20
            )

            # Shared flags
            vol_inc = self.is_volume_increasing(symbol)

            if direction == "BUY":
                ema_full    = (ema5 > ema10 > ema20)
                ema_partial = (ema5 > ema10)
                side_vwap   = (price > vwap)
            else:
                ema_full    = (ema5 < ema10 < ema20)
                ema_partial = (ema5 < ema10)
                side_vwap   = (price < vwap)

            # Debug - print live values for every tick that reaches here
            print(
                f"[LIVE] {symbol} | {direction} | "
                f"mf={round(m_fast,3)}% ms={round(m_slow,3)}% acc={round(acceleration,3)}% | "
                f"ema_full={ema_full} ema_partial={ema_partial} "
                f"vwap={side_vwap} vol_inc={vol_inc} | "
                f"day={round(day_change,2)}% str={strength}"
            )

            # ================================================================
            # TIER 1 - HIGH CONFIDENCE
            # ================================================================
            if direction == "BUY":
                is_high = (
                    m_fast       >  0.50
                    and m_slow       >  0.30
                    and acceleration >  0.20
                    and ema_full
                    and side_vwap
                    and vol_inc
                )
            else:
                is_high = (
                    m_fast       < -0.50
                    and m_slow       < -0.30
                    and acceleration < -0.20
                    and ema_full
                    and side_vwap
                    and vol_inc
                )

            # ================================================================
            # TIER 2 - MEDIUM CONFIDENCE
            # ================================================================
            if direction == "BUY":
                is_medium = (
                    not is_high
                    and m_fast       >  0.20
                    and m_slow       >  0.10
                    and acceleration >  0.05
                    and ema_partial
                    and side_vwap
                    and vol_inc
                )
            else:
                is_medium = (
                    not is_high
                    and m_fast       < -0.20
                    and m_slow       < -0.10
                    and acceleration < -0.05
                    and ema_partial
                    and side_vwap
                    and vol_inc
                )

            if not is_high and not is_medium:
                print(
                    f"[DROP] {symbol} | no tier | "
                    f"mf={round(m_fast,3)} ms={round(m_slow,3)} acc={round(acceleration,3)} "
                    f"ema_full={ema_full} ema_partial={ema_partial} "
                    f"vwap={side_vwap} vol={vol_inc}"
                )
                return

            if strength <= 5.0:
                print(f"[DROP] {symbol} | strength {strength} <= 5.0")
                return

            # -- Build message based on tier --------------------------------------
            if is_high:
                header   = "ROCKET HIGH CONFIDENCE TRADE ROCKET"
                if direction == "BUY":
                    ema_line = "EMA5 > EMA10 > EMA20  OK (Full Bullish Stack)"
                else:
                    ema_line = "EMA5 < EMA10 < EMA20  OK (Full Bearish Stack)"
            else:
                header   = "YELLOW MEDIUM CONFIDENCE TRADE YELLOW"
                if direction == "BUY":
                    ema_line = "EMA5 > EMA10  OK (Bullish Crossover)"
                else:
                    ema_line = "EMA5 < EMA10  OK (Bearish Crossover)"

            # -- VWAP distance ---------------------------------------------------
            vwap_dist_pct = round(abs((price - vwap) / vwap) * 100, 2)
            if direction == "BUY":
                vwap_label = f"VWAP       : Rs{round(vwap, 2)}  (+{vwap_dist_pct}% above)"
            else:
                vwap_label = f"VWAP       : Rs{round(vwap, 2)}  (-{vwap_dist_pct}% below)"

            # -- SL Logic --------------------------------------------------------
            # BUY  SL = lower of VWAP or EMA10  (support below price)
            # SELL SL = higher of VWAP or EMA10 (resistance above price)
            # --------------------------------------------------------------------
            if direction == "BUY":
                sl_price   = round(min(vwap, ema10), 2)
                sl_reason  = "VWAP" if vwap <= ema10 else "EMA10"
                sl_pct     = round(((price - sl_price) / price) * 100, 2)
                risk       = price - sl_price
                target     = round(price + (risk * 2), 2)
                target_pct = round(((target - price) / price) * 100, 2)
                sl_label   = f"SL         : Rs{sl_price}  (-{sl_pct}%)"
                tgt_label  = f"Target      : Rs{target}  (+{target_pct}%)"
            else:
                sl_price   = round(max(vwap, ema10), 2)
                sl_reason  = "VWAP" if vwap >= ema10 else "EMA10"
                sl_pct     = round(((sl_price - price) / price) * 100, 2)
                risk       = sl_price - price
                target     = round(price - (risk * 2), 2)
                target_pct = round(((price - target) / price) * 100, 2)
                sl_label   = f"SL         : Rs{sl_price}  (+{sl_pct}%)"
                tgt_label  = f"Target      : Rs{target}  (-{target_pct}%)"

            sl_basis = f"SL Basis    : Above {sl_reason}" if direction == "SELL" else f"SL Basis    : Below {sl_reason}"

            message = (
                f"\n{header}\n"
                f"----------------------------\n"
                f"{symbol} -> {direction}\n"
                f"Rs{round(price, 2)}\n"
                f"Strength    : {strength}/10\n"
                f"\n"
                f"ROC Fast     : {round(m_fast, 3)}%\n"
                f"ROC Slow     : {round(m_slow, 3)}%\n"
                f"Acceleration : {round(acceleration, 3)}%\n"
                f"\n"
                f"{ema_line}\n"
                f"EMA5  : Rs{round(ema5, 2)}\n"
                f"EMA10 : Rs{round(ema10, 2)}\n"
                f"EMA20 : Rs{round(ema20, 2)}\n"
                f"\n"
                f"{vwap_label}\n"
                f"\n"
                f"{sl_label}\n"
                f"{sl_basis}\n"
                f"{tgt_label}\n"
                f"Risk:Reward  : 1 : 2\n"
                f"\n"
                f"Volume Increasing  OK\n"
                f"Day Change : {round(day_change, 2)}%\n"
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
                    f"\nTOP TRADE\n"
                    f"{symbol} -> {direction}\n"
                    f"Rs{round(price, 2)}\n"
                    f"Score: {score}\n"
                    f"(Queued signal - price may have moved)\n"
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
        self.SIGNAL_COOLDOWN = 2700  # 45 min - increased from 30 min

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

        # Raised from 1.5x to 2.0x - only genuine volume surges
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

            # Raised from 4% to 5% - filters weaker moves
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
                f"\nPULLBACK STRATEGY\n\n"
                f"{symbol} -> BUY\n\n"
                f"Rs{round(price, 2)}\n\n"
                f"Type       : {signal_type}\n"
                f"Day Change : {round(day_change, 2)}%\n\n"
                f"OK Strong Buying\n"
                f"OK Volume Increasing\n"
                f"OK Volume Spike\n"
                f"OK Pullback Recovery\n"
                f"OK Bullish Candle\n"
                f"OK Previous High Break\n"
                f"OK Near Day High / Resistance Break\n"
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
        self.SIGNAL_COOLDOWN = 3600  # 60 min - increased from 30 min

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

            # CONDITION 1 - 5-day high > 120-day high + 5%
            recent_5_max = max(closes[-5:])
            past_120_max = max(closes[-126:-6])

            if past_120_max == 0:
                return

            if recent_5_max <= past_120_max * 1.05:
                return

            # CONDITION 2 - current volume > 5-day average
            if len(volumes) < 6:
                return

            avg_5_volume   = sum(volumes[-6:-1]) / 5
            current_volume = volumes[-1]

            if avg_5_volume == 0:
                return

            if current_volume <= avg_5_volume:
                return

            # CONDITION 3 - today closed higher than yesterday
            if closes[-1] <= closes[-2]:
                return

            if self.already_sent_recent(symbol):
                return

            message = (
                f"\nJINNING EFFECT\n"
                f"{symbol} -> BUY\n"
                f"Rs{round(close_price, 2)}\n\n"
                f"OK 5-Day Breakout > 120D + 5%\n"
                f"OK Volume > 5D Avg\n"
                f"OK Strong Closing\n"
            )

            try:
                send_alert(message)
            finally:
                self.signal_history[symbol] = time.time()


# ================================
# ✅ INTRADAY RECOVERY STRATEGY
# ================================

class IntradayRecoveryStrategy:
    """
    Fires a BUY signal when a stock that has dipped intraday
    starts recovering with VWAP reclaim + EMA crossover + volume surge.

    Conditions:
      1. Dip from day high  >= 2.0%  (meaningful pullback occurred)
      2. Recovery from low  >= 1.0%  (bounce is real, not noise)
      3. Price > VWAP                (VWAP reclaimed - key intraday level)
      4. EMA5 > EMA10                (short-term momentum turning bullish)
      5. Volume increasing (3 bars)  (buyers stepping in on recovery)
      6. Day change > -5.0%          (not a full crash / circuit filter)
      7. 4 consecutive higher closes (momentum confirmation)
    """

    def __init__(self):

        self.price_history  = defaultdict(lambda: deque(maxlen=60))
        self.volume_history = defaultdict(lambda: deque(maxlen=60))

        self.day_open = {}
        self.day_high = {}
        self.day_low  = {}

        self.ema_state = {}

        self.signal_history  = {}
        self.SIGNAL_COOLDOWN = 2400  # 40 min

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

    def compute_ema(self, symbol, price):
        """
        Incremental EMA5 and EMA10 - O(1) per tick.
        Seeds both EMAs with first price on first call.
        Returns (ema5, ema10).
        """

        k5  = 2 / (5  + 1)   # 0.3333
        k10 = 2 / (10 + 1)   # 0.1818

        if symbol not in self.ema_state:
            self.ema_state[symbol] = {
                "ema5":  price,
                "ema10": price,
            }
        else:
            prev = self.ema_state[symbol]
            self.ema_state[symbol] = {
                "ema5":  price * k5  + prev["ema5"]  * (1 - k5),
                "ema10": price * k10 + prev["ema10"] * (1 - k10),
            }

        s = self.ema_state[symbol]
        return s["ema5"], s["ema10"]

    def volume_increasing(self, symbol):

        vols = list(self.volume_history[symbol])

        if len(vols) < 3:
            return False

        return vols[-1] > vols[-2] > vols[-3]

    def consecutive_higher_closes(self, prices):
        """
        4 consecutive higher closes - confirms momentum is building,
        not just a single-bar spike.
        """

        if len(prices) < 4:
            return False

        return prices[-1] > prices[-2] > prices[-3] > prices[-4]

    def reset_daily(self):
        """Call this at market open every day."""

        with self._lock:
            self.day_open.clear()
            self.day_high.clear()
            self.day_low.clear()
            self.signal_history.clear()
            self.ema_state.clear()

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume is None:
            return

        # Minimum absolute volume gate
        if volume < 20000:
            return

        with self._lock:

            self.price_history[symbol].append(price)
            self.volume_history[symbol].append(volume)

            # Track day open (first tick of the day)
            if symbol not in self.day_open:
                self.day_open[symbol] = price

            # Track day high
            if symbol not in self.day_high:
                self.day_high[symbol] = price
            else:
                self.day_high[symbol] = max(self.day_high[symbol], price)

            # Track day low
            if symbol not in self.day_low:
                self.day_low[symbol] = price
            else:
                self.day_low[symbol] = min(self.day_low[symbol], price)

            prices  = list(self.price_history[symbol])
            volumes = list(self.volume_history[symbol])

            if len(prices) < 20:
                return

            day_high = self.day_high[symbol]
            day_low  = self.day_low[symbol]

            if day_high == 0 or day_low == 0:
                return

            # -- CONDITION 1: Meaningful dip from day high -------------------------
            # Stock must have pulled back at least 2% from its intraday peak
            # ----------------------------------------------------------------------
            dip_pct = ((day_high - price) / day_high) * 100
            if dip_pct < 2.0:
                print(f"[RECOVERY-DROP] {symbol} | dip {round(dip_pct, 2)}% < 2.0%")
                return

            # -- CONDITION 2: Real recovery from day low ---------------------------
            # Price must have bounced at least 1% from the intraday low
            # ----------------------------------------------------------------------
            recovery_pct = ((price - day_low) / day_low) * 100
            if recovery_pct < 1.0:
                print(f"[RECOVERY-DROP] {symbol} | recovery {round(recovery_pct, 2)}% < 1.0%")
                return

            # -- CONDITION 3: Day change filter - not a full crash -----------------
            day_change = self.get_day_change(symbol, price)
            if day_change < -5.0:
                print(f"[RECOVERY-DROP] {symbol} | day_change {round(day_change, 2)}% < -5.0%")
                return

            # -- Cooldown ----------------------------------------------------------
            if self.already_sent_recent(symbol):
                return

            # -- VWAP --------------------------------------------------------------
            length         = min(len(prices), len(volumes))
            recent_prices  = prices[-length:]
            recent_volumes = volumes[-length:]
            vol_sum        = sum(recent_volumes)
            if vol_sum == 0:
                return

            vwap = sum(p * v for p, v in zip(recent_prices, recent_volumes)) / vol_sum

            # -- EMA ---------------------------------------------------------------
            ema5, ema10 = self.compute_ema(symbol, price)

            # -- CONDITION 4: VWAP reclaim -----------------------------------------
            # Price must be back above VWAP - confirms intraday bias has flipped
            # ----------------------------------------------------------------------
            if price <= vwap:
                print(
                    f"[RECOVERY-DROP] {symbol} | "
                    f"price {round(price, 2)} <= vwap {round(vwap, 2)}"
                )
                return

            # -- CONDITION 5: EMA5 > EMA10 - short-term momentum turning up --------
            if ema5 <= ema10:
                print(
                    f"[RECOVERY-DROP] {symbol} | "
                    f"ema5 {round(ema5, 2)} <= ema10 {round(ema10, 2)}"
                )
                return

            # -- CONDITION 6: Volume increasing on recovery ------------------------
            if not self.volume_increasing(symbol):
                print(f"[RECOVERY-DROP] {symbol} | volume not increasing")
                return

            # -- CONDITION 7: Consecutive higher closes ----------------------------
            if not self.consecutive_higher_closes(prices):
                print(f"[RECOVERY-DROP] {symbol} | no consecutive higher closes")
                return

            # -- SL / Target -------------------------------------------------------
            # SL  = just below day low (natural intraday support)
            # TGT = 1:2 R:R from current price
            # ----------------------------------------------------------------------
            sl_price   = round(day_low * 0.998, 2)
            sl_pct     = round(((price - sl_price) / price) * 100, 2)
            risk       = price - sl_price
            target     = round(price + (risk * 2), 2)
            target_pct = round(((target - price) / price) * 100, 2)

            vwap_dist_pct = round(((price - vwap) / vwap) * 100, 2)

            print(
                f"[RECOVERY-SIGNAL] {symbol} | "
                f"dip={round(dip_pct, 2)}% rec={round(recovery_pct, 2)}% "
                f"day={round(day_change, 2)}% "
                f"ema5={round(ema5, 2)} ema10={round(ema10, 2)} "
                f"vwap={round(vwap, 2)} price={round(price, 2)}"
            )

            message = (
                f"\nINTRADAY RECOVERY\n"
                f"----------------------------\n"
                f"{symbol} -> BUY\n"
                f"Rs{round(price, 2)}\n"
                f"\n"
                f"Dip from High    : -{round(dip_pct, 2)}%\n"
                f"Recovery from Low: +{round(recovery_pct, 2)}%\n"
                f"Day Change       : {round(day_change, 2)}%\n"
                f"\n"
                f"EMA5  : Rs{round(ema5, 2)}  >  EMA10 : Rs{round(ema10, 2)}  OK\n"
                f"VWAP  : Rs{round(vwap, 2)}  (+{vwap_dist_pct}% above)  OK\n"
                f"\n"
                f"SL    : Rs{sl_price}  (-{sl_pct}%)  [Below Day Low]\n"
                f"Target: Rs{target}  (+{target_pct}%)\n"
                f"Risk:Reward : 1 : 2\n"
                f"\n"
                f"OK VWAP Reclaimed\n"
                f"OK EMA Crossover (Bullish)\n"
                f"OK Volume Increasing\n"
                f"OK Consecutive Higher Closes\n"
                f"OK Meaningful Dip + Recovery Confirmed\n"
            )

            try:
                send_alert(message)
            finally:
                self.signal_history[symbol] = time.time()