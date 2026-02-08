from datetime import datetime
import numpy as np
import pandas as pd


class Strategy1:
    """
    PDH/PDL Breakout Strategy with EMA, VWAP, and Volume confirmation
    """

    def __init__(self):
        # Strategy parameters
        self.EMA_LEN = 50
        self.VOL_LEN = 20
        self.VOL_MULT = 0.5  # Relaxed - only need 50% volume increase
        self.RR = 1.2  # Risk-reward ratio
        self.VWAP_DIST = 0.01  # VWAP distance threshold
        self.SL_BUFFER = 0.08  # Stop loss buffer percentage

        self.trade_start = 915
        self.trade_end = 1525

        # State
        self.active_position = None
        self.pdh = None
        self.pdl = None
        self.today_date = None

        # Note: long_taken_today and short_taken_today removed as they were never used
        # Add them back if you want to limit to one trade per direction per day

    def set_pdh_pdl(self, pdh, pdl):
        """Set previous day high/low for the strategy"""
        self.pdh = pdh
        self.pdl = pdl

    def reset_daily_state(self, new_date):
        """Reset daily state when new trading day starts"""
        self.today_date = new_date
        self.active_position = None

    def calculate_indicators(self, df):
        """Calculate technical indicators on the dataframe"""
        df = df.copy()
        df["EMA"] = df["close"].ewm(span=self.EMA_LEN).mean()
        df["VWAP"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
        df["VolMA"] = df["volume"].rolling(self.VOL_LEN).mean()
        return df

    def process(self, df, symbol=None):
        """
        Main strategy processing logic

        Args:
            df: DataFrame with OHLCV data and timestamp
            symbol: Optional symbol name for logging

        Returns:
            dict with signal information or None
        """
        MIN_CANDLES = self.EMA_LEN + 10
        if len(df) < MIN_CANDLES:
            return None

        # Calculate indicators
        df = self.calculate_indicators(df)

        # Get current and previous candle
        row = df.iloc[-1]
        prev = df.iloc[-2]

        # Date change reset
        cur_date = row["timestamp"].date()
        if self.today_date != cur_date:
            self.reset_daily_state(cur_date)

            # Compute PDH/PDL from yesterday's data
            prev_data = df[df["timestamp"].dt.date != cur_date]
            if len(prev_data) > 0:
                self.pdh = prev_data["high"].max()
                self.pdl = prev_data["low"].min()

        # Check if we can trade (within trading hours)
        curTime = row.timestamp.hour * 100 + row.timestamp.minute
        can_trade = (self.trade_start <= curTime <= self.trade_end)

        # Volume check - handle NaN VolMA
        if pd.isna(row.VolMA):
            vol_ok = False
        else:
            vol_ok = row.volume > row.VolMA * self.VOL_MULT

        # VWAP distance check
        dist_pct = abs(row.close - row.VWAP) / row.VWAP * 100
        vwap_ok = dist_pct >= self.VWAP_DIST

        # Trend detection
        uptrend = row.close > row.EMA
        downtrend = row.close < row.EMA

        # Breakout detection
        long_break = self.pdh is not None and row.high > self.pdh
        short_break = self.pdl is not None and row.low < self.pdl

        # ===============================
        # HANDLE OPEN POSITION
        # ===============================
        if self.active_position:
            pos = self.active_position
            entry_price = pos["entry"]
            sl = pos["sl"]
            tp = pos["tp"]

            if pos["side"] == "LONG":
                if row.low <= sl:
                    self.active_position = None
                    return {"signal": "EXIT", "reason": "SL HIT", "exit_price": sl}

                if row.high >= tp:
                    self.active_position = None
                    return {"signal": "EXIT", "reason": "TP HIT", "exit_price": tp}

            if pos["side"] == "SHORT":
                if row.high >= sl:
                    self.active_position = None
                    return {"signal": "EXIT", "reason": "SL HIT", "exit_price": sl}

                if row.low <= tp:
                    self.active_position = None
                    return {"signal": "EXIT", "reason": "TP HIT", "exit_price": tp}

            return None

        # ===============================
        # ENTRY: LONG
        # ===============================
        if (
            can_trade and
            not self.active_position and
            vol_ok and
            vwap_ok and
            uptrend and
            long_break
        ):
            sl_vwap = row.VWAP * (1 - self.SL_BUFFER/100)
            sl = min(sl_vwap, row.low)

            if sl < row.close:
                risk = row.close - sl
                tp = row.close + risk * self.RR

                self.active_position = {
                    "side": "LONG",
                    "entry": row.close,
                    "sl": sl,
                    "tp": tp
                }
                return {"signal": "BUY", "entry_price": row.close, "sl": sl, "tp": tp}

        # ===============================
        # ENTRY: SHORT
        # ===============================
        if (
            can_trade and
            not self.active_position and
            vol_ok and
            vwap_ok and
            downtrend and
            short_break
        ):
            sl_vwap = row.VWAP * (1 + self.SL_BUFFER/100)
            sl = max(sl_vwap, row.high)

            if sl > row.close:
                risk = sl - row.close
                tp = row.close - risk * self.RR

                self.active_position = {
                    "side": "SHORT",
                    "entry": row.close,
                    "sl": sl,
                    "tp": tp
                }
                return {"signal": "SELL", "entry_price": row.close, "sl": sl, "tp": tp}

        return None

class Strategy2:

    """
    RMS Intraday Momentum Strategy (Renko + MACD + MACD-slope)

    Research grounding (provided papers only):
    - Uses Renko trend strength (Renko bar count / momentum)
    - Uses MACD line vs Signal line
    - Uses slope comparison over last 5 periods (MACD slope vs Signal slope)
    - Intraday-only: hard exit before/at market close, no overnight positions

    Notes:
    - Uses 5-minute OHLCV candles.
    - Designed to run candle-by-candle with no lookahead.
    - No TP/SL added (not specified in the RMS paper excerpt); exits are RMS + time exit.
    """

    def __init__(self):
        # ===== Parameters (chosen defaults) =====
        # Trading hours (you requested 09:20 to 15:30)
        self.trade_start = 920          # allow entries from 09:20
        self.trade_end = 1525           # latest entry time (leave a few minutes buffer)
        self.hard_exit_time = 1530      # force flat at/after 15:30

        # Renko (fixed percent brick to avoid adding ATR indicator)
        self.RENKO_BRICK_PCT = 0.25     # 0.25% brick size
        self.RENKO_MIN_BARS = 2         # >=2 for buy, <=-2 for sell

        # MACD
        self.MACD_FAST = 12
        self.MACD_SLOW = 26
        self.MACD_SIGNAL = 9

        # Slope settings (paper uses last five periods)
        self.SLOPE_LEN = 5

        # ===== State =====
        self.active_position = None
        self.today_date = None

    def reset_daily_state(self, new_date):
        """Reset daily state when new trading day starts"""
        self.today_date = new_date
        self.active_position = None

    def calculate_indicators(self, df):
        """Calculate technical indicators on the dataframe (no future data)."""
        df = df.copy()

        # --- MACD ---
        ema_fast = df["close"].ewm(span=self.MACD_FAST).mean()
        ema_slow = df["close"].ewm(span=self.MACD_SLOW).mean()
        df["MACD"] = ema_fast - ema_slow
        df["MACD_SIGNAL"] = df["MACD"].ewm(span=self.MACD_SIGNAL).mean()

        # --- Slopes (linear regression slope over last SLOPE_LEN points) ---
        def _rolling_slope(series, window):
            values = series.values
            out = np.full(len(values), np.nan, dtype=float)
            x = np.arange(window, dtype=float)

            for i in range(window - 1, len(values)):
                y = values[i - window + 1 : i + 1]
                if np.any(np.isnan(y)):
                    continue
                # slope of best-fit line
                out[i] = np.polyfit(x, y, 1)[0]
            return out

        df["macd_slope"] = _rolling_slope(df["MACD"], self.SLOPE_LEN)
        df["signal_slope"] = _rolling_slope(df["MACD_SIGNAL"], self.SLOPE_LEN)

        # --- Renko bar count (consecutive bricks in current direction) ---
        closes = df["close"].values.astype(float)
        renko_bar_num = np.full(len(closes), np.nan, dtype=float)

        if len(closes) > 0:
            last_brick_price = closes[0]
            direction = 0  # -1, 0, +1
            bar_num = 0

            for i in range(len(closes)):
                price = closes[i]
                if price <= 0 or np.isnan(price):
                    continue

                brick = (self.RENKO_BRICK_PCT / 100.0) * price
                if brick <= 0:
                    continue

                moved = True
                while moved:
                    moved = False

                    if price >= last_brick_price + brick:
                        last_brick_price = last_brick_price + brick
                        if direction >= 0:
                            bar_num = bar_num + 1
                        else:
                            bar_num = 1
                        direction = 1
                        moved = True

                    elif price <= last_brick_price - brick:
                        last_brick_price = last_brick_price - brick
                        if direction <= 0:
                            bar_num = bar_num - 1
                        else:
                            bar_num = -1
                        direction = -1
                        moved = True

                renko_bar_num[i] = bar_num

        df["renko_bar_num"] = renko_bar_num

        return df

    def process(self, df, symbol=None):
        """
        Main strategy processing logic (candle-by-candle, no lookahead).

        Args:
            df: DataFrame with columns: timestamp, open, high, low, close, volume
            symbol: Optional symbol for logging

        Returns:
            dict with signal info or None
        """
        # Minimum candles to have stable MACD + signal + slopes
        MIN_CANDLES = self.MACD_SLOW + self.MACD_SIGNAL + self.SLOPE_LEN + 5
        if len(df) < MIN_CANDLES:
            return None

        df = self.calculate_indicators(df)

        row = df.iloc[-1]
        prev = df.iloc[-2]

        # Date change reset
        cur_date = row["timestamp"].date()
        if self.today_date != cur_date:
            self.reset_daily_state(cur_date)

        # Current time HHMM
        curTime = row.timestamp.hour * 100 + row.timestamp.minute

        # Entry window
        can_enter = (self.trade_start <= curTime <= self.trade_end)

        # Indicator readiness
        if (
            pd.isna(row.renko_bar_num) or
            pd.isna(row.MACD) or
            pd.isna(row.MACD_SIGNAL) or
            pd.isna(row.macd_slope) or
            pd.isna(row.signal_slope)
        ):
            return None

        # RMS conditions
        long_ok = (
            row.renko_bar_num >= self.RENKO_MIN_BARS and
            row.MACD > row.MACD_SIGNAL and
            row.macd_slope > row.signal_slope
        )

        short_ok = (
            row.renko_bar_num <= -self.RENKO_MIN_BARS and
            row.MACD < row.MACD_SIGNAL and
            row.macd_slope < row.signal_slope
        )

        # ===============================
        # HANDLE OPEN POSITION
        # ===============================
        if self.active_position:
            pos = self.active_position

            # Hard exit at/after market close (intraday-only)
            if curTime >= self.hard_exit_time:
                self.active_position = None
                return {
                    "signal": "EXIT",
                    "reason": "HARD EOD EXIT",
                    "exit_price": row.close,
                    "side": pos["side"],
                }

            # RMS exits (paper-defined style: MACD cross + slope reversal)
            if pos["side"] == "LONG":
                if (row.MACD < row.MACD_SIGNAL) and (row.macd_slope < row.signal_slope):
                    self.active_position = None
                    return {
                        "signal": "EXIT",
                        "reason": "RMS EXIT (MACD DOWN + SLOPE DOWN)",
                        "exit_price": row.close,
                        "side": "LONG",
                    }

            if pos["side"] == "SHORT":
                if (row.MACD > row.MACD_SIGNAL) and (row.macd_slope > row.signal_slope):
                    self.active_position = None
                    return {
                        "signal": "EXIT",
                        "reason": "RMS EXIT (MACD UP + SLOPE UP)",
                        "exit_price": row.close,
                        "side": "SHORT",
                    }

            return None

        # ===============================
        # ENTRY: LONG
        # ===============================
        if can_enter and (not self.active_position) and long_ok:
            self.active_position = {
                "side": "LONG",
                "entry": row.close,
                "entry_time": row.timestamp,
            }
            return {
                "signal": "BUY",
                "entry_price": row.close,
                "reason": "RMS LONG (RENKO+MACD+SLOPE)",
            }

        # ===============================
        # ENTRY: SHORT
        # ===============================
        if can_enter and (not self.active_position) and short_ok:
            self.active_position = {
                "side": "SHORT",
                "entry": row.close,
                "entry_time": row.timestamp,
            }
            return {
                "signal": "SELL",
                "entry_price": row.close,
                "reason": "RMS SHORT (RENKO+MACD+SLOPE)",
            }

        # If we are past hard exit time, ensure no new trades
        if curTime >= self.hard_exit_time:
            return None

        return None

class Strategy3:
    """
    Intraday Momentum Capture (IMC) Strategy

    Two-layer signal system:
      Layer 1: Directional bias from ROD/ONFH sign agreement
               (Motwani et al., Hedging Demand and Intraday Momentum)
      Layer 2: RMS entry trigger — Renko + MACD + Slope + Volume
               (Soorej & James, Profitable Intraday Momentum Using RMS Algorithm)

    Designed for Indian small/mid-cap equities on 5-minute OHLCV data.
    Intraday only — all positions closed by 15:10.
    """

    def __init__(self):
        # ---- Indicator Parameters ----
        self.MACD_FAST = 12
        self.MACD_SLOW = 26
        self.MACD_SIGNAL = 9
        self.SLOPE_LEN = 5              # Bars for MACD / Signal slope regression
        self.ATR_LEN = 14               # ATR lookback
        self.RENKO_ATR_MULT = 0.5       # Brick size = 0.5 * previous day ATR
        self.RENKO_MIN_BRICKS = 2       # Min consecutive same-direction bricks
        self.VOL_MA_LEN = 20            # Volume moving-average period
        self.VOL_MULT = 1.2             # Volume must exceed 1.2x VolMA

        # ---- Risk Parameters ----
        self.SL_PCT = 0.005             # 0.5 % stop loss from entry
        self.TP_PCT = 0.01              # 1.0 % take profit (2:1 RR)
        self.TRAIL_ACTIVATE = 0.005     # Activate trailing after 0.5 % unrealised profit
        self.TRAIL_PCT = 0.003          # Trail 0.3 % from peak close

        # ---- Directional Bias Parameters ----
        self.ROD_MIN_MAG = 0.003        # Min |ROD| for non-neutral bias (0.3 %)

        # ---- Volatility Guard ----
        self.ATR_SPIKE_ENTRY = 2.0      # Skip entry if TR > 2x avg TR
        self.ATR_SPIKE_EXIT = 3.0       # Force exit if TR > 3x avg TR

        # ---- Time Windows (HHMM int format) ----
        self.trade_start = 1030         # Earliest new-entry time
        self.trade_end = 1500           # Latest new-entry time
        self.hard_exit_time = 1510      # Force-close all positions
        self.onfh_time = 1015           # Capture ONFH price at this bar
        self.lunch_start = 1230         # Lunch lull start — no new entries
        self.lunch_end = 1330           # Lunch lull end

        # ---- State ----
        self.active_position = None
        self.today_date = None
        self.prev_close = None          # Yesterday's closing price
        self.onfh_price = None          # Price captured at 10:15 today

        # Renko state (reset daily)
        self.renko_brick_size = None
        self.renko_ref_price = None
        self.renko_direction = 0        # 1 = up, -1 = down, 0 = no bricks yet
        self.renko_consec = 0           # +N = up bricks, -N = down bricks

        # Trailing-stop tracker
        self.peak_since_entry = None    # Best close since entry (high for long, low for short)

    # ------------------------------------------------------------------
    # Daily reset
    # ------------------------------------------------------------------
    def reset_daily_state(self, new_date):
        """Reset all intraday state at the start of a new trading day."""
        self.today_date = new_date
        self.active_position = None
        self.onfh_price = None
        self.renko_direction = 0
        self.renko_consec = 0
        self.renko_ref_price = None
        self.renko_brick_size = None
        self.peak_since_entry = None

    # ------------------------------------------------------------------
    # Indicator calculation
    # ------------------------------------------------------------------
    def calculate_indicators(self, df):
        """
        Calculate MACD, MACD/Signal slopes, Volume MA, True Range
        on the full dataframe.  Called once per process() invocation.
        """
        df = df.copy()

        # --- MACD ---
        ema_fast = df["close"].ewm(span=self.MACD_FAST, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.MACD_SLOW, adjust=False).mean()
        df["MACD"] = ema_fast - ema_slow
        df["MACD_Signal"] = df["MACD"].ewm(span=self.MACD_SIGNAL, adjust=False).mean()

        # --- Slopes (linear-regression slope over SLOPE_LEN bars) ---
        slope_x = np.arange(self.SLOPE_LEN, dtype=float)

        def _slope(y):
            if np.any(np.isnan(y)):
                return np.nan
            return np.polyfit(slope_x, y, 1)[0]

        df["MACD_Slope"] = (
            df["MACD"]
            .rolling(self.SLOPE_LEN)
            .apply(_slope, raw=True)
        )
        df["Signal_Slope"] = (
            df["MACD_Signal"]
            .rolling(self.SLOPE_LEN)
            .apply(_slope, raw=True)
        )

        # --- Volume MA ---
        df["VolMA"] = df["volume"].rolling(self.VOL_MA_LEN).mean()

        # --- True Range & ATR ---
        prev_close_col = df["close"].shift(1)
        df["TR"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                (df["high"] - prev_close_col).abs(),
                (df["low"] - prev_close_col).abs(),
            ),
        )
        df["ATR"] = df["TR"].rolling(self.ATR_LEN).mean()
        df["TR_MA"] = df["TR"].rolling(self.VOL_MA_LEN).mean()

        return df

    # ------------------------------------------------------------------
    # Renko helper (stateful, called once per bar)
    # ------------------------------------------------------------------
    def _update_renko(self, close_price):
        """
        Update the Renko brick count from a new close price.
        Brick size is fixed at start of day.
        """
        if (
            self.renko_ref_price is None
            or self.renko_brick_size is None
            or self.renko_brick_size <= 0
        ):
            return

        delta = close_price - self.renko_ref_price

        if delta >= self.renko_brick_size:
            n = int(delta / self.renko_brick_size)
            self.renko_ref_price += n * self.renko_brick_size
            if self.renko_direction == 1:
                self.renko_consec += n
            else:
                self.renko_direction = 1
                self.renko_consec = n

        elif delta <= -self.renko_brick_size:
            n = int(abs(delta) / self.renko_brick_size)
            self.renko_ref_price -= n * self.renko_brick_size
            if self.renko_direction == -1:
                self.renko_consec -= n          # more negative
            else:
                self.renko_direction = -1
                self.renko_consec = -n

    # ------------------------------------------------------------------
    # Directional bias helper (Layer 1)
    # ------------------------------------------------------------------
    def _get_directional_bias(self, r_rod, r_onfh):
        """
        Classify directional bias from ROD/ONFH sign agreement.

        Returns one of: 'LONG_BIAS', 'SHORT_BIAS', 'NEUTRAL'
        """
        if r_onfh is None or abs(r_rod) < self.ROD_MIN_MAG:
            return "NEUTRAL"

        same_sign = (r_rod > 0 and r_onfh > 0) or (r_rod < 0 and r_onfh < 0)
        if same_sign:
            return "LONG_BIAS" if r_rod > 0 else "SHORT_BIAS"
        return "NEUTRAL"

    # ------------------------------------------------------------------
    # Main processing (candle-by-candle)
    # ------------------------------------------------------------------
    def process(self, df, symbol=None):
        """
        Main strategy logic — called once per new 5-minute bar.

        Args:
            df: DataFrame with columns
                [timestamp, open, high, low, close, volume].
                Must contain at least 3 days of 5-min history ending
                at the current bar.
            symbol: Optional symbol name for logging.

        Returns:
            dict  {"signal": "BUY"|"SELL"|"EXIT", ...}  or  None
        """
        # Minimum bars for MACD + signal + slope to be valid
        MIN_CANDLES = self.MACD_SLOW + self.MACD_SIGNAL + self.SLOPE_LEN
        if len(df) < MIN_CANDLES:
            return None

        # Calculate indicators on full history
        df = self.calculate_indicators(df)

        # Current and previous candle
        row = df.iloc[-1]
        prev = df.iloc[-2]

        # ============================================================
        # DATE CHANGE DETECTION
        # ============================================================
        cur_date = row.timestamp.date()

        if self.today_date != cur_date:
            # Derive yesterday's close and ATR from previous-day bars
            prev_day_data = df[df["timestamp"].dt.date < cur_date]
            new_prev_close = None
            new_brick_size = None
            if len(prev_day_data) > 0:
                new_prev_close = prev_day_data.iloc[-1].close
                last_atr = prev_day_data.iloc[-1].ATR
                if not pd.isna(last_atr) and last_atr > 0:
                    new_brick_size = self.RENKO_ATR_MULT * last_atr

            # Defensive: force-close if position survived overnight
            had_position = self.active_position is not None

            # Reset daily state
            self.reset_daily_state(cur_date)
            self.prev_close = new_prev_close
            self.renko_brick_size = new_brick_size
            self.renko_ref_price = new_prev_close

            if had_position:
                return {
                    "signal": "EXIT",
                    "reason": "DAY CHANGE",
                    "exit_price": prev.close,
                }

        # ============================================================
        # CURRENT TIME
        # ============================================================
        cur_time = row.timestamp.hour * 100 + row.timestamp.minute
        in_lunch = self.lunch_start <= cur_time <= self.lunch_end
        can_trade = (
            self.trade_start <= cur_time <= self.trade_end
            and not in_lunch
        )

        # ============================================================
        # CAPTURE ONFH PRICE (once per day, at first bar >= 10:15)
        # ============================================================
        if self.onfh_price is None and cur_time >= self.onfh_time:
            self.onfh_price = row.close

        # ============================================================
        # UPDATE RENKO STATE
        # ============================================================
        self._update_renko(row.close)

        # ============================================================
        # COMPUTE ROD / ONFH RETURNS & DIRECTIONAL BIAS (Layer 1)
        # ============================================================
        r_rod = None
        r_onfh = None
        if self.prev_close is not None and self.prev_close > 0:
            r_rod = (row.close / self.prev_close) - 1.0
            if self.onfh_price is not None:
                r_onfh = (self.onfh_price / self.prev_close) - 1.0

        bias = "NEUTRAL"
        if r_rod is not None:
            bias = self._get_directional_bias(r_rod, r_onfh)

        # ============================================================
        # VOLUME CONFIRMATION
        # ============================================================
        if pd.isna(row.VolMA) or row.VolMA <= 0:
            vol_ok = False
        else:
            vol_ok = row.volume > row.VolMA * self.VOL_MULT

        # ============================================================
        # ATR SPIKE GUARDS
        # ============================================================
        atr_entry_ok = True
        atr_exit_ok = True
        if not pd.isna(row.TR) and not pd.isna(row.TR_MA) and row.TR_MA > 0:
            atr_entry_ok = row.TR <= self.ATR_SPIKE_ENTRY * row.TR_MA
            atr_exit_ok = row.TR <= self.ATR_SPIKE_EXIT * row.TR_MA

        # ============================================================
        # MACD CONDITIONS (Layer 2 — part 1)
        # ============================================================
        macd_valid = (
            not pd.isna(row.MACD)
            and not pd.isna(row.MACD_Signal)
            and not pd.isna(row.MACD_Slope)
            and not pd.isna(row.Signal_Slope)
        )

        macd_long = (
            macd_valid
            and row.MACD > row.MACD_Signal
            and row.MACD_Slope > row.Signal_Slope
        )
        macd_short = (
            macd_valid
            and row.MACD < row.MACD_Signal
            and row.MACD_Slope < row.Signal_Slope
        )

        # ============================================================
        # RENKO CONDITIONS (Layer 2 — part 2)
        # ============================================================
        renko_long = self.renko_consec >= self.RENKO_MIN_BRICKS
        renko_short = self.renko_consec <= -self.RENKO_MIN_BRICKS

        # ===============================
        # HANDLE OPEN POSITION
        # ===============================
        if self.active_position:
            pos = self.active_position
            entry = pos["entry"]
            side = pos["side"]

            # --- Time stop (absolute priority) ---
            if cur_time >= self.hard_exit_time:
                self.active_position = None
                return {
                    "signal": "EXIT",
                    "reason": "TIME STOP",
                    "exit_price": row.close,
                }

            # --- Volatility exit ---
            if not atr_exit_ok:
                self.active_position = None
                return {
                    "signal": "EXIT",
                    "reason": "VOLATILITY SPIKE",
                    "exit_price": row.close,
                }

            # ----- LONG exits -----
            if side == "LONG":
                # Track peak close since entry
                self.peak_since_entry = max(self.peak_since_entry, row.close)

                # Effective SL: original or trailing, whichever is tighter
                effective_sl = pos["sl"]
                unrealised_pct = (self.peak_since_entry - entry) / entry
                if unrealised_pct >= self.TRAIL_ACTIVATE:
                    trail_sl = self.peak_since_entry * (1 - self.TRAIL_PCT)
                    effective_sl = max(effective_sl, trail_sl)

                # SL hit
                if row.low <= effective_sl:
                    reason = "TRAIL SL" if effective_sl > pos["sl"] else "SL HIT"
                    self.active_position = None
                    return {
                        "signal": "EXIT",
                        "reason": reason,
                        "exit_price": effective_sl,
                    }

                # TP hit
                if row.high >= pos["tp"]:
                    self.active_position = None
                    return {
                        "signal": "EXIT",
                        "reason": "TP HIT",
                        "exit_price": pos["tp"],
                    }

                # Signal reversal (MACD flips bearish)
                if macd_short:
                    self.active_position = None
                    return {
                        "signal": "EXIT",
                        "reason": "SIGNAL REVERSAL",
                        "exit_price": row.close,
                    }

                # Persist tighter SL for next bar
                pos["sl"] = effective_sl

            # ----- SHORT exits -----
            elif side == "SHORT":
                # Track trough close since entry
                self.peak_since_entry = min(self.peak_since_entry, row.close)

                # Effective SL: original or trailing, whichever is tighter
                effective_sl = pos["sl"]
                unrealised_pct = (entry - self.peak_since_entry) / entry
                if unrealised_pct >= self.TRAIL_ACTIVATE:
                    trail_sl = self.peak_since_entry * (1 + self.TRAIL_PCT)
                    effective_sl = min(effective_sl, trail_sl)

                # SL hit
                if row.high >= effective_sl:
                    reason = "TRAIL SL" if effective_sl < pos["sl"] else "SL HIT"
                    self.active_position = None
                    return {
                        "signal": "EXIT",
                        "reason": reason,
                        "exit_price": effective_sl,
                    }

                # TP hit
                if row.low <= pos["tp"]:
                    self.active_position = None
                    return {
                        "signal": "EXIT",
                        "reason": "TP HIT",
                        "exit_price": pos["tp"],
                    }

                # Signal reversal (MACD flips bullish)
                if macd_long:
                    self.active_position = None
                    return {
                        "signal": "EXIT",
                        "reason": "SIGNAL REVERSAL",
                        "exit_price": row.close,
                    }

                # Persist tighter SL for next bar
                pos["sl"] = effective_sl

            return None

        # ===============================
        # ENTRY: LONG
        # ===============================
        if (
            can_trade
            and not self.active_position
            and bias in ("LONG_BIAS", "NEUTRAL")
            and renko_long
            and macd_long
            and vol_ok
            and atr_entry_ok
        ):
            sl = row.close * (1 - self.SL_PCT)
            tp = row.close * (1 + self.TP_PCT)

            self.active_position = {
                "side": "LONG",
                "entry": row.close,
                "sl": sl,
                "tp": tp,
            }
            self.peak_since_entry = row.close

            return {
                "signal": "BUY",
                "entry_price": row.close,
                "sl": sl,
                "tp": tp,
            }

        # ===============================
        # ENTRY: SHORT
        # ===============================
        if (
            can_trade
            and not self.active_position
            and bias in ("SHORT_BIAS", "NEUTRAL")
            and renko_short
            and macd_short
            and vol_ok
            and atr_entry_ok
        ):
            sl = row.close * (1 + self.SL_PCT)
            tp = row.close * (1 - self.TP_PCT)

            self.active_position = {
                "side": "SHORT",
                "entry": row.close,
                "sl": sl,
                "tp": tp,
            }
            self.peak_since_entry = row.close

            return {
                "signal": "SELL",
                "entry_price": row.close,
                "sl": sl,
                "tp": tp,
            }

        return None
