"""
Telegram Bot Controller
Interactive bot to control the stock trading program with a clean UI
"""
import os
import subprocess
import sys
import time
from datetime import datetime
from datetime import time as dt_time
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler,
                          filters)

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core_logic.logger_config import get_logger
from telegram_bot.config import (AUTHORIZED_USERS, TELEGRAM_BOT_TOKEN,
                                 TRADE_END_TIME, TRADE_START_TIME)
from telegram_bot.symbol_lookup import get_lookup
from telegram_bot.token_manager import get_token_manager

logger = get_logger()

# Conversation states
ADDING_STOCK, REMOVING_STOCK, EXCHANGE_SELECTION, WAITING_AUTH_CODE = range(4)

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
    
    def get_symbols_with_names(self):
        """Get symbols with their stock names"""
        symbols = self.get_symbols()
        lookup = get_lookup()
        result = []
        
        for symbol in symbols:
            details = lookup.parse_instrument_key(symbol)
            if details:
                result.append({
                    'instrument_key': symbol,
                    'name': details['name'],
                    'trading_symbol': details['trading_symbol'],
                    'exchange': details['exchange']
                })
            else:
                result.append({
                    'instrument_key': symbol,
                    'name': 'Unknown',
                    'trading_symbol': 'Unknown',
                    'exchange': 'Unknown'
                })
        
        return result
    
    def add_symbol(self, stock_name, exchange):
        """Add a new symbol to .env using stock name and exchange"""
        symbols = self.get_symbols()
        lookup = get_lookup()
        
        # Create instrument key from stock name
        instrument_key = lookup.create_instrument_key(stock_name, exchange)
        
        if not instrument_key:
            return False, f"Stock '{stock_name}' not found for exchange {exchange}"
        
        if instrument_key in symbols:
            return False, "Stock already exists in watchlist"
        
        symbols.append(instrument_key)
        env_vars = self.read_env()
        env_vars['SYMBOLS'] = ','.join(symbols)
        self.write_env(env_vars)
        
        return True, f"Added {stock_name} ({exchange})"
    
    def remove_symbol(self, instrument_key):
        """Remove a symbol from .env"""
        symbols = self.get_symbols()
        instrument_key = instrument_key.strip()
        
        if instrument_key not in symbols:
            return False, "Stock not found"
        
        # Get stock name for confirmation message
        lookup = get_lookup()
        details = lookup.parse_instrument_key(instrument_key)
        stock_name = details['name'] if details else instrument_key
        
        symbols.remove(instrument_key)
        env_vars = self.read_env()
        env_vars['SYMBOLS'] = ','.join(symbols)
        self.write_env(env_vars)
        return True, f"Removed {stock_name}"
    
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
        symbols_with_names = self.get_symbols_with_names()
        env_vars = self.read_env()
        
        status_msg = f"🤖 <b>Trading Bot Status</b>\n\n"
        status_msg += f"Status: {'🟢 Running' if trading_status == 'running' else '🔴 Stopped'}\n\n"
        status_msg += f"📊 <b>Tracked Stocks ({len(symbols_with_names)}):</b>\n"
        
        if symbols_with_names:
            for i, stock in enumerate(symbols_with_names, 1):
                status_msg += f"{i}. <b>{stock['name']}</b> (<code>{stock['trading_symbol']}</code>) - {stock['exchange']}\n"
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
            InlineKeyboardButton("🔑 Token", callback_data="token_menu")
        ],
        [
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
        return ConversationHandler.END
    
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
        symbols_with_names = controller.get_symbols_with_names()
        msg = f"📈 <b>Stock Management</b>\n\n"
        msg += f"Current stocks ({len(symbols_with_names)}):\n"
        
        if symbols_with_names:
            for i, stock in enumerate(symbols_with_names, 1):
                msg += f"{i}. <b>{stock['name']}</b> (<code>{stock['trading_symbol']}</code>) - {stock['exchange']}\n"
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
        keyboard = [
            [InlineKeyboardButton("NSE", callback_data="exchange_NSE_EQ")],
            [InlineKeyboardButton("BSE", callback_data="exchange_BSE_EQ")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="stocks_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "➕ <b>Add New Stock</b>\n\n"
            "First, select the exchange:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return
    
    elif data.startswith("exchange_"):
        exchange = data.replace("exchange_", "")
        context.user_data['selected_exchange'] = exchange
        await query.edit_message_text(
            f"➕ <b>Add New Stock - {exchange}</b>\n\n"
            f"Now, send the stock name or trading symbol.\n\n"
            f"<b>Examples:</b>\n"
            f"• RELIANCE\n"
            f"• TCS\n"
            f"• TATAMOTORS\n"
            f"• Infosys\n\n"
            f"Or send /cancel to go back.",
            parse_mode=ParseMode.HTML
        )
        return ADDING_STOCK
    
    elif data == "remove_stock":
        symbols_with_names = controller.get_symbols_with_names()
        if not symbols_with_names:
            await query.edit_message_text(
                "No stocks to remove.\n\nUse /menu to return."
            )
            return ConversationHandler.END
        
        keyboard = []
        for stock in symbols_with_names:
            button_text = f"❌ {stock['name']} ({stock['trading_symbol']})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"rm_{stock['instrument_key']}")])
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
            "<b>Adding Stocks:</b>\n"
            "1. Select exchange (NSE or BSE)\n"
            "2. Enter stock name or trading symbol\n"
            "Examples: RELIANCE, TCS, TATAMOTORS\n\n"
            "The bot will automatically find the correct ISIN code."
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
                InlineKeyboardButton("🔑 Token", callback_data="token_menu")
            ],
            [
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🤖 <b>Stock Trading Bot Controller</b>\n\nSelect an option:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    
    elif data == "token_menu":
        token_manager = get_token_manager()
        token_info = token_manager.get_token_info()
        
        status_icon = "✅" if token_info['is_valid'] else "❌"
        msg = f"🔑 <b>Upstox Token Status</b>\n\n"
        msg += f"Status: {status_icon} {token_info['message']}\n"
        msg += f"Last Checked: {token_info['checked_at']}\n\n"
        
        if not token_info['is_valid']:
            msg += "⚠️ <b>Token needs refresh!</b>\n"
            msg += "Click 'Check Token' to verify or 'Refresh Token' to update.\n"
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Check Token", callback_data="check_token"),
                InlineKeyboardButton("🔑 Refresh Token", callback_data="refresh_token")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    elif data == "check_token":
        token_manager = get_token_manager()
        is_valid, message = token_manager.check_token_validity()
        
        status_icon = "✅" if is_valid else "❌"
        msg = f"🔑 <b>Token Check Result</b>\n\n"
        msg += f"{status_icon} {message}\n\n"
        msg += f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="token_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    elif data == "refresh_token":
        token_manager = get_token_manager()
        auth_url = token_manager.get_authorization_url()
        
        if not auth_url:
            msg = "❌ <b>Error</b>\n\nMissing Upstox credentials in .env file."
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="token_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            return
        
        # Create clickable button with the auth URL
        keyboard = [
            [InlineKeyboardButton("🔐 Login to Upstox", url=auth_url)],
            [InlineKeyboardButton("✅ I've Authorized", callback_data="auth_complete")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="token_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = (
            "🔑 <b>Token Refresh Process</b>\n\n"
            "<b>Step 1:</b> Click the 'Login to Upstox' button below\n"
            "<b>Step 2:</b> Enter OTP and authorize the app\n"
            "<b>Step 3:</b> Copy the authorization code from the redirect URL\n"
            "<b>Step 4:</b> Click 'I've Authorized' and paste the code\n\n"
            "The redirect URL will look like:\n"
            "<code>http://your-redirect-uri/?code=XXXXX</code>\n\n"
            "Copy only the code part (after <code>code=</code>)"
        )
        
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    elif data == "auth_complete":
        msg = (
            "📝 <b>Enter Authorization Code</b>\n\n"
            "Please send the authorization code you received from the redirect URL.\n\n"
            "Example: If the URL is:\n"
            "<code>http://localhost/?code=abc123xyz</code>\n\n"
            "Send: <code>abc123xyz</code>\n\n"
            "Or send /cancel to abort."
        )
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        return WAITING_AUTH_CODE

async def add_stock_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding a new stock"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END
    
    stock_name = update.message.text.strip()
    exchange = context.user_data.get('selected_exchange')
    
    logger.info(f"Add stock handler: stock_name='{stock_name}', exchange='{exchange}'")
    
    if not exchange:
        await update.message.reply_text(
            "❌ Exchange not selected. Please start over with /menu"
        )
        return ConversationHandler.END
    
    # Search for the stock first
    lookup = get_lookup()
    search_results = lookup.search_stocks(stock_name, limit=5)
    
    # Filter by exchange
    exchange_clean = exchange.replace('_EQ', '')
    filtered_results = [r for r in search_results if r['exchange'].upper() == exchange_clean.upper()]
    
    logger.info(f"Stock search: '{stock_name}' on {exchange}, found {len(filtered_results)} results")
    
    if not filtered_results:
        await update.message.reply_text(
            f"❌ Stock '{stock_name}' not found on {exchange}.\n\n"
            f"Please check the spelling and try again, or send /cancel to go back.",
            parse_mode=ParseMode.HTML
        )
        return ADDING_STOCK
    
    # If exact match found, use it; otherwise use first result
    selected_stock = filtered_results[0]
    
    success, message = controller.add_symbol(selected_stock['name'], exchange)
    
    if success:
        await update.message.reply_text(
            f"✅ {message}\n\n<b>Stock Details:</b>\n"
            f"Name: {selected_stock['name']}\n"
            f"Symbol: <code>{selected_stock['trading_symbol']}</code>\n"
            f"Exchange: {exchange}\n\n"
            f"Use /menu to return to main menu.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"❌ {message}\n\nUse /menu to return to main menu."
        )
    
    # Clear user data
    context.user_data.clear()
    
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
            InlineKeyboardButton("🔑 Token", callback_data="token_menu")
        ],
        [
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

async def refresh_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger token refresh process"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return
    
    token_manager = get_token_manager()
    auth_url = token_manager.get_authorization_url()
    
    if not auth_url:
        await update.message.reply_text(
            "❌ <b>Error</b>\n\nMissing Upstox credentials in .env file.",
            parse_mode=ParseMode.HTML
        )
        return
    
    keyboard = [[InlineKeyboardButton("🔐 Login to Upstox", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔑 <b>Token Refresh</b>\n\n"
        "Click the button below to login to Upstox in your browser.\n\n"
        "After authorizing, copy the code from the redirect URL and send it back here.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_auth_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle authorization code submission"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END
    
    auth_code = update.message.text.strip()
    
    await update.message.reply_text("🔄 <b>Processing...</b>\n\nExchanging code for access token...", parse_mode=ParseMode.HTML)
    
    token_manager = get_token_manager()
    success, message, token = token_manager.exchange_code_for_token(auth_code)
    
    if success:
        await update.message.reply_text(
            f"✅ <b>Success!</b>\n\n{message}\n\n"
            f"Your Upstox access token has been updated.\n\n"
            f"Use /menu to return to main menu.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"❌ <b>Failed</b>\n\n{message}\n\n"
            f"Please try again with /refresh_token",
            parse_mode=ParseMode.HTML
        )
    
    return ConversationHandler.END

async def send_startup_message(app):
    """Send startup message to all authorized users"""
    startup_msg = (
        "🟢 <b>Bot Started</b>\n\n"
        "The trading bot controller is now online and ready!\n\n"
        "Use /start to access the main menu."
    )
    
    for user_id in AUTHORIZED_USERS:
        try:
            await app.bot.send_message(
                chat_id=user_id,
                text=startup_msg,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Startup message sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send startup message to user {user_id}: {e}")

async def notify_users(app, message):
    """Send notification to all authorized users"""
    for user_id in AUTHORIZED_USERS:
        try:
            await app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send notification to user {user_id}: {e}")

async def check_token_daily(context: ContextTypes.DEFAULT_TYPE):
    """Check Upstox token validity daily"""
    token_manager = get_token_manager()
    is_valid, message = token_manager.check_token_validity()
    
    logger.info(f"Daily token check: {message}")
    
    if not is_valid:
        warning_msg = (
            "⚠️ <b>Token Status Alert</b>\n\n"
            f"{message}\n\n"
            "Please refresh your Upstox access token.\n"
            "Use the 🔑 Token menu or /refresh_token command."
        )
        await notify_users(context.application, warning_msg)

async def check_trading_hours(context: ContextTypes.DEFAULT_TYPE):
    """Check if it's time to start or stop trading"""
    global trading_status
    
    now = datetime.now()
    current_time = now.hour * 100 + now.minute
    
    # Convert TRADE_START_TIME and TRADE_END_TIME to comparable format
    # e.g., 915 -> 9:15, 1525 -> 15:25
    start_hour = TRADE_START_TIME // 100
    start_min = TRADE_START_TIME % 100
    end_hour = TRADE_END_TIME // 100
    end_min = TRADE_END_TIME % 100
    
    start_time = start_hour * 100 + start_min
    end_time = end_hour * 100 + end_min
    
    # Check if within trading hours
    is_trading_hours = start_time <= current_time <= end_time
    
    # Auto-start at trading start time
    if current_time == start_time and trading_status == "stopped":
        success, message = controller.start_trading()
        if success:
            logger.info("Auto-started trading bot at market open")
            await notify_users(context.application, 
                f"⏰ <b>Auto-Start</b>\n\n{message}\n\nMarket hours have begun.")
    
    # Auto-stop at trading end time
    elif current_time == end_time and trading_status == "running":
        success, message = controller.stop_trading()
        if success:
            logger.info("Auto-stopped trading bot at market close")
            await notify_users(context.application,
                f"⏰ <b>Auto-Stop</b>\n\n{message}\n\nMarket hours have ended.")
    
    # Also stop if running outside trading hours
    elif not is_trading_hours and trading_status == "running":
        success, message = controller.stop_trading()
        if success:
            logger.info("Auto-stopped trading bot (outside trading hours)")
            await notify_users(context.application,
                f"⏰ <b>Auto-Stop</b>\n\n{message}\n\nOutside trading hours.")

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
    stock_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^add_stock$"),
            CallbackQueryHandler(button_handler, pattern="^exchange_")
        ],
        states={
            ADDING_STOCK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_stock_handler),
                CallbackQueryHandler(button_handler, pattern="^exchange_")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )
    
    # Conversation handler for token refresh
    token_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^auth_complete$"),
            CommandHandler("refresh_token", refresh_token_command)
        ],
        states={
            WAITING_AUTH_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_auth_code)
            ],
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
    app.add_handler(stock_conv_handler)
    app.add_handler(token_conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Start bot
    logger.info("Starting Telegram bot controller...")
    print("🤖 Telegram bot controller started!")
    print(f"Authorized users: {', '.join(AUTHORIZED_USERS)}")
    print(f"Auto-trading hours: {TRADE_START_TIME} to {TRADE_END_TIME}")
    
    # Set up job queue for scheduled tasks
    if app.job_queue:
        # Check trading hours every minute
        app.job_queue.run_repeating(check_trading_hours, interval=60, first=10)
        logger.info("Scheduled auto-start/stop based on trading hours")
        
        # Check token validity daily at 8:30 AM
        app.job_queue.run_daily(
            check_token_daily,
            time=dt_time(hour=8, minute=30),
            days=(0, 1, 2, 3, 4, 5, 6)  # All days
        )
        logger.info("Scheduled daily token validity check at 8:30 AM")
    
    # Initialize the app first
    async def post_init(application):
        """Send startup message after bot initialization"""
        await send_startup_message(application)
    
    app.post_init = post_init
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
