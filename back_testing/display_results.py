import os
import sys
import webbrowser
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core_logic.logger_config import get_logger

logger = get_logger()


class BacktestResults:
    """Container for backtest results with analysis methods"""

    def __init__(self, trades: List, equity_curve: List[Dict], config: Dict):
        """
        Initialize backtest results

        Args:
            trades: List of Trade objects
            equity_curve: List of equity snapshots
            config: Backtest configuration
        """
        self.trades = trades
        self.equity_curve = pd.DataFrame(equity_curve)
        self.config = config
        self.initial_capital = config['execution']['initial_capital']

        # Calculate metrics
        self.metrics = self._calculate_metrics()

    def _calculate_metrics(self) -> Dict:
        """Calculate comprehensive performance metrics"""
        if len(self.trades) == 0:
            return self._empty_metrics()

        # Convert trades to DataFrame for easier analysis
        trades_df = pd.DataFrame([t.to_dict() for t in self.trades])

        # Basic trade statistics
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['net_pnl'] > 0])
        losing_trades = len(trades_df[trades_df['net_pnl'] < 0])
        breakeven_trades = len(trades_df[trades_df['net_pnl'] == 0])

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # P&L analysis
        gross_profit = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum() if winning_trades > 0 else 0
        gross_loss = abs(trades_df[trades_df['net_pnl'] < 0]['net_pnl'].sum()) if losing_trades > 0 else 0
        net_profit = trades_df['net_pnl'].sum()

        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

        avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0
        avg_win_pct = trades_df[trades_df['net_pnl'] > 0]['pnl_pct'].mean() if winning_trades > 0 else 0
        avg_loss_pct = trades_df[trades_df['net_pnl'] < 0]['pnl_pct'].mean() if losing_trades > 0 else 0

        largest_win = trades_df['net_pnl'].max()
        largest_loss = trades_df['net_pnl'].min()

        # Expectancy
        expectancy = (avg_win * win_rate / 100) - (avg_loss * (100 - win_rate) / 100)

        # Returns
        final_equity = self.equity_curve['equity'].iloc[-1]
        total_return = ((final_equity - self.initial_capital) / self.initial_capital) * 100

        # Calculate CAGR (assuming date range from config)
        start_date = datetime.strptime(self.config['data']['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(self.config['data']['end_date'], '%Y-%m-%d')
        days = (end_date - start_date).days
        years = days / 365.25

        if years > 0 and final_equity > 0:
            cagr = (((final_equity / self.initial_capital) ** (1 / years)) - 1) * 100
        else:
            cagr = 0

        # Risk metrics
        max_dd, max_dd_duration = self._calculate_max_drawdown()
        sharpe_ratio = self._calculate_sharpe_ratio()
        sortino_ratio = self._calculate_sortino_ratio()
        calmar_ratio = (cagr / abs(max_dd)) if max_dd != 0 else 0

        # Trade duration
        avg_duration = trades_df['duration_minutes'].mean() if total_trades > 0 else 0
        max_duration = trades_df['duration_minutes'].max() if total_trades > 0 else 0
        min_duration = trades_df['duration_minutes'].min() if total_trades > 0 else 0

        # Breakdown by side
        long_trades = trades_df[trades_df['side'] == 'LONG']
        short_trades = trades_df[trades_df['side'] == 'SHORT']

        long_count = len(long_trades)
        short_count = len(short_trades)
        long_win_rate = (len(long_trades[long_trades['net_pnl'] > 0]) / long_count * 100) if long_count > 0 else 0
        short_win_rate = (len(short_trades[short_trades['net_pnl'] > 0]) / short_count * 100) if short_count > 0 else 0

        # Exit reasons
        tp_exits = len(trades_df[trades_df['exit_reason'] == 'TP HIT'])
        sl_exits = len(trades_df[trades_df['exit_reason'] == 'SL HIT'])
        eod_exits = len(trades_df[trades_df['exit_reason'] == 'EOD EXIT'])

        # Consecutive wins/losses
        max_consec_wins, max_consec_losses = self._calculate_consecutive_streaks(trades_df)

        # Costs (would need to sum from trades if tracked separately)
        total_commission = 0
        total_slippage = 0

        metrics = {
            # Returns
            "total_return": round(total_return, 2),
            "net_profit": round(net_profit, 2),
            "cagr": round(cagr, 2),

            # Trade Statistics
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "breakeven_trades": breakeven_trades,
            "win_rate": round(win_rate, 2),

            # P&L Analysis
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else float('inf'),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_win_pct": round(avg_win_pct, 2),
            "avg_loss_pct": round(avg_loss_pct, 2),
            "largest_win": round(largest_win, 2),
            "largest_loss": round(largest_loss, 2),
            "expectancy": round(expectancy, 2),

            # Risk Metrics
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_duration": max_dd_duration,
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "calmar_ratio": round(calmar_ratio, 2),

            # Trade Duration
            "avg_trade_duration": round(avg_duration, 1),
            "max_trade_duration": max_duration,
            "min_trade_duration": min_duration,

            # Breakdown by Side
            "long_trades": long_count,
            "long_win_rate": round(long_win_rate, 2),
            "short_trades": short_count,
            "short_win_rate": round(short_win_rate, 2),

            # Exit Reasons
            "tp_exits": tp_exits,
            "sl_exits": sl_exits,
            "eod_exits": eod_exits,

            # Streaks
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,

            # Other
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2)
        }

        return metrics

    def _empty_metrics(self) -> Dict:
        """Return empty metrics when no trades"""
        return {
            "total_return": 0, "net_profit": 0, "cagr": 0,
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "breakeven_trades": 0, "win_rate": 0, "gross_profit": 0,
            "gross_loss": 0, "profit_factor": 0, "avg_win": 0,
            "avg_loss": 0, "avg_win_pct": 0, "avg_loss_pct": 0,
            "largest_win": 0, "largest_loss": 0, "expectancy": 0,
            "max_drawdown": 0, "max_drawdown_duration": 0,
            "sharpe_ratio": 0, "sortino_ratio": 0, "calmar_ratio": 0,
            "avg_trade_duration": 0, "max_trade_duration": 0,
            "min_trade_duration": 0, "long_trades": 0, "long_win_rate": 0,
            "short_trades": 0, "short_win_rate": 0, "tp_exits": 0,
            "sl_exits": 0, "eod_exits": 0, "max_consecutive_wins": 0,
            "max_consecutive_losses": 0, "initial_capital": self.initial_capital,
            "final_equity": self.initial_capital
        }

    def _calculate_max_drawdown(self) -> tuple:
        """Calculate maximum drawdown and duration"""
        if len(self.equity_curve) == 0:
            return 0, 0

        equity = self.equity_curve['equity']
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max * 100

        max_dd = drawdown.min()

        # Calculate drawdown duration (simplified)
        max_dd_duration = 0

        return max_dd, max_dd_duration

    def _calculate_sharpe_ratio(self) -> float:
        """Calculate Sharpe ratio"""
        if len(self.equity_curve) < 2:
            return 0

        returns = self.equity_curve['equity'].pct_change().dropna()

        if len(returns) == 0 or returns.std() == 0:
            return 0

        # Annualize assuming 252 trading days
        sharpe = returns.mean() / returns.std() * np.sqrt(252)

        return sharpe

    def _calculate_sortino_ratio(self) -> float:
        """Calculate Sortino ratio (downside deviation)"""
        if len(self.equity_curve) < 2:
            return 0

        returns = self.equity_curve['equity'].pct_change().dropna()

        if len(returns) == 0:
            return 0

        # Downside deviation (only negative returns)
        downside_returns = returns[returns < 0]

        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0

        sortino = returns.mean() / downside_returns.std() * np.sqrt(252)

        return sortino

    def _calculate_consecutive_streaks(self, trades_df: pd.DataFrame) -> tuple:
        """Calculate maximum consecutive wins and losses"""
        if len(trades_df) == 0:
            return 0, 0

        # Create win/loss series
        results = (trades_df['net_pnl'] > 0).astype(int)

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for is_win in results:
            if is_win:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return max_wins, max_losses


class ReportGenerator:
    """Generates HTML report with interactive charts"""

    def __init__(self, results: BacktestResults):
        """
        Initialize report generator

        Args:
            results: BacktestResults object
        """
        self.results = results
        self.metrics = results.metrics

    def generate_report(self, output_path: str) -> str:
        """
        Create HTML report and save to file

        Args:
            output_path: Path to save HTML report

        Returns:
            str: Path to generated report
        """
        logger.info(f"Generating report at {output_path}")

        # Create output directory if needed
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Generate charts
        equity_chart = self._create_equity_chart()
        drawdown_chart = self._create_drawdown_chart()
        pnl_dist_chart = self._create_trade_distribution_chart()
        monthly_returns_chart = self._create_monthly_returns_chart()
        hourly_dist_chart = self._create_hourly_distribution_chart()

        # Generate trade table
        trade_table_html = self._create_trade_analysis_table()

        # Build HTML
        html = self._build_html(
            equity_chart, drawdown_chart, pnl_dist_chart,
            monthly_returns_chart, hourly_dist_chart, trade_table_html
        )

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"Report generated successfully: {output_path}")

        return output_path

    def _create_equity_chart(self) -> str:
        """Generate Plotly equity curve chart"""
        df = self.results.equity_curve

        if len(df) == 0:
            return ""

        fig = go.Figure()

        # Equity line
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['equity'],
            mode='lines',
            name='Equity',
            line=dict(color='#2E86AB', width=2)
        ))

        # Initial capital line
        fig.add_trace(go.Scatter(
            x=[df['timestamp'].iloc[0], df['timestamp'].iloc[-1]],
            y=[self.results.initial_capital, self.results.initial_capital],
            mode='lines',
            name='Initial Capital',
            line=dict(color='gray', width=1, dash='dash')
        ))

        # Mark trades on equity curve
        if len(self.results.trades) > 0:
            trade_times = [t.exit_time for t in self.results.trades if t.exit_time]
            trade_equities = []
            trade_colors = []
            trade_sizes = []

            for trade in self.results.trades:
                if trade.exit_time:
                    # Find equity at trade exit time
                    equity_at_exit = df[df['timestamp'] <= trade.exit_time]['equity'].iloc[-1] if len(df[df['timestamp'] <= trade.exit_time]) > 0 else self.results.initial_capital
                    trade_equities.append(equity_at_exit)
                    trade_colors.append('green' if trade.net_pnl > 0 else 'red')
                    trade_sizes.append(10)

            fig.add_trace(go.Scatter(
                x=trade_times,
                y=trade_equities,
                mode='markers',
                name='Trades',
                marker=dict(
                    color=trade_colors,
                    size=trade_sizes,
                    symbol='circle',
                    line=dict(width=1, color='white')
                ),
                hovertemplate='%{x}<br>Equity: %{y:.2f}<extra></extra>'
            ))

        fig.update_layout(
            title='Equity Curve',
            xaxis_title='Date',
            yaxis_title='Equity (INR)',
            template='plotly_white',
            hovermode='x unified',
            height=500
        )

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def _create_drawdown_chart(self) -> str:
        """Generate drawdown chart"""
        df = self.results.equity_curve

        if len(df) == 0:
            return ""

        equity = df['equity']
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max * 100

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=drawdown,
            fill='tozeroy',
            name='Drawdown',
            line=dict(color='#A23B72', width=2),
            fillcolor='rgba(162, 59, 114, 0.3)'
        ))

        fig.update_layout(
            title='Drawdown (%)',
            xaxis_title='Date',
            yaxis_title='Drawdown (%)',
            template='plotly_white',
            hovermode='x unified',
            height=400
        )

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def _create_trade_distribution_chart(self) -> str:
        """Generate P&L distribution histogram"""
        if len(self.results.trades) == 0:
            return ""

        pnls = [t.net_pnl for t in self.results.trades]
        colors = ['green' if p > 0 else 'red' for p in pnls]

        fig = go.Figure()

        fig.add_trace(go.Histogram(
            x=pnls,
            marker=dict(
                color=colors,
                line=dict(width=1, color='white')
            ),
            name='Trades',
            nbinsx=20
        ))

        fig.update_layout(
            title='Trade P&L Distribution',
            xaxis_title='P&L (INR)',
            yaxis_title='Frequency',
            template='plotly_white',
            height=400
        )

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def _create_monthly_returns_chart(self) -> str:
        """Generate monthly returns heatmap"""
        if len(self.results.equity_curve) == 0:
            return ""

        df = self.results.equity_curve.copy()
        df['year'] = df['timestamp'].dt.year
        df['month'] = df['timestamp'].dt.month

        # Calculate monthly returns
        monthly_returns = {}
        for year in df['year'].unique():
            year_data = df[df['year'] == year]
            for month in range(1, 13):
                month_data = year_data[year_data['month'] == month]
                if len(month_data) > 0:
                    start_equity = month_data['equity'].iloc[0]
                    end_equity = month_data['equity'].iloc[-1]
                    ret = ((end_equity - start_equity) / start_equity) * 100
                    monthly_returns[(year, month)] = ret

        if len(monthly_returns) == 0:
            return ""

        # Build heatmap data
        years = sorted(set(y for y, m in monthly_returns.keys()))
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        z_data = []
        for year in years:
            row = []
            for month_idx in range(1, 13):
                row.append(monthly_returns.get((year, month_idx), None))
            z_data.append(row)

        fig = go.Figure(data=go.Heatmap(
            z=z_data,
            x=months,
            y=[str(y) for y in years],
            colorscale='RdYlGn',
            zmid=0,
            text=[[f"{val:.1f}%" if val is not None else "" for val in row] for row in z_data],
            texttemplate="%{text}",
            textfont={"size": 10},
            hovertemplate='%{y} %{x}<br>Return: %{z:.2f}%<extra></extra>'
        ))

        fig.update_layout(
            title='Monthly Returns (%)',
            xaxis_title='Month',
            yaxis_title='Year',
            template='plotly_white',
            height=300
        )

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def _create_hourly_distribution_chart(self) -> str:
        """Generate trade distribution by hour"""
        if len(self.results.trades) == 0:
            return ""

        hours = [t.entry_time.hour for t in self.results.trades]
        wins = [1 if t.net_pnl > 0 else 0 for t in self.results.trades]

        hour_data = {}
        for h, w in zip(hours, wins):
            if h not in hour_data:
                hour_data[h] = {'total': 0, 'wins': 0}
            hour_data[h]['total'] += 1
            hour_data[h]['wins'] += w

        sorted_hours = sorted(hour_data.keys())
        total_counts = [hour_data[h]['total'] for h in sorted_hours]
        win_counts = [hour_data[h]['wins'] for h in sorted_hours]
        loss_counts = [hour_data[h]['total'] - hour_data[h]['wins'] for h in sorted_hours]

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=sorted_hours,
            y=win_counts,
            name='Wins',
            marker_color='green'
        ))

        fig.add_trace(go.Bar(
            x=sorted_hours,
            y=loss_counts,
            name='Losses',
            marker_color='red'
        ))

        fig.update_layout(
            title='Trade Distribution by Hour',
            xaxis_title='Hour of Day',
            yaxis_title='Number of Trades',
            barmode='stack',
            template='plotly_white',
            height=400
        )

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def _create_trade_analysis_table(self) -> str:
        """Generate HTML table of all trades"""
        if len(self.results.trades) == 0:
            return "<p>No trades executed</p>"

        rows = ""
        for trade in self.results.trades:
            pnl_class = "positive" if trade.net_pnl > 0 else "negative"
            rows += f"""
            <tr>
                <td>{trade.trade_id}</td>
                <td>{trade.entry_time.strftime('%Y-%m-%d %H:%M')}</td>
                <td>{trade.exit_time.strftime('%Y-%m-%d %H:%M') if trade.exit_time else '-'}</td>
                <td>{trade.side}</td>
                <td>{trade.entry_price:.2f}</td>
                <td>{f"{trade.exit_price:.2f}" if trade.exit_price else '-'}</td>
                <td>{trade.quantity:.0f}</td>
                <td class="{pnl_class}">{trade.net_pnl:.2f}</td>
                <td class="{pnl_class}">{trade.pnl_pct:.2f}%</td>
                <td>{trade.duration_minutes} min</td>
                <td>{trade.exit_reason}</td>
            </tr>
            """

        table_html = f"""
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Entry Time</th>
                    <th>Exit Time</th>
                    <th>Side</th>
                    <th>Entry Price</th>
                    <th>Exit Price</th>
                    <th>Quantity</th>
                    <th>P&L (INR)</th>
                    <th>P&L %</th>
                    <th>Duration</th>
                    <th>Exit Reason</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """

        return table_html

    def _build_html(self, equity_chart, drawdown_chart, pnl_dist_chart,
                    monthly_returns_chart, hourly_dist_chart, trade_table) -> str:
        """Build complete HTML report"""
        m = self.metrics

        # Build metric cards
        metric_cards = f"""
        <div class="metric-card">
            <div class="metric-label">Total Return</div>
            <div class="metric-value {'positive' if m['total_return'] > 0 else 'negative'}">{m['total_return']:.2f}%</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Total Trades</div>
            <div class="metric-value">{m['total_trades']}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Win Rate</div>
            <div class="metric-value">{m['win_rate']:.2f}%</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Profit Factor</div>
            <div class="metric-value">{m['profit_factor']:.2f}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Max Drawdown</div>
            <div class="metric-value negative">{m['max_drawdown']:.2f}%</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Sharpe Ratio</div>
            <div class="metric-value">{m['sharpe_ratio']:.2f}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Net Profit</div>
            <div class="metric-value {'positive' if m['net_profit'] > 0 else 'negative'}">₹{m['net_profit']:.2f}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Avg Win</div>
            <div class="metric-value positive">₹{m['avg_win']:.2f}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Avg Loss</div>
            <div class="metric-value negative">₹{m['avg_loss']:.2f}</div>
        </div>
        """

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Backtest Report - {self.results.config['name']}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #2E86AB;
            border-bottom: 3px solid #2E86AB;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #333;
            margin-top: 40px;
        }}
        .metric-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            min-width: 150px;
            flex: 1;
        }}
        .metric-label {{
            color: #666;
            font-size: 14px;
            margin-bottom: 8px;
        }}
        .metric-value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
        }}
        .positive {{
            color: #28a745;
        }}
        .negative {{
            color: #dc3545;
        }}
        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin: 20px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #2E86AB;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .config-info {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
    </style>
