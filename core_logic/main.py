import datetime
import os
import threading
import time
from datetime import datetime, timedelta

import upstox_client
from dotenv import load_dotenv
from LiveStrategyEngine import LiveStrategyEngine

load_dotenv()

# Get multiple symbols from environment (comma-separated)
SYMBOLS_ENV = os.getenv("SYMBOLS")  # e.g., NSE_EQ|INE467B01029,NSE_EQ|INE053F01010

if not SYMBOLS_ENV:
    print("Error: SYMBOLS not set in .env file")
    exit(1)

# Parse multiple instrument keys
INSTRUMENT_KEYS = [key.strip() for key in SYMBOLS_ENV.split(",")]

# Create a dictionary of engines for each stock
engines = {}
for instrument_key in INSTRUMENT_KEYS:
    symbol = instrument_key.split("|")[1] if "|" in instrument_key else None
    if symbol:
        print(f"Initializing LiveStrategyEngine for {symbol} ({instrument_key})...")
        engines[instrument_key] = LiveStrategyEngine(symbol=symbol, instrument_key=instrument_key)
    else:
        print(f"Warning: Invalid instrument key format: {instrument_key}")

if not engines:
    print("Error: No valid symbols found")
    exit(1)

print(f"\nTracking {len(engines)} stocks: {list(engines.keys())}\n")

def on_message(msg):
    if msg["type"] != "live_feed":
        return

    # Process each feed in the message
    for instrument_key, feed_data in msg["feeds"].items():
        if instrument_key not in engines:
            continue
        
        feed = feed_data["fullFeed"]
        engine = engines[instrument_key]
        
        result = engine.update_candle(feed)
        
        ltp = feed["marketFF"]["ltpc"]["ltp"]
        symbol = engine.symbol
        
        if result:
            print(f"[{symbol}] SIGNAL:", result)


def start_streamer():
    configuration = upstox_client.Configuration()
    configuration.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

    streamer = upstox_client.MarketDataStreamerV3(
        upstox_client.ApiClient(configuration),
        INSTRUMENT_KEYS,  # Pass all instrument keys
        "full"
    )

    streamer.on("message", on_message)
    streamer.connect()  # This blocks forever

def wait_next_minute():
    now = datetime.now()
    next_min = (now.replace(second=0, microsecond=0) + timedelta(minutes=1))
    sleep_seconds = (next_min - now + timedelta(seconds=3)).total_seconds()
    print(f"Sleeping until next minute: {sleep_seconds:.2f} seconds...")
    time.sleep(sleep_seconds)


def main():

    thread = threading.Thread(target=start_streamer, daemon=True)

    print("Waiting for next minute to start streamer...")
    wait_next_minute()
    thread.start()

    print("Streaming... Press CTRL+C to stop")

    try:
        while True:
            time.sleep(1)   # prevents 100% CPU load
    except KeyboardInterrupt:
        print("\nStopping program...")
        # Graceful exit (thread is daemon, so it will exit too)
        exit(0)

if __name__ == "__main__":
    main()
