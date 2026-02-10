"""
Loads historical data from 2022 to 2025 for backtesting.
"""
from database_logic.fetch_historical_candles import UpstoxHistoricalFetcher
from database_logic.candle_db import CandleDB

db_path = 'back_testing_market_data.db'
# Reliance Power, Vodafone Idea, Tata Steel, Hindalco, State Bank of India, Zee Entertainment, Indian Oil Corporation, Federal Bank, BHEL, IDFC First Bank
raw_stocks=["INE614G01033","INE669E01016","INE081A01020","INE038A01020","INE062A01020","INE256A01028","INE242A01010","INE171A01029","INE257A01026","INE092T01019"]
raw_stocks1= ["INE242A01010","INE171A01029","INE257A01026","INE092T01019"]


# putting NSE| in front of key
stocks = [f"NSE_EQ|{s}" for s in raw_stocks]

from_date = "2022-01-01"
to_date = "2025-12-31"

fetcher = UpstoxHistoricalFetcher(root_db_path=db_path)

for stock in stocks:
    print(f"Fetching data for {stock} from {from_date} to {to_date}...")
    fetcher.fetch_and_store_candles(instrument_key=stock, start_date=from_date, end_date=to_date)
print("Data fetching completed.")
print("-"*50)

# validate data
print(raw_stocks)
candle_db = CandleDB(db_path=db_path)
for stock in raw_stocks:
    candles = candle_db.get_candles(symbol=stock, start_date=from_date, end_date=to_date)
    print(f"{stock}: Retrieved {len(candles)} candles from database.")
