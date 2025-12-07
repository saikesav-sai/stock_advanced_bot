# Quick Setup Guide - Telegram Bot Integration

## Step 1: Create Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Choose a name and username for your bot
4. Copy the bot token (e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

## Step 2: Get Your Chat ID

1. Start a chat with your bot (send any message)
2. Visit this URL in your browser (replace `<BOT_TOKEN>` with your actual token):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
3. Look for `"chat":{"id":123456789}` in the JSON response
4. Copy the chat ID number

## Step 3: Configure .env File

Edit `.env` and add these lines:

```env
TELEGRAM_BOT_TOKEN=paste_your_bot_token_here
TELEGRAM_CHAT_IDS=paste_your_chat_id_here
AUTHORIZED_USERS=paste_your_user_id_here
```

## Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 5: Test Configuration

```bash
python test_telegram.py
```

You should receive test messages in your Telegram chat!

## Step 6: Run the Bot

### Option A: Quick Start (Windows)
```bash
start_bot.bat
```

### Option B: Manual Start

**Terminal 1** - Trading Bot (sends alerts):
```bash
cd core_logic
python main.py
```

**Terminal 2** - Interactive Bot (commands):
```bash
python telegram_bot.py
```

## Telegram Commands

Once running, send these commands to your bot:

- `/start` - Welcome message
- `/status` - Check bot status
- `/symbols` - View monitored stocks
- `/positions` - See active trades
- `/stats` - Trading statistics
- `/help` - Help information

## Troubleshooting

**No messages received?**
- Verify bot token is correct
- Ensure you sent a message to your bot first
- Check chat ID is correct
- Run `test_telegram.py` to diagnose

**Bot commands not working?**
- Make sure `telegram_bot.py` is running
- Check your user ID is in `AUTHORIZED_USERS`
- Send `/start` command first

**No trading signals?**
- Check market hours (9:15 AM - 3:25 PM IST)
- Verify `main.py` is running in `core_logic` folder
- Check symbols are correct in `.env`

## What You'll Receive

**BUY Signal:**
```
🚀 BUY SIGNAL - INE467B01029

📍 Entry Price: 1245.50
🛑 Stop Loss: 1230.25
🎯 Take Profit: 1269.90
📊 Risk/Reward: 1.60
```

**EXIT Signal:**
```
✅ EXIT SIGNAL - INE467B01029

📍 Exit Price: 1269.90
📝 Reason: TP HIT
```

---

For detailed documentation, see `README_TELEGRAM.md`
