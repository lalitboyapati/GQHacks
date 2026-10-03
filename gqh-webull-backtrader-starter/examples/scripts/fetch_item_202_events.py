"""Fetch and cache Massive Item 2.02 8-K events for backtests.

Usage:
    # Requires MASSIVE_APP_KEY in the environment or examples/backtest/.env
    uv run python examples/scripts/fetch_item_202_events.py --symbols AAPL,MSFT,TSLA

    # Write a custom cache consumed by the strategy via MASSIVE_EVENTS_CACHE
    uv run python examples/scripts/fetch_item_202_events.py \\
        --symbols AAPL --gte 2023-01-01 --out examples/data/item_202_events.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from webull_bt.logging_utils import get_logger, setup_logging
from webull_bt.massive_filings import load_item_202_events, save_events_cache

logger = get_logger("fetch_item_202")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache Massive Item 2.02 events")
    parser.add_argument(
        "--symbols",
        default=os.environ.get("WEBULL_SYMBOLS", "AAPL"),
        help="Comma-separated tickers",
    )
    parser.add_argument("--gte", default=os.environ.get("MASSIVE_FILING_DATE_GTE", ""), help="filing_date >= YYYY-MM-DD")
    parser.add_argument("--lte", default=os.environ.get("MASSIVE_FILING_DATE_LTE", ""), help="filing_date <= YYYY-MM-DD")
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "examples" / "data" / "item_202_events.json"),
        help="Output JSON cache path",
    )
    parser.add_argument(
        "--benzinga",
        action="store_true",
        help="Try Benzinga earnings enrichment (requires Massive Benzinga entitlement)",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / "examples" / "backtest" / ".env")
    setup_logging()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    events = load_item_202_events(
        symbols,
        filing_date_gte=args.gte or None,
        filing_date_lte=args.lte or None,
        cache_path=None,
        refresh=True,
        enrich_benzinga=bool(args.benzinga),
        enrich_disclosures=True,
    )
    path = save_events_cache(events, args.out)
    logger.info("Cached %d Item 2.02 event(s) -> %s", len(events), path)
    for event in events:
        logger.info(
            "  %s filing=%s trade=%s primary=%s tertiary=%s polarity=%s",
            event.ticker,
            event.filing_date,
            event.trade_date,
            event.primary_category or "n/a",
            event.tertiary_category or "n/a",
            event.category_polarity,
        )


if __name__ == "__main__":
    main()
