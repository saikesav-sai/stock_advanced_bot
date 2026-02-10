"""
TradingBotController class - core business logic for the trading bot.
Manages .env configuration, symbol management, and trading process lifecycle.
"""
import os
import subprocess
import sys
from pathlib import Path

from core_logic.logger_config import get_logger
from telegram_bot.symbol_lookup import get_lookup
from telegram_bot.token_manager import get_token_manager

logger = get_logger()

# Global variable to track the trading process
trading_process = None
trading_status = "stopped"


class TradingBotController:
    def __init__(self):
        self.env_path = Path(__file__).parent.parent.parent / ".env"
        self.main_script = Path(__file__).parent.parent.parent / "core_logic" / "main.py"

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
                    'isin': details['isin'],
                    'name': details['name'],
                    'trading_symbol': details['trading_symbol'],
                    'exchange': details['exchange']
                })
            else:
                result.append({
                    'instrument_key': symbol,
                    'name': 'Unknown',
                    'isin': 'Unknown',
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

        # Check token validity before starting
        token_manager = get_token_manager()
        is_valid, token_message = token_manager.check_token_validity()

        if not is_valid:
            error_msg = f"❌ Cannot start bot: Token is expired or invalid\n\n{token_message}\n\nPlease refresh your token using the Token menu."
            logger.error(f"Cannot start bot - token invalid: {token_message}")
            return False, error_msg

        try:
            # Start the main.py script as a subprocess
            log_dir = Path(__file__).parent.parent.parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file_path = log_dir / "trading_process.log"

            log_file = open(log_file_path, "a")

            # Build a fresh environment so the subprocess reads
            # the latest .env values instead of inheriting stale ones
            fresh_env = os.environ.copy()
            env_vars = self.read_env()
            fresh_env.update(env_vars)

            trading_process = subprocess.Popen(
                [sys.executable, str(self.main_script)],
                stdout=log_file,
                stderr=log_file,
                env=fresh_env
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


# Module-level singleton
controller = TradingBotController()
