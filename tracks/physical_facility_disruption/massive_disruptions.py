"""Massive 8-K pull + filter for physical facility disruptions.

Reuses the same Massive ``list_stocks_filings_8k_text`` / disclosures paths as
the Item 2.02 track, but keeps filings whose text or taxonomy points at a
fire, explosion, outage, plant shutdown, or similar physical disruption.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from webull_bt.logging_utils import get_logger
from webull_bt.massive_filings import (
    _get_api_key,
    fetch_8k_disclosures,
    resolve_trade_date,
)

logger = get_logger("massive_disruptions")

# Case-insensitive phrases that mark a physical facility disruption.
_DISRUPTION_RE = re.compile(
    r"""
    \b(
        (?:facility|plant|refinery|mill|warehouse|factory|mine|terminal|pipeline|smelter|foundry)
        .{0,60}?
        (?:fire|explosion|blast|outage|shutdown|shut\s*down|destroyed|damaged|idled)
      | (?:fire|explosion|blast|outage|shutdown|shut\s*down)
        .{0,60}?
        (?:facility|plant|refinery|mill|warehouse|factory|mine|terminal|pipeline|smelter|foundry|operations?)
      | (?:industrial|warehouse|plant|mill|refinery)\s+fire
      | fire\s+at\s+the\s+(?:company|corporation|issuer)'?s?
      | explosion\s+at\s+the\s+(?:company|corporation|issuer)'?s?
      | force\s+majeure.{0,60}?(?:facility|plant|refinery|mill|mine|operations|production)
      | (?:facility|plant|refinery|mill|mine|operations|production).{0,60}?force\s+majeure
      | temporary\s+(?:suspension|halt|closure|shutdown)
      | (?:operations?|production)\s+(?:suspended|halted|idled|curtailed)
      | power\s+outage
      | gas\s+leak
      | chemical\s+(?:release|spill|leak)
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Massive disclosure tertiaries that can co-occur with disruption filings.
_DISRUPTION_TERTIARY = frozenset({
    "cybersecurity_incident",  # sometimes paired; kept for audit, soft match
    "asset_impairment",
    "goodwill_impairment",
    "material_charge_or_gain",
})

_DISRUPTION_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("facility_fire", re.compile(r"\bfire\b", re.I)),
    ("explosion", re.compile(r"\b(explosion|blast)\b", re.I)),
    ("plant_outage", re.compile(r"\b(outage|power\s+outage)\b", re.I)),
    ("plant_shutdown", re.compile(r"\b(shut\s*down|shutdown|suspended|halted|idled)\b", re.I)),
    ("force_majeure", re.compile(r"\bforce\s+majeure\b", re.I)),
    ("chemical_release", re.compile(r"\b(chemical|gas)\s+(release|spill|leak)\b", re.I)),
]


@dataclass
class DisruptionEvent:
    """One candidate disruption 8-K, ready for FIRMS join."""

    ticker: str
    filing_date: str
    accession_number: str | None = None
    filing_url: str | None = None
    form_type: str | None = None
    trade_date: str | None = None
    items_text: str | None = None
    primary_category: str | None = None
    secondary_category: str | None = None
    tertiary_category: str | None = None
    supporting_text: str | None = None
    disruption_type: str | None = None
    match_snippet: str | None = None
    # Site / satellite fields (filled later or via --sites map)
    facility_name: str | None = None
    site_lat: float | None = None
    site_lon: float | None = None
    has_site: bool = False
    has_satellite_coverage: bool | None = None
    anomaly_detected: bool | None = None
    anomaly_persist_days: int | None = None
    facility_group: str | None = None
    source: str = "8k_text"
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DisruptionEvent":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in payload.items() if k in known}
        extras = dict(filtered.pop("extras", {}) or {})
        unknown = {k: v for k, v in payload.items() if k not in known}
        extras.update(unknown)
        return cls(**filtered, extras=extras)


def is_disruption_text(text: str | None) -> bool:
    """Return True if free text looks like a physical facility disruption."""
    if not text:
        return False
    return bool(_DISRUPTION_RE.search(text))


def classify_disruption_type(text: str | None) -> str | None:
    if not text:
        return None
    for label, pattern in _DISRUPTION_TYPE_PATTERNS:
        if pattern.search(text):
            return label
    return "physical_disruption" if is_disruption_text(text) else None


def _snippet(text: str | None, *, radius: int = 80) -> str | None:
    if not text:
        return None
    match = _DISRUPTION_RE.search(text)
    if not match:
        return text.strip()[:160] or None
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return " ".join(text[start:end].split())


