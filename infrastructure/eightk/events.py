"""Assemble tradable event records from filings, text, news, and reference data.

This is the join step: EDGAR supplies the filing and its exact publication
instant, ``classify`` reads what the filing actually says, ``novelty`` judges
whether it was already public, and Massive supplies the market cap that
decides whether the issuer is small enough to be under-covered.

The output is a flat, JSON-serializable record per filing so the event set
can be built once, inspected by hand, committed for reproducibility, and
re-run through many strategy variants without re-fetching anything.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Iterable

from eightk.classify import (
    EfficiencyPlan,
    ExecChange,
    parse_efficiency_plan,
    parse_exec_change,
    split_items,
)
from eightk.edgar import EdgarClient, Filing
from eightk.novelty import NoveltyAssessment, assess_novelty

logger = logging.getLogger(__name__)

# 8-K items that carry the disclosures under study.
EXEC_ITEMS = {"5.02"}
PLAN_ITEMS = {"2.05", "2.06"}
# Restructuring is frequently announced under Reg FD or "Other Events"
# instead of 2.05, so these are scanned for plan language too. Item 2.02 is
# deliberately absent: an earnings release mentions efficiency work in
# passing and carries financial statements whose tables yield spurious
# multi-billion-dollar "charges".
PLAN_CANDIDATE_ITEMS = {"2.05", "2.06", "7.01", "8.01"}

# An earnings release in the same filing swamps any other disclosure in it.
EARNINGS_ITEM = "2.02"


@dataclass
class EventRecord:
    """One 8-K with everything a strategy needs to decide and to trade."""

    filing: Filing
    exec_change: ExecChange | None = None
    plan: EfficiencyPlan | None = None
    novelty: NoveltyAssessment | None = None
    market_cap: float | None = None
    company_name: str | None = None
    sic_description: str | None = None
    text_chars: int = 0
    event_types: tuple[str, ...] = ()
    extras: dict = field(default_factory=dict)

    @property
    def ticker(self) -> str:
        return self.filing.ticker

    @property
    def confounded_by_earnings(self) -> bool:
        """True when an earnings release shares the filing.

        A CEO departure announced alongside quarterly results cannot be
        attributed to the departure, so these are tracked separately rather
        than silently pooled.
        """
        return EARNINGS_ITEM in self.filing.items

    @property
    def cap_bucket(self) -> str:
        """Standard size buckets; ``unknown`` when no market cap was found."""
        cap = self.market_cap
        if cap is None:
            return "unknown"
        if cap < 300e6:
            return "micro"
        if cap < 2e9:
            return "small"
        if cap < 10e9:
            return "mid"
        if cap < 200e9:
            return "large"
        return "mega"

    def to_dict(self) -> dict:
        row = {
            **self.filing.to_dict(),
            "company_name": self.company_name,
            "sic_description": self.sic_description,
            "market_cap": self.market_cap,
            "cap_bucket": self.cap_bucket,
            "text_chars": self.text_chars,
            "event_types": list(self.event_types),
            "confounded_by_earnings": self.confounded_by_earnings,
        }
        if self.exec_change:
            row.update({f"exec_{k}": v for k, v in self.exec_change.to_dict().items()})
        if self.plan:
            row.update({f"plan_{k}": v for k, v in self.plan.to_dict().items()})
        if self.novelty:
            row.update(self.novelty.to_dict())
        row.update(self.extras)
        return row


def build_event(
    filing: Filing,
    *,
    edgar: EdgarClient,
    massive=None,
    news_lookback_days: int = 10,
    fetch_news: bool = True,
) -> EventRecord:
    """Parse one filing into an ``EventRecord``."""
    text = edgar.filing_text(filing)
    sections = split_items(text)

    # The press release carries the substance when the 8-K body only points
    # at an exhibit, so it is folded in for text-dependent scoring.
    exhibit_text = ""
    if len(text) < 8000:
        try:
            exhibit_text = edgar.exhibit_text(filing)
        except Exception:
            logger.debug("exhibit fetch failed for %s", filing.accession, exc_info=True)
    full_text = text if not exhibit_text else f"{text}\n\n{exhibit_text}"

    event_types: list[str] = []

    exec_change = None
    if set(filing.items) & EXEC_ITEMS:
        exec_change = parse_exec_change(sections.get("5.02", ""))
        if exec_change.is_senior_departure:
            event_types.append("exec_departure")
        elif exec_change.is_departure:
            event_types.append("other_departure")

    plan = None
    if set(filing.items) & PLAN_CANDIDATE_ITEMS:
        # Scan the plan-bearing sections plus any press release, since the
        # numbers usually live in the exhibit rather than the 8-K body.
        plan_text_parts = [
            sections.get(code, "") for code in sorted(PLAN_CANDIDATE_ITEMS)
        ]
        if exhibit_text:
            plan_text_parts.append(exhibit_text)
        filed_under_plan_item = bool(set(filing.items) & PLAN_ITEMS)
        try:
            filing_year = int(filing.filing_date[:4])
        except (TypeError, ValueError):
            filing_year = None
        plan_candidate = parse_efficiency_plan(
            "\n".join(filter(None, plan_text_parts)),
            filing_year=filing_year,
            # Money figures are only trusted from a document the issuer
            # actually filed as a cost/impairment disclosure.
            trust_tables=filed_under_plan_item,
        )
        if plan_candidate.is_plan:
            plan = plan_candidate
            # A plan is only tradable if the filing quantified it. The
            # keyword alone fires on passing mentions of "realignment", which
            # carry no cost/savings asymmetry to trade against.
            if filed_under_plan_item or plan.quantified:
                event_types.append("efficiency_plan")

    # --- novelty -------------------------------------------------------
    prior_news: list = []
    if fetch_news and massive is not None:
        start = (filing.acceptance_utc - timedelta(days=news_lookback_days)).strftime("%Y-%m-%d")
        end = filing.acceptance_utc.strftime("%Y-%m-%d")
        try:
            prior_news = massive.news(filing.ticker, published_gte=start, published_lte=end)
        except Exception:
            logger.debug("news fetch failed for %s", filing.ticker, exc_info=True)
            prior_news = []

    novelty = assess_novelty(
        filing_text=full_text,
        acceptance_utc=filing.acceptance_utc,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        prior_news=prior_news,
        lookback_days=news_lookback_days,
    )

    # --- reference data ------------------------------------------------
    market_cap = None
    company_name = None
    sic_description = None
    if massive is not None:
        try:
            details = massive.ticker_details(filing.ticker, as_of=filing.filing_date)
            market_cap = details.get("market_cap")
            company_name = details.get("name")
            sic_description = details.get("sic_description")
        except Exception:
            logger.debug("ticker details failed for %s", filing.ticker, exc_info=True)

    return EventRecord(
        filing=filing,
        exec_change=exec_change,
        plan=plan,
        novelty=novelty,
        market_cap=market_cap,
        company_name=company_name,
        sic_description=sic_description,
        text_chars=len(full_text),
        event_types=tuple(event_types),
    )


def build_events(
    tickers: Iterable[str],
    *,
    edgar: EdgarClient,
    massive=None,
    date_gte: str,
    date_lte: str,
    items: set[str] | None = None,
    fetch_news: bool = True,
    progress_every: int = 25,
) -> list[EventRecord]:
    """Build event records for every matching 8-K across ``tickers``."""
    wanted = items if items is not None else (EXEC_ITEMS | PLAN_CANDIDATE_ITEMS)
    records: list[EventRecord] = []
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]

    for index, ticker in enumerate(tickers, start=1):
        try:
            filings = edgar.list_8k(ticker, date_gte=date_gte, date_lte=date_lte, items=wanted)
        except Exception:
            logger.warning("filing list failed for %s", ticker, exc_info=True)
            continue

        for filing in filings:
            try:
                record = build_event(
                    filing, edgar=edgar, massive=massive, fetch_news=fetch_news,
                )
            except Exception:
                logger.warning("event build failed for %s", filing.accession, exc_info=True)
                continue
            if record.event_types:
                records.append(record)

        if index % progress_every == 0:
            logger.info("processed %d/%d tickers, %d events so far",
                        index, len(tickers), len(records))

    records.sort(key=lambda r: r.filing.acceptance_utc)
    logger.info("built %d event record(s) from %d ticker(s)", len(records), len(tickers))
    return records


def save_events(records: list[EventRecord], path: str | Path) -> Path:
    """Write event records to JSON for inspection and reproducible re-runs."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([r.to_dict() for r in records], indent=2, default=str))
    logger.info("wrote %d events to %s", len(records), out)
    return out


def load_events_table(path: str | Path):
    """Load a saved event file as a pandas DataFrame."""
    import pandas as pd
    rows = json.loads(Path(path).read_text())
    return pd.DataFrame(rows)
