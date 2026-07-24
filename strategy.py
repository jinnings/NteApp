from collections import defaultdict, deque
import threading
import time
import requests
from alerts import send_alert


# =========================
# ✅ MULTI SIGNAL STRATEGY
# =========================

class MultiSignalStrategy:
    """
    Intraday momentum strategy — BUY and SELL.

    Improvements that reduce losses:
      1. Direction requires BOTH fast AND slow ROC to agree — no conflicting signals
      2. RSI(14) filter — avoids overbought/oversold entries
      3. ATR(14)-based SL — adapts to current volatility, not fixed VWAP/EMA10
      4. SL distance guard — min 0.3%, max 2.5% (no too-tight or too-wide SL)
      5. Volume ratio gate — current vol > 1.5x 20-bar average (not just 3 rising bars)
      6. Trend filter — price must be above SMA30 for BUY, below for SELL
      7. No-trade zone — skip if price within 0.2% of VWAP (indecision zone)
      8. Score threshold raised to 6.5 (was 5.0)
      9. Tighter tier thresholds — fewer but higher quality signals
     10. Cooldown raised to 45 min (was 30 min)
    """

    def __init__(self):

        self.price_history  = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=100))

        self.last_direction = {}
        self.signal_history = {}
        self.SIGNAL_COOLDOWN = 2700  # 45 min

        self.day_open       = {}
        self.candidates     = []
        self.last_rank_sent = 0

        self._lock          = threading.Lock()
        self.MAX_CANDIDATE_AGE = 30

        self.ema_state = {}

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────────────────
    # INDICATORS
    # ─────────────────────────────────────────────────────────────────────────

    def compute_ema(self, symbol, price):
        """
        Incremental EMA — O(1) per tick.
        Returns (ema5, ema10, ema20).
        Seeds all EMAs with first price on first call.
        """
        k5  = 2 / (5  + 1)
        k10 = 2 / (10 + 1)
        k20 = 2 / (20 + 1)

        if symbol not in self.ema_state:
            self.ema_state[symbol] = {"ema5": price, "ema10": price, "ema20": price}
        else:
            prev = self.ema_state[symbol]
            self.ema_state[symbol] = {
                "ema5":  price * k5  + prev["ema5"]  * (1 - k5),
                "ema10": price * k10 + prev["ema10"] * (1 - k10),
                "ema20": price * k20 + prev["ema20"] * (1 - k20),
            }

        s = self.ema_state[symbol]
        return s["ema5"], s["ema10"], s["ema20"]

    def compute_rsi(self, prices, period=14):
        """
        RSI(14) using last period+1 closes.
        Returns 50 (neutral) if not enough data.
        """
        if len(prices) < period + 1:
            return 50

        recent = prices[-(period + 1):]
        gains, losses = [], []
        for i in range(1, len(recent)):
            diff = recent[i] - recent[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100
        rs  = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 1)

    def compute_atr(self, prices, period=14):
        """
        ATR using close-to-close differences (no high/low available).
        Returns None if not enough data.
        """
        if len(prices) < period + 1:
            return None
        recent = prices[-(period + 1):]
        trs    = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
        return sum(trs) / period

    def compute_sma(self, prices, period):
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    def get_volume_ratio(self, volumes, period=20):
        """
        current_volume / avg_volume over last `period` bars.
        Returns 0 if not enough data.
        """
        if len(volumes) < period + 1:
            return 0
        avg = sum(volumes[-(period + 1):-1]) / period
        if avg == 0:
            return 0
        return volumes[-1] / avg

    def trend_alignment(self, prices, direction):
        """SMA10 vs SMA20 alignment."""
        if len(prices) < 20:
            return False
        sma10 = sum(prices[-10:]) / 10
        sma20 = sum(prices[-20:]) / 20
        return sma10 > sma20 if direction == "BUY" else sma10 < sma20

    # ─────────────────────────────────────────────────────────────────────────
    # SCORING  (max 55 pts → normalised to 0–10)
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_score(
        self, symbol, direction, price, vwap,
        day_change, m_fast, m_slow, acceleration,
        ema5, ema10, ema20, vol_ratio, rsi
    ):
        """
        Components:
          1. Day change   — max 12 pts
          2. ROC Fast     — max  5 pts
          3. ROC Slow     — max  5 pts
          4. Acceleration — max  6 pts
          5. VWAP dist    — max 10 pts
          6. EMA stack    — max  5 pts
          7. SMA trend    — max  3 pts
          8. Vol ratio    — max  5 pts
          9. RSI quality  — max  4 pts
                            ─────────
                    Total   max 55 pts → normalised to 10
        """
        raw = 0

        # 1. Day change — max 12 pts
        raw += min(abs(day_change) * 3, 12)

        # 2. ROC Fast — max 5 pts
        if abs(m_fast) > 0.15:
            raw += min(abs(m_fast) * 4, 5)

        # 3. ROC Slow — max 5 pts
        if abs(m_slow) > 0.25:
            raw += min(abs(m_slow) * 2.5, 5)

        # 4. Acceleration — max 6 pts
        if direction == "BUY" and acceleration > 0:
            raw += min(acceleration * 3, 6)
        elif direction == "SELL" and acceleration < 0:
            raw += min(abs(acceleration) * 3, 6)

        # 5. VWAP distance — max 10 pts
        if vwap > 0:
            vwap_dist = ((price - vwap) / vwap) * 100
            if direction == "BUY":
                raw += (7 + min(vwap_dist * 1.5, 3)) if vwap_dist > 0 else 3
            else:
                raw += (7 + min(abs(vwap_dist) * 1.5, 3)) if vwap_dist < 0 else 3
        else:
            raw += 3

        # 6. EMA stack — max 5 pts
        if direction == "BUY":
            if ema5 > ema10 > ema20:
                raw += 5
            elif ema5 > ema10:
                raw += 2
        else:
            if ema5 < ema10 < ema20:
                raw += 5
            elif ema5 < ema10:
                raw += 2

        # 7. SMA trend — max 3 pts
        prices = list(self.price_history[symbol])
        if self.trend_alignment(prices, direction):
            raw += 3

        # 8. Volume ratio — max 5 pts
        if vol_ratio >= 3.0:
            raw += 5
        elif vol_ratio >= 2.0:
            raw += 4
        elif vol_ratio >= 1.5:
            raw += 3
        elif vol_ratio >= 1.0:
            raw += 1

        # 9. RSI quality — max 4 pts
        # BUY:  ideal 45–65 (momentum, not overbought)
        # SELL: ideal 35–55 (momentum, not oversold)
        if direction == "BUY":
            if 45 <= rsi <= 65:
                raw += 4
            elif 40 <= rsi < 45 or 65 < rsi <= 70:
                raw += 2
        else:
            if 35 <= rsi <= 55:
                raw += 4
            elif 30 <= rsi < 35 or 55 < rsi <= 60:
                raw += 2

        return round((raw / 55) * 10, 1)

    # ─────────────────────────────────────────────────────────────────────────
    # DAILY RESET
    # ─────────────────────────────────────────────────────────────────────────

    def reset_daily(self):
        """Call this at market open every day."""
        with self._lock:
            self.day_open.clear()
            self.signal_history.clear()
            self.last_direction.clear()
            self.candidates.clear()
            self.ema_state.clear()
            self.last_rank_sent = 0

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN UPDATE
    # ─────────────────────────────────────────────────────────────────────────

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume is None:
            return

        # ── Absolute volume gate ───────────────────────────────────────────
        if volume < 20000:
            print(f"[DROP] {symbol} | low abs volume {volume}")
            return

        with self._lock:

            self.price_history[symbol].append(price)
            self.volume_history[symbol].append(volume)

            prices  = list(self.price_history[symbol])
            volumes = list(self.volume_history[symbol])

            # ── Warmup — need at least 30 bars ────────────────────────────
            if len(prices) < 30:
                print(f"[DROP] {symbol} | warming up {len(prices)}/30")
                return

            # ── Volume ratio gate — current vol must be > 1.5x 20-bar avg ─
            vol_ratio = self.get_volume_ratio(volumes, period=20)
            if vol_ratio < 1.5:
                print(f"[DROP] {symbol} | vol ratio {round(vol_ratio, 2)} < 1.5x")
                return

            # ── VWAP ──────────────────────────────────────────────────────
            length         = min(len(prices), len(volumes))
            recent_prices  = prices[-length:]
            recent_volumes = volumes[-length:]
            vol_sum        = sum(recent_volumes)
            if vol_sum == 0:
                return

            vwap = sum(p * v for p, v in zip(recent_prices, recent_volumes)) / vol_sum

            # ── ROC ───────────────────────────────────────────────────────
            if len(prices) < 10:
                return
            base_fast = prices[-3]
            base_slow = prices[-10]
            if base_fast == 0 or base_slow == 0:
                return

            m_fast       = ((prices[-1] - base_fast) / base_fast) * 100
            m_slow       = ((prices[-1] - base_slow) / base_slow) * 100
            acceleration = m_fast - m_slow

            # ── Direction — BOTH fast AND slow must agree ─────────────────
            # This is the #1 fix: eliminates conflicting signals
            dir_fast = "BUY" if m_fast > 0 else "SELL"
            dir_slow = "BUY" if m_slow > 0 else "SELL"

            if dir_fast != dir_slow:
                print(f"[DROP] {symbol} | direction conflict fast={dir_fast} slow={dir_slow}")
                return

            direction = dir_fast

            # ── Cooldown ──────────────────────────────────────────────────
            if self.already_sent_recent(symbol, direction):
                print(f"[DROP] {symbol} | cooldown active")
                return

            # ── Day change gate ───────────────────────────────────────────
            day_change = self.get_day_change(symbol, price)
            if abs(day_change) < 0.5:
                print(f"[DROP] {symbol} | day_change {round(day_change, 3)}% < 0.5%")
                return

            # ── EMA ───────────────────────────────────────────────────────
            ema5, ema10, ema20 = self.compute_ema(symbol, price)

            # ── RSI filter ────────────────────────────────────────────────
            rsi = self.compute_rsi(prices)
            if direction == "BUY" and rsi > 72:
                print(f"[DROP] {symbol} | RSI {rsi} overbought for BUY")
                return
            if direction == "SELL" and rsi < 28:
                print(f"[DROP] {symbol} | RSI {rsi} oversold for SELL")
                return

            # ── Trend filter — price vs SMA30 ─────────────────────────────
            sma30 = self.compute_sma(prices, 30)
            if sma30 is not None:
                if direction == "BUY" and price < sma30:
                    print(f"[DROP] {symbol} | price {price} below SMA30 {round(sma30, 2)} for BUY")
                    return
                if direction == "SELL" and price > sma30:
                    print(f"[DROP] {symbol} | price {price} above SMA30 {round(sma30, 2)} for SELL")
                    return

            # ── No-trade zone — price within 0.2% of VWAP ────────────────
            vwap_dist_pct = abs((price - vwap) / vwap) * 100
            if vwap_dist_pct < 0.2:
                print(f"[DROP] {symbol} | price too close to VWAP ({round(vwap_dist_pct, 3)}%) — indecision zone")
                return

            # ── Shared flags ──────────────────────────────────────────────
            if direction == "BUY":
                ema_full    = (ema5 > ema10 > ema20)
                ema_partial = (ema5 > ema10)
                side_vwap   = (price > vwap)
            else:
                ema_full    = (ema5 < ema10 < ema20)
                ema_partial = (ema5 < ema10)
                side_vwap   = (price < vwap)

            # ── Score ─────────────────────────────────────────────────────
            strength = self.calculate_score(
                symbol, direction, price, vwap,
                day_change, m_fast, m_slow, acceleration,
                ema5, ema10, ema20, vol_ratio, rsi
            )

            # ── Debug log ─────────────────────────────────────────────────
            print(
                f"[LIVE] {symbol} | {direction} | "
                f"mf={round(m_fast, 3)}% ms={round(m_slow, 3)}% acc={round(acceleration, 3)}% | "
                f"rsi={rsi} vol_ratio={round(vol_ratio, 2)} | "
                f"ema_full={ema_full} ema_partial={ema_partial} "
                f"vwap={side_vwap} | "
                f"day={round(day_change, 2)}% str={strength}"
            )

            # ════════════════════════════════════════════════════════════
            # TIER 1 — HIGH CONFIDENCE
            # Tightened thresholds + both ROC already agree (direction gate above)
            # ════════════════════════════════════════════════════════════
            if direction == "BUY":
                is_high = (
                    m_fast       >  0.60
                    and m_slow       >  0.40
                    and acceleration >  0.25
                    and ema_full
                    and side_vwap
                    and vol_ratio    >= 2.0
                )
            else:
                is_high = (
                    m_fast       < -0.60
                    and m_slow       < -0.40
                    and acceleration < -0.25
                    and ema_full
                    and side_vwap
                    and vol_ratio    >= 2.0
                )

            # ════════════════════════════════════════════════════════════
            # TIER 2 — MEDIUM CONFIDENCE
            # ════════════════════════════════════════════════════════════
            if direction == "BUY":
                is_medium = (
                    not is_high
                    and m_fast       >  0.25
                    and m_slow       >  0.15
                    and acceleration >  0.08
                    and ema_partial
                    and side_vwap
                    and vol_ratio    >= 1.5
                )
            else:
                is_medium = (
                    not is_high
                    and m_fast       < -0.25
                    and m_slow       < -0.15
                    and acceleration < -0.08
                    and ema_partial
                    and side_vwap
                    and vol_ratio    >= 1.5
                )

            if not is_high and not is_medium:
                print(
                    f"[DROP] {symbol} | no tier | "
                    f"mf={round(m_fast, 3)} ms={round(m_slow, 3)} acc={round(acceleration, 3)} "
                    f"ema_full={ema_full} ema_partial={ema_partial} "
                    f"vwap={side_vwap} vol_ratio={round(vol_ratio, 2)}"
                )
                return

            # ── Score gate — raised to 6.5 ────────────────────────────────
            if strength <= 6.5:
                print(f"[DROP] {symbol} | strength {strength} <= 6.5")
                return

            # ── ATR-based Stop Loss ───────────────────────────────────────
            # SL = price ± 1.5 × ATR(14)
            # Clamped: min 0.3%, max 2.5% from price
            atr = self.compute_atr(prices)
            if atr is None:
                atr = price * 0.005  # fallback: 0.5% of price

            atr_sl_distance = atr * 1.5
            min_sl_distance = price * 0.003   # 0.3%
            max_sl_distance = price * 0.025   # 2.5%
            sl_distance     = max(min_sl_distance, min(atr_sl_distance, max_sl_distance))

            if direction == "BUY":
                sl_price   = round(price - sl_distance, 2)
                sl_pct     = round((sl_distance / price) * 100, 2)
                target     = round(price + sl_distance * 2, 2)
                target_pct = round((sl_distance * 2 / price) * 100, 2)
                sl_label   = f"🛡 SL         : ₹{sl_price}  (-{sl_pct}%)"
                tgt_label  = f"🎯 Target      : ₹{target}  (+{target_pct}%)"
            else:
                sl_price   = round(price + sl_distance, 2)
                sl_pct     = round((sl_distance / price) * 100, 2)
                target     = round(price - sl_distance * 2, 2)
                target_pct = round((sl_distance * 2 / price) * 100, 2)
                sl_label   = f"🛡 SL         : ₹{sl_price}  (+{sl_pct}%)"
                tgt_label  = f"🎯 Target      : ₹{target}  (-{target_pct}%)"

            sl_basis = f"📌 SL Basis    : ATR(14) × 1.5"

            # ── Build message ─────────────────────────────────────────────
            if is_high:
                header = "🚀 HIGH CONFIDENCE TRADE 🚀"
                ema_line = (
                    "📊 EMA5 > EMA10 > EMA20  ✅ (Full Bullish Stack)"
                    if direction == "BUY" else
                    "📊 EMA5 < EMA10 < EMA20  ✅ (Full Bearish Stack)"
                )
            else:
                header = "🟡 MEDIUM CONFIDENCE TRADE 🟡"
                ema_line = (
                    "📊 EMA5 > EMA10  ✅ (Bullish Crossover)"
                    if direction == "BUY" else
                    "📊 EMA5 < EMA10  ✅ (Bearish Crossover)"
                )

            signed_vwap_dist = round(((price - vwap) / vwap) * 100, 2)
            vwap_label = (
                f"💧 VWAP       : ₹{round(vwap, 2)}  (+{signed_vwap_dist}% above)"
                if direction == "BUY" else
                f"💧 VWAP       : ₹{round(vwap, 2)}  ({signed_vwap_dist}% below)"
            )

            rsi_label = f"📉 RSI(14)     : {rsi}"
            vol_label = f"📦 Vol Ratio   : {round(vol_ratio, 2)}x avg"

            message = (
                f"\n{header}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{symbol} → {direction}\n"
                f"₹{round(price, 2)}\n"
                f"💪 Strength    : {strength}/10\n"
                f"\n"
                f"📈 ROC Fast     : {round(m_fast, 3)}%\n"
                f"📈 ROC Slow     : {round(m_slow, 3)}%\n"
                f"⚡ Acceleration : {round(acceleration, 3)}%\n"
                f"\n"
                f"{ema_line}\n"
                f"📊 EMA5  : ₹{round(ema5, 2)}\n"
                f"📊 EMA10 : ₹{round(ema10, 2)}\n"
                f"📊 EMA20 : ₹{round(ema20, 2)}\n"
                f"\n"
                f"{vwap_label}\n"
                f"{rsi_label}\n"
                f"{vol_label}\n"
                f"\n"
                f"{sl_label}\n"
                f"{sl_basis}\n"
                f"{tgt_label}\n"
                f"⚖️ Risk:Reward  : 1 : 2\n"
                f"\n"
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

            now   = time.time()
            fresh = [
                c for c in self.candidates
                if now - c["timestamp"] < self.MAX_CANDIDATE_AGE
            ]

            if not fresh:
                self.candidates.clear()
                self.last_rank_sent = now
                return

            top = sorted(fresh, key=lambda x: x["score"], reverse=True)[:3]

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
    """
    Intraday pullback recovery — BUY only.

    Improvements:
      1. Day change range 3%–10% (was ≥ 5%) — catches earlier, avoids exhausted moves
      2. Volume spike threshold lowered to 1.5x (was 2x) — catches more genuine setups
      3. SMA20 trend filter — price must be above SMA20 (only trade with the trend)
      4. SL and Target added — SL = 5-bar low, Target = 2x risk
      5. Cooldown raised to 60 min
    """

    def __init__(self):

        self.price_history  = defaultdict(lambda: deque(maxlen=50))
        self.volume_history = defaultdict(lambda: deque(maxlen=50))

        self.day_open = {}
        self.day_high = {}

        self.signal_history  = {}
        self.SIGNAL_COOLDOWN = 3600  # 60 min

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
        return len(vols) >= 3 and vols[-1] > vols[-2] > vols[-3]

    def volume_spike(self, symbol):
        """Current volume > 1.5x 5-bar average (was 2x — too restrictive)."""
        vols = list(self.volume_history[symbol])
        if len(vols) < 6:
            return False
        avg_vol = sum(vols[-6:-1]) / 5
        return vols[-1] > avg_vol * 1.5

    def strong_buying(self, prices):
        if len(prices) < 6 or prices[-6] == 0:
            return False
        move = ((prices[-1] - prices[-6]) / prices[-6]) * 100
        return move > 1.0

    def bullish_candle(self, prices):
        if len(prices) < 2 or prices[-2] == 0:
            return False
        return ((prices[-1] - prices[-2]) / prices[-2]) * 100 > 0.5

    def break_previous_high(self, prices):
        return len(prices) >= 2 and prices[-1] > prices[-2]

    def break_resistance(self, prices):
        if len(prices) < 20:
            return False
        return prices[-1] > max(prices[-20:-1])

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
        return retracement <= 10 and prices[-1] > prices[-2]

    def near_day_high(self, symbol, price):
        return price >= self.day_high.get(symbol, price) * 0.97

    def above_sma20(self, prices):
        """Trend filter — only buy when price is above SMA20."""
        if len(prices) < 20:
            return False
        sma20 = sum(prices[-20:]) / 20
        return prices[-1] > sma20

    def get_sl_price(self, prices):
        """SL = lowest price of last 5 bars."""
        if len(prices) < 5:
            return None
        return min(prices[-5:])

    def reset_daily(self):
        """Call this at market open every day."""
        with self._lock:
            self.day_open.clear()
            self.day_high.clear()
            self.signal_history.clear()

    def update(self, symbol, price, volume):

        if not symbol or price is None or volume is None:
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

            # Day change must be 3%–10%
            # < 3%: move too weak
            # > 10%: move likely exhausted — late entry risk
            if day_change < 3.0 or day_change > 10.0:
                return

            if self.already_sent_recent(symbol):
                return

            # ── Trend filter — only buy above SMA20 ───────────────────────
            if not self.above_sma20(prices):
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

            # ── SL and Target ─────────────────────────────────────────────
            sl_price = self.get_sl_price(prices)
            if sl_price is None or sl_price >= price:
                sl_price = round(price * 0.985, 2)  # fallback: 1.5% below

            sl_pct     = round(((price - sl_price) / price) * 100, 2)
            risk       = price - sl_price
            target     = round(price + risk * 2, 2)
            target_pct = round((risk * 2 / price) * 100, 2)

            message = (
                f"\n🔥 PULLBACK STRATEGY 🔥\n\n"
                f"{symbol} → BUY\n\n"
                f"₹{round(price, 2)}\n\n"
                f"Type       : {signal_type}\n"
                f"Day Change : {round(day_change, 2)}%\n\n"
                f"✅ Above SMA20 (Trend Confirmed)\n"
                f"✅ Strong Buying\n"
                f"✅ Volume Increasing\n"
                f"✅ Volume Spike (1.5x avg)\n"
                f"✅ Pullback Recovery (≤10% retracement)\n"
                f"✅ Bullish Candle\n"
                f"✅ Previous High Break\n"
                f"✅ Near Day High / Resistance Break\n\n"
                f"🛡 SL     : ₹{sl_price}  (-{sl_pct}%)  [5-bar low]\n"
                f"🎯 Target : ₹{target}  (+{target_pct}%)\n"
                f"⚖️ Risk:Reward : 1 : 2\n"
            )

            try:
                send_alert(message)
            finally:
                self.signal_history[symbol] = time.time()


# =========================
# ✅ JINNING EFFECT STRATEGY
# =========================

class JinningEffectStrategy:
    """
    Daily 120-day breakout strategy — BUY only.

    Improvements:
      1. Volume must be > 1.5x 5-day average (was just > average — too weak)
      2. Requires 2 consecutive closes higher (was just 1 day)
      3. Shows breakout % above 120-day high in alert
      4. Cooldown raised to once per day (86400 sec)
    """

    def __init__(self):

        self.close_history  = defaultdict(lambda: deque(maxlen=150))
        self.volume_history = defaultdict(lambda: deque(maxlen=150))

        self.signal_history  = {}
        self.SIGNAL_COOLDOWN = 86400  # once per day

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

            # ── CONDITION 1 — 5-day high > 120-day high + 5% ─────────────
            recent_5_max = max(closes[-5:])
            past_120_max = max(closes[-126:-6])

            if past_120_max == 0:
                return

            if recent_5_max <= past_120_max * 1.05:
                return

            # ── CONDITION 2 — volume > 1.5x 5-day average ────────────────
            # (was just > average — too easy to trigger)
            if len(volumes) < 6:
                return

            avg_5_volume   = sum(volumes[-6:-1]) / 5
            current_volume = volumes[-1]

            if avg_5_volume == 0:
                return

            if current_volume <= avg_5_volume * 1.5:
                return

            # ── CONDITION 3 — 2 consecutive closes higher ─────────────────
            # (was just 1 day — stronger confirmation)
            if len(closes) < 3:
                return

            if not (closes[-1] > closes[-2] > closes[-3]):
                return

            if self.already_sent_recent(symbol):
                return

            # ── Breakout % above 120-day high ─────────────────────────────
            breakout_pct = round(((recent_5_max - past_120_max) / past_120_max) * 100, 2)
            vol_ratio    = round(current_volume / avg_5_volume, 2)

            message = (
                f"\n🔥 JINNING EFFECT 🔥\n"
                f"{symbol} → BUY\n"
                f"₹{round(close_price, 2)}\n\n"
                f"✅ 5-Day High breaks 120D High by +{breakout_pct}%\n"
                f"✅ Volume {vol_ratio}x above 5D average\n"
                f"✅ 2 Consecutive Strong Closes\n"
            )

            try:
                send_alert(message)
            finally:
                self.signal_history[symbol] = time.time()


# =========================
# ✅ NSE MARKET MOVERS
# =========================

class NSEMarketMovers:

    def __init__(self):
        self.session   = requests.Session()
        self.last_sent = 0
        self.INTERVAL  = 120  # 2 minutes
        self.headers   = {
            "User-Agent": "Mozilla/5.0"
        }

    def run(self):
        if time.time() - self.last_sent < self.INTERVAL:
            return
        try:
            self.session.get(
                "https://www.nseindia.com",
                headers=self.headers,
                timeout=10
            )
            gainers = self.session.get(
                "https://www.nseindia.com/api/live-analysis-variations?index=gainers",
                headers=self.headers,
                timeout=10
            ).json()
            losers = self.session.get(
                "https://www.nseindia.com/api/live-analysis-variations?index=losers",
                headers=self.headers,
                timeout=10
            ).json()

            gainers_list = []
            losers_list  = []

            for v in gainers.values():
                if isinstance(v, list):
                    gainers_list.extend(v)
            for v in losers.values():
                if isinstance(v, list):
                    losers_list.extend(v)

            gainers_list = sorted(
                gainers_list,
                key=lambda x: float(x.get("perChange", 0)),
                reverse=True
            )[:10]
            losers_list = sorted(
                losers_list,
                key=lambda x: float(x.get("perChange", 0))
            )[:10]

            msg = "📈 TOP 10 GAINERS\n\n"
            for i, s in enumerate(gainers_list, 1):
                msg += f"{i}. {s['symbol']} ({s['perChange']}%)\n"

            msg += "\n📉 TOP 10 LOSERS\n\n"
            for i, s in enumerate(losers_list, 1):
                msg += f"{i}. {s['symbol']} ({s['perChange']}%)\n"

            send_alert(msg)
            self.last_sent = time.time()

        except Exception as e:
            print("[MARKET MOVERS ERROR]", e)


multi_strategy    = MultiSignalStrategy()
pullback_strategy = PullbackStrategy()
jinning_strategy  = JinningEffectStrategy()
market_movers     = NSEMarketMovers()


def market_movers_worker():
    while True:
        try:
            market_movers.run()
        except Exception as e:
            print("[MOVERS THREAD ERROR]", e)
        time.sleep(10)


threading.Thread(
    target=market_movers_worker,
    daemon=True
).start()