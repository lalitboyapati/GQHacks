"""Massive.com helpers for SEC Form 8-K Item 2.02 event discovery.

Item 2.02 ("Results of Operations and Financial Condition") is the 8-K item
companies use to furnish earnings releases. Those filings are the formal
disclosure around scheduled earnings events and are highly relevant to
options markets (implied vs realized move, IV crush, PEAD).

This module:
  1. Pulls parsed 8-K text via Massive ``list_stocks_filings_8k_text`` and
     keeps filings whose ``items_text`` contains Item 2.02.
  2. Optionally enriches each event with Benzinga earnings calendar fields
     (scheduled time, EPS/revenue surprise) when that plan is available.
  3. Can load/save a JSON cache so backtests remain reproducible offline.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from webull_bt.logging_utils import get_logger

logger = get_logger("massive_filings")

# Matches "Item 2.02", "ITEM 2.02", "Item 2.02:", etc.
_ITEM_202_RE = re.compile(r"\bitem\s*2\.02\b", re.IGNORECASE)


@dataclass(frozen=True)
class Item202Event:
    """A single Item 2.02 / earnings-results event for one ticker."""

    ticker: str
    filing_date: str  # YYYY-MM-DD (SEC filing date)
    accession_number: str | None = None
    filing_url: str | None = None
    form_type: str | None = None
    # First equity session where the overnight gap from the release is visible.
    trade_date: str | None = None
    session: str | None = None  # "BMO" | "AMC" | None
    eps_surprise_percent: float | None = None
    revenue_surprise_percent: float | None = None
    estimated_eps: float | None = None
    actual_eps: float | None = None
    importance: int | None = None
    source: str = "8k_text"
    extras: dict = field(default_factory=dict)

    @property
    def event_date(self) -> date:
        """Date used for strategy scheduling (prefer trade_date)."""
        raw = self.trade_date or self.filing_date
        return date.fromisoformat(raw)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Item202Event":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in payload.items() if k in known}
        extras = filtered.pop("extras", {}) or {}
        unknown = {k: v for k, v in payload.items() if k not in known}
        extras = {**extras, **unknown}
        return cls(**filtered, extras=extras)


def is_item_202_text(items_text: str | None) -> bool:
    """Return True if parsed 8-K text discloses Item 2.02."""
    if not items_text:
        return False
    return bool(_ITEM_202_RE.search(items_text))


def _infer_session(time_str: str | None) -> str | None:
    """Map Benzinga HH:MM:SS (ET) to BMO / AMC for gap timing."""
    if not time_str:
        return None
    try:
        parts = time_str.strip().split(":")
        hour = int(parts[0])
    except (ValueError, IndexError):
        return None
    # Rough cut: releases at/after 16:00 ET are after the close.
    if hour >= 16:
        return "AMC"
    return "BMO"


def _next_weekday(d: date) -> date:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:  # Sat/Sun
        nxt += timedelta(days=1)
    return nxt


def resolve_trade_date(filing_date: str, session: str | None) -> str:
    """Equity session where the post-release gap is observable on daily bars."""
    d = date.fromisoformat(filing_date)
    if session == "AMC":
        return _next_weekday(d).isoformat()
    # BMO or unknown: gap typically prints on the filing/report calendar day.
    return d.isoformat()


def _get_api_key() -> str | None:
    return (
        os.environ.get("MASSIVE_API_KEY")
        or os.environ.get("POLYGON_API_KEY")
        or os.environ.get("POLYGON_KEY")
        or ""
    ).strip() or None


def fetch_item_202_filings(
    tickers: Iterable[str],
    *,
    filing_date_gte: str | None = None,
    filing_date_lte: str | None = None,
    api_key: str | None = None,
    limit_per_ticker: int = 100,
) -> list[Item202Event]:
    """Fetch Item 2.02 8-K filings from Massive for the given tickers."""
    key = api_key or _get_api_key()
    if not key:
        raise SystemExit(
            "missing MASSIVE_API_KEY (or POLYGON_API_KEY): required to fetch "
            "8-K Item 2.02 filings from Massive, or set MASSIVE_EVENTS_CACHE "
            "to a local JSON file"
        )

    from massive import RESTClient

    client = RESTClient(api_key=key)
    events: list[Item202Event] = []
    for ticker in sorted({t.strip().upper() for t in tickers if t and t.strip()}):
        logger.info(
            "[Massive] fetching 8-K text for %s (gte=%s lte=%s)",
            ticker, filing_date_gte, filing_date_lte,
        )
        try:
            filings = client.list_stocks_filings_8k_text(
                ticker=ticker,
                form_type="8-K",
                filing_date_gte=filing_date_gte,
                filing_date_lte=filing_date_lte,
                limit=limit_per_ticker,
                sort="filing_date.asc",
            )
        except Exception:
            logger.exception("[Massive] 8-K text request failed for %s", ticker)
            raise

        for filing in filings:
            items_text = getattr(filing, "items_text", None)
            if not is_item_202_text(items_text):
                continue
            filing_date = getattr(filing, "filing_date", None)
            if not filing_date:
                continue
            events.append(
                Item202Event(
                    ticker=ticker,
                    filing_date=str(filing_date)[:10],
                    accession_number=getattr(filing, "accession_number", None),
                    filing_url=getattr(filing, "filing_url", None),
                    form_type=getattr(filing, "form_type", None),
                    trade_date=resolve_trade_date(str(filing_date)[:10], None),
                    source="8k_text",
                )
            )
    logger.info("[Massive] found %d Item 2.02 filing(s)", len(events))
    return events


def fetch_benzinga_earnings(
    tickers: Iterable[str],
    *,
    date_gte: str | None = None,
    date_lte: str | None = None,
    api_key: str | None = None,
    limit_per_ticker: int = 100,
) -> list[dict]:
    """Fetch Benzinga scheduled/reported earnings rows (optional enrichment).

    Benzinga is a paid Massive add-on. Entitlement errors are swallowed so
    Item 2.02 8-K backtests still work on Stocks-only plans.
    """
    key = api_key or _get_api_key()
    if not key:
        return []

    from massive import RESTClient

    client = RESTClient(api_key=key)
    rows: list[dict] = []
    for ticker in sorted({t.strip().upper() for t in tickers if t and t.strip()}):
        try:
            # Iteration triggers the HTTP call (lazy paginator).
            results = client.list_benzinga_earnings(
                ticker=ticker,
                date_gte=date_gte,
                date_lte=date_lte,
                limit=limit_per_ticker,
                sort="date.asc",
            )
            for row in results:
                rows.append({
                    "ticker": ticker,
                    "date": getattr(row, "date", None),
                    "time": getattr(row, "time", None),
                    "date_status": getattr(row, "date_status", None),
                    "eps_surprise_percent": getattr(row, "eps_surprise_percent", None),
                    "revenue_surprise_percent": getattr(row, "revenue_surprise_percent", None),
                    "estimated_eps": getattr(row, "estimated_eps", None),
                    "actual_eps": getattr(row, "actual_eps", None),
                    "importance": getattr(row, "importance", None),
                })
        except Exception as exc:
            logger.warning(
                "[Massive] Benzinga earnings unavailable (%s); "
                "continuing with 8-K Item 2.02 dates only",
                exc,
            )
            return rows
    return rows


def enrich_with_benzinga(
    events: list[Item202Event],
    earnings: list[dict],
    *,
    match_window_days: int = 2,
) -> list[Item202Event]:
    """Attach Benzinga schedule/surprise fields to nearby Item 2.02 filings."""
    by_ticker: dict[str, list[dict]] = {}
    for row in earnings:
        t = (row.get("ticker") or "").upper()
        if t and row.get("date"):
            by_ticker.setdefault(t, []).append(row)

    enriched: list[Item202Event] = []
    for event in events:
        candidates = by_ticker.get(event.ticker, [])
        best = None
        best_dist = match_window_days + 1
        filing = date.fromisoformat(event.filing_date)
        for row in candidates:
            try:
                ed = date.fromisoformat(str(row["date"])[:10])
            except (TypeError, ValueError):
                continue
            dist = abs((ed - filing).days)
            if dist <= match_window_days and dist < best_dist:
                best = row
                best_dist = dist
        if not best:
            enriched.append(event)
            continue

        session = _infer_session(best.get("time"))
        report_date = str(best["date"])[:10]
        trade_date = resolve_trade_date(report_date, session)
        enriched.append(
            Item202Event(
                ticker=event.ticker,
                filing_date=event.filing_date,
                accession_number=event.accession_number,
                filing_url=event.filing_url,
                form_type=event.form_type,
                trade_date=trade_date,
                session=session,
                eps_surprise_percent=_as_float(best.get("eps_surprise_percent")),
                revenue_surprise_percent=_as_float(best.get("revenue_surprise_percent")),
                estimated_eps=_as_float(best.get("estimated_eps")),
                actual_eps=_as_float(best.get("actual_eps")),
                importance=_as_int(best.get("importance")),
                source="8k_text+benzinga",
                extras={
                    **event.extras,
                    "benzinga_date": report_date,
                    "benzinga_time": best.get("time"),
                    "date_status": best.get("date_status"),
                },
            )
        )
    return enriched


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def save_events_cache(events: list[Item202Event], path: str | Path) -> Path:
    """Persist events to JSON for offline / reproducible backtests."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "count": len(events),
        "events": [e.to_dict() for e in events],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("[Massive] wrote %d event(s) to %s", len(events), out)
    return out


