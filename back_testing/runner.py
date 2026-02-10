import copy
import importlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from back_testing.loading_data import BacktestDataLoader
from core_logic.logger_config import get_logger

logger = get_logger()


def _backtest_symbol_worker(args):
    """
    Standalone worker function for parallel backtesting of a single symbol.
    Must be at module level for pickling by ProcessPoolExecutor.
    """
    config, symbol, initial_capital = args

    from back_testing.loading_data import BacktestDataLoader

    # Create isolated components
    db_path = config['data']['database_path']
    interval = config['data']['interval']
    auto_fetch = config['data'].get('auto_fetch', True)
    data_loader = BacktestDataLoader(db_path, interval, auto_fetch=auto_fetch)

    # Strategy
    module_name = config['strategy']['module']
    class_name = config['strategy']['class']
    module = importlib.import_module(module_name)
    strategy_class = getattr(module, class_name)
    params = config['strategy'].get('parameters', {})
    strategy = strategy_class(**params)

    # Portfolio
    exec_config = config['execution']
    portfolio = Portfolio(
        initial_capital=initial_capital,
        position_size=exec_config['position_size'],
        commission_pct=exec_config['commission_pct'],
        slippage_pct=exec_config['slippage_pct']
    )

    trades = []
    equity_curve = []

    # Load data
    start_date = config['data']['start_date']
    end_date = config['data']['end_date']
    instrument_keys = config['data'].get('instrument_keys', {})
    instrument_key = instrument_keys.get(symbol, None)

    df = data_loader.load_data(symbol, start_date, end_date, instrument_key=instrument_key)
    if len(df) == 0:
        return symbol, trades, equity_curve, {
            'trades': [], 'equity_curve': [], 'total_trades': 0,
            'final_equity': initial_capital, 'net_profit': 0, 'return_pct': 0
        }

    trading_days = data_loader.get_trading_days(df)

    for current_date in trading_days:
        day_df = df[df['timestamp'].dt.date == current_date].copy()

        for i in range(len(day_df)):
            current_idx = day_df.index[i]
            rolling_df = df.loc[:current_idx].copy()
            row = day_df.iloc[i]

            signal = strategy.process(rolling_df, symbol=symbol)

            if signal and signal.get('signal') == 'EXIT' and portfolio.position:
                trade = portfolio.close_position(
                    exit_price=signal.get('exit_price', row['close']),
                    timestamp=row['timestamp'],
                    reason=signal.get('reason', 'STRATEGY EXIT')
                )
                if trade:
                    trades.append(trade)

            if signal and signal.get('signal') in ['BUY', 'SELL'] and not portfolio.position:
                trade = portfolio.open_position(signal, row['timestamp'], symbol)
                if trade is None and hasattr(strategy, 'active_position'):
                    strategy.active_position = None

            equity_curve.append({
                'timestamp': row['timestamp'],
                'equity': portfolio.calculate_equity(row['close']),
                'cash': portfolio.cash
            })

        # EOD square-off
        if portfolio.position:
            last_candle = day_df.iloc[-1]
            trade = portfolio.close_position(
                exit_price=last_candle['close'],
                timestamp=last_candle['timestamp'],
                reason="EOD EXIT"
            )
            if trade:
                trades.append(trade)
            if hasattr(strategy, 'active_position'):
                strategy.active_position = None
            equity_curve.append({
                'timestamp': last_candle['timestamp'],
                'equity': portfolio.equity,
                'cash': portfolio.cash
            })

    stock_result = {
        'trades': trades,
        'equity_curve': equity_curve,
        'total_trades': len(trades),
        'final_equity': portfolio.equity,
        'net_profit': portfolio.equity - initial_capital,
        'return_pct': ((portfolio.equity - initial_capital) / initial_capital) * 100
    }

    return symbol, trades, equity_curve, stock_result