def fetch_disruption_filings(
    tickers: Iterable[str],
    *,
    filing_date_gte: str | None = None,
    filing_date_lte: str | None = None,
    api_key: str | None = None,
    limit_per_ticker: int = 100,
    enrich_disclosures: bool = True,
) -> list[DisruptionEvent]:
    """Pull Massive 8-K text and keep disruption-like filings."""
    key = api_key or _get_api_key()
    if not key:
        raise SystemExit(
            "missing MASSIVE_API_KEY / MASSIVE_APP_KEY (or POLYGON_API_KEY): "
            "required to fetch 8-K filings from Massive"
        )

    from massive import RESTClient

    client = RESTClient(api_key=key)
    events: list[DisruptionEvent] = []
    tickers_u = sorted({t.strip().upper() for t in tickers if t and t.strip()})

    for ticker in tickers_u:
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
            if not is_disruption_text(items_text):
                continue
            filing_date = getattr(filing, "filing_date", None)
            if not filing_date:
                continue
            fd = str(filing_date)[:10]
            text = str(items_text or "")
            events.append(
                DisruptionEvent(
                    ticker=ticker,
                    filing_date=fd,
                    accession_number=getattr(filing, "accession_number", None),
                    filing_url=getattr(filing, "filing_url", None),
                    form_type=getattr(filing, "form_type", None),
                    trade_date=resolve_trade_date(fd, None),
                    items_text=text[:4000] if text else None,
                    disruption_type=classify_disruption_type(text),
                    match_snippet=_snippet(text),
                    source="8k_text",
                )
            )

    if enrich_disclosures:
        disclosures = fetch_8k_disclosures(
            tickers_u,
            filing_date_gte=filing_date_gte,
            filing_date_lte=filing_date_lte,
            api_key=key,
        )
        events = _merge_disclosure_hits(events, disclosures, tickers_u)
        events = _attach_disclosures(events, disclosures)

    # De-dupe by ticker + accession (or filing_date if accession missing).
    events = _dedupe_events(events)
    logger.info("[Massive] found %d disruption filing(s)", len(events))
    return events


def _disclosure_to_event(ticker: str, row: dict) -> DisruptionEvent | None:
    supporting = row.get("supporting_text") or ""
    if not is_disruption_text(supporting):
        return None
    filing_date = str(row.get("filing_date") or "")[:10]
    if not filing_date:
        return None
    return DisruptionEvent(
        ticker=ticker,
        filing_date=filing_date,
        accession_number=row.get("accession_number"),
        trade_date=resolve_trade_date(filing_date, None),
        primary_category=row.get("primary_category"),
        secondary_category=row.get("secondary_category"),
        tertiary_category=row.get("tertiary_category"),
        supporting_text=supporting,
        disruption_type=classify_disruption_type(supporting),
        match_snippet=_snippet(supporting),
        source="disclosure",
    )


def _merge_disclosure_hits(
    events: list[DisruptionEvent],
    disclosures: list[dict],
    tickers: list[str],
) -> list[DisruptionEvent]:
    """Add disruption events found only in disclosure supporting_text."""
    existing = {
        (e.ticker, e.accession_number or e.filing_date)
        for e in events
    }
    out = list(events)
    for row in disclosures:
        row_tickers = row.get("tickers") or []
        if isinstance(row_tickers, str):
            row_tickers = [row_tickers]
        for raw in row_tickers:
            ticker = str(raw).upper()
            if ticker not in tickers:
                continue
            event = _disclosure_to_event(ticker, row)
            if event is None:
                continue
            key = (event.ticker, event.accession_number or event.filing_date)
            if key in existing:
                continue
            existing.add(key)
            out.append(event)
    return out


def _dedupe_events(events: list[DisruptionEvent]) -> list[DisruptionEvent]:
    best: dict[tuple[str, str], DisruptionEvent] = {}
    for event in events:
        key = (event.ticker, event.accession_number or event.filing_date)
        prev = best.get(key)
        if prev is None:
            best[key] = event
            continue
        # Prefer rows that already carry taxonomy / longer text.
        prev_score = len(prev.supporting_text or "") + len(prev.items_text or "")
        new_score = len(event.supporting_text or "") + len(event.items_text or "")
        if new_score >= prev_score:
            best[key] = event
    return sorted(best.values(), key=lambda e: (e.filing_date, e.ticker))


