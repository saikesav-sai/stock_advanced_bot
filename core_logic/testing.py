import LiveStrategyEngine
import os
from dotenv import load_dotenv

load_dotenv()

def test_live_strategy_engine():
    symbol = "INE467B01029"  # Example symbol
    instrument_key = "NSE_EQ|INE467B01029"
    engine = LiveStrategyEngine.LiveStrategyEngine(symbol=symbol, instrument_key=instrument_key)
    
    # Simulate incoming candle data
    test_candles = [
        {'marketFF': {'ltpc': {'ltp': 114.15, 'ltt': '1764916714694', 'ltq': '4', 'cp': 114.85}, 'marketLevel': {'bidAskQuote': [{'bidQ': '173', 'bidP': 114.15, 'askQ': '587', 'askP': 114.2}, {'bidQ': '30', 'bidP': 114.14, 'askQ': '1130', 'askP': 114.21}, {'bidQ': '811', 'bidP': 114.13, 'askQ': '1417', 'askP': 114.22}, {'bidQ': '3070', 'bidP': 114.12, 'askQ': '777', 'askP': 114.23}, {'bidQ': '2108', 'bidP': 114.11, 'askQ': '1409', 'askP': 114.24}]}, 'optionGreeks': {}, 'marketOHLC': {'ohlc': [{'interval': '1d', 'open': 115.19, 'high': 115.19, 'low': 113.8, 'close': 114.15, 'vol': '2585615', 'ts': '1764873000000'}, {'interval': 'I1', 'open': 114.18, 'high': 114.21, 'low': 114.15, 'close': 114.2, 'vol': '5103', 'ts': '1764916620000'}]}, 'atp': 114.3, 'vtt': '2585615', 'tbq': 1179085.0, 'tsq': 1509949.0}},
        {'marketFF': {'ltpc': {'ltp': 114.15, 'ltt': '1764916714694', 'ltq': '4', 'cp': 114.85}, 'marketLevel': {'bidAskQuote': [{'bidQ': '173', 'bidP': 114.15, 'askQ': '65', 'askP': 114.19}, {'bidQ': '30', 'bidP': 114.14, 'askQ': '5026', 'askP': 114.2}, {'bidQ': '315', 'bidP': 114.13, 'askQ': '2106', 'askP': 114.21}, {'bidQ': '403', 'bidP': 114.12, 'askQ': '391', 'askP': 114.22}, {'bidQ': '840', 'bidP': 114.11, 'askQ': '777', 'askP': 114.23}]}, 'optionGreeks': {}, 'marketOHLC': {'ohlc': [{'interval': '1d', 'open': 115.19, 'high': 115.19, 'low': 113.8, 'close': 114.15, 'vol': '2585615', 'ts': '1764873000000'}, {'interval': 'I1', 'open': 114.18, 'high': 114.21, 'low': 114.15, 'close': 114.2, 'vol': '5103', 'ts': '1764916620000'}]}, 'atp': 114.3, 'vtt': '2585615', 'tbq': 1178618.0, 'tsq': 1514304.0}}
    ]
    
    for candle in test_candles:
        signal = engine.update_candle(candle)
        if signal:
            print(f"Signal generated ")
        else:
            print(f"No signal")

if __name__ == "__main__":
    test_live_strategy_engine()