</head>
<body>
    <h1>📊 Backtest Report: {self.results.config['name']}</h1>

    <div class="config-info">
        <strong>Period:</strong> {self.results.config['data']['start_date']} to {self.results.config['data']['end_date']}<br>
        <strong>Symbol:</strong> {', '.join(self.results.config['data']['symbols'])}<br>
        <strong>Strategy:</strong> {self.results.config['strategy']['class']}<br>
        <strong>Initial Capital:</strong> ₹{m['initial_capital']:,.2f}<br>
        <strong>Final Equity:</strong> ₹{m['final_equity']:,.2f}
    </div>

    <h2>Performance Summary</h2>
    <div class="metric-container">
        {metric_cards}
    </div>

    <h2>Equity Curve</h2>
    <div class="chart-container">
        {equity_chart}
    </div>

    <h2>Drawdown</h2>
    <div class="chart-container">
        {drawdown_chart}
    </div>

    <h2>Trade P&L Distribution</h2>
    <div class="chart-container">
        {pnl_dist_chart}
    </div>

    <h2>Monthly Returns</h2>
    <div class="chart-container">
        {monthly_returns_chart}
    </div>

    <h2>Trade Distribution by Hour</h2>
    <div class="chart-container">
        {hourly_dist_chart}
    </div>

    <h2>Trade-by-Trade Analysis</h2>
    {trade_table}

    <div style="margin-top: 40px; padding: 20px; background: white; border-radius: 8px; text-align: center;">
        <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p style="color: #666;">🤖 Generated with stock_advanced_bot backtesting framework</p>
    </div>
</body>
</html>
        """

        return html


def open_report_in_browser(report_path: str):
    """Open report in default browser"""
    abs_path = os.path.abspath(report_path)
    webbrowser.open('file://' + abs_path)
    logger.info(f"Opened report in browser: {abs_path}")
