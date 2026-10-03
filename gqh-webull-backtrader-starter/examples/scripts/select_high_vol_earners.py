"""Rank tickers by realized volatility around Item 2.02 earnings filings.

Large mega-caps (AAPL/MSFT) often print muted gaps. This script starts from a
candidate universe of names that historically reprice hard on earnings, pulls
their Massive 8-K Item 2.02 dates, measures the overnight gap with Massive
daily aggregates, and keeps the top movers for Webull backtests.

Usage:
    uv run python examples/scripts/select_high_vol_earners.py
    uv run python examples/scripts/select_high_vol_earners.py --top 8 --gte 2023-01-01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from webull_bt.logging_utils import get_logger, setup_logging
from webull_bt.massive_filings import (
    Item202Event,
    _get_api_key,
    load_item_202_events,
    save_events_cache,
)

logger = get_logger("select_high_vol_earners")

# Names that typically reprice sharply into/after scheduled earnings
# (high implied move / options activity). Intentionally excludes mega-cap
# "low surprise" prints like AAPL/MSFT.
DEFAULT_CANDIDATES = [
    "TSLA", "NVDA", "AMD", "META", "NFLX", "CRM", "COIN", "PLTR",
    "SNOW", "ROKU", "SNAP", "UBER", "SHOP", "NET", "DDOG", "MARA",
    "SOFI", "HOOD", "PATH", "AI", "RBLX", "U", "AFRM", "DKNG",
]


def _bar_date(agg) -> date | None:
    ts = getattr(agg, "timestamp", None) or getattr(agg, "t", None)
    if ts is None:
        return None
    # Massive timestamps are ms since epoch.
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).date()
    return None


def _avg_abs_event_gap(
    client,
    ticker: str,
    events: list[Item202Event],
) -> tuple[float, int]:
    """Mean |open/prev_close - 1| on Item 2.02 trade dates; returns (avg, n)."""
    if not events:
        return 0.0, 0

    trade_dates = sorted({e.event_date for e in events})
    start = (trade_dates[0] - timedelta(days=10)).isoformat()
    end = (trade_dates[-1] + timedelta(days=5)).isoformat()

    try:
        aggs = list(
            client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_=start,
                to=end,
                adjusted=True,
                sort="asc",
                limit=50000,
            )
        )
    except Exception as exc:
        logger.warning("[Rank] %s aggregates unavailable: %s", ticker, exc)
        return 0.0, 0

    by_day: dict[date, object] = {}
    ordered_days: list[date] = []
    for agg in aggs:
        d = _bar_date(agg)
        if d is None:
            continue
        by_day[d] = agg
        ordered_days.append(d)

    day_index = {d: i for i, d in enumerate(ordered_days)}
    gaps: list[float] = []
    for event_day in trade_dates:
        # Exact match, else next available session on/after the event date.
        idx = day_index.get(event_day)
        if idx is None:
            later = [d for d in ordered_days if d >= event_day]
            if not later:
                continue
            idx = day_index[later[0]]
        if idx <= 0:
            continue
        today = by_day[ordered_days[idx]]
        prev = by_day[ordered_days[idx - 1]]
        prev_close = float(getattr(prev, "close"))
        open_px = float(getattr(today, "open"))
        if prev_close <= 0:
            continue
        gaps.append(abs(open_px / prev_close - 1.0))

    if not gaps:
        return 0.0, 0
    return sum(gaps) / len(gaps), len(gaps)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select high earnings-vol tickers from Item 2.02 gaps",
    )
    parser.add_argument(
        "--candidates",
        default=",".join(DEFAULT_CANDIDATES),
        help="Comma-separated candidate tickers",
    )
    parser.add_argument("--top", type=int, default=8, help="How many tickers to keep")
    parser.add_argument("--min-events", type=int, default=3, help="Min Item 2.02 events required")
    parser.add_argument("--gte", default="2023-01-01", help="filing_date >= YYYY-MM-DD")
    parser.add_argument("--lte", default="", help="filing_date <= YYYY-MM-DD")
    parser.add_argument(
        "--out-events",
        default=str(PROJECT_ROOT / "examples" / "data" / "item_202_events_high_vol.json"),
        help="Filtered event cache path",
    )
    parser.add_argument(
        "--out-ranking",
        default=str(PROJECT_ROOT / "examples" / "data" / "earnings_vol_ranking.json"),
        help="Full ranking JSON path",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / "examples" / "backtest" / ".env")
    setup_logging()

    if not _get_api_key():
        raise SystemExit("Set MASSIVE_APP_KEY or MASSIVE_API_KEY in examples/backtest/.env")

    from massive import RESTClient

    client = RESTClient(api_key=_get_api_key())
    candidates = [s.strip().upper() for s in args.candidates.split(",") if s.strip()]

    logger.info(
        "[Rank] fetching Item 2.02 for %d candidates (gte=%s)",
        len(candidates), args.gte,
    )
    events = load_item_202_events(
        candidates,
        filing_date_gte=args.gte or None,
        filing_date_lte=args.lte or None,
        cache_path=None,
        refresh=True,
        enrich_benzinga=False,
    )
    by_ticker: dict[str, list[Item202Event]] = defaultdict(list)
    for event in events:
        by_ticker[event.ticker].append(event)

    ranking = []
    for ticker in candidates:
        rows = by_ticker.get(ticker, [])
        avg_gap, n_gaps = _avg_abs_event_gap(client, ticker, rows)
        ranking.append({
            "ticker": ticker,
            "item_202_events": len(rows),
            "measured_gaps": n_gaps,
            "avg_abs_gap_pct": round(avg_gap * 100.0, 3),
        })
        logger.info(
            "[Rank] %s events=%d measured=%d avg_|gap|=%.2f%%",
            ticker, len(rows), n_gaps, avg_gap * 100.0,
        )

    eligible = [
        r for r in ranking
        if r["measured_gaps"] >= args.min_events and r["avg_abs_gap_pct"] > 0
    ]
    eligible.sort(key=lambda r: r["avg_abs_gap_pct"], reverse=True)
    selected = eligible[: max(1, args.top)]
    selected_tickers = [r["ticker"] for r in selected]

    ranking_path = Path(args.out_ranking)
    ranking_path.parent.mkdir(parents=True, exist_ok=True)
    ranking_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
                "gte": args.gte,
                "selected": selected_tickers,
                "ranking": ranking,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    selected_set = set(selected_tickers)
    filtered = [e for e in events if e.ticker in selected_set]
    save_events_cache(filtered, args.out_events)

    logger.info("=" * 60)
    logger.info("Selected high earnings-vol universe (%d): %s", len(selected_tickers), selected_tickers)
    for row in selected:
        logger.info(
            "  %s  avg_|gap|=%.2f%%  events=%d",
            row["ticker"], row["avg_abs_gap_pct"], row["item_202_events"],
        )
    logger.info("Event cache -> %s (%d events)", args.out_events, len(filtered))
    logger.info("Ranking    -> %s", ranking_path)
    logger.info(
        "Set in .env: WEBULL_SYMBOLS=%s",
        ",".join(selected_tickers),
    )
    logger.info("            MASSIVE_EVENTS_CACHE=%s", args.out_events)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