def load_events_cache(path: str | Path) -> list[Item202Event]:
    """Load events previously saved by ``save_events_cache``."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("events", raw if isinstance(raw, list) else [])
    return [Item202Event.from_dict(row) for row in rows]


def load_item_202_events(
    tickers: Iterable[str],
    *,
    filing_date_gte: str | None = None,
    filing_date_lte: str | None = None,
    cache_path: str | Path | None = None,
    refresh: bool = False,
    enrich_benzinga: bool = False,
) -> list[Item202Event]:
    """Load Item 2.02 events from cache or Massive API.

    Resolution order:
      1. Existing ``cache_path`` (unless ``refresh``).
      2. Live Massive 8-K Item 2.02 pull (+ optional Benzinga enrichment),
         then write cache when ``cache_path`` is set.
    """
    tickers_list = [t.strip().upper() for t in tickers if t and str(t).strip()]
    cache = Path(cache_path) if cache_path else None

    if cache and cache.exists() and not refresh:
        events = load_events_cache(cache)
        wanted = set(tickers_list)
        if wanted:
            events = [e for e in events if e.ticker in wanted]
        logger.info(
            "[Massive] loaded %d Item 2.02 event(s) from cache %s",
            len(events), cache,
        )
        return events

    events = fetch_item_202_filings(
        tickers_list,
        filing_date_gte=filing_date_gte,
        filing_date_lte=filing_date_lte,
    )
    if enrich_benzinga:
        earnings = fetch_benzinga_earnings(
            tickers_list,
            date_gte=filing_date_gte,
            date_lte=filing_date_lte,
        )
        if earnings:
            events = enrich_with_benzinga(events, earnings)

    if cache:
        save_events_cache(events, cache)
    return events


def events_by_ticker(events: Iterable[Item202Event]) -> dict[str, list[Item202Event]]:
    """Group events by ticker, sorted by event_date ascending."""
    grouped: dict[str, list[Item202Event]] = {}
    for event in events:
        grouped.setdefault(event.ticker.upper(), []).append(event)
    for ticker in grouped:
        grouped[ticker].sort(key=lambda e: e.event_date)
    return grouped
