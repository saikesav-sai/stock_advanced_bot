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

