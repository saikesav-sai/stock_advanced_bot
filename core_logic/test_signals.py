from datetime import datetime, timedelta

import LiveStrategyEngine
import pandas as pd


def setup_engine_for_test(engine, trend="up"):
    """Setup existing engine with mock data for testing"""
    now = datetime.now()
    base_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    
    # Set PDH/PDL first
    engine.pdh = 115.0
    engine.pdl = 113.0
    
    # Create 220 candles for proper EMA calculation
    data = []
    for i in range(220):
        ts = base_time - timedelta(minutes=220-i)
        
        if trend == "up":
            # Uptrend: rising prices BUT staying below PDH until last candle
            base_price = 110 + (i * 0.02)  # Slower rise to stay below 115
            if base_price > 114.5:  # Cap at 114.5 to be below PDH
                base_price = 114.5
        else:
            # Downtrend: falling prices BUT staying above PDL until last candle
            base_price = 120 - (i * 0.02)  # Slower fall to stay above 113
            if base_price < 113.5:  # Floor at 113.5 to be above PDL
                base_price = 113.5
        
        data.append({
            'timestamp': ts,
            'open': base_price,
            'high': base_price + 0.3,
            'low': base_price - 0.3,
            'close': base_price,
            'volume': 60000 + (i * 200)
        })
    
    engine.df = pd.DataFrame(data)
    engine.current_minute = data[-1]['timestamp']
    
    return base_time


def test_long_breakout():
    """Test LONG signal - price breaks above PDH in uptrend"""
    print("\n" + "="*70)
    print("TEST 1: LONG SIGNAL - PDH Breakout")
    print("="*70)
    
    # Initialize your engine without loading historical data
    symbol = "INE467B01029"
    instrument_key = f"NSE_EQ|{symbol}"
    engine = LiveStrategyEngine.LiveStrategyEngine(symbol=None, instrument_key=None)
    engine.symbol = symbol
    engine.instrument_key = instrument_key
    
    # Setup with mock data
    base_time = setup_engine_for_test(engine, trend="up")
    
    print(f"[{engine.symbol}] Setup:")
    print(f"  - PDH: {engine.pdh}")
    print(f"  - PDL: {engine.pdl}")
    print(f"  - Last price: {engine.df.iloc[-1]['close']:.2f}")
    print(f"  - Trend: UPTREND (price will be > EMA200)")
    
    # Create breakout tick - price goes ABOVE PDH with HIGH volume
    # Use same minute as last candle to update it, not create new one
    breakout_time = base_time
    tick = {
        'marketFF': {
            'ltpc': {
                'ltp': 115.8,  # ABOVE PDH (115.0)
                'ltt': str(int(breakout_time.timestamp() * 1000)),
                'ltq': '200000',  # HIGH volume (triggers vol_ok)
                'cp': 114.85
            }
        }
    }
    
    print(f"\nFeeding tick data:")
    print(f"  - LTP: {tick['marketFF']['ltpc']['ltp']} (breaks PDH {engine.pdh})")
    print(f"  - Volume: {tick['marketFF']['ltpc']['ltq']}")
    print(f"  - Time: {breakout_time}")
    
    signal = engine.update_candle(tick)
    print(signal)
    print("\n" + "-"*70)
    if signal and signal.get('signal') == 'BUY':
        print("✓ LONG SIGNAL GENERATED!")
        print(f"  Entry Price: {signal.get('entry_price'):.2f}")
        print(f"  Stop Loss:   {signal.get('sl'):.2f}")
        print(f"  Take Profit: {signal.get('tp'):.2f}")
        print(f"  Risk:        {signal.get('entry_price') - signal.get('sl'):.2f}")
        print(f"  Reward:      {signal.get('tp') - signal.get('entry_price'):.2f}")
        return True
    else:
        print("✗ NO SIGNAL GENERATED")
        print(f"  Result: {signal}")
        return False


def test_short_breakdown():
    """Test SHORT signal - price breaks below PDL in downtrend"""
    print("\n" + "="*70)
    print("TEST 2: SHORT SIGNAL - PDL Breakdown")
    print("="*70)
    
    # Initialize your engine without loading historical data
    symbol = "INE467B01029"
    instrument_key = f"NSE_EQ|{symbol}"
    engine = LiveStrategyEngine.LiveStrategyEngine(symbol=None, instrument_key=None)
    engine.symbol = symbol
    engine.instrument_key = instrument_key
    
    # Setup with mock data
    base_time = setup_engine_for_test(engine, trend="down")
    
    print(f"[{engine.symbol}] Setup:")
    print(f"  - PDH: {engine.pdh}")
    print(f"  - PDL: {engine.pdl}")
    print(f"  - Last price: {engine.df.iloc[-1]['close']:.2f}")
    print(f"  - Trend: DOWNTREND (price will be < EMA200)")
    
    # Create breakdown tick - price goes BELOW PDL with HIGH volume
    # Use same minute as last candle to update it, not create new one
    breakdown_time = base_time
    tick = {
        'marketFF': {
            'ltpc': {
                'ltp': 112.3,  # BELOW PDL (113.0)
                'ltt': str(int(breakdown_time.timestamp() * 1000)),
                'ltq': '200000',  # HIGH volume
                'cp': 114.85
            }
        }
    }
    
    print(f"\nFeeding tick data:")
    print(f"  - LTP: {tick['marketFF']['ltpc']['ltp']} (breaks PDL {engine.pdl})")
    print(f"  - Volume: {tick['marketFF']['ltpc']['ltq']}")
    print(f"  - Time: {breakdown_time}")
    
    signal = engine.update_candle(tick)
    print(signal)
    print("\n" + "-"*70)
    if signal and signal.get('signal') == 'SELL':
        print("✓ SHORT SIGNAL GENERATED!")
        print(f"  Entry Price: {signal.get('entry_price'):.2f}")
        print(f"  Stop Loss:   {signal.get('sl'):.2f}")
        print(f"  Take Profit: {signal.get('tp'):.2f}")
        print(f"  Risk:        {signal.get('sl') - signal.get('entry_price'):.2f}")
        print(f"  Reward:      {signal.get('entry_price') - signal.get('tp'):.2f}")
        return True
    else:
        print("✗ NO SIGNAL GENERATED")
        print(f"  Result: {signal}")
        return False


