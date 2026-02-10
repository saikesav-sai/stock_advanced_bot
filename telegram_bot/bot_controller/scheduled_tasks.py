"""
Scheduled tasks and notification helpers.
Handles daily token checks, database cleanup, trading hour automation,
and user notifications.
"""
import os
from datetime import datetime
from pathlib import Path

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core_logic.logger_config import get_logger
from telegram_bot.backtest_controller import get_backtest_controller
from telegram_bot.bot_controller.controller import controller
from telegram_bot.config import (AUTHORIZED_USERS, TRADE_END_TIME,
                                 TRADE_START_TIME)
from telegram_bot.token_manager import get_token_manager

logger = get_logger()


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


async def cleanup_database(context: ContextTypes.DEFAULT_TYPE):
    """Delete old database and create a new one at the start of each day"""
    try:
        root_folder = Path(__file__).parent.parent.parent
        db_path = root_folder / 'market_data.db'

        if db_path.exists():
            os.remove(db_path)
            logger.info(f"Deleted old database: {db_path}")

            cleanup_msg = (
                "🗑️ <b>Daily Database Cleanup</b>\n\n"
                "Old market data database has been deleted.\n"
                "A fresh database will be created when trading starts.\n\n"
                f"Cleanup time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await notify_users(context.application, cleanup_msg)
        else:
            logger.info("No database file found to clean up")

    except Exception as e:
        logger.error(f"Error during database cleanup: {e}")
        error_msg = (
            "⚠️ <b>Database Cleanup Error</b>\n\n"
            f"Failed to delete old database: {str(e)}"
        )
        await notify_users(context.application, error_msg)


async def cleanup_old_backtest_reports(context: ContextTypes.DEFAULT_TYPE):
    """Clean up backtest reports older than 30 days"""
    try:
        backtest_controller = get_backtest_controller()
        backtest_controller.cleanup_old_reports(days=30)
        logger.info("Completed backtest reports cleanup")
    except Exception as e:
        logger.error(f"Error during backtest reports cleanup: {e}")


async def check_trading_hours(context: ContextTypes.DEFAULT_TYPE):
    """Check if it's time to start or stop trading"""
    import telegram_bot.bot_controller.controller as ctrl_mod
    trading_status = ctrl_mod.trading_status

    now = datetime.now()
    current_time = now.hour * 100 + now.minute

    start_hour = TRADE_START_TIME // 100
    start_min = TRADE_START_TIME % 100
    end_hour = TRADE_END_TIME // 100
    end_min = TRADE_END_TIME % 100

    start_time = start_hour * 100 + start_min
    end_time = end_hour * 100 + end_min

    is_trading_hours = start_time <= current_time <= end_time

    # Auto-start at trading start time
    if current_time == start_time and trading_status == "stopped":
        success, message = controller.start_trading()
        if success:
            logger.info("Auto-started trading bot at market open")
            await notify_users(context.application,
                f"⏰ <b>Auto-Start</b>\n\n{message}\n\nMarket hours have begun.")
        else:
            logger.warning(f"Failed to auto-start trading bot: {message}")
            await notify_users(context.application,
                f"⚠️ <b>Auto-Start Failed</b>\n\n{message}")

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
