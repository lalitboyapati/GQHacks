"""Quick one-command runner for Webull Backtrader backtesting.

Examples:
    python run.py AAPL
    python run.py TSLA --timespan M5
    python run.py AAPL,MSFT,GOOG --strategy portfolio
    python run.py AAPL --params short_period=10,long_period=30
    python run.py AAPL --no-open
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

# Resolve paths
HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE if (HERE / "webull_bt").exists() else HERE / "gqh-webull-backtrader-starter"
BACKTEST_DIR = PROJECT_DIR / "examples" / "backtest"

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(PROJECT_DIR / "examples" / "strategies") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "examples" / "strategies"))

from dotenv import load_dotenv

# Pre-load existing .env from backtest directory
env_path = BACKTEST_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)


def main():
    parser = argparse.ArgumentParser(
        description="Run a Webull Backtrader backtest with automatic browser report display.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("symbol", nargs="?", default=None, help="Ticker symbol(s), e.g. AAPL or AAPL,MSFT,NVDA")
    parser.add_argument("-s", "--strategy", default=None, help="Strategy name in examples/strategies (e.g. dual_ma, portfolio)")
    parser.add_argument("-t", "--timespan", default=None, help="Timespan (D, M1, M5, M15, M30, M60, W)")
    parser.add_argument("-c", "--count", type=int, default=None, help="Number of bars to fetch")
    parser.add_argument("-p", "--params", default=None, help="Strategy params override (e.g. short_period=10,long_period=30)")
    parser.add_argument("-e", "--engine", choices=["lwc", "plotly"], default="lwc", help="Visualization engine: lwc (TradingView) or plotly")
    parser.add_argument("--fromdate", default=None, help="Start datetime (ISO 8601, e.g. 2026-09-01T09:30:00-04:00)")
    parser.add_argument("--todate", default=None, help="End datetime (ISO 8601, e.g. 2026-09-30T16:00:00-04:00)")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open the HTML report in the browser")
    args = parser.parse_args()

    # Apply overrides to environment for the backtester
    if args.symbol:
        os.environ["WEBULL_SYMBOLS"] = args.symbol
    if args.strategy:
        os.environ["WEBULL_STRATEGY"] = args.strategy
    if args.timespan:
        os.environ["WEBULL_TIMESPAN"] = args.timespan
    if args.count:
        os.environ["WEBULL_COUNT"] = str(args.count)
    if args.params:
        os.environ["WEBULL_STRATEGY_PARAMS"] = args.params
    if args.fromdate:
        os.environ["WEBULL_FROMDATE"] = args.fromdate
    if args.todate:
        os.environ["WEBULL_TODATE"] = args.todate
    if args.engine:
        os.environ["WEBULL_VISUALIZE_ENGINE"] = args.engine

    # Ensure output report filename
    report_file = BACKTEST_DIR / f"backtest_report_{os.environ.get('WEBULL_VISUALIZE_ENGINE', 'lwc')}.html"
    os.environ["WEBULL_VISUALIZE_OUTPUT"] = str(report_file)

    # Run backtest
    from examples.backtest.main import setup_logging, run_backtest
    setup_logging()
    run_backtest()

    # Auto-open browser
    if not args.no_open and report_file.exists():
        print(f"\n[Browser] Opening interactive report: {report_file}")
        webbrowser.open(f"file:///{report_file.resolve().as_posix()}")


if __name__ == "__main__":
    main()
