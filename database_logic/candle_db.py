import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from core_logic.logger_config import get_logger

logger = get_logger()


class CandleDB:
    def __init__(self, db_path="market_data.db"):
        self.db_path = db_path
        self.conn = None
        self._init_db()
    
    def _init_db(self):
        """Initialize database and create tables if they don't exist"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = self.conn.cursor()
        
        # Create candles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                date TEXT NOT NULL,
                interval TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                PRIMARY KEY (symbol, timestamp, interval)
            )
        """)
        
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_date_interval 
            ON candles(symbol, date, interval)
        """)
        
        self.conn.commit()
        logger.info(f"Database initialized: {self.db_path}")
    
    def insert_candle(self, symbol: str, timestamp: datetime, 
                     open_price: float, high: float, low: float, 
                     close: float, volume: int, interval: str = os.getenv("INTERVAL", "5m")):
        """Insert a single candle"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO candles 
            (symbol, timestamp, date, interval, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            int(timestamp.timestamp()),
            timestamp.strftime("%Y-%m-%d"),
            interval,
            open_price,
            high,
            low,
            close,
            volume
        ))
        
        self.conn.commit()
    
    def insert_candles_batch(self, candles: List[Dict]):
        """Insert multiple candles efficiently"""
        cursor = self.conn.cursor()
        
        data = []
        for candle in candles:
            ts = candle['timestamp']
            data.append((
                candle['symbol'],
                int(ts.timestamp()) if isinstance(ts, datetime) else ts,
                ts.strftime("%Y-%m-%d") if isinstance(ts, datetime) else datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                candle.get('interval', '1m'),
                candle['open'],
                candle['high'],
                candle['low'],
                candle['close'],
                candle['volume']
            ))
        
        cursor.executemany("""
            INSERT OR REPLACE INTO candles 
            (symbol, timestamp, date, interval, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)
        
        self.conn.commit()
        logger.info(f"Inserted {len(candles)} candles")
    
    def get_candles(self, symbol: str, start_date:str = None, 
                   end_date: str = None, interval: str = os.getenv("INTERVAL", "5m")) -> pd.DataFrame:
        """Get candles for a symbol within date range"""
        query = """
            SELECT  timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = ? AND interval = ?
        """
        params = [symbol, interval]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        query += " ORDER BY timestamp ASC"
        
        df = pd.read_sql_query(query, self.conn, params=params)
        
        if len(df) > 0:
            # Convert Unix timestamp to datetime - timestamps are already in IST
            # We use utc=True then remove timezone to get naive datetime matching stored IST values
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            # Add IST offset (UTC + 5:30) and remove timezone info
            df['timestamp'] = df['timestamp'] + pd.Timedelta(hours=5, minutes=30)
            df['timestamp'] = df['timestamp'].dt.tz_localize(None)
        
        return df
    
    def get_previous_day_high_low(self, symbol: str, current_date: str, interval: str = os.getenv("INTERVAL", "5m")) -> tuple:
        """Get previous day high and low"""
        current = datetime.strptime(current_date, "%Y-%m-%d")
        prev_date = (current - timedelta(days=1)).strftime("%Y-%m-%d")
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT MAX(high) as pdh, MIN(low) as pdl
            FROM candles
            WHERE symbol = ? AND date = ? AND interval = ?
        """, (symbol, prev_date, interval))
        
        result = cursor.fetchone()
        
        if result and result[0] is not None:
            return result[0], result[1]  # PDH, PDL
        
        return None, None
    
    def cleanup_old_candles(self, days_to_keep: int = 2):
        """Delete candles older than specified days"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
        
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM candles WHERE date < ?", (cutoff_date,))
        deleted = cursor.rowcount
        self.conn.commit()
        
        logger.info(f"Cleaned up {deleted} old candles (before {cutoff_date})")
        return deleted
    
    def get_latest_candle(self, symbol: str, interval: str = os.getenv("INTERVAL", "5m")) -> Optional[Dict]:
        """Get the most recent candle for a symbol"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = ? AND interval = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol, interval))
        
        result = cursor.fetchone()
        
        if result:
            return {
                'timestamp': datetime.fromtimestamp(result[0]),
                'open': result[1],
                'high': result[2],
                'low': result[3],
                'close': result[4],
                'volume': result[5]
            }
        
        return None
    
    def get_stats(self):
        """Get database statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM candles")
        total_candles = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM candles")
        total_symbols = cursor.fetchone()[0]
        
        cursor.execute("SELECT MIN(date), MAX(date) FROM candles")
        date_range = cursor.fetchone()
        
        return {
            'total_candles': total_candles,
            'total_symbols': total_symbols,
            'date_range': date_range
        }
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")


# if __name__ == "__main__":
#     # Test the database
#     db = CandleDB()
    
#     # Insert test candle
#     now = datetime.now()
#     db.insert_candle(
#         symbol="TCS",
#         timestamp=now,
#         open_price=3500.0,
#         high=3510.0,
#         low=3495.0,
#         close=3505.0,
#         volume=10000
#     )
    
#     # Get candles
#     df = db.get_candles("TCS")
#     print("\nCandles DataFrame:")
#     print(df)
    
#     # Get stats
#     stats = db.get_stats()
#     print("\nDatabase Stats:")
#     print(stats)
    
#     db.close()
