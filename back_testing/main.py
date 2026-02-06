#!/usr/bin/env python3
"""
Main entry point for backtesting framework
"""
import argparse
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from back_testing.display_results import (BacktestResults, ReportGenerator,
                                          open_report_in_browser)
from back_testing.runner import BacktestRunner
from core_logic.logger_config import get_logger

logger = get_logger()


def main():
    """Main CLI function"""
    # Configure stdout/stderr to use UTF-8 encoding for rupee symbol (₹) support on Windows
    import io
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description='Stock Advanced Bot - Backtesting Framework',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python back_testing/main.py
  python back_testing/main.py --config back_testing/my_config.json
  python back_testing/main.py --output reports/custom_report.html
  python back_testing/main.py --no-browser

For more information, visit: https://github.com/saikesav-sai/stock_advanced_bot
        """
    )

    parser.add_argument(
        '--config',
        default='back_testing/back_testing_config.json',
        help='Path to configuration file (default: back_testing/back_testing_config.json)'
    )

    parser.add_argument(
        '--output',
        default=None,
        help='Output path for HTML report (default: back_testing/reports/backtest_report_TIMESTAMP.html)'
    )

    parser.add_argument(
        '--no-browser',
        action='store_true',
        help='Do not auto-open report in browser'
    )

    args = parser.parse_args()


    # Check if config file exists
    if not os.path.exists(args.config):
        logger.error(f"Configuration file not found: {args.config}")
        print(f"ERROR: Configuration file not found: {args.config}")
        print("\nPlease create a configuration file or specify a different path using --config")
        sys.exit(1)

    try:
        # Initialize backtest runner
        logger.info(f"Loading configuration from: {args.config}")
        print(f"Loading configuration: {args.config}")

        runner = BacktestRunner(args.config)

        # Run backtest

        results = runner.run()

        # Display per-stock summary
        print("\n" + "=" * 80)
        print("PER-STOCK RESULTS")
        print("=" * 80)

        stock_results = results.get('stock_results', {})
        if stock_results:
            print(f"\n{'Symbol':<15} {'Trades':<10} {'Return %':<12} {'Net P&L':<15} {'Final Equity':<15}")
            print("-" * 80)
            for symbol, stock_data in stock_results.items():
                print(f"{symbol:<15} {stock_data['total_trades']:<10} "
                      f"{stock_data['return_pct']:>10.2f}% "
                      f"₹{stock_data['net_profit']:>12,.2f} "
                      f"₹{stock_data['final_equity']:>12,.2f}")

        print("\n" + "=" * 80)
        print(f"OVERALL SUMMARY")
        print("=" * 80)
        print(f"Total trades across all stocks: {len(results['trades'])}")
        print(f"Number of stocks tested: {len(stock_results)}")

        # Generate report
        print("\nGenerating report...")

        backtest_results = BacktestResults(
            trades=results['trades'],
            equity_curve=results['equity_curve'],
            config=results['config'],
            stock_results=results.get('stock_results', {})
        )

        report_gen = ReportGenerator(backtest_results)

        # Determine output path
        if args.output:
            report_path = args.output
        else:
            # Generate default path with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_dir = 'back_testing/reports'
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, f'backtest_report_{timestamp}.html')

        # Generate report
        report_path = report_gen.generate_report(report_path)

        # Print summary metrics
        m = backtest_results.metrics
        print("\n" + "=" * 80)
        print("  BACKTEST SUMMARY")
        print("=" * 80)
        print(f"Total Return:        {m['total_return']:>10.2f}%")
        print(f"Net Profit:          ₹{m['net_profit']:>10,.2f}")
        print(f"Total Trades:        {m['total_trades']:>10}")
        print(f"Win Rate:            {m['win_rate']:>10.2f}%")
        print(f"Profit Factor:       {m['profit_factor']:>10.2f}")
        print(f"Max Drawdown:        {m['max_drawdown']:>10.2f}%")
        print(f"Sharpe Ratio:        {m['sharpe_ratio']:>10.2f}")
        print(f"Avg Win:             ₹{m['avg_win']:>10,.2f}")
        print(f"Avg Loss:            ₹{m['avg_loss']:>10,.2f}")
        print("=" * 80)

        print(f"\n✅ Report saved to: {report_path}")

        # Open in browser
        if not args.no_browser:
            print("\nOpening report in browser...")
            open_report_in_browser(report_path)
        else:
            print("\nTo view the report, open:")
            print(f"  file://{os.path.abspath(report_path)}")

        print("\nDone!\n")

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        print(f"\nERROR: File not found: {e}")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        print(f"\nERROR: Backtest failed: {e}")
        print("\nCheck the logs for more details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