@dataclass
class Trade:
    """Represents a single trade with entry/exit details"""

    trade_id: int
    symbol: str
    entry_time: datetime
    entry_price: float
    side: str  # "LONG" or "SHORT"
    quantity: float
    sl: Optional[float]
    tp: Optional[float]
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "SL HIT", "TP HIT", "EOD EXIT"
    entry_commission: float = 0.0
    exit_commission: float = 0.0
    entry_slippage: float = 0.0
    exit_slippage: float = 0.0
    gross_pnl: Optional[float] = None
    net_pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    duration_minutes: Optional[int] = None

    def close(self, exit_price: float, exit_time: datetime, reason: str):
        """Close the trade and calculate P&L metrics"""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = reason

        # Calculate gross P&L
        if self.side == "LONG":
            self.gross_pnl = (exit_price - self.entry_price) * self.quantity
        else:  # SHORT
            self.gross_pnl = (self.entry_price - exit_price) * self.quantity

        # Calculate net P&L (after costs)
        total_costs = (self.entry_commission + self.exit_commission +
                      self.entry_slippage + self.exit_slippage)
        self.net_pnl = self.gross_pnl - total_costs

        # Calculate P&L percentage
        entry_value = self.entry_price * self.quantity
        if entry_value > 0:
            self.pnl_pct = (self.net_pnl / entry_value) * 100
        else:
            self.pnl_pct = 0.0

        # Calculate duration
        self.duration_minutes = int((exit_time - self.entry_time).total_seconds() / 60)

    def to_dict(self) -> Dict:
        """Convert to dictionary for export"""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'side': self.side,
            'entry_time': self.entry_time.strftime('%Y-%m-%d %H:%M') if self.entry_time else None,
            'entry_price': round(self.entry_price, 2),
            'exit_time': self.exit_time.strftime('%Y-%m-%d %H:%M') if self.exit_time else None,
            'exit_price': round(self.exit_price, 2) if self.exit_price else None,
            'quantity': round(self.quantity, 2),
            'sl': round(self.sl, 2) if self.sl is not None else None,
            'tp': round(self.tp, 2) if self.tp is not None else None,
            'net_pnl': round(self.net_pnl, 2) if self.net_pnl else None,
            'pnl_pct': round(self.pnl_pct, 2) if self.pnl_pct else None,
            'duration_minutes': self.duration_minutes,
            'exit_reason': self.exit_reason
        }


