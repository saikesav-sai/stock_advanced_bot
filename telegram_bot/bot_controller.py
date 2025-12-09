"""
Telegram Bot Controller
Interactive bot to control the stock trading program with a clean UI
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler,
                          filters)

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core_logic.logger_config import get_logger
from telegram_bot.config import AUTHORIZED_USERS, TELEGRAM_BOT_TOKEN

logger = get_logger()

# Conversation states
ADDING_STOCK, REMOVING_STOCK = range(2)

# Global variable to track the trading process
trading_process = None
trading_status = "stopped"

class TradingBotController:
    def __init__(self):
        self.env_path = Path(__file__).parent.parent / ".env"
        self.main_script = Path(__file__).parent.parent / "core_logic" / "main.py"
        
    def read_env(self):
        """Read .env file and return as dictionary"""
        env_vars = {}
        if self.env_path.exists():
            with open(self.env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        return env_vars
    
    def write_env(self, env_vars):
        """Write dictionary back to .env file"""
        with open(self.env_path, 'w') as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
    
    def get_symbols(self):
        """Get current list of symbols from .env"""
        env_vars = self.read_env()
        symbols_str = env_vars.get('SYMBOLS', '')
        if symbols_str:
            return [s.strip() for s in symbols_str.split(',') if s.strip()]
        return []
    
    def add_symbol(self, symbol):
        """Add a new symbol to .env"""
        symbols = self.get_symbols()
        symbol = symbol.strip()
        
        if symbol in symbols:
            return False, "Symbol already exists"
        
        symbols.append(symbol)
        env_vars = self.read_env()
        env_vars['SYMBOLS'] = ','.join(symbols)
        self.write_env(env_vars)
        return True, f"Added {symbol}"
    
    def remove_symbol(self, symbol):
        """Remove a symbol from .env"""
        symbols = self.get_symbols()
        symbol = symbol.strip()
        
        if symbol not in symbols:
            return False, "Symbol not found"
        
        symbols.remove(symbol)
        env_vars = self.read_env()
        env_vars['SYMBOLS'] = ','.join(symbols)
        self.write_env(env_vars)
        return True, f"Removed {symbol}"
    
    def start_trading(self):
        """Start the main trading script"""
        global trading_process, trading_status
        
        if trading_status == "running":
            return False, "Trading bot is already running"
        
        try:
            # Start the main.py script as a subprocess
            trading_process = subprocess.Popen(
                [sys.executable, str(self.main_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            trading_status = "running"
            logger.info("Trading bot started successfully")
            return True, "✅ Trading bot started successfully"
        except Exception as e:
            logger.error(f"Failed to start trading bot: {e}")
            return False, f"❌ Failed to start: {str(e)}"
    
    def stop_trading(self):
        """Stop the trading script"""
        global trading_process, trading_status
        
        if trading_status == "stopped":
            return False, "Trading bot is not running"
        
        try:
            if trading_process:
                trading_process.terminate()
                trading_process.wait(timeout=5)
                trading_process = None
            trading_status = "stopped"
            logger.info("Trading bot stopped successfully")
            return True, "🛑 Trading bot stopped successfully"
        except Exception as e:
            logger.error(f"Failed to stop trading bot: {e}")
            if trading_process:
                trading_process.kill()
                trading_process = None
            trading_status = "stopped"
            return True, "🛑 Trading bot force stopped"
    
    def get_status(self):
        """Get current status of trading bot and configuration"""
        symbols = self.get_symbols()
        env_vars = self.read_env()
        
        status_msg = f"🤖 <b>Trading Bot Status</b>\n\n"
        status_msg += f"Status: {'🟢 Running' if trading_status == 'running' else '🔴 Stopped'}\n\n"
        status_msg += f"📊 <b>Tracked Stocks ({len(symbols)}):</b>\n"
        
        if symbols:
            for i, symbol in enumerate(symbols, 1):
                status_msg += f"{i}. <code>{symbol}</code>\n"
        else:
            status_msg += "<i>No stocks configured</i>\n"
        
        status_msg += f"\n⚙️ <b>Configuration:</b>\n"
        status_msg += f"Interval: <code>{env_vars.get('INTERVAL', '1m')}</code>\n"
        status_msg += f"EMA Length: <code>{env_vars.get('EMA_LENGTH', '200')}</code>\n"
        status_msg += f"Risk/Reward: <code>{env_vars.get('RISK_REWARD', '1.6')}</code>\n"
        
        return status_msg

# Initialize controller
controller = TradingBotController()

def is_authorized(user_id):
    """Check if user is authorized to use the bot"""
    if not AUTHORIZED_USERS:
        logger.warning("No authorized users configured!")
        return False
    return str(user_id) in AUTHORIZED_USERS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show main menu"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("▶️ Start Bot", callback_data="start_bot"),
            InlineKeyboardButton("⏹️ Stop Bot", callback_data="stop_bot")
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("📈 Stocks", callback_data="stocks_menu")
        ],
        [
            InlineKeyboardButton("⚙️ Config", callback_data="config"),
            InlineKeyboardButton("❓ Help", callback_data="help")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_msg = (
        "🤖 <b>Stock Trading Bot Controller</b>\n\n"
        "Welcome! Use the buttons below to control your trading bot.\n\n"
        "• Start/Stop the trading program\n"
        "• Manage your stock watchlist\n"
        "• View configuration and status"
    )
    
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_authorized(user_id):
        await query.answer("❌ Not authorized", show_alert=True)
        return
    
    await query.answer()
    
    data = query.data
    
    if data == "start_bot":
        success, message = controller.start_trading()
        await query.edit_message_text(
            f"{message}\n\nUse /menu to return to main menu."
        )
    
    elif data == "stop_bot":
        success, message = controller.stop_trading()
        await query.edit_message_text(
            f"{message}\n\nUse /menu to return to main menu."
        )
    
    elif data == "status":
        status_msg = controller.get_status()
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(status_msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    elif data == "stocks_menu":
        symbols = controller.get_symbols()
        msg = f"📈 <b>Stock Management</b>\n\n"
        msg += f"Current stocks ({len(symbols)}):\n"
        
        if symbols:
            for i, symbol in enumerate(symbols, 1):
                msg += f"{i}. <code>{symbol}</code>\n"
        else:
            msg += "<i>No stocks configured</i>\n"
        
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Stock", callback_data="add_stock"),
                InlineKeyboardButton("➖ Remove Stock", callback_data="remove_stock")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    elif data == "add_stock":
        await query.edit_message_text(
            "➕ <b>Add New Stock</b>\n\n"
            "Send the instrument key in format:\n"
            "<code>NSE_EQ|INE467B01029</code>\n\n"
            "Or send /cancel to go back.",
            parse_mode=ParseMode.HTML
        )
        return ADDING_STOCK
    
    elif data == "remove_stock":
        symbols = controller.get_symbols()
        if not symbols:
            await query.edit_message_text(
                "No stocks to remove.\n\nUse /menu to return."
            )
            return ConversationHandler.END
        
        keyboard = []
        for symbol in symbols:
            keyboard.append([InlineKeyboardButton(f"❌ {symbol}", callback_data=f"rm_{symbol}")])
        keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data="stocks_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "➖ <b>Remove Stock</b>\n\nSelect a stock to remove:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    
    elif data.startswith("rm_"):
        symbol = data[3:]
        success, message = controller.remove_symbol(symbol)
        
        if success:
            await query.edit_message_text(
                f"✅ {message}\n\nUse /menu to return to main menu."
            )
        else:
            await query.edit_message_text(
                f"❌ {message}\n\nUse /menu to return to main menu."
            )
    
    elif data == "config":
        env_vars = controller.read_env()
        msg = "⚙️ <b>Current Configuration</b>\n\n"
        
        config_items = {
            'INTERVAL': 'Candle Interval',
            'EMA_LENGTH': 'EMA Length',
            'VOL_LENGTH': 'Volume Length',
            'VOL_MULTIPLIER': 'Volume Multiplier',
            'RISK_REWARD': 'Risk/Reward Ratio',
            'VWAP_DISTANCE': 'VWAP Distance',
            'SL_BUFFER': 'Stop Loss Buffer',
            'TRADE_START_TIME': 'Trading Start',
            'TRADE_END_TIME': 'Trading End'
        }
        
        for key, label in config_items.items():
            value = env_vars.get(key, 'Not set')
            msg += f"• {label}: <code>{value}</code>\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    elif data == "help":
        help_msg = (
            "❓ <b>Help &amp; Commands</b>\n\n"
            "<b>Main Features:</b>\n"
            "• Start/Stop - Control the trading bot\n"
            "• Status - View bot status and stocks\n"
            "• Stocks - Add/remove stocks from watchlist\n"
            "• Config - View trading parameters\n\n"
            "<b>Commands:</b>\n"
            "/start - Show main menu\n"
            "/menu - Return to main menu\n"
            "/status - Quick status check\n\n"
            "<b>Stock Format:</b>\n"
            "Use format: <code>EXCHANGE|ISIN</code>\n"
            "Example: <code>NSE_EQ|INE467B01029</code>"
        )
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    elif data == "main_menu":
        keyboard = [
            [
                InlineKeyboardButton("▶️ Start Bot", callback_data="start_bot"),
                InlineKeyboardButton("⏹️ Stop Bot", callback_data="stop_bot")
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("📈 Stocks", callback_data="stocks_menu")
            ],
            [
                InlineKeyboardButton("⚙️ Config", callback_data="config"),
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🤖 <b>Stock Trading Bot Controller</b>\n\nSelect an option:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def add_stock_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding a new stock"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END
    
    symbol = update.message.text.strip()
    
    # Validate format
    if '|' not in symbol or len(symbol.split('|')) != 2:
        await update.message.reply_text(
            "❌ Invalid format. Use: <code>EXCHANGE|ISIN</code>\n"
            "Example: <code>NSE_EQ|INE467B01029</code>\n\n"
            "Try again or send /cancel",
            parse_mode=ParseMode.HTML
        )
        return ADDING_STOCK
    
    success, message = controller.add_symbol(symbol)
    
    if success:
        await update.message.reply_text(
            f"✅ {message}\n\nUse /menu to return to main menu."
        )
    else:
        await update.message.reply_text(
            f"❌ {message}\n\nUse /menu to return to main menu."
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    await update.message.reply_text(
        "Operation cancelled. Use /menu to return to main menu."
    )
    return ConversationHandler.END

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("▶️ Start Bot", callback_data="start_bot"),
            InlineKeyboardButton("⏹️ Stop Bot", callback_data="stop_bot")
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("📈 Stocks", callback_data="stocks_menu")
        ],
        [
            InlineKeyboardButton("⚙️ Config", callback_data="config"),
            InlineKeyboardButton("❓ Help", callback_data="help")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 <b>Stock Trading Bot Controller</b>\n\nSelect an option:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick status command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return
    
    status_msg = controller.get_status()
    await update.message.reply_text(status_msg, parse_mode=ParseMode.HTML)

def main():
    """Run the bot"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in .env file")
        print("Error: TELEGRAM_BOT_TOKEN not set in .env file")
        return
    
    if not AUTHORIZED_USERS:
        logger.error("AUTHORIZED_USERS not set in .env file")
        print("Error: AUTHORIZED_USERS not set in .env file")
        return
    
    # Create application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Conversation handler for adding stocks
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^add_stock$")],
        states={
            ADDING_STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_stock_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Start bot
    logger.info("Starting Telegram bot controller...")
    print("🤖 Telegram bot controller started!")
    print(f"Authorized users: {', '.join(AUTHORIZED_USERS)}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
