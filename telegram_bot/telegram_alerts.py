"""
Telegram Alerts Module
Sends trading signals and alerts to configured Telegram chat IDs
"""
import os
import sys

import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core_logic.logger_config import get_logger
from telegram_bot.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS

logger = get_logger()

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

def send_telegram_alert(text, parse_mode="Markdown"):
    """
    Send alert message to all configured Telegram chat IDs
    
    Args:
        text: Message text to send
        parse_mode: Message formatting (Markdown or HTML)
    
    Returns:
        bool: True if at least one message was sent successfully
    """
    if not TELEGRAM_CHAT_IDS:
        logger.warning("[TELEGRAM] No chat IDs configured. Set TELEGRAM_CHAT_IDS in .env")
        return False
    
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("[TELEGRAM] Bot token not configured. Set TELEGRAM_BOT_TOKEN in .env")
        return False
    
    success_count = 0
    fail_count = 0
    
    for chat_id in TELEGRAM_CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        try:
            r = requests.post(TELEGRAM_API, json=payload, timeout=10)
            r.raise_for_status()
            logger.info(f"[TELEGRAM] ✓ Message sent to chat_id: {chat_id}")
            success_count += 1
        except Exception as e:
            logger.error(f"[TELEGRAM] ✗ Failed to send to chat_id {chat_id}: {e}")
            fail_count += 1
    
    logger.info(f"[TELEGRAM] Summary: {success_count} sent, {fail_count} failed")
    return success_count > 0


def format_signal_message(symbol, signal_data):
    """
    Format trading signal into a Telegram message
    
    Args:
        symbol: Stock symbol (ISIN code)
        signal_data: Dictionary containing signal information
    
    Returns:
        str: Formatted message
    """
    signal_type = signal_data.get("signal", "UNKNOWN")
    
    if signal_type in ["BUY", "SELL"]:
        entry = signal_data.get("entry_price", 0)
        sl = signal_data.get("sl", 0)
        tp = signal_data.get("tp", 0)
        
        emoji = "🚀" if signal_type == "BUY" else "💣"
        
        message = f"{emoji} *{signal_type} SIGNAL* - `{symbol}`\n\n"
        message += f"📍 Entry Price: `{entry:.2f}`\n"
        message += f"🛑 Stop Loss: `{sl:.2f}`\n"
        message += f"🎯 Take Profit: `{tp:.2f}`\n"
        message += f"📊 Risk/Reward: `{signal_data.get('rr', 1.6):.2f}`\n"
        
        return message
    
    elif signal_type == "EXIT":
        exit_price = signal_data.get("exit_price", 0)
        reason = signal_data.get("reason", "UNKNOWN")
        
        emoji = "✅" if reason == "TP HIT" else "❌"
        
        message = f"{emoji} *EXIT SIGNAL* - `{symbol}`\n\n"
        message += f"📍 Exit Price: `{exit_price:.2f}`\n"
        message += f"📝 Reason: `{reason}`\n"
        
        return message
    
    else:
        return f"⚠️ *UNKNOWN SIGNAL* - `{symbol}`\n{signal_data}"


def send_status_update(symbol, status_info):
    """
    Send status update message
    
    Args:
        symbol: Stock symbol
        status_info: Dictionary with status information
    """
    message = f"📊 *Status Update* - `{symbol}`\n\n"
    
    for key, value in status_info.items():
        message += f"{key}: `{value}`\n"
    
    return send_telegram_alert(message)


def send_error_alert(error_message):
    """
    Send error alert to Telegram
    
    Args:
        error_message: Error description
    """
    message = f"⚠️ *ERROR ALERT*\n\n`{error_message}`"
    return send_telegram_alert(message)