class Portfolio:
    """Manages capital, positions, and trade execution"""

    def __init__(self, initial_capital: float, position_size: float,
                 commission_pct: float, slippage_pct: float):
        """
        Initialize portfolio

        Args:
            initial_capital: Starting capital (INR)
            position_size: Fixed position size per trade (INR)
            commission_pct: Commission percentage (e.g., 0.05 for 5 basis points)
            slippage_pct: Slippage percentage (e.g., 0.05 for 5 basis points)
        """
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission_pct = commission_pct / 100  # Convert to decimal
        self.slippage_pct = slippage_pct / 100  # Convert to decimal

        self.cash = initial_capital
        self.equity = initial_capital
        self.position: Optional[Trade] = None
        self.trade_counter = 0

    def open_position(self, signal: Dict, timestamp: datetime, symbol: str) -> Trade:
        """
        Open new position based on signal

        Args:
            signal: Strategy signal dict with keys: signal, entry_price, sl, tp
            timestamp: Entry timestamp
            symbol: Symbol identifier

        Returns:
            Trade object
        """
        entry_price = signal['entry_price']
        sl = signal.get('sl')
        tp = signal.get('tp')
        side = "LONG" if signal['signal'] == "BUY" else "SHORT"

        # Apply slippage to entry price
        if side == "LONG":
            entry_price_with_slippage = entry_price * (1 + self.slippage_pct)
        else:  # SHORT
            entry_price_with_slippage = entry_price * (1 - self.slippage_pct)

        # Calculate quantity (round down to avoid over-leverage)
        quantity = int(self.position_size / entry_price_with_slippage)

        if quantity <= 0:
            logger.warning(f"Quantity is 0, position size too small for price {entry_price_with_slippage}")
            return None

        # Calculate costs
        entry_value = entry_price_with_slippage * quantity
        entry_commission = entry_value * self.commission_pct
        entry_slippage_cost = abs(entry_price_with_slippage - entry_price) * quantity

        # Check if we have enough cash
        total_cost = entry_value + entry_commission
        if total_cost > self.cash:
            logger.warning(f"Insufficient cash: need {total_cost}, have {self.cash}")
            return None

        # Create trade
        self.trade_counter += 1
        trade = Trade(
            trade_id=self.trade_counter,
            symbol=symbol,
            entry_time=timestamp,
            entry_price=entry_price_with_slippage,
            side=side,
            quantity=quantity,
            sl=sl,
            tp=tp,
            entry_commission=entry_commission,
            entry_slippage=entry_slippage_cost
        )

        # Deduct from cash
        self.cash -= total_cost

        # Store position
        self.position = trade

        sl_text = f"{sl:.2f}" if sl is not None else "N/A"
        tp_text = f"{tp:.2f}" if tp is not None else "N/A"
        logger.info(f"Opened {side} position: {quantity} @ {entry_price_with_slippage:.2f}, "
               f"SL={sl_text}, TP={tp_text}, Cost={total_cost:.2f}")

        return trade

    def close_position(self, exit_price: float, timestamp: datetime, reason: str) -> Trade:
        """
        Close current position and update portfolio

        Args:
            exit_price: Exit price (before slippage)
            timestamp: Exit timestamp
            reason: Exit reason

        Returns:
            Updated Trade object
        """
        if not self.position:
            logger.warning("No position to close")
            return None

        trade = self.position

        # Apply slippage to exit price
        if trade.side == "LONG":
            exit_price_with_slippage = exit_price * (1 - self.slippage_pct)
        else:  # SHORT
            exit_price_with_slippage = exit_price * (1 + self.slippage_pct)

        # Calculate exit costs
        exit_value = exit_price_with_slippage * trade.quantity
        exit_commission = exit_value * self.commission_pct
        exit_slippage_cost = abs(exit_price_with_slippage - exit_price) * trade.quantity

        trade.exit_commission = exit_commission
        trade.exit_slippage = exit_slippage_cost

        # Close trade
        trade.close(exit_price_with_slippage, timestamp, reason)

        # Update cash
        entry_value = trade.entry_price * trade.quantity
        self.cash += entry_value + trade.net_pnl + trade.entry_commission

        # Update equity
        self.equity = self.cash

        logger.info(f"Closed {trade.side} position: {reason}, P&L={trade.net_pnl:.2f} "
                   f"({trade.pnl_pct:.2f}%), Duration={trade.duration_minutes}min")

        # Clear position
        self.position = None

        return trade

    def calculate_equity(self, current_price: float) -> float:
        """
        Calculate current portfolio equity (cash + unrealized P&L)

        Args:
            current_price: Current market price

        Returns:
            Total equity value
        """
        if not self.position:
            return self.cash

        # Calculate unrealized P&L
        if self.position.side == "LONG":
            unrealized_pnl = (current_price - self.position.entry_price) * self.position.quantity
        else:  # SHORT
            unrealized_pnl = (self.position.entry_price - current_price) * self.position.quantity

        return self.cash + unrealized_pnl


