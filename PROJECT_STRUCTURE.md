# Stock Advanced Bot - Project Structure

```
stock_advanced_bot/
│
├── 📁 core_logic/                    # Main trading logic
│   ├── main.py                       # ✨ Entry point with Telegram integration
│   ├── LiveStrategyEngine.py         # Trading strategy implementation
│   ├── test_signals.py
│   ├── testing.py
│   └── upstox_LTP_chart.py
│
├── 📁 database_logic/                # Database operations
│   ├── candle_db.py                  # SQLite database for candles
│   └── fetch_historical_candles.py  # Historical data fetcher
│
├── 📁 bin/                           # Utilities
│   ├── base_strategy.py
│   ├── companies_combined.csv
│   └── extract_companies_combined.py
│
├── 📁 ref/                           # Reference implementation
│   ├── bot.py
│   ├── config.py
│   ├── signals.py
│   ├── alerts.py
│   ├── interactive_bot.py
│   ├── requirements.txt
│   └── ...
│
├── 📄 config.py                      # ✨ NEW: Configuration management
├── 📄 telegram_alerts.py             # ✨ NEW: Telegram messaging
├── 📄 telegram_bot.py                # ✨ NEW: Interactive bot
├── 📄 test_telegram.py               # ✨ NEW: Test Telegram setup
├── 📄 auto_fetch_token.py            # Upstox token fetcher
│
├── 📄 requirements.txt               # ✨ UPDATED: Python dependencies
├── 📄 .env                          # ✨ UPDATED: Environment config
├── 📄 .env.example                   # ✨ NEW: Config template
│
├── 📄 start_bot.bat                  # ✨ NEW: Quick start script
├── 📄 README_TELEGRAM.md             # ✨ NEW: Complete documentation
├── 📄 SETUP_GUIDE.md                 # ✨ NEW: Quick setup guide
├── 📄 INTEGRATION_SUMMARY.md         # ✨ NEW: Integration summary
└── 📄 market_data.db                 # SQLite database file

✨ = New or modified files for Telegram integration
```

## Data Flow

```
┌─────────────────┐
│  Upstox API     │
│  (WebSocket)    │
└────────┬────────┘
         │ Real-time tick data
         ▼
┌─────────────────────────┐
│   main.py               │
│   - Receives ticks      │
│   - Forms candles       │
└────────┬────────────────┘
         │ Candle data
         ▼
┌─────────────────────────┐
│  LiveStrategyEngine     │
│  - EMA, VWAP, Volume    │
│  - PDH/PDL breakouts    │
│  - Signal generation    │
└────────┬────────────────┘
         │ Trading signals
         ▼
┌─────────────────────────┐
│  telegram_alerts.py     │
│  - Format message       │
│  - Send to Telegram     │
└────────┬────────────────┘
         │ HTTP POST
         ▼
┌─────────────────────────┐
│  Telegram API           │
│  - Deliver message      │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Your Telegram Chat 📱  │
│  🚀 BUY/SELL signals    │
└─────────────────────────┘
```

## Interactive Bot Flow

```
┌─────────────────────────┐
│  User sends /status     │
│  in Telegram            │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  telegram_bot.py        │
│  - Receives command     │
│  - Check authorization  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Import engines from    │
│  core_logic.main        │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Query engine status    │
│  - Active positions     │
│  - Candle count         │
│  - PDH/PDL values       │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Format response        │
│  Send back to user      │
└─────────────────────────┘
```

## Configuration Flow

```
.env file
    ├── TELEGRAM_BOT_TOKEN ──────┐
    ├── TELEGRAM_CHAT_IDS ───────┤
    ├── AUTHORIZED_USERS ────────┤
    ├── SYMBOLS ─────────────────┤
    ├── UPSTOX_ACCESS_TOKEN ─────┤
    └── Trading parameters ──────┤
                                 │
                                 ▼
                           ┌─────────────┐
                           │  config.py  │
                           └─────┬───────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
            telegram_bot.py  telegram_   main.py
                             alerts.py
```

## Running Configuration

### Scenario 1: Alerts Only
```
Terminal 1:
cd core_logic
python main.py

Result: Automatic Telegram alerts for signals
```

### Scenario 2: Full Interactive Bot
```
Terminal 1:                Terminal 2:
cd core_logic             python telegram_bot.py
python main.py            

Result: 
- Automatic alerts        - Bot commands work
- Signal monitoring       - /status, /positions, etc.
```

### Scenario 3: Quick Start
```
start_bot.bat
  ├── Option 1: Trading bot only
  ├── Option 2: Interactive bot only
  └── Option 3: Both (opens 2 terminals)
```

## Key Components

| Component | Purpose | Runs Where |
|-----------|---------|------------|
| `main.py` | Monitor stocks, detect signals, send alerts | Terminal/Background |
| `telegram_bot.py` | Handle bot commands (/status, /positions) | Optional Terminal |
| `LiveStrategyEngine.py` | Trading strategy logic | Called by main.py |
| `telegram_alerts.py` | Send messages to Telegram | Called by main.py |
| `config.py` | Configuration management | Imported everywhere |
| `test_telegram.py` | Test Telegram setup | Run once for testing |

## Dependencies

```
Python 3.8+
├── pandas (data manipulation)
├── numpy (calculations)
├── python-telegram-bot (Telegram API)
├── requests (HTTP requests)
├── python-dotenv (environment vars)
├── upstox-python-sdk (market data)
└── pytz (timezone handling)
```

Install all: `pip install -r requirements.txt`
