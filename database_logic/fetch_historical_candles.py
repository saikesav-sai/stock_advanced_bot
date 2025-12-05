import os
import sys
from datetime import datetime, timedelta

import pytz
import requests
from database_logic.candle_db import CandleDB
from dotenv import load_dotenv

load_dotenv()

# IST timezone
IST = pytz.timezone('Asia/Kolkata')


class UpstoxHistoricalFetcher:
    def __init__(self, access_token=None):
        self.access_token = access_token or os.getenv("UPSTOX_ACCESS_TOKEN")
        self.base_url = "https://api.upstox.com/v3/historical-candle"
        
        # Get absolute path to root folder's market_data.db
        root_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        db_path = os.path.join(root_folder, 'market_data.db')
        self.db = CandleDB(db_path=db_path)
    
    def fetch_and_store_candles(self, instrument_key: str, days: int = 2):
        """
        Fetch last N days of 1-minute candles and store in database
        
        Args:
            instrument_key: e.g., "NSE_EQ|INE467B01029" for TCS
            days: Number of days to fetch (default 2)
        """
        today = datetime.now().date()
        
        all_candles = []
        trading_days_found = 0
        day_offset = 1  # Start from yesterday
        
        # Keep going back until we find 'days' trading days
        while trading_days_found < days:
            target_date = today - timedelta(days=day_offset)
            day_offset += 1
            
            # Skip weekends
            if target_date.weekday() >= 5:  # Saturday=5, Sunday=6
                print(f"Skipping weekend: {target_date}")
                continue
            
            print(f"\nFetching candles for {target_date}...")
            
            candles = self._fetch_single_day(instrument_key, target_date)
            
            if candles:
                all_candles.extend(candles)
                trading_days_found += 1
                print(f"  ✓ Fetched {len(candles)} candles for {target_date} (Trading day {trading_days_found}/{days})")
            else:
                print(f"  ✗ No candles found for {target_date}")
        
        print("Fetching todays candles...  ")
        candles_today = self._fetch_today(instrument_key)
        if candles_today:
            all_candles.extend(candles_today)
            print(f"  ✓ Fetched {len(candles_today)} candles for today ({today})")
        else:
            print(f"  ✗ No candles found for today ({today})")
        

        # Store in database
        if all_candles:
            # Extract symbol from instrument_key (e.g., NSE_EQ|INE467B01029 -> INE467B01029)
            symbol = instrument_key.split("|")[1] if "|" in instrument_key else instrument_key
            
            # Add symbol to each candle
            for candle in all_candles:
                candle['symbol'] = symbol
            
            self.db.insert_candles_batch(all_candles)
            print(f"\n✓ Total {len(all_candles)} candles stored in database")
        else:
            print("\n✗ No candles to store")
        
        return all_candles
    
    def _fetch_today(self, instrument_key: str):
        """
        Fetch today's 1-minute candles up to current time
        
        Upstox API format: /instrument_key/interval/to_date/from_date
        Example: /NSE_EQ|INE467B01029/minutes/1/2025-01-03/2025-01-03
        """
        today = datetime.now().date()
        to_date = today.strftime("%Y-%m-%d")
        from_date = today.strftime("%Y-%m-%d")
        
        # URL encode the instrument key
        encoded_key = requests.utils.quote(instrument_key, safe='')
        
        url = f"{self.base_url}/intraday/{encoded_key}/minutes/1/"
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }
        
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse Upstox response
                # Response format: {"data": {"candles": [[timestamp, open, high, low, close, volume, oi]]}}
                if data.get('status') == 'success' and 'data' in data:
                    raw_candles = data['data'].get('candles', [])
                    
                    # Convert to our format
                    candles = []
                    for candle in raw_candles:
                        # Upstox candle format: [timestamp_str, open, high, low, close, volume, oi]
                        timestamp_str = candle[0]
                        
                        # Parse timestamp (format: "2025-01-03T09:15:00+05:30")
                        # Convert to IST and remove timezone info
                        timestamp = datetime.fromisoformat(timestamp_str).astimezone(IST).replace(tzinfo=None)
                        timestamp= timestamp.replace(second=0, microsecond=0)
                        candles.append({
                            'timestamp': timestamp,
                            'open': float(candle[1]),
                            'high': float(candle[2]),
                            'low': float(candle[3]),
                            'close': float(candle[4]),
                            'volume': int(candle[5]),
                            'interval': '1m'
                        })
                    
                    return candles
                else:
                    print(f"  Error: {data.get('message', 'Unknown error')}")
                    return []
            
            elif response.status_code == 401:
                print(f"  Error: Unauthorized - Check your access token")
                return []
        except Exception as e:
            print(f"  Exception: {e}")
            return []

    def _fetch_single_day(self, instrument_key: str, date: datetime.date):
        """
        Fetch 1-minute candles for a single day
        
        Upstox API format: /instrument_key/interval/to_date/from_date
        Example: /NSE_EQ|INE467B01029/minutes/1/2025-01-02/2025-01-01
        """
        # Format dates as YYYY-MM-DD
        to_date = date.strftime("%Y-%m-%d")
        from_date = date.strftime("%Y-%m-%d")
        
        # URL encode the instrument key
        encoded_key = requests.utils.quote(instrument_key, safe='')
        
        url = f"{self.base_url}/{encoded_key}/minutes/1/{to_date}/{from_date}"
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }
        
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse Upstox response
                # Response format: {"data": {"candles": [[timestamp, open, high, low, close, volume, oi]]}}
                if data.get('status') == 'success' and 'data' in data:
                    raw_candles = data['data'].get('candles', [])
                    
                    # Convert to our format
                    candles = []
                    for candle in raw_candles:
                        # Upstox candle format: [timestamp_str, open, high, low, close, volume, oi]
                        timestamp_str = candle[0]
                        
                        # Parse timestamp (format: "2025-01-02T09:15:00+05:30")
                        # Convert to IST and remove timezone info
                        timestamp = datetime.fromisoformat(timestamp_str).astimezone(IST).replace(tzinfo=None)
                        timestamp= timestamp.replace(second=0, microsecond=0)
                        candles.append({
                            'timestamp': timestamp,
                            'open': float(candle[1]),
                            'high': float(candle[2]),
                            'low': float(candle[3]),
                            'close': float(candle[4]),
                            'volume': int(candle[5]),
                            'interval': '1m'
                        })
                    
                    return candles
                else:
                    print(f"  Error: {data.get('message', 'Unknown error')}")
                    return []
            
            elif response.status_code == 401:
                print(f"  Error: Unauthorized - Check your access token")
                return []
            
            else:
                print(f"  Error: {response.status_code} - {response.text}")
                return []
        
        except Exception as e:
            print(f"  Exception: {e}")
            return []
    
    def close(self):
        """Close database connection"""
        self.db.close()


def main():

    SYMBOL = os.getenv("SYMBOLS")
    print(SYMBOL)
    print("="*80)
    print("Upstox Historical Candle Fetcher")
    print("="*80)
    
    fetcher = UpstoxHistoricalFetcher()
    
    # Fetch last 2 days of candles
    candles = fetcher.fetch_and_store_candles(SYMBOL, days=2)
    
    # Show stats
    print("\n" + "="*80)
    print("Database Stats:")
    print("="*80)
    stats = fetcher.db.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Test PDH/PDL calculation
    today = datetime.now().strftime("%Y-%m-%d")
    symbol = SYMBOL.split("|")[1]
    
    pdh, pdl = fetcher.db.get_previous_day_high_low(symbol, today)
    print(f"\nPrevious Day High (PDH): {pdh}")
    print(f"Previous Day Low (PDL): {pdl}")
    
    fetcher.close()


if __name__ == "__main__":
    main()
