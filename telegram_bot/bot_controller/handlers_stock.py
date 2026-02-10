"""
Stock management handlers.
Handles adding/removing stocks from the watchlist via Telegram UI.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from core_logic.logger_config import get_logger
from telegram_bot.bot_controller import ADDING_STOCK
from telegram_bot.bot_controller.controller import controller
from telegram_bot.bot_controller.handlers_menu import is_authorized
from telegram_bot.symbol_lookup import get_lookup

logger = get_logger()


async def handle_stocks_menu(query):
    """Handle stocks_menu callback"""
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


async def handle_add_stock(query):
    """Handle add_stock callback - show exchange selection"""
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


async def handle_exchange_selection(query, context):
    """Handle exchange_* callback"""
    exchange = query.data.replace("exchange_", "")
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


async def handle_remove_stock(query):
    """Handle remove_stock callback - show stock list for removal"""
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


async def handle_remove_symbol(query, symbol):
    """Handle rm_* callback - remove a specific stock"""
    success, message = controller.remove_symbol(symbol)

    if success:
        await query.edit_message_text(
            f"✅ {message}\n\n Takes Effect after restart \n \nUse /menu to return to main menu."
        )
    else:
        await query.edit_message_text(
            f"❌ {message}\n\nUse /menu to return to main menu."
        )


async def add_stock_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding a new stock (conversation message handler)"""
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
            f"✅ {message}\n\n Takes Effect after restart \n \n<b>Stock Details:</b>\n"
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
