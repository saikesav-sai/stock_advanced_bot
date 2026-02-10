"""
Backtest handlers.
Handles the full backtesting workflow: symbol selection, date entry,
capital configuration, execution and report viewing.
"""
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from telegram_bot.backtest_controller import get_backtest_controller
from telegram_bot.backtest_state import BacktestSessionData
from telegram_bot.bot_controller import (BACKTEST_CONFIRMING,
                                         BACKTEST_ENTERING_CAPITAL,
                                         BACKTEST_ENTERING_END_DATE,
                                         BACKTEST_ENTERING_POSITION_SIZE,
                                         BACKTEST_ENTERING_START_DATE,
                                         BACKTEST_SELECTING_SYMBOLS)
from telegram_bot.bot_controller.controller import (TradingBotController,
                                                    controller)
from telegram_bot.bot_controller.handlers_menu import is_authorized
from telegram_bot.symbol_lookup import get_lookup


async def _show_backtest_symbol_selection(query_or_update, ctrl, session=None):
    """Helper to show backtest symbol selection screen"""
    session_data = session or {}
    selected_count = len(session_data.symbols) if hasattr(session_data, 'symbols') and session_data.symbols else 0

    msg = "🔬 <b>New Backtest - Select Symbols</b>\n\n"

    # Show currently selected symbols
    if selected_count > 0:
        msg += f"✅ <b>Selected: {selected_count} stock(s)</b>\n\n"

    keyboard = []
    keyboard.append([InlineKeyboardButton("➕ Add Stocks", callback_data="backtest_add_symbol")])

    if selected_count > 0:
        keyboard.append([
            InlineKeyboardButton(f"📋 View/Edit Selected ({selected_count})", callback_data="backtest_view_selected"),
            InlineKeyboardButton("➡️ Continue", callback_data="backtest_continue_to_dates")
        ])

    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data="backtest_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if hasattr(query_or_update, 'edit_message_text'):
        await query_or_update.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await query_or_update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_backtest_menu(query):
    """Handle backtest_menu callback"""
    keyboard = [
        [InlineKeyboardButton("▶️ Run Backtest", callback_data="backtest_run")],
        [InlineKeyboardButton("📊 View Reports", callback_data="backtest_reports")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = "🔬 <b>Back Testing Menu</b>\n\nSelect an option:"
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_backtest_run(query, context):
    """Handle backtest_run callback"""
    backtest_controller = get_backtest_controller()
    last_config = backtest_controller.load_last_config()

    session = BacktestSessionData(
        symbols=last_config.get('symbols', []),
        start_date=last_config.get('start_date', ''),
        end_date=last_config.get('end_date', ''),
        initial_capital=last_config.get('initial_capital', 100000),
        position_size=last_config.get('position_size', 10000),
        strategy=last_config.get('strategy', 'Strategy1'),
        interval=last_config.get('interval', '5')
    )
    context.user_data['backtest_session'] = session

    if last_config.get('symbols'):
        await query.answer(f"Loaded {len(last_config['symbols'])} stocks from last backtest", show_alert=False)

    await _show_backtest_symbol_selection(query, controller, session)


async def handle_backtest_continue_to_dates(query, context):
    """Handle backtest_continue_to_dates callback"""
    session = context.user_data.get('backtest_session')
    if not session or not session.symbols:
        await query.answer("Please select at least one symbol first", show_alert=True)
        return

    lookup = get_lookup()
    stock_names = []
    for isin in session.symbols[:10]:
        name = lookup.get_name_by_isin(isin)
        stock_names.append(name if name else isin[:12])

    msg = (
        f"✅ <b>Symbols Confirmed</b>\n\n"
        f"Selected {len(session.symbols)} stock(s):\n"
    )
    for name in stock_names:
        msg += f"• {name}\n"
    if len(session.symbols) > 10:
        msg += f"• ...and {len(session.symbols) - 10} more\n"

    if session.start_date and session.end_date:
        msg += f"\n📅 <b>Date Selection</b>\n\n"
        msg += f"<b>Previous dates:</b> {session.start_date} to {session.end_date}\n\n"
        msg += "Do you want to use these dates or enter new ones?"

        keyboard = [
            [InlineKeyboardButton("✅ Use Previous Dates", callback_data="backtest_use_prev_dates")],
            [InlineKeyboardButton("📝 Enter New Dates", callback_data="backtest_enter_new_dates")],
            [InlineKeyboardButton("🔙 Back", callback_data="backtest_symbol_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        msg += "\n📅 <b>Enter Start Date</b>\n\n"
        msg += "Send the start date in <code>YYYY-MM-DD</code> format.\n\n"
        msg += "<b>Examples:</b>\n• 2026-01-01\n• 2025-12-01\n\nOr send /cancel to abort."

        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        return BACKTEST_ENTERING_START_DATE


async def handle_backtest_view_selected(query, context):
    """Handle backtest_view_selected callback"""
    session = context.user_data.get('backtest_session')
    if not session or not session.symbols:
        await query.answer("No symbols selected", show_alert=True)
        return

    lookup = get_lookup()
    msg = f"📋 <b>Selected Symbols ({len(session.symbols)})</b>\n\n"

    keyboard = []
    for i, isin in enumerate(session.symbols[:20]):
        name = lookup.get_name_by_isin(isin)
        display_name = name if name else isin[:12]
        keyboard.append([
            InlineKeyboardButton(
                f"❌ {display_name}",
                callback_data=f"backtest_remove_{i}"
            )
        ])

    if len(session.symbols) > 20:
        msg += f"Showing first 20 of {len(session.symbols)} stocks\n\n"

    keyboard.append([InlineKeyboardButton("🔙 Back to Selection", callback_data="backtest_symbol_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_backtest_remove(query, context):
    """Handle backtest_remove_* callback"""
    session = context.user_data.get('backtest_session')
    if not session:
        await query.answer("Session expired", show_alert=True)
        return

    try:
        index = int(query.data.replace("backtest_remove_", ""))
        if 0 <= index < len(session.symbols):
            removed_isin = session.symbols.pop(index)
            lookup = get_lookup()
            name = lookup.get_name_by_isin(removed_isin)
            await query.answer(f"Removed {name if name else removed_isin[:12]}")

            await _show_backtest_symbol_selection(query, controller, session)
    except (ValueError, IndexError):
        await query.answer("Invalid selection", show_alert=True)


async def handle_backtest_symbol_menu(query, context):
    """Handle backtest_symbol_menu callback"""
    session = context.user_data.get('backtest_session')
    if session:
        await _show_backtest_symbol_selection(query, controller, session)


async def handle_backtest_use_prev_dates(query, context):
    """Handle backtest_use_prev_dates callback"""
    session = context.user_data.get('backtest_session')
    if not session:
        await query.answer("Session expired. Please start again.", show_alert=True)
        return

    start = datetime.strptime(session.start_date, '%Y-%m-%d')
    end = datetime.strptime(session.end_date, '%Y-%m-%d')
    days = (end - start).days

    msg = (
        f"✅ <b>Dates Confirmed</b>\n\n"
        f"• Start: {session.start_date}\n"
        f"• End: {session.end_date}\n"
        f"• Duration: {days} days\n\n"
        f"💰 <b>Capital Settings</b>\n\n"
        f"Current defaults:\n"
        f"• Initial Capital: ₹{session.initial_capital:,.0f}\n"
        f"• Position Size: ₹{session.position_size:,.0f}\n\n"
        f"Keep these defaults or customize?"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Use Defaults", callback_data="backtest_use_defaults")],
        [InlineKeyboardButton("✏️ Change Capital", callback_data="backtest_change_capital")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="backtest_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return BACKTEST_CONFIRMING


async def handle_backtest_enter_new_dates(query, context):
    """Handle backtest_enter_new_dates callback"""
    session = context.user_data.get('backtest_session')
    if not session:
        await query.answer("Session expired. Please start again.", show_alert=True)
        return

    msg = (
        "📅 <b>Enter Start Date</b>\n\n"
        "Send the start date in <code>YYYY-MM-DD</code> format.\n\n"
        "<b>Examples:</b>\n• 2026-01-01\n• 2025-12-01\n\nOr send /cancel to abort."
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
    return BACKTEST_ENTERING_START_DATE


async def handle_backtest_add_symbol(query, context):
    """Handle backtest_add_symbol callback"""
    session = context.user_data.get('backtest_session')
    if not session:
        await query.answer("Session expired. Please start again.", show_alert=True)
        return

    msg = (
        "➕ <b>Add Custom Symbols</b>\n\n"
        "Send stock names or ISINs separated by commas.\n\n"
        "<b>Examples:</b>\n"
        "• RELIANCE, TCS, INFY\n"
        "• INE467B01029, INE669E01016\n"
        "• RELIANCE, INE467B01029, TCS\n\n"
        "Or send /cancel to go back."
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
    return BACKTEST_SELECTING_SYMBOLS


async def handle_backtest_reports(query, user_id):
    """Handle backtest_reports callback"""
    backtest_controller = get_backtest_controller()
    reports = backtest_controller.get_user_reports(str(user_id), limit=10)

    if not reports:
        msg = "📊 <b>No Reports Found</b>\n\nYou haven't run any backtests yet."
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="backtest_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return

    msg = "📊 <b>Previous Backtests</b>\n\n"
    keyboard = []

    for i, report in enumerate(reports[:10], 1):
        timestamp = datetime.fromisoformat(report['timestamp'])
        date_str = timestamp.strftime("%Y-%m-%d %H:%M")
        summary = report['summary']

        msg += (
            f"<b>{i}. {date_str}</b>\n"
            f"   • Stocks: {summary.get('symbols_count', 0)}\n"
            f"   • Return: {summary.get('total_return', 0):+.2f}%\n"
            f"   • P&L: ₹{summary.get('net_pnl', 0):,.2f}\n\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"📄 View Report #{i}",
                callback_data=f"backtest_view_{report['report_id']}"
            )
        ])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="backtest_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_backtest_view_report(query, context, user_id):
    """Handle backtest_view_* callback"""
    report_id = query.data.replace("backtest_view_", "")
    backtest_controller = get_backtest_controller()
    reports = backtest_controller.get_user_reports(str(user_id), limit=50)

    report = next((r for r in reports if r['report_id'] == report_id), None)

    if not report:
        await query.answer("Report not found", show_alert=True)
        return

    report_path = Path(report['file_path'])
    if report_path.exists():
        summary = report['summary']
        caption = (
            f"📊 <b>Backtest Report</b>\n\n"
            f"• Stocks: {summary.get('symbols_count', 0)}\n"
            f"• Return: {summary.get('total_return', 0):+.2f}%\n"
            f"• Net P&L: ₹{summary.get('net_pnl', 0):,.2f}\n"
            f"• Trades: {summary.get('total_trades', 0)}\n"
            f"• Win Rate: {summary.get('win_rate', 0):.1f}%"
        )

        await query.answer()
        with open(report_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=f,
                filename=report_path.name,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
    else:
        await query.answer("Report file not found", show_alert=True)


# --- Conversation message handlers ---

async def backtest_start_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle start date input for backtest"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END

    session = context.user_data.get('backtest_session')
    if not session:
        await update.message.reply_text("Session expired. Please start over with /menu")
        return ConversationHandler.END

    start_date = update.message.text.strip()

    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        session.start_date = start_date

        msg = (
            f"✅ <b>Start Date:</b> {start_date}\n\n"
            f"📅 <b>Enter End Date</b>\n\n"
            f"Send the end date in <code>YYYY-MM-DD</code> format.\n\n"
            f"<b>Examples:</b>\n• 2026-01-31\n• 2025-12-31\n\nOr send /cancel to abort."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return BACKTEST_ENTERING_END_DATE

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid date format. Please use <code>YYYY-MM-DD</code> format.\n\n"
            "Example: 2026-01-01\n\nOr send /cancel to abort.",
            parse_mode=ParseMode.HTML
        )
        return BACKTEST_ENTERING_START_DATE


async def backtest_end_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle end date input for backtest"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END

    session = context.user_data.get('backtest_session')
    if not session:
        await update.message.reply_text("Session expired. Please start over with /menu")
        return ConversationHandler.END

    end_date = update.message.text.strip()

    try:
        start = datetime.strptime(session.start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        if end < start:
            await update.message.reply_text(
                "❌ End date must be after start date.\n\nPlease enter a valid end date or send /cancel to abort.",
                parse_mode=ParseMode.HTML
            )
            return BACKTEST_ENTERING_END_DATE

        if end > datetime.now():
            await update.message.reply_text(
                "❌ End date cannot be in the future.\n\nPlease enter a valid end date or send /cancel to abort.",
                parse_mode=ParseMode.HTML
            )
            return BACKTEST_ENTERING_END_DATE

        session.end_date = end_date

        days = (end - start).days
        msg = (
            f"✅ <b>Dates Confirmed</b>\n\n"
            f"• Start: {session.start_date}\n"
            f"• End: {session.end_date}\n"
            f"• Duration: {days} days\n\n"
            f"💰 <b>Capital Settings</b>\n\n"
            f"Current defaults:\n"
            f"• Initial Capital: ₹{session.initial_capital:,.0f}\n"
            f"• Position Size: ₹{session.position_size:,.0f}\n\n"
            f"Keep these defaults or customize?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Use Defaults", callback_data="backtest_use_defaults")],
            [InlineKeyboardButton("✏️ Change Capital", callback_data="backtest_change_capital")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="backtest_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return BACKTEST_CONFIRMING

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid date format. Please use <code>YYYY-MM-DD</code> format.\n\n"
            "Example: 2026-01-31\n\nOr send /cancel to abort.",
            parse_mode=ParseMode.HTML
        )
        return BACKTEST_ENTERING_END_DATE


async def backtest_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle backtest confirmation and execution"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if not is_authorized(user_id):
        await query.answer("❌ Not authorized", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    session = context.user_data.get('backtest_session')
    if not session:
        await query.edit_message_text("Session expired. Please start over with /menu")
        return ConversationHandler.END

    if data == "backtest_use_defaults":
        backtest_controller = get_backtest_controller()
        is_valid, errors = backtest_controller.validate_backtest_params(
            session.symbols,
            session.start_date,
            session.end_date,
            session.initial_capital,
            session.position_size
        )

        if not is_valid:
            error_msg = "\n".join(errors)
            await query.edit_message_text(
                f"❌ <b>Validation Failed</b>\n\n{error_msg}\n\nPlease start over with /menu",
                parse_mode=ParseMode.HTML
            )
            return ConversationHandler.END

        lookup = get_lookup()
        stock_names = []
        for isin in session.symbols[:5]:
            name = lookup.get_name_by_isin(isin)
            stock_names.append(name if name else isin[:12])

        msg = (
            f"🔬 <b>Starting Backtest...</b>\n\n"
            f"📊 <b>Configuration:</b>\n"
            f"• Symbols: {len(session.symbols)} stocks\n"
        )
        for name in stock_names:
            msg += f"  - {name}\n"
        if len(session.symbols) > 5:
            msg += f"  - ...and {len(session.symbols) - 5} more\n"

        msg += (
            f"• Period: {session.start_date} to {session.end_date}\n"
            f"• Capital: ₹{session.initial_capital:,.0f}\n"
            f"• Position: ₹{session.position_size:,.0f}\n"
            f"• Strategy: {session.strategy}\n\n"
            f"⏳ <i>Processing... This may take 30-60 seconds</i>"
        )

        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

        config_path = backtest_controller.create_user_config(
            symbols=session.symbols,
            start_date=session.start_date,
            end_date=session.end_date,
            initial_capital=session.initial_capital,
            position_size=session.position_size,
            strategy=session.strategy,
            interval=session.interval
        )

        context.job_queue.run_once(
            lambda ctx: backtest_controller.run_backtest_async(config_path, str(user_id), ctx),
            when=1
        )

        context.user_data.pop('backtest_session', None)

        return ConversationHandler.END

    elif data == "backtest_change_capital":
        msg = (
            "💰 <b>Change Initial Capital</b>\n\n"
            f"Current: ₹{session.initial_capital:,.0f}\n\n"
            "Send the new initial capital amount (minimum ₹10,000).\n\n"
            "<b>Examples:</b>\n• 100000\n• 200000\n• 500000\n\nOr send /cancel to abort."
        )
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        return BACKTEST_ENTERING_CAPITAL


async def backtest_capital_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle capital input for backtest"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END

    session = context.user_data.get('backtest_session')
    if not session:
        await update.message.reply_text("Session expired. Please start over with /menu")
        return ConversationHandler.END

    capital_text = update.message.text.strip()

    if capital_text.lower() == '/skip':
        msg = (
            f"✅ <b>Using Previous Capital:</b> ₹{session.initial_capital:,.0f}\n\n"
            "💰 <b>Change Position Size</b>\n\n"
            f"Current: ₹{session.position_size:,.0f}\n\n"
            "Send the new position size per trade (minimum ₹1,000).\n"
            "Or send /skip to use current value."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return BACKTEST_ENTERING_POSITION_SIZE

    try:
        capital = float(capital_text)

        if capital < 10000:
            await update.message.reply_text(
                "❌ Minimum capital is ₹10,000.\n\nPlease enter a valid amount or send /cancel to abort."
            )
            return BACKTEST_ENTERING_CAPITAL

        session.initial_capital = capital

        msg = (
            f"✅ <b>Capital Set:</b> ₹{capital:,.0f}\n\n"
            "💰 <b>Change Position Size</b>\n\n"
            f"Current: ₹{session.position_size:,.0f}\n\n"
            "Send the new position size per trade (minimum ₹1,000).\n"
            "Or send /skip to use current value."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return BACKTEST_ENTERING_POSITION_SIZE

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a numeric value.\n\n"
            "Example: 100000\n\nOr send /cancel to abort."
        )
        return BACKTEST_ENTERING_CAPITAL


async def backtest_position_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle position size input for backtest"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END

    session = context.user_data.get('backtest_session')
    if not session:
        await update.message.reply_text("Session expired. Please start over with /menu")
        return ConversationHandler.END

    position_text = update.message.text.strip()

    if position_text.lower() == '/skip':
        lookup = get_lookup()
        stock_names = []
        for isin in session.symbols[:5]:
            name = lookup.get_name_by_isin(isin)
            stock_names.append(name if name else isin[:12])

        msg = (
            f"✅ <b>Configuration Complete!</b>\n\n"
            f"📊 <b>Backtest Summary:</b>\n"
            f"• Symbols: {len(session.symbols)} stocks\n"
        )
        for name in stock_names:
            msg += f"  - {name}\n"
        if len(session.symbols) > 5:
            msg += f"  - ...and {len(session.symbols) - 5} more\n"

        msg += (
            f"• Period: {session.start_date} to {session.end_date}\n"
            f"• Capital: ₹{session.initial_capital:,.0f}\n"
            f"• Position: ₹{session.position_size:,.0f}\n\n"
            f"Ready to start backtest?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Start Backtest", callback_data="backtest_use_defaults")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="backtest_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return BACKTEST_CONFIRMING

    try:
        position = float(position_text)

        if position < 1000:
            await update.message.reply_text(
                "❌ Minimum position size is ₹1,000.\n\nPlease enter a valid amount or send /cancel to abort."
            )
            return BACKTEST_ENTERING_POSITION_SIZE

        if position > session.initial_capital:
            await update.message.reply_text(
                f"❌ Position size cannot exceed initial capital (₹{session.initial_capital:,.0f}).\n\n"
                "Please enter a valid amount or send /cancel to abort."
            )
            return BACKTEST_ENTERING_POSITION_SIZE

        session.position_size = position

        lookup = get_lookup()
        stock_names = []
        for isin in session.symbols[:5]:
            name = lookup.get_name_by_isin(isin)
            stock_names.append(name if name else isin[:12])

        msg = (
            f"✅ <b>Configuration Complete!</b>\n\n"
            f"📊 <b>Backtest Summary:</b>\n"
            f"• Symbols: {len(session.symbols)} stocks\n"
        )
        for name in stock_names:
            msg += f"  - {name}\n"
        if len(session.symbols) > 5:
            msg += f"  - ...and {len(session.symbols) - 5} more\n"

        msg += (
            f"• Period: {session.start_date} to {session.end_date}\n"
            f"• Capital: ₹{session.initial_capital:,.0f}\n"
            f"• Position: ₹{session.position_size:,.0f}\n\n"
            f"Ready to start backtest?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Start Backtest", callback_data="backtest_use_defaults")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="backtest_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return BACKTEST_CONFIRMING

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a numeric value.\n\n"
            "Example: 10000\n\nOr send /cancel to abort."
        )
        return BACKTEST_ENTERING_POSITION_SIZE


async def backtest_add_symbols_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom symbol input for backtest"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END

    session = context.user_data.get('backtest_session')
    if not session:
        await update.message.reply_text("Session expired. Please start over with /menu")
        return ConversationHandler.END

    symbols_input = update.message.text.strip()

    symbol_names = [s.strip() for s in symbols_input.split(',') if s.strip()]

    if not symbol_names:
        await update.message.reply_text(
            "❌ No symbols provided. Please enter stock names or ISINs separated by commas.\n\n"
            "Example: RELIANCE, TCS, INFY\n\nOr send /cancel to abort."
        )
        return BACKTEST_SELECTING_SYMBOLS

    lookup = get_lookup()
    found_symbols = []
    not_found = []

    for name in symbol_names:
        if len(name) == 12 and name.isalnum():
            stock_name = lookup.get_name_by_isin(name)
            if stock_name:
                found_symbols.append({'isin': name, 'name': stock_name})
            else:
                not_found.append(name)
        else:
            results = lookup.search_stocks(name, limit=1)
            if results:
                found_symbols.append({'isin': results[0]['isin'], 'name': results[0]['name']})
            else:
                not_found.append(name)

    if not found_symbols:
        await update.message.reply_text(
            f"❌ No stocks found for: {', '.join(symbol_names)}\n\n"
            "Please check the names and try again, or send /cancel to abort."
        )
        return BACKTEST_SELECTING_SYMBOLS

    existing_isins = set(session.symbols) if session.symbols else set()
    new_isins = [stock['isin'] for stock in found_symbols if stock['isin'] not in existing_isins]

    if new_isins:
        session.symbols.extend(new_isins)

    ctrl = TradingBotController()
    await _show_backtest_symbol_selection(update, ctrl, session)

    return ConversationHandler.END
