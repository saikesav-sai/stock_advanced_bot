import os,sys,pytz
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from core_logic.strategies import Strategy1 as strategy
from core_logic.logger_config import get_logger
from database_logic.candle_db import CandleDB
from database_logic.fetch_historical_candles import UpstoxHistoricalFetcher

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

logger = get_logger()


class LiveStrategyEngine:
    def __init__(self, symbol, instrument_key=None):
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

        self.strategy = strategy()
        
        # Load historical data from DB
        if self.symbol:
            self._load_historical_data()

    def _load_historical_data(self):
        """Load historical candles from database, fetch if not found"""
        today = datetime.now().strftime("%Y-%m-%d")
        

        # cleanup old candles
        self.db.cleanup_old_candles(days_to_keep=int(os.getenv("STOCK_DAYS_NEED", "3")))
         
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

            # Calculate PDH/PDL from yesterday's data and set in strategy
            pdh, pdl = self.db.get_previous_day_high_low(self.symbol, today)
            if pdh and pdl:
                self.strategy.set_pdh_pdl(pdh, pdl)
                logger.info(f"[{self.symbol}] PDH: {pdh}, PDL: {pdl}")
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
                interval='5'
            )
        except Exception as e:
            logger.error(f"[{self.symbol}] Error saving candle to DB: {e}")

    # ---------------------------------------------
    # Update candle from live tick
    # ---------------------------------------------
    def update_candle(self, tick):
        ts_raw = int(tick["marketFF"]["ltpc"]["ltt"])
        price = tick["marketFF"]["ltpc"]["ltp"]
        vol = int(tick["marketFF"]["ltpc"]["ltq"])
        # Convert millisecond timestamp to datetime (timezone-naive)
        ts = datetime.fromtimestamp(ts_raw /1000)
        # Round timestamp to nearest 5-minute interval
        minute_ts = ts.replace(second=0, microsecond=0)
        minute_ts = minute_ts.replace(minute=(minute_ts.minute // 5) * 5)

        current_candle_time= self.df['timestamp'].iloc[-1] if len(self.df)>0 else None

        # every 5 minutes create new candle
        if current_candle_time != minute_ts:
            # Save the previous completed candle to DB
            if current_candle_time is not None and len(self.df) > 0:
                last_candle = self.df.iloc[-1]
                self._save_completed_candle({
                    'timestamp': last_candle['timestamp'],
                    'open': last_candle['open'],
                    'high': last_candle['high'],
                    'low': last_candle['low'],
                    'close': last_candle['close'],
                    'volume': last_candle['volume']
                })
            
            current_candle_time = minute_ts
            logger.info(f"[{self.symbol}] New 5-min candle created | df length: {len(self.df)} | Time: {minute_ts}")
            logger.info(f"[{self.symbol}] Last 3 candles: {self.df.tail(3).to_string()}")

            # Creating new candle and Ensure numeric types
            self.df.loc[len(self.df)] = [minute_ts, float(price), float(price), float(price), float(price), int(vol)]
            
        else:
            # Update candle
            idx = self.df.index[-1]
            self.df.at[idx, "high"] = max(float(self.df.at[idx, "high"]), float(price))
            self.df.at[idx, "low"] = min(float(self.df.at[idx, "low"]), float(price))
            self.df.at[idx, "close"] = float(price)
            self.df.at[idx, "volume"] = int(self.df.at[idx, "volume"]) + int(vol)

        return self.process_strategy()


    def process_strategy(self):
        """Process strategy using strategy class"""
        return self.strategy.process(self.df, symbol=self.symbol)
