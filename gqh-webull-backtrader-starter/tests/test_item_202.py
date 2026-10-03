"""Unit tests for Massive Item 2.02 helpers and the options-impact strategy."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import backtrader as bt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_DIR = PROJECT_ROOT / "examples" / "strategies"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(STRATEGIES_DIR))

from webull_bt.massive_filings import (
    Item202Event,
    enrich_with_benzinga,
    is_item_202_text,
    load_events_cache,
    resolve_trade_date,
    save_events_cache,
)
from item_202_options import Item202OptionsImpactStrategy


class Item202ParsingTests(unittest.TestCase):
    def test_detects_item_202(self):
        text = "Item 2.02\tResults of Operations and Financial Condition\nOn Jan 1..."
        self.assertTrue(is_item_202_text(text))
        self.assertTrue(is_item_202_text("ITEM 2.02: Results"))
        self.assertFalse(is_item_202_text("Item 7.01 Regulation FD"))
        self.assertFalse(is_item_202_text(None))

    def test_resolve_trade_date_amc_skips_weekend(self):
        # Friday AMC -> Monday
        self.assertEqual(resolve_trade_date("2024-08-02", "AMC"), "2024-08-05")
        self.assertEqual(resolve_trade_date("2024-08-02", "BMO"), "2024-08-02")

    def test_enrich_benzinga_sets_session(self):
        events = [
            Item202Event(ticker="AAPL", filing_date="2024-08-01", accession_number="x"),
        ]
        earnings = [{
            "ticker": "AAPL",
            "date": "2024-08-01",
            "time": "16:30:00",
            "eps_surprise_percent": 4.0,
            "revenue_surprise_percent": 1.0,
            "importance": 5,
        }]
        out = enrich_with_benzinga(events, earnings)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].session, "AMC")
        self.assertEqual(out[0].trade_date, "2024-08-02")
        self.assertEqual(out[0].eps_surprise_percent, 4.0)

    def test_cache_roundtrip(self):
        events = [
            Item202Event(
                ticker="AAPL",
                filing_date="2024-02-01",
                trade_date="2024-02-02",
                session="AMC",
                eps_surprise_percent=3.5,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            save_events_cache(events, path)
            loaded = load_events_cache(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].ticker, "AAPL")
            self.assertEqual(loaded[0].trade_date, "2024-02-02")


class _SyntheticDaily(bt.feeds.PandasData):
    pass


class Item202StrategySmokeTest(unittest.TestCase):
    def test_strategy_trades_on_cached_event(self):
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover
            self.skipTest(f"pandas required: {exc}")

        # Build ~40 daily bars with a clear gap on the event trade_date.
        start = datetime(2024, 1, 2, tzinfo=timezone.utc)
        rows = []
        price = 100.0
        event_day = datetime(2024, 2, 2, tzinfo=timezone.utc)
        for i in range(40):
            dt = start + timedelta(days=i)
            if dt.weekday() >= 5:
                continue
            open_px = price
            if dt.date() == event_day.date():
                open_px = price * 1.04  # +4% gap
            close = open_px * 1.005
            high = max(open_px, close) * 1.01
            low = min(open_px, close) * 0.99
            rows.append({
                "datetime": dt,
                "open": open_px,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1_000_000,
            })
            price = close

        frame = pd.DataFrame(rows).set_index("datetime")
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "events.json"
            cache.write_text(json.dumps({
                "events": [{
                    "ticker": "AAPL",
                    "filing_date": "2024-02-01",
                    "trade_date": "2024-02-02",
                    "session": "AMC",
                    "eps_surprise_percent": 5.0,
                    "source": "test",
                }]
            }), encoding="utf-8")

            cerebro = bt.Cerebro()
            data = bt.feeds.PandasData(dataname=frame, name="AAPL")
            cerebro.adddata(data)
            cerebro.addstrategy(
                Item202OptionsImpactStrategy,
                hold_bars=3,
                atr_period=5,
                min_gap_atr=0.1,
                mode="momentum",
                allow_short=True,
                target_pct=0.5,
                events_cache=str(cache),
                enrich_benzinga=False,
            )
            cerebro.broker.setcash(100_000.0)
            results = cerebro.run(runonce=False)
            strat = results[0]

        self.assertGreaterEqual(len(strat.event_log), 1)
        self.assertEqual(strat.event_log[0]["action"], "long")
        self.assertGreater(len(strat.closed_trades) + int(bool(strat.position)), 0)


if __name__ == "__main__":
    unittest.main()
