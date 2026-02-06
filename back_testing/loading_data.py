import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pytz

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core_logic.logger_config import get_logger
from database_logic.candle_db import CandleDB
from database_logic.fetch_historical_candles import UpstoxHistoricalFetcher

logger = get_logger()


class BacktestDataLoader:
    """
    Handles loading and validation of historical candle data for backtesting
    """

    def __init__(self, db_path: str, interval: str = "5", auto_fetch: bool = True):
        """
        Initialize data loader

        Args:
            db_path: Path to SQLite database
            interval: Candle interval (e.g., "5" for 5-minute)
            auto_fetch: Automatically fetch data from Upstox if not found in DB
        """
        self.db = CandleDB(db_path)
        self.interval = interval
        self.auto_fetch = auto_fetch
        self.IST = pytz.timezone('Asia/Kolkata')
        logger.info(f"Initialized BacktestDataLoader with interval={interval}, auto_fetch={auto_fetch}")

    def _get_working_dates(self, start_date: str, end_date: str) -> List[datetime.date]:
        """
        Get list of working dates (weekdays only) between start and end dates

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of datetime.date objects (Monday-Friday only)
        """
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()

        working_dates = []
        current_date = start_dt
        while current_date <= end_dt:
            if current_date.weekday() < 5:  # Monday=0 to Friday=4
                working_dates.append(current_date)
            current_date += timedelta(days=1)

        return working_dates

    def load_data(self, symbol: str, start_date: str, end_date: str, instrument_key: str = None) -> pd.DataFrame:
        """
        Load candles from database with validation. If data is missing for any dates, automatically fetch from Upstox.

        Args:
            symbol: ISIN code (e.g., "INE467B01029")
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            instrument_key: Full instrument key (e.g., "NSE_EQ|INE467B01029"). If not provided, constructed from symbol.

        Returns:
            pd.DataFrame: Validated OHLCV data with timestamp column
        """
        logger.info(f"Loading data for {symbol} from {start_date} to {end_date}")

        # Load candles from database
        df = self.db.get_candles(symbol, start_date, end_date, self.interval)

        expected_dates = set(self._get_working_dates(start_date, end_date))

        # Get actual dates present in database
        if len(df) > 0:
            actual_dates = set(df['timestamp'].dt.date.unique())
        else:
            actual_dates = set()

        missing_dates = expected_dates - actual_dates
        percentage_missing = (len(missing_dates) / len(expected_dates)) * 100 if len(expected_dates) > 0 else 0

        if percentage_missing > 30:  # If more than 30% of expected dates are missing, log a warning and fetch them
            logger.warning(f"Missing data for {len(missing_dates)} working days out of {len(expected_dates)} expected for {symbol}")
            logger.info(f"Missing dates: {sorted(missing_dates)[:10]}{'...' if len(missing_dates) > 10 else ''}")

            if self.auto_fetch:
                logger.info(f"Attempting to fetch missing historical data from Upstox for {len(missing_dates)} dates...")

                # Construct instrument_key if not provided
                if instrument_key is None:
                    instrument_key = f"NSE_EQ|{symbol}"
                    logger.info(f"Using constructed instrument_key: {instrument_key}")

                try:
                    # Fetch historical data for the entire range (fetcher will handle individual dates)
                    fetcher = UpstoxHistoricalFetcher(root_db_path=self.db.db_path)
                    fetcher.fetch_and_store_candles(instrument_key, start_date=start_date, end_date=end_date)
                    fetcher.close()

                    logger.info(f"Successfully fetched historical data for {symbol}")

                    # Reload from database to get complete data
                    df = self.db.get_candles(symbol, start_date, end_date, self.interval)

                    # Recheck missing dates after fetch
                    if len(df) > 0:
                        actual_dates_after = set(df['timestamp'].dt.date.unique())
                        still_missing = expected_dates - actual_dates_after
                        if len(still_missing) > 0:
                            logger.warning(f"Still missing data for {len(still_missing)} dates after fetching: {sorted(still_missing)[:5]}")
                        else:
                            logger.info(f"Successfully loaded complete data: {len(df)} candles across {len(actual_dates_after)} days")
                    else:
                        logger.error(f"Still no data after fetching for {symbol}")

                except Exception as e:
                    logger.error(f"Failed to fetch historical data: {e}")
                    logger.warning("Make sure UPSTOX_ACCESS_TOKEN is set in environment variables")
                    # Continue with whatever data we have
        else:
            logger.info(f"Complete data available: {len(df)} candles across {len(actual_dates)} days")

        # If still no data at all, return empty dataframe
        if len(df) == 0:
            logger.error(f"No data available for {symbol} from {start_date} to {end_date}")
            return df

        # Ensure data types are correct
        df["open"] = pd.to_numeric(df["open"], errors='coerce')
        df["high"] = pd.to_numeric(df["high"], errors='coerce')
        df["low"] = pd.to_numeric(df["low"], errors='coerce')
        df["close"] = pd.to_numeric(df["close"], errors='coerce')
        df["volume"] = pd.to_numeric(df["volume"], errors='coerce')

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        logger.info(f"Loaded {len(df)} candles for {symbol}")

        return df

    def validate_data(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Check data completeness and quality

        Args:
            df: DataFrame with candle data
            symbol: Symbol name for logging

        Returns:
            dict: {
                "total_candles": int,
                "trading_days": int,
                "missing_days": list,
                "gaps_detected": int,
                "valid": bool,
                "warnings": list
            }
        """
        if len(df) == 0:
            return {
                "total_candles": 0,
                "trading_days": 0,
                "missing_days": [],
                "gaps_detected": 0,
                "valid": False,
                "warnings": ["No data available"]
            }

        warnings = []

        # Get unique trading days
        df['date'] = df['timestamp'].dt.date
        trading_days = df['date'].nunique()
        total_candles = len(df)

        # Check minimum candles for strategy (60 candles for EMA)
        MIN_CANDLES = 60
        if total_candles < MIN_CANDLES:
            warnings.append(f"Insufficient data: {total_candles} candles (minimum {MIN_CANDLES} required)")

        # Check candles per day (should be ~75 for 5-min in 6.5hr session)
        expected_candles_per_day = 75  # Approximate for 5-minute candles
        avg_candles_per_day = total_candles / trading_days if trading_days > 0 else 0

        if avg_candles_per_day < expected_candles_per_day * 0.8:  # Allow 20% tolerance
            warnings.append(f"Low candles per day: {avg_candles_per_day:.1f} (expected ~{expected_candles_per_day})")

        # Detect gaps in data
        gaps_detected = 0
        if len(df) > 1:
            # Calculate time differences between consecutive candles
            time_diffs = df['timestamp'].diff()
            expected_diff = pd.Timedelta(minutes=int(self.interval))

            # Allow for market breaks (lunch, weekend) - gaps > 20 minutes indicates issue
            large_gaps = time_diffs[time_diffs > pd.Timedelta(minutes=20)]

            # Filter out weekend gaps (Friday to Monday)
            for idx in large_gaps.index:
                prev_ts = df.loc[idx - 1, 'timestamp']
                curr_ts = df.loc[idx, 'timestamp']

                # Skip if it's a weekend gap or next day gap
                if prev_ts.date() != curr_ts.date():
                    continue

                gaps_detected += 1

                if gaps_detected <= 5:  # Only log first 5 gaps
                    warnings.append(f"Gap detected: {prev_ts} to {curr_ts}")

        # # Check for missing weekdays
        # min_date = df['timestamp'].min().date()
        # max_date = df['timestamp'].max().date()
        # all_dates = set(df['date'].unique())

        # # Generate expected weekdays
        # current = min_date
        # expected_dates = []
        # while current <= max_date:
        #     if current.weekday() < 5:  # Monday=0, Friday=4
        #         expected_dates.append(current)
        #     current += timedelta(days=1)
        missing_days=[]
        # missing_days = [d for d in expected_dates if d not in all_dates]

        # if len(missing_days) > 0:
        #     warnings.append(f"Missing {len(missing_days)} trading days")

        # Overall validity
        valid = len(warnings) == 0

        result = {
            "total_candles": total_candles,
            "trading_days": trading_days,
            "missing_days": missing_days,
            "gaps_detected": gaps_detected,
            "valid": valid,
            "warnings": warnings
        }

        logger.info(f"Validation for {symbol}: {total_candles} candles, {trading_days} days, "
                   f"{len(missing_days)} missing days, {gaps_detected} gaps")

        if warnings:
            for warning in warnings:
                logger.warning(f"[{symbol}] {warning}")

        return result

    def get_trading_days(self, df: pd.DataFrame) -> List[datetime.date]:
        """
        Extract unique trading days from dataframe

        Args:
            df: DataFrame with timestamp column

        Returns:
            list: Sorted list of datetime.date objects
        """
        if len(df) == 0:
            return []

        trading_days = sorted(df['timestamp'].dt.date.unique())
        return trading_days

    def get_pdh_pdl_for_date(self, df: pd.DataFrame, current_date: datetime.date) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate PDH/PDL from previous day's data

        Args:
            df: Full dataframe with all historical data
            current_date: datetime.date for which to calculate PDH/PDL

        Returns:
            tuple: (pdh, pdl) or (None, None) if insufficient data
        """
        # Get data from previous day
        prev_data = df[df['timestamp'].dt.date < current_date]

        if len(prev_data) == 0:
            return None, None

        # Get the most recent previous trading day
        last_prev_date = prev_data['timestamp'].dt.date.max()
        prev_day_data = prev_data[prev_data['timestamp'].dt.date == last_prev_date]

        if len(prev_day_data) == 0:
            return None, None

        pdh = prev_day_data['high'].max()
        pdl = prev_day_data['low'].min()

        logger.debug(f"PDH/PDL for {current_date}: PDH={pdh}, PDL={pdl} (from {last_prev_date})")

        return pdh, pdl

    def close(self):
        """Close database connection"""
        self.db.close()
        logger.info("BacktestDataLoader closed")
