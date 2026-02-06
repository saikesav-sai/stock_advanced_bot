"""
Backtest session state management for Telegram bot.

This module defines data structures for tracking user backtest configuration
during the conversation flow.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class BacktestSessionData:
    """
    Tracks user's backtest configuration during conversation flow.

    Attributes:
        symbols: List of ISINs to backtest
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        initial_capital: Starting capital in INR
        position_size: Position size per trade in INR
        strategy: Strategy class name (default: Strategy1)
        interval: Candle interval in minutes (default: 5)
        commission_pct: Commission percentage in basis points
        slippage_pct: Slippage percentage in basis points
    """
    symbols: List[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 100000
    position_size: float = 10000
    strategy: str = "Strategy1"
    interval: str = "5"
    commission_pct: float = 0.05
    slippage_pct: float = 0.05

    def to_dict(self) -> dict:
        """Convert to dictionary for config generation."""
        return {
            "symbols": self.symbols,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "position_size": self.position_size,
            "strategy": self.strategy,
            "interval": self.interval,
            "commission_pct": self.commission_pct,
            "slippage_pct": self.slippage_pct
        }

    def is_valid(self) -> bool:
        """Check if session has minimum required data."""
        return (
            len(self.symbols) > 0 and
            self.start_date != "" and
            self.end_date != "" and
            self.initial_capital > 0 and
            self.position_size > 0
        )
