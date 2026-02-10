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

import pandas as pd

