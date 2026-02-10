"""
Application entry point and central callback router.
Builds the Telegram Application, registers handlers, and starts polling.
"""
import os
import sys
from datetime import time as dt_time

from telegram import Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler,
                          filters)

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from core_logic.logger_config import get_logger
from telegram_bot.bot_controller import (ADDING_STOCK, BACKTEST_CONFIRMING,
                                         BACKTEST_ENTERING_CAPITAL,
                                         BACKTEST_ENTERING_END_DATE,
                                         BACKTEST_ENTERING_POSITION_SIZE,
                                         BACKTEST_ENTERING_START_DATE,
                                         BACKTEST_SELECTING_SYMBOLS,
                                         WAITING_AUTH_CODE)
from telegram_bot.bot_controller.handlers_backtest import (
    backtest_add_symbols_handler, backtest_capital_handler,
    backtest_confirm_handler, backtest_end_date_handler,
    backtest_position_handler, backtest_start_date_handler,
    handle_backtest_add_symbol, handle_backtest_continue_to_dates,
    handle_backtest_enter_new_dates, handle_backtest_menu,
    handle_backtest_remove, handle_backtest_reports, handle_backtest_run,
    handle_backtest_symbol_menu, handle_backtest_use_prev_dates,
    handle_backtest_view_report, handle_backtest_view_selected)
from telegram_bot.bot_controller.handlers_menu import (cancel, handle_help,
                                                       handle_main_menu,
                                                       handle_start_bot,
                                                       handle_status,
                                                       handle_stop_bot,
                                                       is_authorized, menu,
                                                       start, status_command)
from telegram_bot.bot_controller.handlers_stock import (
    add_stock_handler, handle_add_stock, handle_exchange_selection,
    handle_remove_stock, handle_remove_symbol, handle_stocks_menu)
from telegram_bot.bot_controller.handlers_token import (handle_auth_code,
                                                        handle_auth_complete,
                                                        handle_check_token,
                                                        handle_refresh_token,
                                                        handle_token_menu,
                                                        refresh_token_command)
from telegram_bot.bot_controller.scheduled_tasks import (
    check_token_daily, check_trading_hours, cleanup_database,
    cleanup_old_backtest_reports, send_startup_message)
from telegram_bot.config import (AUTHORIZED_USERS, TELEGRAM_BOT_TOKEN,
                                 TRADE_END_TIME, TRADE_START_TIME)

