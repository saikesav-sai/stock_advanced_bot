"""
Menu and general command handlers.
Handles /start, /menu, /status, /cancel and the main menu display.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from telegram_bot.bot_controller.controller import controller
from telegram_bot.config import AUTHORIZED_USERS


def is_authorized(user_id):
    """Check if user is authorized to use the bot"""
    if not AUTHORIZED_USERS:
        return False
    return str(user_id) in AUTHORIZED_USERS


def get_main_menu_keyboard():
    """Return the main menu inline keyboard"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Start Bot", callback_data="start_bot"),
            InlineKeyboardButton("⏹️ Stop Bot", callback_data="stop_bot")
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("📈 Stocks", callback_data="stocks_menu")
        ],
        [
            InlineKeyboardButton("🔬 Back Testing", callback_data="backtest_menu"),
            InlineKeyboardButton("🔑 Token", callback_data="token_menu")
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="help")
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show main menu"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    welcome_msg = (
        "🤖 <b>Stock Trading Bot Controller</b>\n\n"
        "Welcome! Use the buttons below to control your trading bot.\n\n"
        "• Start/Stop the trading program\n"
        "• Manage your stock watchlist\n"
        "• View configuration and status"
    )

    await update.message.reply_text(
        welcome_msg, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return

    await update.message.reply_text(
        "🤖 <b>Stock Trading Bot Controller</b>\n\nSelect an option:",
        reply_markup=get_main_menu_keyboard(),
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


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    await update.message.reply_text(
        "Operation cancelled. Use /menu to return to main menu."
    )
    return ConversationHandler.END


async def handle_start_bot(query):
    """Handle start_bot callback"""
    success, message = controller.start_trading()
    await query.edit_message_text(f"{message}\n\nUse /menu to return to main menu.")


async def handle_stop_bot(query):
    """Handle stop_bot callback"""
    success, message = controller.stop_trading()
    await query.edit_message_text(f"{message}\n\nUse /menu to return to main menu.")


async def handle_status(query):
    """Handle status callback"""
    status_msg = controller.get_status()
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(status_msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_main_menu(query):
    """Handle main_menu callback"""
    await query.edit_message_text(
        "🤖 <b>Stock Trading Bot Controller</b>\n\nSelect an option:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


async def handle_help(query):
    """Handle help callback"""
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
