"""
Configuration file for Stock Advanced Bot with Telegram Integration
"""
import os

from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_USERS = os.getenv("AUTHORIZED_USERS", "").split(",")
AUTHORIZED_USERS = [uid.strip() for uid in AUTHORIZED_USERS if uid.strip()]

# Parse chat IDs for sending alerts (can be multiple recipients)
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "")
TELEGRAM_CHAT_IDS = [cid.strip() for cid in TELEGRAM_CHAT_IDS.split(",") if cid.strip()]

# Trading Configuration
SYMBOLS = os.getenv("SYMBOLS", "")  # Comma-separated instrument keys
INTERVAL = os.getenv("INTERVAL", "1m")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))  # seconds

# Upstox Configuration
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID")
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI")

# Trading Parameters (from LiveStrategyEngine)
EMA_LENGTH = int(os.getenv("EMA_LENGTH", "200"))
VOL_LENGTH = int(os.getenv("VOL_LENGTH", "20"))
VOL_MULTIPLIER = float(os.getenv("VOL_MULTIPLIER", "1.5"))
RISK_REWARD = float(os.getenv("RISK_REWARD", "1.6"))
VWAP_DISTANCE = float(os.getenv("VWAP_DISTANCE", "0.15"))
SL_BUFFER = float(os.getenv("SL_BUFFER", "0.08"))

# Trading Time Window
TRADE_START_TIME = int(os.getenv("TRADE_START_TIME", "915"))  # 9:15 AM
TRADE_END_TIME = int(os.getenv("TRADE_END_TIME", "1525"))    # 3:25 PM