logger = get_logger()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the telegram bot"""
    error = context.error

    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning(f"Network error occurred: {error.__class__.__name__}. Will retry automatically.")
        return

    logger.exception(
        "Unhandled exception while processing update",
        exc_info=context.error
    )

    try:
        if update and hasattr(update, "effective_message") and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ An internal error occurred. Please try again."
            )
    except Exception:
        pass


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central callback query router - delegates to domain-specific handlers"""
    try:
        query = update.callback_query
        user_id = query.from_user.id

        if not is_authorized(user_id):
            await query.answer("❌ Not authorized", show_alert=True)
            return ConversationHandler.END

        await query.answer()
        data = query.data

        # --- Menu / general ---
        if data == "start_bot":
            await handle_start_bot(query)
        elif data == "stop_bot":
            await handle_stop_bot(query)
        elif data == "status":
            await handle_status(query)
        elif data == "main_menu":
            await handle_main_menu(query)
        elif data == "help":
            await handle_help(query)

        # --- Stock management ---
        elif data == "stocks_menu":
            await handle_stocks_menu(query)
        elif data == "add_stock":
            await handle_add_stock(query)
        elif data.startswith("exchange_"):
            return await handle_exchange_selection(query, context)
        elif data == "remove_stock":
            await handle_remove_stock(query)
        elif data.startswith("rm_"):
            await handle_remove_symbol(query, data[3:])

        # --- Token management ---
        elif data == "token_menu":
            await handle_token_menu(query)
        elif data == "check_token":
            await handle_check_token(query)
        elif data == "refresh_token":
            await handle_refresh_token(query)
        elif data == "auth_complete":
            return await handle_auth_complete(query)

        # --- Backtesting ---
        elif data == "backtest_menu":
            await handle_backtest_menu(query)
        elif data == "backtest_run":
            await handle_backtest_run(query, context)
        elif data == "backtest_continue_to_dates":
            return await handle_backtest_continue_to_dates(query, context)
        elif data == "backtest_view_selected":
            await handle_backtest_view_selected(query, context)
        elif data.startswith("backtest_remove_"):
            await handle_backtest_remove(query, context)
        elif data == "backtest_symbol_menu":
            await handle_backtest_symbol_menu(query, context)
        elif data == "backtest_use_prev_dates":
            return await handle_backtest_use_prev_dates(query, context)
        elif data == "backtest_enter_new_dates":
            return await handle_backtest_enter_new_dates(query, context)
        elif data == "backtest_add_symbol":
            return await handle_backtest_add_symbol(query, context)
        elif data == "backtest_reports":
            await handle_backtest_reports(query, user_id)
        elif data.startswith("backtest_view_"):
            await handle_backtest_view_report(query, context, user_id)

    except Exception as e:
        logger.exception("Error in button_handler")

        try:
            if update.callback_query:
                await update.callback_query.answer(
                    "⚠️ Something went wrong. Please try again.",
                    show_alert=True
                )
        except Exception:
            pass


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

    # Create application with connection pool settings for better reliability
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .get_updates_connect_timeout(30.0)
        .get_updates_read_timeout(30.0)
        .build()
    )

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

    # Conversation handler for backtesting
    backtest_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^backtest_add_symbol$"),
            CallbackQueryHandler(button_handler, pattern="^backtest_continue_to_dates$"),
            CallbackQueryHandler(button_handler, pattern="^backtest_use_prev_dates$"),
            CallbackQueryHandler(button_handler, pattern="^backtest_enter_new_dates$"),
        ],
        states={
            BACKTEST_SELECTING_SYMBOLS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, backtest_add_symbols_handler)
            ],
            BACKTEST_ENTERING_START_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, backtest_start_date_handler)
            ],
            BACKTEST_ENTERING_END_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, backtest_end_date_handler)
            ],
            BACKTEST_ENTERING_CAPITAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, backtest_capital_handler)
            ],
            BACKTEST_ENTERING_POSITION_SIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, backtest_position_handler)
            ],
            BACKTEST_CONFIRMING: [
                CallbackQueryHandler(backtest_confirm_handler)
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
    app.add_handler(backtest_conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    # Start bot
    logger.info("Starting Telegram bot controller...")
    print("🤖 Telegram bot controller started!")
    print(f"Authorized users: {', '.join(AUTHORIZED_USERS)}")
    print(f"Auto-trading hours: {TRADE_START_TIME} to {TRADE_END_TIME}")

    # Set up job queue for scheduled tasks
    if app.job_queue:
        app.job_queue.run_repeating(check_trading_hours, interval=60, first=10)
        logger.info("Scheduled auto-start/stop based on trading hours")

        app.job_queue.run_daily(
            cleanup_database,
            time=dt_time(hour=0, minute=1),
            days=(0, 1, 2, 3, 4, 5, 6)
        )
        logger.info("Scheduled daily database cleanup at 12:01 AM")

        app.job_queue.run_daily(
            check_token_daily,
            time=dt_time(hour=8, minute=30),
            days=(0, 1, 2, 3, 4, 5, 6)
        )
        logger.info("Scheduled daily token validity check at 8:30 AM")

        app.job_queue.run_daily(
            cleanup_old_backtest_reports,
            time=dt_time(hour=0, minute=30),
            days=(6,)
        )
        logger.info("Scheduled weekly backtest reports cleanup on Sunday at 12:30 AM")

    async def post_init(application):
        """Send startup message after bot initialization"""
        await send_startup_message(application)

    app.post_init = post_init
    app.add_error_handler(error_handler)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