def _attach_disclosures(
    events: list[DisruptionEvent],
    disclosures: list[dict],
    *,
    match_window_days: int = 2,
) -> list[DisruptionEvent]:
    by_ticker: dict[str, list[dict]] = {}
    for row in disclosures:
        tickers = row.get("tickers") or []
        if isinstance(tickers, str):
            tickers = [tickers]
        for t in tickers:
            by_ticker.setdefault(str(t).upper(), []).append(row)

    out: list[DisruptionEvent] = []
    for event in events:
        filing = date.fromisoformat(event.filing_date)
        best = None
        best_score = -10**9
        for row in by_ticker.get(event.ticker, []):
            try:
                d = date.fromisoformat(str(row.get("filing_date"))[:10])
            except (TypeError, ValueError):
                continue
            if abs((d - filing).days) > match_window_days:
                continue
            if (
                event.accession_number
                and row.get("accession_number")
                and row.get("accession_number") != event.accession_number
            ):
                # Still allow if dates match closely; prefer same accession.
                score = -5
            else:
                score = 0
            if event.accession_number and row.get("accession_number") == event.accession_number:
                score += 50
            tertiary = (row.get("tertiary_category") or "").lower()
            if tertiary in _DISRUPTION_TERTIARY:
                score += 10
            supporting = row.get("supporting_text") or ""
            if is_disruption_text(supporting):
                score += 30
            if score > best_score:
                best_score = score
                best = row
        if best is None:
            out.append(event)
            continue
        supporting = best.get("supporting_text")
        blob = " ".join(
            x for x in (event.items_text, supporting, event.match_snippet) if x
        )
        out.append(
            DisruptionEvent(
                ticker=event.ticker,
                filing_date=event.filing_date,
                accession_number=event.accession_number or best.get("accession_number"),
                filing_url=event.filing_url,
                form_type=event.form_type,
                trade_date=event.trade_date,
                items_text=event.items_text,
                primary_category=best.get("primary_category"),
                secondary_category=best.get("secondary_category"),
                tertiary_category=best.get("tertiary_category"),
                supporting_text=supporting,
                disruption_type=classify_disruption_type(blob) or event.disruption_type,
                match_snippet=_snippet(blob) or event.match_snippet,
                facility_name=event.facility_name,
                site_lat=event.site_lat,
                site_lon=event.site_lon,
                has_site=event.has_site,
                has_satellite_coverage=event.has_satellite_coverage,
                anomaly_detected=event.anomaly_detected,
                anomaly_persist_days=event.anomaly_persist_days,
                facility_group=event.facility_group,
                source=event.source if "disclosure" in event.source else f"{event.source}+disclosure",
                extras={
                    **event.extras,
                    "disclosure_accession": best.get("accession_number"),
                },
            )
        )
    return out


def apply_site_map(
    events: list[DisruptionEvent],
    sites: dict[str, dict[str, Any]],
) -> list[DisruptionEvent]:
    """Attach lat/lon (and optional facility_name) from a ticker→site map."""
    out: list[DisruptionEvent] = []
    for event in events:
        site = sites.get(event.ticker.upper()) or sites.get(event.ticker)
        if not site:
            out.append(event)
            continue
        lat = site.get("lat", site.get("site_lat"))
        lon = site.get("lon", site.get("site_lon"))
        try:
            lat_f = float(lat) if lat is not None else None
            lon_f = float(lon) if lon is not None else None
        except (TypeError, ValueError):
            lat_f, lon_f = None, None
        row = event.to_dict()
        row.update({
            "facility_name": site.get("facility_name") or event.facility_name,
            "site_lat": lat_f,
            "site_lon": lon_f,
            "has_site": lat_f is not None and lon_f is not None,
        })
        out.append(DisruptionEvent.from_dict(row))
    return out


def load_site_map(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"site map not found: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "sites" in payload:
        payload = payload["sites"]
    if not isinstance(payload, dict):
        raise SystemExit("site map must be a JSON object of ticker → {lat, lon, ...}")
    return {str(k).upper(): v for k, v in payload.items()}


def save_disruption_events(
    events: list[DisruptionEvent] | list[dict[str, Any]],
    path: str | Path,
    *,
    persist_days_threshold: int = 3,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        e.to_dict() if isinstance(e, DisruptionEvent) else dict(e)
        for e in events
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "persist_days_threshold": persist_days_threshold,
        "count": len(rows),
        "events": rows,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def load_disruption_events(path: str | Path) -> list[DisruptionEvent]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("events", payload if isinstance(payload, list) else [])
    return [DisruptionEvent.from_dict(r) for r in rows]
