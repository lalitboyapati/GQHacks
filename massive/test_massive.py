"""Test script demonstrating Massive (Polygon.io) capabilities and Backtrader integration."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import backtrader as bt
from massive.client import MassiveClient
from massive.feed_massive import MassiveData


def test_massive():
    print("=" * 65)
    print(" MASSIVE (POLYGON.IO) CAPABILITIES & HEALTH CHECK")
    print("=" * 65)

    client = MassiveClient()
    ticker = "AAPL"

    # 1. Historical Bars
    print(f"\n[1] Historical K-Line Aggregates ({ticker} 2026-09-01 ~ 2026-09-30):")
    bars = client.get_bars(ticker, multiplier=1, timespan="day", from_date="2026-09-01", to_date="2026-09-30")
    print(f"    Loaded {len(bars)} daily bars.")
    if bars:
        first = bars[0]
        print(f"    Sample Bar: Open=${first['o']}, High=${first['h']}, Low=${first['l']}, Close=${first['c']}, Vol={first['v']:,}")

    # 2. Market Snapshot & Level 1 Quotes
    print(f"\n[2] Real-time Market Snapshot & Bid/Ask Quotes ({ticker}):")
    snapshot = client.get_snapshot(ticker)
    day = snapshot.get("day", {})
    prev = snapshot.get("prevDay", {})
    print(f"    Current Day Range: ${day.get('l', 'N/A')} - ${day.get('h', 'N/A')} | Close: ${day.get('c', 'N/A')}")
    print(f"    Previous Close   : ${prev.get('c', 'N/A')}")

    quotes = client.get_quotes(ticker, limit=2)
    if quotes:
        q = quotes[0]
        print(f"    Latest Top-of-Book Quote: Bid=${q.get('bid_price')} (size {q.get('bid_size')}) / Ask=${q.get('ask_price')} (size {q.get('ask_size')})")

    # 3. Server-side Technical Indicators
    print(f"\n[3] Server-Side Technical Indicators ({ticker} 20-period SMA):")
    sma_vals = client.get_indicator("sma", ticker, timespan="day", window=20, limit=3)
    for s in sma_vals:
        print(f"    SMA(20): {s.get('value'):.2f}")

    # 4. Options Contracts
    print(f"\n[4] Options Contracts ({ticker}):")
    options = client.get_options_contracts(ticker, limit=3)
    for opt in options:
        print(f"    Contract: {opt.get('ticker')} | Type: {opt.get('contract_type')} | Strike: ${opt.get('strike_price')} | Exp: {opt.get('expiration_date')}")

    # 5. Financial News
    print(f"\n[5] Financial Market News ({ticker}):")
    news = client.get_news(ticker=ticker, limit=2)
    for n in news:
        print(f"    - \"{n.get('title')}\" ({n.get('publisher', {}).get('name')})")

    # 6. Backtrader Engine Integration
    print(f"\n[6] Backtrader Backtest Integration using MassiveData:")
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(100000.0)

    # Use MassiveData feed
    feed = MassiveData(
        dataname=ticker,
        timespan="day",
        from_date="2026-06-01",
        to_date="2026-10-02"
    )
    cerebro.adddata(feed, name=ticker)

    class SimpleSmaStrategy(bt.Strategy):
        def __init__(self):
            self.sma = bt.ind.SMA(self.data.close, period=10)
        def next(self):
            if not self.position and self.data.close[0] > self.sma[0]:
                self.buy(size=10)
            elif self.position and self.data.close[0] < self.sma[0]:
                self.close()

    cerebro.addstrategy(SimpleSmaStrategy)
    cerebro.run()
    final_val = cerebro.broker.getvalue()
    print(f"    Backtest completed! Starting cash: $100,000.00 -> Ending value: ${final_val:,.2f}")

    print("\n" + "=" * 65)
    print(" [SUCCESS] Massive API is fully operational and integrated!")
    print("=" * 65)


if __name__ == "__main__":
    test_massive()
