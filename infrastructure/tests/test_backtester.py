"""Basic end-to-end test for WebullData and the Backtrader backtesting engine.

This script tests:
  1. Data ingestion via WebullData (using real Webull OpenAPI if credentials exist,
     or an authentic simulated OpenAPI response).
  2. Integration with Backtrader's Cerebro engine.
  3. Execution of the DualMovingAverageStrategy.
  4. Performance metrics computation (Sharpe ratio, Drawdown, TradeAnalyzer).
  5. Interactive HTML report rendering (RecorderAnalyzer + Plotly/LWC).

Usage:
    # Run standalone with uv:
    python -m uv run python tests/test_backtester.py

    # Or with an activated virtualenv:
    python tests/test_backtester.py

    # Force simulated/mock data even if credentials exist:
    python tests/test_backtester.py --mock
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root and strategies directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_DIR = PROJECT_ROOT / "examples" / "strategies"
BACKTEST_ENV = PROJECT_ROOT / "backtest" / ".env"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(STRATEGIES_DIR))

import backtrader as bt
from dotenv import load_dotenv

from webull_bt.feed import WebullData
from webull_bt.visualize import RecorderAnalyzer, render_report
from webull_bt.visualize_lwc import render_report_lwc
from dual_ma import DualMovingAverageStrategy


class MockApiResponse:
    """Simulates an HTTP response from the Webull OpenAPI market data endpoint."""

    def __init__(self, data: dict, status_code: int = 200, text: str = ""):
        self._data = data
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._data


class MockMarketData:
    """Simulates DataClient.market_data."""

    def __init__(self, symbol: str = "AAPL", num_bars: int = 150):
        self.symbol = symbol
        self.num_bars = num_bars

    def get_batch_history_bar(
        self,
        symbols: list[str],
        category: str = "US_STOCK",
        timespan: str = "D",
        count: str = "200",
        real_time_required: bool = False,
        trading_sessions: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> MockApiResponse:
        """Generates realistic synthetic OHLCV bars with cyclical waves to trigger trades."""
        symbol = symbols[0] if symbols else self.symbol
        base_time = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
        records = []
        base_price = 150.0

        for i in range(self.num_bars):
            # Create a sinusoidal wave so fast MA crosses slow MA multiple times
            bar_time = base_time + timedelta(days=i)
            # Skip weekends for realism
            if bar_time.weekday() >= 5:
                continue

            cycle = math.sin(i / 6.0) * 15.0
            trend = (i / self.num_bars) * 10.0
            close_price = round(base_price + cycle + trend, 2)
            open_price = round(close_price - math.cos(i / 3.0) * 1.5, 2)
            high_price = round(max(open_price, close_price) + 1.2, 2)
            low_price = round(min(open_price, close_price) - 1.2, 2)
            volume = int(1_000_000 + math.sin(i) * 300_000)

            # Webull time format: 2026-01-01T09:30:00.000+0000
            time_str = bar_time.strftime("%Y-%m-%dT%H:%M:%S.000+0000")

            records.append({
                "time": time_str,
                "open": str(open_price),
                "high": str(high_price),
                "low": str(low_price),
                "close": str(close_price),
                "volume": str(volume),
                "trading_session": "RTH",
            })

        # Webull endpoint usually returns most recent bars in descending order
        records.reverse()

        payload = {
            "result": [
                {
                    "symbol": symbol,
                    "result": records,
                }
            ]
        }
        return MockApiResponse(payload, status_code=200)


class MockDataClient:
    """Mock Webull DataClient providing market_data."""

    def __init__(self, symbol: str = "AAPL", num_bars: int = 150):
        self.market_data = MockMarketData(symbol=symbol, num_bars=num_bars)


def run_basic_test(force_mock: bool = False) -> bool:
    print("=" * 65)
    print(" GATOR QUANT HACKS - WEBULL BACKTRADER TEST SUITE")
    print("=" * 65)

    # 1. Attempt to load credentials from examples/backtest/.env
    if BACKTEST_ENV.exists():
        load_dotenv(BACKTEST_ENV)
        print(f"[Setup] Loaded environment from: {BACKTEST_ENV}")
    else:
        print("[Setup] No .env found in examples/backtest (checking process env)")

    app_key = os.environ.get("WEBULL_APP_KEY")
    app_secret = os.environ.get("WEBULL_APP_SECRET")
    use_live_api = bool(app_key and app_secret and not force_mock)

    symbol = os.environ.get("WEBULL_SYMBOLS", "AAPL").split(",")[0].strip().upper()

    if use_live_api:
        print(f"[Mode] LIVE API MODE: Fetching real historical data for {symbol} via Webull OpenAPI...")
        from webull.core.client import ApiClient
        from webull.data.data_client import DataClient

        region_id = os.environ.get("WEBULL_REGION_ID", "us")
        api_endpoint = os.environ.get("WEBULL_API_ENDPOINT", "api.webull.com")
        api_client = ApiClient(app_key, app_secret, region_id)
        api_client.add_endpoint(region_id, api_endpoint)
        data_client = DataClient(api_client)
    else:
        if force_mock:
            print("[Mode] SIMULATED MODE: Forced via --mock flag.")
        else:
            print("[Mode] SIMULATED MODE: No Webull API credentials detected.")
        print(f"[Mode] Using simulated Webull OpenAPI response for {symbol} (120 bars)...")
        data_client = MockDataClient(symbol=symbol, num_bars=120)

    # 2. Initialize Cerebro Backtesting Engine
    cerebro = bt.Cerebro()
    initial_cash = 100000.0
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.001)  # 10 bps realistic commission

    # 3. Add WebullData Feed
    print(f"[Feed] Adding WebullData feed for {symbol}...")
    feed = WebullData(
        dataname=symbol,
        data_client=data_client,
        category="US_STOCK",
        timespan="D",
        count=150,
    )
    cerebro.adddata(feed, name=symbol)

    # 4. Add Strategy: Dual Moving Average (5-day vs 20-day)
    print("[Strategy] Adding DualMovingAverageStrategy (short_period=5, long_period=20)...")
    cerebro.addstrategy(DualMovingAverageStrategy, short_period=5, long_period=20)
    cerebro.addsizer(bt.sizers.FixedSize, stake=50)

    # 5. Add Performance Analyzers
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        timeframe=bt.TimeFrame.Days,
        compression=1,
        annualize=True,
        riskfreerate=0.0,
    )
    cerebro.addanalyzer(RecorderAnalyzer, _name="recorder")

    # 6. Execute Backtest
    print("\n[Execution] Running backtest through Cerebro...")
    results = cerebro.run(runonce=False)
    strat = results[0]

    final_value = cerebro.broker.getvalue()
    net_pnl = final_value - initial_cash
    pnl_pct = (net_pnl / initial_cash) * 100.0

    dd_analysis = strat.analyzers.drawdown.get_analysis()
    max_dd_pct = dd_analysis.get("max", {}).get("drawdown", 0.0)

    trades_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trades_analysis.get("total", {}).get("total", 0)
    won_trades = trades_analysis.get("won", {}).get("total", 0)
    lost_trades = trades_analysis.get("lost", {}).get("total", 0)
    win_rate = (won_trades / total_trades * 100.0) if total_trades else 0.0

    sharpe_analysis = strat.analyzers.sharpe.get_analysis()
    sharpe = sharpe_analysis.get("sharperatio")
    sharpe_str = f"{sharpe:.4f}" if sharpe is not None else "N/A"

    print("\n" + "=" * 65)
    print(" [TEST RESULT] BACKTEST METRICS SUMMARY")
    print("=" * 65)
    print(f" Initial Portfolio Value : ${initial_cash:,.2f}")
    print(f" Final Portfolio Value   : ${final_value:,.2f}")
    print(f" Net P&L                 : ${net_pnl:,.2f} ({pnl_pct:+.2f}%)")
    print(f" Max Drawdown            : {max_dd_pct:.2f}%")
    print(f" Annualized Sharpe Ratio : {sharpe_str}")
    print(f" Total Closed Trades     : {total_trades} (Won: {won_trades}, Lost: {lost_trades})")
    print(f" Win Rate                : {win_rate:.1f}%")
    print("=" * 65)

    # 7. Render Interactive HTML Report
    test_output_dir = PROJECT_ROOT / "examples" / "backtest"
    report_path = test_output_dir / "test_report.html"
    lwc_report_path = test_output_dir / "test_report_lwc.html"

    recorded = strat.analyzers.recorder.get_analysis()
    closed_trades = getattr(strat, "closed_trades", [])
    metrics = {
        "starting_value": initial_cash,
        "final_value": final_value,
        "pnl": net_pnl,
        "pnl_pct": pnl_pct,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_money": dd_analysis.get("max", {}).get("moneydown", 0.0),
        "sharpe_ratio": sharpe,
        "total_trades": total_trades,
        "won": won_trades,
        "lost": lost_trades,
        "win_rate": win_rate,
        "net_pnl": trades_analysis.get("pnl", {}).get("net", {}).get("total", 0.0),
    }

    print("\n[Report] Generating interactive chart reports...")
    try:
        render_report(
            recorded,
            closed_trades,
            str(report_path),
            title=f"Test Run: Dual MA [{symbol}]",
            metrics=metrics,
        )
        print(f"  [OK] Plotly report generated: {report_path}")
    except Exception as exc:
        print(f"  [FAIL] Plotly report rendering failed: {exc}")
        return False

    try:
        render_report_lwc(
            recorded,
            closed_trades,
            str(lwc_report_path),
            title=f"Test Run: Dual MA (TradingView LWC) [{symbol}]",
            metrics=metrics,
        )
        print(f"  [OK] TradingView LWC report generated: {lwc_report_path}")
    except Exception as exc:
        print(f"  [FAIL] TradingView LWC report rendering failed: {exc}")
        return False

    # 8. Assertions
    bars_loaded = len(recorded.get("symbols", {}).get(symbol, {}).get("close", []))
    assert bars_loaded > 0, f"Expected bars to be loaded into feed, got {bars_loaded}"
    print(f"\n[Validation] Successfully processed {bars_loaded} bars through WebullData feed.")
    print("[SUCCESS] All pipeline stages verified successfully!")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Webull Backtrader pipeline")
    parser.add_argument("--mock", action="store_true", help="Force mock data generation")
    args = parser.parse_args()

    success = run_basic_test(force_mock=args.mock)
    sys.exit(0 if success else 1)