class BacktestRunner:
    """Main backtesting engine - simulates strategy execution on historical data"""

    def __init__(self, config_path: str):
        """
        Initialize backtest runner

        Args:
            config_path: Path to JSON configuration file
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)

        # Initialize components
        db_path = self.config['data']['database_path']
        interval = self.config['data']['interval']
        auto_fetch = self.config['data'].get('auto_fetch', True)  # Default to True
        self.data_loader = BacktestDataLoader(db_path, interval, auto_fetch=auto_fetch)

        # Initialize strategy
        self.strategy = self._load_strategy()

        # Initialize portfolio
        exec_config = self.config['execution']
        self.portfolio = Portfolio(
            initial_capital=exec_config['initial_capital'],
            position_size=exec_config['position_size'],
            commission_pct=exec_config['commission_pct'],
            slippage_pct=exec_config['slippage_pct']
        )

        # Results storage
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []

        # Per-stock results tracking
        self.stock_results: Dict[str, Dict] = {}

        logger.info(f"Initialized BacktestRunner: {self.config['name']}")

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config['backtest_config']

    def _load_strategy(self):
        """Dynamically load strategy class from config"""
        module_name = self.config['strategy']['module']
        class_name = self.config['strategy']['class']

        # Import module
        module = importlib.import_module(module_name)
        strategy_class = getattr(module, class_name)

        # Instantiate with optional parameters
        params = self.config['strategy'].get('parameters', {})
        strategy = strategy_class(**params)

        # Verify interface
        required_methods = ['set_pdh_pdl', 'reset_daily_state', 'process']
        for method in required_methods:
            if not hasattr(strategy, method):
                raise ValueError(f"Strategy missing required method: {method}")

        logger.info(f"Loaded strategy: {class_name}")
        return strategy

    def run(self):
        """
        Execute backtest and return results.
        Uses parallel processing when multiple symbols are configured.
        """
        logger.info("=" * 80)
        logger.info("STARTING BACKTEST")
        logger.info("=" * 80)

        start_time = datetime.now()
        symbols = self.config['data']['symbols']
        initial_capital = self.portfolio.initial_capital

        if len(symbols) > 1:
            self._run_parallel(symbols, initial_capital)
        else:
            self._run_sequential(symbols, initial_capital)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("\n" + "=" * 80)
        logger.info(f"BACKTEST COMPLETED in {duration:.2f} seconds")
        logger.info(f"Total trades across all stocks: {len(self.trades)}")
        logger.info("=" * 80)

        return {
            'config': self.config,
            'trades': self.trades,
            'equity_curve': self.equity_curve,
            'initial_capital': initial_capital,
            'final_equity': self.portfolio.equity,
            'stock_results': self.stock_results
        }

    def _run_sequential(self, symbols, initial_capital):
        """Original sequential symbol processing"""
        for symbol_idx, symbol in enumerate(symbols):
            logger.info(f"\n{'='*60}")
            logger.info(f"Backtesting symbol {symbol_idx + 1}/{len(symbols)}: {symbol}")
            logger.info(f"{'='*60}")

            self.portfolio.cash = initial_capital
            self.portfolio.equity = initial_capital
            self.portfolio.position = None

            stock_start_idx = len(self.trades)
            equity_start_idx = len(self.equity_curve)

            self._simulate_single_symbol(symbol)

            stock_trades = self.trades[stock_start_idx:]
            stock_equity_curve = self.equity_curve[equity_start_idx:]

            self.stock_results[symbol] = {
                'trades': stock_trades,
                'equity_curve': stock_equity_curve,
                'total_trades': len(stock_trades),
                'final_equity': self.portfolio.equity,
                'net_profit': self.portfolio.equity - initial_capital,
                'return_pct': ((self.portfolio.equity - initial_capital) / initial_capital) * 100
            }

            logger.info(f"\n{symbol} Summary:")
            logger.info(f"  Trades: {len(stock_trades)}")
            logger.info(f"  Final Equity: ₹{self.portfolio.equity:,.2f}")
            logger.info(f"  Net P&L: ₹{self.portfolio.equity - initial_capital:,.2f}")
            logger.info(f"  Return: {((self.portfolio.equity - initial_capital) / initial_capital) * 100:.2f}%")

    def _run_parallel(self, symbols, initial_capital):
        """Parallel symbol processing using multiple CPU cores"""
        import multiprocessing
        max_workers = min(len(symbols), multiprocessing.cpu_count())
        logger.info(f"Running {len(symbols)} symbols in parallel ({max_workers} workers)")

        worker_args = [
            (copy.deepcopy(self.config), symbol, initial_capital)
            for symbol in symbols
        ]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(_backtest_symbol_worker, worker_args))

        # Aggregate results (maintain symbol order)
        for symbol, trades, equity_curve, stock_result in results:
            self.trades.extend(trades)
            self.equity_curve.extend(equity_curve)
            self.stock_results[symbol] = stock_result

            # Update portfolio to reflect last stock's final equity (for reporting)
            self.portfolio.equity = stock_result['final_equity']
            self.portfolio.cash = stock_result['final_equity']

            logger.info(f"\n{symbol} Summary:")
            logger.info(f"  Trades: {stock_result['total_trades']}")
            logger.info(f"  Final Equity: ₹{stock_result['final_equity']:,.2f}")
            logger.info(f"  Net P&L: ₹{stock_result['net_profit']:,.2f}")
            logger.info(f"  Return: {stock_result['return_pct']:.2f}%")

    def _simulate_single_symbol(self, symbol: str):
        """Run strategy on single symbol's data"""
        # Load data
        start_date = self.config['data']['start_date']
        end_date = self.config['data']['end_date']

        # Get instrument_key from config if available (for symbol mapping)
        instrument_keys = self.config['data'].get('instrument_keys', {})
        instrument_key = instrument_keys.get(symbol, None)  # Will use NSE_EQ|{symbol} if None

        df = self.data_loader.load_data(symbol, start_date, end_date, instrument_key=instrument_key)

        if len(df) == 0:
            logger.warning(f"No data for {symbol}, skipping")
            return

        # Validate data
        validation = self.data_loader.validate_data(df, symbol)
        if not validation['valid']:
            logger.warning(f"Data validation warnings for {symbol}: {validation['warnings']}")

        # Get trading days
        trading_days = self.data_loader.get_trading_days(df)
        logger.info(f"Processing {len(trading_days)} trading days")

        # Simulate day by day
        for day_idx, current_date in enumerate(trading_days):
            logger.debug(f"\nDay {day_idx + 1}/{len(trading_days)}: {current_date}")

            # Get candles for current day
            day_df = df[df['timestamp'].dt.date == current_date].copy()

            # Process each candle
            for i in range(len(day_df)):
                # Build rolling DataFrame (all data up to current candle)
                current_idx = day_df.index[i]
                rolling_df = df.loc[:current_idx].copy()

                # Get current candle
                row = day_df.iloc[i]

                # Process candle
                self._process_candle(row, rolling_df, symbol)

            # End of day square-off handled by backtest
            if self.portfolio.position:
                last_candle = day_df.iloc[-1]
                trade = self.portfolio.close_position(
                    exit_price=last_candle['close'],
                    timestamp=last_candle['timestamp'],
                    reason="EOD EXIT"
                )
                if trade:
                    self.trades.append(trade)
                if hasattr(self.strategy, 'active_position'):
                    self.strategy.active_position = None

                # Record post-square-off equity to keep final equity in sync
                self.equity_curve.append({
                    'timestamp': last_candle['timestamp'],
                    'equity': self.portfolio.equity,
                    'cash': self.portfolio.cash
                })

    def _process_candle(self, row, rolling_df: pd.DataFrame, symbol: str):
        """
        Process single candle and handle signals

        Args:
            row: Current candle (Series)
            rolling_df: Historical data up to current candle
            symbol: Symbol identifier
        """
        signal = self.strategy.process(rolling_df, symbol=symbol)

        # Strategy-driven exit
        if signal and signal.get('signal') == 'EXIT' and self.portfolio.position:
            exit_price = signal.get('exit_price', row['close'])
            reason = signal.get('reason', 'STRATEGY EXIT')
            trade = self.portfolio.close_position(
                exit_price=exit_price,
                timestamp=row['timestamp'],
                reason=reason
            )
            if trade:
                self.trades.append(trade)

        # Strategy-driven entry
        if signal and signal.get('signal') in ['BUY', 'SELL'] and not self.portfolio.position:
            trade = self.portfolio.open_position(signal, row['timestamp'], symbol)
            if trade is None and hasattr(self.strategy, 'active_position'):
                # Keep strategy state aligned when entry is rejected (e.g., cash/size constraints).
                self.strategy.active_position = None

        # Update equity curve
        current_equity = self.portfolio.calculate_equity(row['close'])
        self.equity_curve.append({
            'timestamp': row['timestamp'],
            'equity': current_equity,
            'cash': self.portfolio.cash
        })

