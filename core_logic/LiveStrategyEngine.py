import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytz

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core_logic.logger_config import get_logger
from database_logic.candle_db import CandleDB
from database_logic.fetch_historical_candles import UpstoxHistoricalFetcher

logger = get_logger()


class LiveStrategyEngine:
    def __init__(self, symbol=None, instrument_key=None):
        self.symbol = symbol  # ISIN code (e.g., INE467B01029)
        self.instrument_key = instrument_key  # Full key (e.g., NSE_EQ|INE467B01029)
        self.IST = pytz.timezone('Asia/Kolkata')
        
        # Get absolute path to root folder's market_data.db
        root_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        db_path = os.path.join(root_folder, 'market_data.db')
        self.db = CandleDB(db_path=db_path)
        
        self.df = pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
        self.current_minute = None
        self.minute=None
        # State
        self.long_taken_today = False
        self.short_taken_today = False
        self.active_position = None
        self.pdh = None
        self.pdl = None
        self.today_date = None
        
        # Load historical data from DB
        if self.symbol:
            self._load_historical_data()

        # Strategy parameters
        self.EMA_LEN = 200
        self.VOL_LEN = 20 # set to 20
        self.VOL_MULT = 1.5
        self.RR = 1.6
        self.VWAP_DIST = 0.15
        self.SL_BUFFER = 0.08

        self.trade_start = 915
        self.trade_end = 1525

    def fetch_last_3_working_days(self):
        """Fetch the last 3 working days as strings in 'YYYY-MM-DD' format"""
        today = datetime.now().date()
        working_days = []
        day_offset = 1  # Start from yesterday

        while len(working_days) < int(os.getenv("STOCK_DAYS_NEED", "3")):
            target_date = today - timedelta(days=day_offset)
            day_offset += 1

            # Skip weekends
            if target_date.weekday() >= 5:  # Saturday=5, Sunday=6
                continue

            working_days.append(target_date.strftime("%Y-%m-%d"))

        working_days.reverse()  # Earliest date first
        return working_days[0], working_days[-1]

    def _load_historical_data(self):
        """Load historical candles from database, fetch if not found"""
        today = datetime.now().strftime("%Y-%m-%d")
        

        # Try to load last 3 working days of candles from DB 
        start_date,end_date= self.fetch_last_3_working_days()
        self.db.cleanup_old_candles(days_to_keep=int(os.getenv("STOCK_DAYS_NEED", "3")))
        df = self.db.get_candles(self.symbol, start_date=start_date, end_date=end_date, interval=os.getenv("INTERVAL", "5m"))
        
        logger.info(f"[{self.symbol}] Historical data preview:")
        logger.info(f"[{self.symbol}] {df.tail(3).to_string()}")
    
         
        if not self.instrument_key:
            logger.warning(f"[{self.symbol}] Warning: instrument_key not provided, cannot fetch historical data")
            return
        
        # Fetch historical data
        fetcher = UpstoxHistoricalFetcher()
        fetcher.fetch_and_store_candles(self.instrument_key, days=int(os.getenv("STOCK_DAYS_NEED", "3")))
        fetcher.close()
        
        # Reload from DB
        df = self.db.get_candles(self.symbol, interval=os.getenv("INTERVAL", "5m"))
    
        if len(df) > 0:
            # Convert to numeric types immediately
            df["open"] = pd.to_numeric(df["open"], errors='coerce')
            df["high"] = pd.to_numeric(df["high"], errors='coerce')
            df["low"] = pd.to_numeric(df["low"], errors='coerce')
            df["close"] = pd.to_numeric(df["close"], errors='coerce')
            df["volume"] = pd.to_numeric(df["volume"], errors='coerce')
            
            self.df = df
            logger.info(f"[{self.symbol}] Loaded {len(self.df)} historical candles from database")
            
            # Calculate PDH/PDL from yesterday's data
            self.pdh, self.pdl = self.db.get_previous_day_high_low(self.symbol, today)
            if self.pdh and self.pdl:
                logger.info(f"[{self.symbol}] PDH: {self.pdh}, PDL: {self.pdl}")
        else:
            logger.info(f"[{self.symbol}] No historical data available")
    
    def _save_completed_candle(self, candle_data):
        """Save a completed candle to the database"""
        try:
            self.db.insert_candle(
                symbol=self.symbol,
                timestamp=candle_data['timestamp'],
                open_price=candle_data['open'],
                high=candle_data['high'],
                low=candle_data['low'],
                close=candle_data['close'],
                volume=candle_data['volume'],
                interval='5m'
            )
        except Exception as e:
            logger.error(f"[{self.symbol}] Error saving candle to DB: {e}")

    # ---------------------------------------------
    # Update candle from live tick
    # ---------------------------------------------
    def update_candle(self, tick):
        ts = int(tick["marketFF"]["ltpc"]["ltt"]) // 1000
        # Unix timestamp is always UTC, convert to IST as naive datetime
        ts = datetime.utcfromtimestamp(ts)
        # Add IST offset manually (UTC + 5:30)
        from datetime import timedelta
        ts = ts + timedelta(hours=5, minutes=30)
        price = tick["marketFF"]["ltpc"]["ltp"]
        vol = int(tick["marketFF"]["ltpc"]["ltq"])

        # Round timestamp to nearest 5-minute interval
        minute_ts = ts.replace(second=0, microsecond=0)
        minute_ts = minute_ts.replace(minute=(minute_ts.minute // 5) * 5)

        # every 5 minutes create new candle
        if self.current_minute != minute_ts:
            # Save the previous completed candle to DB
            if self.current_minute is not None and len(self.df) > 0:
                last_candle = self.df.iloc[-1]
                self._save_completed_candle({
                    'timestamp': last_candle['timestamp'],
                    'open': last_candle['open'],
                    'high': last_candle['high'],
                    'low': last_candle['low'],
                    'close': last_candle['close'],
                    'volume': last_candle['volume']
                })
            
            self.current_minute = minute_ts
            # Ensure numeric types
            self.df.loc[len(self.df)] = [minute_ts, float(price), float(price), float(price), float(price), float(vol)]
            logger.info(f"[{self.symbol}] New 5-min candle created | df length: {len(self.df)} | Time: {minute_ts}")
            logger.info(f"[{self.symbol}] Last 3 candles: {self.df.tail(3).to_string()}")
        else:
            # Update candle
            idx = self.df.index[-1]
            self.df.at[idx, "high"] = max(self.df.at[idx, "high"], price)
            self.df.at[idx, "low"] = min(self.df.at[idx, "low"], price)
            self.df.at[idx, "close"] = price
            self.df.at[idx, "volume"] += vol

        return self.process_strategy()

    
    def process_strategy(self):
        if len(self.df) < 210:
            logger.info(f"[{self.symbol}] Not enough data for strategy processing ({len(self.df)}/210 candles)")
            return None

        df = self.df.copy()
        
        # Date change reset
        cur_date = df.iloc[-1]["timestamp"].date()
        if self.today_date != cur_date:
            self.today_date = cur_date
            self.long_taken_today = False
            self.short_taken_today = False

            # Compute PDH/PDL from yesterday
            prev = df[df["timestamp"].dt.date != cur_date]
            if len(prev) > 0:
                self.pdh = prev["high"].max()
                self.pdl = prev["low"].min()
        # Indicators
        
        df["EMA200"] = df["close"].ewm(span=self.EMA_LEN).mean()
        df["VWAP"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
        df["VolMA"] = df["volume"].rolling(self.VOL_LEN).mean()
        
        
        
        
        
        
        

        row = df.iloc[-1]
        prev = df.iloc[-2]

        curTime = row.timestamp.hour * 100 + row.timestamp.minute
        can_trade = (self.trade_start <= curTime <= self.trade_end)


        # Volume OK - handle NaN VolMA
        if pd.isna(row.VolMA):
            vol_ok = False
        else:
            vol_ok = row.volume > row.VolMA * self.VOL_MULT
        # VWAP distance
        dist_pct = abs(row.close - row.VWAP) / row.VWAP * 100
        vwap_ok = dist_pct >= self.VWAP_DIST

        # Trend
        uptrend = row.close > row.EMA200
        downtrend = row.close < row.EMA200

        # Breakouts
        long_break = self.pdh is not None and row.close > self.pdh and prev.close <= self.pdh
        short_break = self.pdl is not None and row.close < self.pdl and prev.close >= self.pdl

            

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
                    return {"signal":"EXIT","reason":"SL HIT","exit_price":sl}

                if row.high >= tp:
                    self.active_position = None
                    return {"signal":"EXIT","reason":"TP HIT","exit_price":tp}

            if pos["side"] == "SHORT":
                if row.high >= sl:
                    self.active_position = None
                    return {"signal":"EXIT","reason":"SL HIT","exit_price":sl}

                if row.low <= tp:
                    self.active_position = None
                    return {"signal":"EXIT","reason":"TP HIT","exit_price":tp}

            return None

        # ===============================
        # ENTRY: LONG
        # ===============================
        if (
            can_trade and
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
                return {"signal":"BUY", "entry_price":row.close, "sl":sl, "tp":tp}

        # ===============================
        # ENTRY: SHORT
        # ===============================
        if (
            can_trade and
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
                    "side":"SHORT",
                    "entry":row.close,
                    "sl":sl,
                    "tp":tp
                }
                return {"signal":"SELL", "entry_price":row.close, "sl":sl, "tp":tp}
        return None
