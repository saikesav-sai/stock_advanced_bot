"""
Production Strategy Diagnostics - Find out why no signals were generated
Run this against your production database to see where signals failed
"""
import os
import sqlite3
import sys
from datetime import datetime as dt

import pandas as pd

# Strategy parameters (match LiveStrategyEngine.py exactly)
EMA_LEN = 50
VOL_LEN = 20
VOL_MULT = 0.5
VWAP_DIST = 0.01  # 0.05%
RR = 1.2
SL_BUFFER = 0.08
TRADE_START = 930
TRADE_END = 1525

def analyze_database(db_path='market_data.db', symbol='INE053F01010'):
    """Analyze why no signals were generated"""

    conn = sqlite3.connect(db_path)

    # Get all candles
    df = pd.read_sql(
        f"SELECT * FROM candles WHERE symbol='{symbol}' ORDER BY timestamp",
        conn,
        parse_dates=['timestamp']
    )

    if len(df) == 0:
        print(f"❌ No data found for symbol {symbol}")
        conn.close()
        return

    # Convert types
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
    df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')

    print(f"\n{'='*80}")
    print(f"PRODUCTION DATA ANALYSIS: {symbol}")
    print(f"{'='*80}")
    print(f"Total candles: {len(df)}")
    print(f"Date range: {df['timestamp'].min().date()} to {df['timestamp'].max().date()}")
    print(f"Total days: {df['timestamp'].dt.date.nunique()}")

    # Calculate indicators for all data
    df['EMA200'] = df['close'].ewm(span=EMA_LEN, adjust=False).mean()

    # Recalculate VWAP per day
    df['date'] = df['timestamp'].dt.date
    vwap_list = []
    for date in df['date'].unique():
        day_df = df[df['date'] == date].copy()
        day_df['cumul_vol'] = day_df['volume'].cumsum()
        day_df['cumul_vol_price'] = (day_df['close'] * day_df['volume']).cumsum()
        day_df['VWAP'] = day_df['cumul_vol_price'] / day_df['cumul_vol']
        vwap_list.append(day_df)

    df = pd.concat(vwap_list, ignore_index=True)
    df['VolMA'] = df['volume'].rolling(VOL_LEN).mean()

    # Add time filter
    df['time_int'] = df['timestamp'].dt.hour * 100 + df['timestamp'].dt.minute
    df['market_hours'] = (df['time_int'] >= TRADE_START) & (df['time_int'] <= TRADE_END)

    # Filter conditions
    df['vol_ok'] = df['volume'] > df['VolMA'] * VOL_MULT
    df['dist_pct'] = abs(df['close'] - df['VWAP']) / df['VWAP'] * 100
    df['vwap_ok'] = df['dist_pct'] >= VWAP_DIST
    df['uptrend'] = df['close'] > df['EMA200']
    df['downtrend'] = df['close'] < df['EMA200']
    df['has_ema'] = ~df['EMA200'].isna()

    # Get unique trading days
    dates = sorted(df['date'].unique())

    print(f"\n{'='*80}")
    print("STRATEGY PARAMETERS (from LiveStrategyEngine.py)")
    print(f"{'='*80}")
    print(f"EMA Length: {EMA_LEN}")
    print(f"Volume Multiplier: {VOL_MULT}x")
    print(f"VWAP Distance: {VWAP_DIST}%")
    print(f"Trading Hours: {TRADE_START} - {TRADE_END}")
    print(f"Data needed for strategy: 210 candles (200 EMA + buffer)")

    # Analyze each day
    print(f"\n{'='*80}")
    print("DAY-BY-DAY BREAKOUT ANALYSIS")
    print(f"{'='*80}")

    total_breakouts = 0
    valid_signals = 0

    for i, date in enumerate(dates):
        if i == 0:
            print(f"\n{date}: SKIPPED (no previous day for PDH/PDL)")
            continue

        # Get PDH/PDL from previous day
        prev_date = dates[i-1]
        prev_day = df[df['date'] == prev_date]
        pdh = prev_day['high'].max()
        pdl = prev_day['low'].min()

        # Today's data
        today = df[df['date'] == date].copy()
        today['prev_close'] = today['close'].shift(1)

        # Find breakouts
        long_breaks = today[
            (today['close'] > pdh) &
            (today['prev_close'] <= pdh)
        ]

        short_breaks = today[
            (today['close'] < pdl) &
            (today['prev_close'] >= pdl)
        ]

        day_breakouts = len(long_breaks) + len(short_breaks)
        total_breakouts += day_breakouts

        print(f"\n{date}:")
        print(f"  PDH: {pdh:.2f} | PDL: {pdl:.2f}")
        print(f"  Day High: {today['high'].max():.2f} | Day Low: {today['low'].min():.2f}")
        print(f"  Breakouts: {len(long_breaks)} LONG, {len(short_breaks)} SHORT")

        # Analyze LONG breakouts
        for idx, row in long_breaks.iterrows():
            vol_ok = row['vol_ok'] if not pd.isna(row['VolMA']) else False
            vwap_ok = row['vwap_ok']
            trend_ok = row['uptrend']
            market_ok = row['market_hours']
            has_ema = row['has_ema']

            valid = vol_ok and vwap_ok and trend_ok and market_ok and has_ema
            if valid:
                valid_signals += 1

            time_str = row['timestamp'].strftime('%H:%M')
            status = "✓ VALID" if valid else "✗ BLOCKED"

            print(f"    {time_str} LONG @ {row['close']:.2f} - {status}")

            if not valid:
                blockers = []
                if not market_ok:
                    blockers.append(f"Outside hours ({row['time_int']})")
                if not has_ema:
                    blockers.append("Insufficient data (<210 candles)")
                if not vol_ok:
                    vol_actual = row['volume']
                    vol_needed = row['VolMA'] * VOL_MULT if not pd.isna(row['VolMA']) else 0
                    blockers.append(f"Low volume ({vol_actual:.0f} < {vol_needed:.0f})")
                if not vwap_ok:
                    blockers.append(f"Too close to VWAP ({row['dist_pct']:.3f}% < {VWAP_DIST}%)")
                if not trend_ok:
                    blockers.append(f"Not in uptrend (Close={row['close']:.2f} < EMA={row['EMA200']:.2f})")

                for blocker in blockers:
                    print(f"       ► {blocker}")

        # Analyze SHORT breakouts
        for idx, row in short_breaks.iterrows():
            vol_ok = row['vol_ok'] if not pd.isna(row['VolMA']) else False
            vwap_ok = row['vwap_ok']
            trend_ok = row['downtrend']
            market_ok = row['market_hours']
            has_ema = row['has_ema']

            valid = vol_ok and vwap_ok and trend_ok and market_ok and has_ema
            if valid:
                valid_signals += 1

            time_str = row['timestamp'].strftime('%H:%M')
            status = "✓ VALID" if valid else "✗ BLOCKED"

            print(f"    {time_str} SHORT @ {row['close']:.2f} - {status}")

            if not valid:
                blockers = []
                if not market_ok:
                    blockers.append(f"Outside hours ({row['time_int']})")
                if not has_ema:
                    blockers.append("Insufficient data (<210 candles)")
                if not vol_ok:
                    vol_actual = row['volume']
                    vol_needed = row['VolMA'] * VOL_MULT if not pd.isna(row['VolMA']) else 0
                    blockers.append(f"Low volume ({vol_actual:.0f} < {vol_needed:.0f})")
                if not vwap_ok:
                    blockers.append(f"Too close to VWAP ({row['dist_pct']:.3f}% < {VWAP_DIST}%)")
                if not trend_ok:
                    blockers.append(f"Not in downtrend (Close={row['close']:.2f} > EMA={row['EMA200']:.2f})")

                for blocker in blockers:
                    print(f"       ► {blocker}")

    # Summary statistics
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total breakout events: {total_breakouts}")
    print(f"Valid trading signals: {valid_signals}")
    print(f"Signal generation rate: {(valid_signals/total_breakouts*100) if total_breakouts > 0 else 0:.1f}%")

    # Filter pass rates (market hours only, sufficient data)
    market_df = df[(df['market_hours']) & (df['has_ema'])].copy()

    if len(market_df) > 0:
        print(f"\n{'='*80}")
        print("FILTER PASS RATES (Market Hours Only)")
        print(f"{'='*80}")
        print(f"Candles during market hours (with EMA data): {len(market_df)}")
        print(f"Volume filter pass: {market_df['vol_ok'].sum()} ({market_df['vol_ok'].mean()*100:.1f}%)")
        print(f"VWAP distance pass: {market_df['vwap_ok'].sum()} ({market_df['vwap_ok'].mean()*100:.1f}%)")
        print(f"Uptrend pass: {market_df['uptrend'].sum()} ({market_df['uptrend'].mean()*100:.1f}%)")
        print(f"Downtrend pass: {market_df['downtrend'].sum()} ({market_df['downtrend'].mean()*100:.1f}%)")

        # All conditions
        all_long = market_df['vol_ok'] & market_df['vwap_ok'] & market_df['uptrend']
        all_short = market_df['vol_ok'] & market_df['vwap_ok'] & market_df['downtrend']

        print(f"\nAll LONG conditions met: {all_long.sum()} ({all_long.mean()*100:.1f}%)")
        print(f"All SHORT conditions met: {all_short.sum()} ({all_short.mean()*100:.1f}%)")

    # Recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")

    if valid_signals == 0:
        print("\n⚠️  ZERO valid signals in the entire period!")
        print("\nMost likely issues:")

        # Find what's blocking most breakouts
        if total_breakouts > 0:
            # Re-analyze all breakouts to find common blockers
            blocker_counts = {
                'volume': 0,
                'vwap_dist': 0,
                'trend': 0,
                'time': 0,
                'data': 0
            }

            for i, date in enumerate(dates[1:], 1):
                prev_date = dates[i-1]
                prev_day = df[df['date'] == prev_date]
                pdh = prev_day['high'].max()
                pdl = prev_day['low'].min()

                today = df[df['date'] == date].copy()
                today['prev_close'] = today['close'].shift(1)

                long_breaks = today[(today['close'] > pdh) & (today['prev_close'] <= pdh)]
                short_breaks = today[(today['close'] < pdl) & (today['prev_close'] >= pdl)]

                for idx, row in pd.concat([long_breaks, short_breaks]).iterrows():
                    if not row['market_hours']:
                        blocker_counts['time'] += 1
                    if not row['has_ema']:
                        blocker_counts['data'] += 1
                    if not (row['vol_ok'] if not pd.isna(row['VolMA']) else False):
                        blocker_counts['volume'] += 1
                    if not row['vwap_ok']:
                        blocker_counts['vwap_dist'] += 1
                    is_long = row['close'] > pdh
                    if is_long and not row['uptrend']:
                        blocker_counts['trend'] += 1
                    elif not is_long and not row['downtrend']:
                        blocker_counts['trend'] += 1

            print(f"\nBlocker frequency (out of {total_breakouts} breakouts):")
            for blocker, count in sorted(blocker_counts.items(), key=lambda x: x[1], reverse=True):
                if count > 0:
                    pct = count/total_breakouts*100
                    print(f"  • {blocker.upper()}: {count} ({pct:.1f}%)")

            # Specific recommendations
            print("\nSuggested parameter changes:")

            if blocker_counts['volume'] > total_breakouts * 0.3:
                print(f"\n1. VOLUME FILTER (blocking {blocker_counts['volume']}/{total_breakouts}):")
                print(f"   Current: VOL_MULT = {VOL_MULT}")
                print(f"   Suggestion: VOL_MULT = 1.0 (or disable entirely)")

            if blocker_counts['vwap_dist'] > total_breakouts * 0.3:
                print(f"\n2. VWAP DISTANCE (blocking {blocker_counts['vwap_dist']}/{total_breakouts}):")
                print(f"   Current: VWAP_DIST = {VWAP_DIST}%")
                print(f"   Suggestion: VWAP_DIST = 0.01% (or disable)")

            if blocker_counts['trend'] > total_breakouts * 0.3:
                print(f"\n3. TREND FILTER (blocking {blocker_counts['trend']}/{total_breakouts}):")
                print(f"   Current: EMA_LEN = {EMA_LEN}")
                print(f"   Suggestion: Use EMA_LEN = 50 or allow counter-trend breakouts")

            if blocker_counts['time'] > total_breakouts * 0.3:
                print(f"\n4. TRADING HOURS (blocking {blocker_counts['time']}/{total_breakouts}):")
                print(f"   Current: {TRADE_START} - {TRADE_END}")
                print(f"   Suggestion: TRADE_START = 915 (many breakouts at market open)")

        else:
            print("\n⚠️  NO BREAKOUTS occurred during this period!")
            print("  • Stock didn't break previous day high/low at all")
            print("  • Try more volatile stocks or different market conditions")

    else:
        print(f"\n✓ Strategy generated {valid_signals} signal(s)")
        print("  Check production logs to see if they were sent to Telegram")

    conn.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Diagnose why no trading signals were generated')
    parser.add_argument('--db', default='market_data.db', help='Path to database')
    parser.add_argument('--symbol', default='INE053F01010', help='Stock symbol to analyze')

    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"❌ Database not found: {args.db}")
        print("\nTo analyze production data:")
        print("1. Copy market_data.db from your production server")
        print("2. Run: python diagnose_strategy.py --db /path/to/market_data.db")
        sys.exit(1)

    analyze_database(args.db, args.symbol)
