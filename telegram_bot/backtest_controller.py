"""
Backtest controller for managing backtest execution via Telegram bot.

This module handles config generation, async backtest execution via subprocess,
report management, and cleanup.
"""

import asyncio
import json
import subprocess
# Import logger from parent directory
import sys,os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core_logic.logger_config import get_logger
from telegram_bot.symbol_lookup import SymbolLookup

logger = get_logger()


class BacktestController:
    """
    Manages backtest lifecycle: config generation, execution, reports.
    """

    def __init__(self):
        """Initialize controller with directory paths."""
        self.base_dir = Path(__file__).parent.parent / "back_testing"
        self.config_dir = self.base_dir / "configs"
        self.report_dir = self.base_dir / "reports"
        self.manifest_path = self.report_dir / "manifest.json"
        self.config_path = self.config_dir / "backtest_config.json"
        self.database_path = self.base_dir.parent / "back_testing_market_data.db"

        # Ensure directories exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # Initialize manifest if doesn't exist
        if not self.manifest_path.exists():
            self._init_manifest()

    def _init_manifest(self):
        """Initialize empty manifest file."""
        manifest = {"reports": []}
        with open(self.manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        logger.info("Initialized backtest manifest")

    def create_user_config(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        initial_capital: float,
        position_size: float,
        strategy: str = "Strategy1",
        interval: str = "5",
        commission_pct: float = 0.05,
        slippage_pct: float = 0.05
    ) -> str:
        """
        Generate config JSON and write to shared config file.

        Args:
            symbols: List of ISINs
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            initial_capital: Starting capital in INR
            position_size: Position size per trade in INR
            strategy: Strategy class name
            interval: Candle interval in minutes
            commission_pct: Commission in basis points
            slippage_pct: Slippage in basis points

        Returns:
            Path to config file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Build instrument_keys mapping
        instrument_keys = {isin: f"NSE_EQ|{isin}" for isin in symbols}

        config = {
            "backtest_config": {
                "name": f"TelegramBacktest_{timestamp}",
                "description": f"Backtest from Telegram - {start_date} to {end_date}",
                "data": {
                    "symbols": symbols,
                    "start_date": start_date,
                    "end_date": end_date,
                    "interval": interval,
                    "database_path": str(self.database_path),
                    "auto_fetch": True,
                    "instrument_keys": instrument_keys
                },
                "strategy": {
                    "module": "core_logic.strategies",
                    "class": strategy,
                    "parameters": {}
                },
                "execution": {
                    "initial_capital": initial_capital,
                    "position_size": position_size,
                    "commission_pct": commission_pct,
                    "slippage_pct": slippage_pct
                },
                "output": {
                    "report_dir": str(self.report_dir),
                    "auto_open_browser": False,
                    "save_trade_log": True
                }
            }
        }

        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"Created backtest config: {self.config_path}")
        return str(self.config_path)

    def load_last_config(self) -> Dict:
        """
        Load the last used backtest configuration.

        Returns dict with: symbols, start_date, end_date, initial_capital, position_size, etc.
        Returns system defaults if config doesn't exist.
        """
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    config = json.load(f)
                    bt_config = config.get('backtest_config', {})
                    data = bt_config.get('data', {})
                    execution = bt_config.get('execution', {})
                    strategy = bt_config.get('strategy', {})

                    return {
                        'symbols': data.get('symbols', []),
                        'start_date': data.get('start_date', ''),
                        'end_date': data.get('end_date', ''),
                        'initial_capital': execution.get('initial_capital', 100000),
                        'position_size': execution.get('position_size', 10000),
                        'strategy': strategy.get('class', 'Strategy1'),
                        'interval': data.get('interval', '5'),
                        'commission_pct': execution.get('commission_pct', 0.05),
                        'slippage_pct': execution.get('slippage_pct', 0.05)
                    }
            except Exception as e:
                logger.warning(f"Failed to load last config: {e}")

        # Return system defaults if config doesn't exist or failed to load
        return {
            'symbols': [],
            'start_date': '',
            'end_date': '',
            'initial_capital': 100000,
            'position_size': 10000,
            'strategy': 'Strategy1',
            'interval': '5',
            'commission_pct': 0.05,
            'slippage_pct': 0.05
        }

    def validate_backtest_params(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        initial_capital: float,
        position_size: float
    ) -> Tuple[bool, List[str]]:
        """
        Validate user inputs before running backtest.

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        # Symbol validation
        if not symbols or len(symbols) == 0:
            errors.append("❌ At least one symbol required")

        if len(symbols) > 50:
            errors.append("❌ Maximum 50 symbols allowed")

        # Date validation
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')

            if end < start:
                errors.append("❌ End date must be after start date")

            if (end - start).days > 365:
                errors.append("⚠️ Date range exceeds 1 year (may take long)")

            if end > datetime.now():
                errors.append("❌ End date cannot be in future")

        except ValueError:
            errors.append("❌ Invalid date format (use YYYY-MM-DD)")

        # Capital validation
        if initial_capital < 10000:
            errors.append("❌ Minimum capital: ₹10,000")

        if position_size > initial_capital:
            errors.append("❌ Position size cannot exceed initial capital")

        if position_size < 1000:
            errors.append("❌ Minimum position size: ₹1,000")

        return len(errors) == 0, errors

    async def run_backtest_async(
        self,
        config_path: str,
        user_id: str,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Execute backtest via subprocess in background.

        Args:
            config_path: Path to config JSON
            user_id: Telegram user ID
            context: Telegram context for sending notifications
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"user_{user_id}_{timestamp}.html"
        report_path = self.report_dir / report_filename

        try:
            # Send starting notification
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🔄 <b>Backtest Starting...</b>\n\n"
                    "• Loading historical data\n"
                    "• Preparing strategy\n"
                    "• Initializing portfolio\n\n"
                    "<i>This may take 30-60 seconds</i>"
                ),
                parse_mode=ParseMode.HTML
            )

            # Run backtest subprocess
            logger.info(f"Starting backtest for user {user_id}")
            result = subprocess.run(
                [
                    sys.executable,
                    str(self.base_dir / "main.py"),
                    "--config", config_path,
                    "--output", str(report_path),
                    "--no-browser"
                ],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                # Parse results from stdout
                summary = self._parse_backtest_output(result.stdout, config_path)

                # Add to manifest
                self._add_to_manifest(user_id, report_filename, summary)

                # Send completion notification (with built-in retry logic)
                try:
                    await self._send_completion_notification(
                        context, user_id, summary, report_path
                    )
                except Exception as e:
                    # Notification failed but backtest succeeded
                    logger.error(f"Failed to send completion notification after retries: {e}")
                    # Don't raise - backtest completed successfully

                logger.info(f"Backtest completed for user {user_id}")
            else:
                # Parse error
                error_msg = self._parse_error(result.stderr)
                try:
                    await self._send_error_notification(context, user_id, error_msg)
                except Exception as e:
                    logger.error(f"Failed to send error notification after retries: {e}")
                logger.error(f"Backtest failed for user {user_id}: {error_msg}")

        except subprocess.TimeoutExpired:
            try:
                await self._send_error_notification(
                    context, user_id, "Backtest timed out (exceeded 5 minutes)"
                )
            except Exception as e:
                logger.error(f"Failed to send timeout notification: {e}")
            logger.error(f"Backtest timeout for user {user_id}")

        except Exception as e:
            try:
                await self._send_error_notification(context, user_id, str(e))
            except Exception as notify_error:
                logger.error(f"Failed to send error notification: {notify_error}")
            logger.exception(f"Backtest error for user {user_id}")

    def _parse_backtest_output(self, stdout: str, config_path: str) -> Dict:
        """
        Extract summary metrics from backtest output.

        Since back_testing/main.py may not have structured JSON output,
        we'll extract key metrics from console output patterns.
        """
        summary = {
            "total_return": 0.0,
            "net_pnl": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "symbols_count": 0,
            "symbols_names": [],
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0
        }

        try:
            # Load config to get symbols count and names
            with open(config_path) as f:
                config = json.load(f)
                isins = config["backtest_config"]["data"]["symbols"]
                summary["symbols_count"] = len(isins)

                # Look up stock names from ISINs
                lookup = SymbolLookup()
                for isin in isins:
                    name = lookup.get_name_by_isin(isin)
                    if name:
                        summary["symbols_names"].append(name)
                    else:
                        summary["symbols_names"].append(isin)  # Fallback to ISIN if not found


            # Parse output for metrics (looking for common patterns)
            lines = stdout.split('\n')
            for line in lines:
                line_lower = line.lower()

                if 'total return' in line_lower or 'return %' in line_lower:
                    # Extract percentage
                    for word in line.split():
                        if '%' in word:
                            try:
                                summary["total_return"] = float(word.replace('%', ''))
                            except:
                                pass

                if 'net profit' in line_lower or 'net p&l' in line_lower:
                    # Extract numeric value
                    for word in line.split():
                        try:
                            val = float(word.replace(',', '').replace('₹', ''))
                            if abs(val) > 100:  # Likely the P&L value
                                summary["net_pnl"] = val
                        except:
                            pass

                if 'total trades' in line_lower:
                    for word in line.split():
                        try:
                            val = int(word)
                            if 0 < val < 10000:
                                summary["total_trades"] = val
                        except:
                            pass

                if 'win rate' in line_lower:
                    for word in line.split():
                        if '%' in word:
                            try:
                                summary["win_rate"] = float(word.replace('%', ''))
                            except:
                                pass

                if 'max drawdown' in line_lower or 'maximum drawdown' in line_lower:
                    for word in line.split():
                        if '%' in word:
                            try:
                                summary["max_drawdown"] = abs(float(word.replace('%', '')))
                            except:
                                pass

                if 'sharpe' in line_lower:
                    for word in line.split():
                        try:
                            val = float(word)
                            if -10 < val < 10:  # Typical Sharpe range
                                summary["sharpe_ratio"] = val
                        except:
                            pass

        except Exception as e:
            logger.warning(f"Failed to parse backtest output: {e}")

        return summary

    def _parse_error(self, stderr: str) -> str:
        """Extract user-friendly error message from subprocess stderr."""
        if "UnicodeEncodeError" in stderr or "charmap" in stderr:
            return "Console encoding error (backtest may have completed - check logs)"
        elif "No data found" in stderr or "No candles" in stderr:
            return "No historical data available for selected date range"
        elif "Database" in stderr:
            return "Database error - please try again"
        elif "Strategy" in stderr:
            return "Strategy error - check configuration"
        else:
            # Return last 200 chars of stderr
            return f"Error: {stderr[-200:] if len(stderr) > 200 else stderr}"

    async def _send_completion_notification(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: str,
        summary: Dict,
        report_path: Path
    ):
        """Send backtest results with summary and HTML file."""
        # Format summary message
        message = "✅ <b>Backtest Complete!</b>\n\n"

        # Display stock names
        if summary.get('symbols_names'):
            message += "📈 <b>Stocks:</b>\n"
            for name in summary['symbols_names']:
                message += f"  • {name}\n"
            message += "\n"

        message += (
            "📊 <b>Summary:</b>\n"
            f"• Total Return: <b>{summary['total_return']:+.2f}%</b>\n"
            f"• Net P&L: ₹{summary['net_pnl']:,.2f}\n"
            f"• Trades: {summary['total_trades']} "
            f"(Win Rate: {summary['win_rate']:.1f}%)\n"
            f"• Max Drawdown: {summary['max_drawdown']:.2f}%\n"
        )

        if summary['sharpe_ratio'] != 0:
            message += f"• Sharpe Ratio: {summary['sharpe_ratio']:.2f}\n"

        message += "\n📄 <i>Full interactive report attached below</i>"

        # Send summary with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.HTML
                )
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to send summary (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                else:
                    logger.error(f"Failed to send summary after {max_retries} attempts: {e}")
                    # Don't raise, continue to try sending the file

        # Send HTML report file with retry logic
        if report_path.exists():
            for attempt in range(max_retries):
                try:
                    with open(report_path, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=user_id,
                            document=f,
                            filename=report_path.name,
                            caption="Open this file in your browser for full interactive charts"
                        )
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Failed to send report file (attempt {attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error(f"Failed to send report file after {max_retries} attempts: {e}")
                        # Try to notify user about the failure
                        try:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=f"⚠️ Report generated but failed to upload. Location: {report_path}"
                            )
                        except:
                            pass  # If even this fails, give up

    async def _send_error_notification(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: str,
        error_msg: str
    ):
        """Send error notification to user."""
        message = (
            "❌ <b>Backtest Failed</b>\n\n"
            f"<code>{error_msg}</code>\n\n"
            "Please check your inputs and try again."
        )

        # Send with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.HTML
                )
                break  # Success
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to send error notification (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Failed to send error notification after {max_retries} attempts: {e}")
                    # Can't notify user, just log it

    def _add_to_manifest(self, user_id: str, report_filename: str, summary: Dict):
        """Add report entry to manifest."""
        try:
            # Load manifest
            with open(self.manifest_path) as f:
                manifest = json.load(f)

            # Add new report
            report_id = report_filename.replace('.html', '')
            manifest["reports"].insert(0, {  # Insert at beginning
                "report_id": report_id,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "file_path": str(self.report_dir / report_filename),
                "summary": summary
            })

            # Save manifest
            with open(self.manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)

            logger.info(f"Added report to manifest: {report_id}")

        except Exception as e:
            logger.error(f"Failed to update manifest: {e}")

    def get_user_reports(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Get user's recent reports from manifest.

        Args:
            user_id: Telegram user ID
            limit: Maximum number of reports to return

        Returns:
            List of report dictionaries
        """
        try:
            with open(self.manifest_path) as f:
                manifest = json.load(f)

            # Filter by user and limit
            user_reports = [
                r for r in manifest["reports"]
                if r["user_id"] == user_id
            ][:limit]

            return user_reports

        except Exception as e:
            logger.error(f"Failed to get user reports: {e}")
            return []

    def cleanup_old_reports(self, days: int = 30):
        """
        Remove reports older than N days.

        Args:
            days: Age threshold in days
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            with open(self.manifest_path) as f:
                manifest = json.load(f)

            # Filter out old reports
            old_reports = []
            new_reports = []

            for report in manifest["reports"]:
                report_date = datetime.fromisoformat(report["timestamp"])
                if report_date < cutoff_date:
                    old_reports.append(report)
                else:
                    new_reports.append(report)

            # Delete old report files
            for report in old_reports:
                file_path = Path(report["file_path"])
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Deleted old report: {file_path.name}")

            # Update manifest
            manifest["reports"] = new_reports
            with open(self.manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)

            logger.info(f"Cleanup complete: removed {len(old_reports)} reports")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


# Global instance
_controller_instance = None


def get_backtest_controller() -> BacktestController:
    """Get singleton BacktestController instance."""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = BacktestController()
    return _controller_instance
