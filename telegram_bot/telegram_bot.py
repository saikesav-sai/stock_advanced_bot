"""
Interactive Telegram Bot for Stock Advanced Trading Bot
Allows users to control the bot, view status, and manage monitored symbols
"""
import asyncio
import json
import os
import sys
import threading
import time
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import AUTHORIZED_USERS, INTERVAL, SYMBOLS, TELEGRAM_BOT_TOKEN
from telegram_alerts import send_telegram_alert

# Bot state management
bot_state = {
    "running": False,
    "monitoring_thread": None,
    "current_symbols": [],
    "active_positions": {},
    "total_signals": 0
}

STATE_FILE = "bot_state.json"
LOG_FILE = "telegram_bot.log"


def log(msg):
    """Log message with timestamp"""
    from datetime import timedelta, timezone
    
    ist = timezone(timedelta(hours=5, minutes=30))
    ts = datetime.now(ist).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0530"
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot"""
    if not AUTHORIZED_USERS:
        return True  # Allow all if no restrictions
    return str(user_id) in AUTHORIZED_USERS


def load_bot_state():
    """Load bot state from file"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            log(f"Error loading state: {e}")
    return {}


def save_bot_state(state):
    """Save bot state to file"""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"Error saving state: {e}")


# =====================================================
# Command Handlers
# =====================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text(
            "❌ You are not authorized to use this bot.\n"
            "Please contact the administrator."
        )
        return
    
    welcome_message = (
        "🤖 *Stock Advanced Trading Bot*\n\n"
        "Welcome! This bot monitors stock signals and sends alerts.\n\n"
        "*Available Commands:*\n"
        "/start - Show this welcome message\n"
        "/status - Show current bot status\n"
        "/symbols - View monitored symbols\n"
        "/positions - View active positions\n"
        "/stats - View trading statistics\n"
        "/help - Show detailed help\n\n"
        "Use /status to check if the bot is running."
    )
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")
    log(f"User {user_id} started the bot")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    # Import here to avoid circular dependency
    try:
        from core_logic.main import engines
        
        status_message = "📊 *Bot Status*\n\n"
        
        if engines:
            status_message += f"✅ *Running* - Monitoring {len(engines)} symbol(s)\n\n"
            
            for instrument_key, engine in engines.items():
                symbol = engine.symbol
                status_message += f"*{symbol}*\n"
                status_message += f"• Instrument: `{instrument_key}`\n"
                status_message += f"• Candles: {len(engine.df)}\n"
                
                if engine.active_position:
                    pos = engine.active_position
                    status_message += f"• Position: {pos['side']}\n"
                    status_message += f"  Entry: `{pos['entry']:.2f}`\n"
                    status_message += f"  SL: `{pos['sl']:.2f}` | TP: `{pos['tp']:.2f}`\n"
                else:
                    status_message += "• Position: None\n"
                
                status_message += "\n"
        else:
            status_message += "❌ *Not Running*\n\n"
            status_message += "The monitoring engine is not active.\n"
            status_message += "Please start it using the main script."
        
    except Exception as e:
        status_message = f"⚠️ *Error checking status*\n\n`{str(e)}`"
    
    await update.message.reply_text(status_message, parse_mode="Markdown")


async def symbols_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /symbols command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    symbols_list = SYMBOLS.split(",") if SYMBOLS else []
    
    if not symbols_list:
        await update.message.reply_text(
            "⚠️ No symbols configured.\n"
            "Set SYMBOLS in your .env file."
        )
        return
    
    message = f"📈 *Monitored Symbols* ({len(symbols_list)})\n\n"
    
    for idx, symbol in enumerate(symbols_list, 1):
        message += f"{idx}. `{symbol.strip()}`\n"
    
    message += f"\n*Interval:* `{INTERVAL}`"
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /positions command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    try:
        from core_logic.main import engines
        
        active_positions = []
        for instrument_key, engine in engines.items():
            if engine.active_position:
                active_positions.append({
                    "symbol": engine.symbol,
                    "position": engine.active_position
                })
        
        if not active_positions:
            await update.message.reply_text(
                "📊 *Active Positions*\n\n"
                "No active positions at the moment."
            )
            return
        
        message = f"📊 *Active Positions* ({len(active_positions)})\n\n"
        
        for item in active_positions:
            symbol = item["symbol"]
            pos = item["position"]
            
            emoji = "🟢" if pos["side"] == "LONG" else "🔴"
            
            message += f"{emoji} *{symbol}* - {pos['side']}\n"
            message += f"Entry: `{pos['entry']:.2f}`\n"
            message += f"SL: `{pos['sl']:.2f}` | TP: `{pos['tp']:.2f}`\n\n"
        
        await update.message.reply_text(message, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: `{str(e)}`", parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    try:
        from core_logic.main import engines
        
        message = "📈 *Trading Statistics*\n\n"
        
        for instrument_key, engine in engines.items():
            symbol = engine.symbol
            message += f"*{symbol}*\n"
            message += f"• Historical Candles: {len(engine.df)}\n"
            message += f"• Long Taken Today: {'Yes' if engine.long_taken_today else 'No'}\n"
            message += f"• Short Taken Today: {'Yes' if engine.short_taken_today else 'No'}\n"
            
            if engine.pdh and engine.pdl:
                message += f"• PDH: `{engine.pdh:.2f}` | PDL: `{engine.pdl:.2f}`\n"
            
            message += "\n"
        
        await update.message.reply_text(message, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: `{str(e)}`", parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    help_message = (
        "📚 *Bot Help Guide*\n\n"
        "*Commands:*\n"
        "/start - Initialize the bot\n"
        "/status - Check bot running status and active monitoring\n"
        "/symbols - List all monitored symbols\n"
        "/positions - View all active trading positions\n"
        "/stats - View trading statistics\n"
        "/help - Show this help message\n\n"
        "*How It Works:*\n"
        "1. The bot monitors configured symbols in real-time\n"
        "2. When a trading signal is detected, you receive an alert\n"
        "3. Signals include entry price, stop loss, and take profit\n"
        "4. Both LONG (buy) and SHORT (sell) signals are supported\n\n"
        "*Trading Strategy:*\n"
        "• EMA 200 for trend direction\n"
        "• VWAP for price levels\n"
        "• Volume confirmation\n"
        "• PDH/PDL breakouts\n"
        "• Risk/Reward ratio: 1.6:1\n\n"
        "*Need Help?*\n"
        "Contact the administrator if you have questions."
    )
    
    await update.message.reply_text(help_message, parse_mode="Markdown")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    log(f"Update {update} caused error {context.error}")


# =====================================================
# Bot Initialization
# =====================================================

def run_telegram_bot():
    """Run the Telegram bot"""
    if not TELEGRAM_BOT_TOKEN:
        log("ERROR: TELEGRAM_BOT_TOKEN not set in .env file")
        return
    
    log("Starting Telegram bot...")
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("symbols", symbols_command))
    application.add_handler(CommandHandler("positions", positions_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    log("Telegram bot is ready and polling...")
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_telegram_bot()
