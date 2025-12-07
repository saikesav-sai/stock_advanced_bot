# Stock Advanced Bot - Telegram Integration

A sophisticated stock trading bot that monitors real-time market data via Upstox API and sends trading signals through Telegram.

## Features

- 📊 Real-time stock monitoring using Upstox WebSocket streams
- 🤖 Interactive Telegram bot with commands
- 📈 Advanced trading strategy with EMA200, VWAP, and volume analysis
- 🎯 Automatic signal detection (BUY/SELL) with entry, stop-loss, and take-profit levels
- 📱 Instant Telegram alerts for trading signals
- 💾 SQLite database for historical candle data
- 🔄 Multiple stock monitoring simultaneously
- 📉 Previous Day High (PDH) and Previous Day Low (PDL) breakout strategy

## Trading Strategy

The bot uses a multi-factor strategy:

1. **Trend Filter**: Price above/below EMA200
2. **Volume Confirmation**: Volume > 1.5x average volume
3. **VWAP Distance**: Minimum 0.15% distance from VWAP
4. **Breakout Signals**: PDH/PDL breaks
5. **Risk Management**: Fixed Risk/Reward ratio of 1.6:1

## Installation

### 1. Clone or Download the Project

```bash
cd stock_advanced_bot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` command
3. Follow instructions to create your bot
4. Copy the bot token (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
5. Start a chat with your bot and send any message
6. Get your Chat ID by visiting: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Look for `"chat":{"id":123456789}` in the response

### 4. Configure Environment Variables

Edit the `.env` file with your credentials:

```env
# Upstox Configuration
UPSTOX_CLIENT_ID=your_client_id
UPSTOX_CLIENT_SECRET=your_client_secret
UPSTOX_ACCESS_TOKEN=your_access_token
UPSTOX_REDIRECT_URI=http://localhost

# Stock Symbols (comma-separated)
SYMBOLS=NSE_EQ|INE053F01010,NSE_EQ|INE467B01029
INTERVAL=1m

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_IDS=your_chat_id
AUTHORIZED_USERS=your_user_id

# Optional: Trading Parameters
# EMA_LENGTH=200
# VOL_LENGTH=20
# VOL_MULTIPLIER=1.5
# RISK_REWARD=1.6
# VWAP_DISTANCE=0.15
# SL_BUFFER=0.08
# TRADE_START_TIME=915
# TRADE_END_TIME=1525
```

### 5. Get Upstox Access Token

Run the token fetcher (if you don't have a token):

```bash
python auto_fetch_token.py
```

This will open a browser window for Upstox authentication.

## Usage

### Running the Trading Bot

The main bot monitors stocks and sends Telegram alerts:

```bash
cd core_logic
python main.py
```

### Running the Interactive Telegram Bot (Optional)

For interactive commands, run the Telegram bot in a separate terminal:

```bash
python telegram_bot.py
```

## Telegram Bot Commands

Once the bot is running, you can interact with it via Telegram:

- `/start` - Initialize and get welcome message
- `/status` - Check bot status and active monitoring
- `/symbols` - View all monitored symbols
- `/positions` - View active trading positions
- `/stats` - View trading statistics (PDH/PDL, candles, etc.)
- `/help` - Display help information

## Signal Format

When a trading signal is detected, you'll receive a message like:

```
🚀 BUY SIGNAL - INE467B01029

📍 Entry Price: 1245.50
🛑 Stop Loss: 1230.25
🎯 Take Profit: 1269.90
📊 Risk/Reward: 1.60
```

## Project Structure

```
stock_advanced_bot/
├── core_logic/
│   ├── main.py                    # Main entry point with WebSocket streaming
│   ├── LiveStrategyEngine.py      # Trading strategy logic
│   ├── test_signals.py
│   ├── testing.py
│   └── upstox_LTP_chart.py
├── database_logic/
│   ├── candle_db.py               # SQLite database operations
│   └── fetch_historical_candles.py
├── bin/
│   ├── base_strategy.py
│   ├── companies_combined.csv
│   └── extract_companies_combined.py
├── ref/                           # Reference implementation
│   ├── bot.py
│   ├── config.py
│   ├── signals.py
│   └── ...
├── config.py                      # Configuration management
├── telegram_alerts.py             # Telegram alert functions
├── telegram_bot.py                # Interactive Telegram bot
├── auto_fetch_token.py            # Upstox token fetcher
├── requirements.txt               # Python dependencies
├── .env                          # Environment variables
└── README_TELEGRAM.md            # This file
```

## How It Works

1. **Data Collection**: The bot connects to Upstox WebSocket API and receives real-time tick data
2. **Candle Formation**: Tick data is aggregated into 1-minute candles
3. **Strategy Execution**: Each completed candle is analyzed using the trading strategy
4. **Signal Generation**: When conditions are met, a BUY or SELL signal is generated
5. **Telegram Alert**: Signal details are sent to your Telegram chat
6. **Position Management**: Stop-loss and take-profit levels are monitored

## Advanced Features

### Multiple Stock Monitoring

To monitor multiple stocks, add them to the `SYMBOLS` variable:

```env
SYMBOLS=NSE_EQ|INE053F01010,NSE_EQ|INE467B01029,NSE_EQ|INE009A01021
```

### Multiple Chat Recipients

To send alerts to multiple Telegram chats:

```env
TELEGRAM_CHAT_IDS=123456789,987654321,555666777
```

### Authorization Control

Restrict bot access to specific users:

```env
AUTHORIZED_USERS=123456789,987654321
```

## Troubleshooting

### Bot Not Sending Messages

1. Check `TELEGRAM_BOT_TOKEN` is correct
2. Verify `TELEGRAM_CHAT_IDS` are correct
3. Ensure you've sent at least one message to your bot
4. Check internet connectivity

### No Trading Signals

1. Verify market hours (9:15 AM - 3:25 PM IST)
2. Check if historical data is loaded properly
3. Ensure symbols are correct and trading is active
4. Review strategy parameters in `.env`

### Upstox Connection Issues

1. Verify `UPSTOX_ACCESS_TOKEN` is valid (tokens expire daily)
2. Run `auto_fetch_token.py` to get a new token
3. Check Upstox API status

### Import Errors

```bash
pip install -r requirements.txt --upgrade
```

## Security Notes

⚠️ **Important Security Reminders:**

1. Never commit `.env` file to version control
2. Keep your Telegram bot token private
3. Restrict authorized users in production
4. Regularly rotate Upstox access tokens
5. Use environment-specific configurations

## Support & Contribution

For issues, questions, or contributions:

1. Check the logs in `market_data.db` and console output
2. Review error messages in terminal
3. Ensure all dependencies are installed
4. Verify API credentials and tokens

## License

This project is for educational and personal use only. Use at your own risk. Trading involves financial risk.

---

**Happy Trading! 📈🚀**