def test_stop_loss():
    """Test Stop Loss exit"""
    print("\n" + "="*70)
    print("TEST 3: STOP LOSS EXIT")
    print("="*70)
    
    # Initialize your engine without loading historical data
    symbol = "INE467B01029"
    instrument_key = f"NSE_EQ|{symbol}"
    engine = LiveStrategyEngine.LiveStrategyEngine(symbol=None, instrument_key=None)
    engine.symbol = symbol
    engine.instrument_key = instrument_key
    
    # Setup with mock data
    base_time = setup_engine_for_test(engine, trend="up")
    
    # Manually create an active LONG position
    engine.active_position = {
        'side': 'LONG',
        'entry': 115.0,
        'sl': 114.0,
        'tp': 116.6
    }
    
    print(f"[{engine.symbol}] Active LONG Position:")
    print(f"  - Entry: {engine.active_position['entry']}")
    print(f"  - Stop Loss: {engine.active_position['sl']}")
    print(f"  - Take Profit: {engine.active_position['tp']}")
    
    # Price hits stop loss
    sl_time = base_time + timedelta(minutes=1)
    tick = {
        'marketFF': {
            'ltpc': {
                'ltp': 113.8,  # BELOW stop loss (114.0)
                'ltt': str(int(sl_time.timestamp() * 1000)),
                'ltq': '50000',
                'cp': 114.85
            }
        }
    }
    
    print(f"\nFeeding tick data:")
    print(f"  - LTP: {tick['marketFF']['ltpc']['ltp']} (below SL {engine.active_position['sl']})")
    
    signal = engine.update_candle(tick)
    print(signal)
    print("\n" + "-"*70)
    if signal and signal.get('reason') == 'SL HIT':
        print("✓ STOP LOSS TRIGGERED!")
        print(f"  Exit Price: {signal.get('exit_price'):.2f}")
        print(f"  Loss: {115.0 - signal.get('exit_price'):.2f}")
        return True
    else:
        print("✗ SL NOT TRIGGERED")
        print(f"  Result: {signal}")
        return False


def test_take_profit():
    """Test Take Profit exit"""
    print("\n" + "="*70)
    print("TEST 4: TAKE PROFIT EXIT")
    print("="*70)
    
    # Initialize your engine without loading historical data
    symbol = "INE467B01029"
    instrument_key = f"NSE_EQ|{symbol}"
    engine = LiveStrategyEngine.LiveStrategyEngine(symbol=None, instrument_key=None)
    engine.symbol = symbol
    engine.instrument_key = instrument_key
    
    # Setup with mock data
    base_time = setup_engine_for_test(engine, trend="up")
    
    # Manually create an active LONG position
    engine.active_position = {
        'side': 'LONG',
        'entry': 115.0,
        'sl': 114.0,
        'tp': 116.6
    }
    
    print(f"[{engine.symbol}] Active LONG Position:")
    print(f"  - Entry: {engine.active_position['entry']}")
    print(f"  - Stop Loss: {engine.active_position['sl']}")
    print(f"  - Take Profit: {engine.active_position['tp']}")
    
    # Price hits take profit
    tp_time = base_time + timedelta(minutes=1)
    tick = {
        'marketFF': {
            'ltpc': {
                'ltp': 116.8,  # ABOVE take profit (116.6)
                'ltt': str(int(tp_time.timestamp() * 1000)),
                'ltq': '50000',
                'cp': 114.85
            }
        }
    }
    
    print(f"\nFeeding tick data:")
    print(f"  - LTP: {tick['marketFF']['ltpc']['ltp']} (above TP {engine.active_position['tp']})")
    
    signal = engine.update_candle(tick)
    print(signal)
    print("\n" + "-"*70)
    if signal and signal.get('reason') == 'TP HIT':
        print("✓ TAKE PROFIT TRIGGERED!")
        print(f"  Exit Price: {signal.get('exit_price'):.2f}")
        print(f"  Profit: {signal.get('exit_price') - 115.0:.2f}")
        return True
    else:
        print("✗ TP NOT TRIGGERED")
        print(f"  Result: {signal}")
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print(" LIVE STRATEGY ENGINE - SIGNAL TESTING ")
    print("="*70)
    print("Testing signal generation with realistic market data...")
    
    results = []
    
    # Run all tests
    results.append(("LONG Signal (PDH Breakout)", test_long_breakout()))
    results.append(("SHORT Signal (PDL Breakdown)", test_short_breakdown()))
    results.append(("Stop Loss Exit", test_stop_loss()))
    results.append(("Take Profit Exit", test_take_profit()))
    
    # Final Summary
    print("\n" + "="*70)
    print(" TEST RESULTS SUMMARY ")
    print("="*70)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:.<50} {status}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print("-"*70)
    print(f"Total: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 All tests passed! Strategy is working correctly.")
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed. Review the output above.")
    
    print("="*70)
