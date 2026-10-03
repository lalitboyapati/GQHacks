#!/usr/bin/env python
"""Fetch Massive disruption 8-Ks and optionally label them with NASA FIRMS.

Examples
--------
    # Massive + auto geocode (OpenStreetMap Nominatim, no key) + FIRMS
    python tracks/physical_facility_disruption/scripts/fetch_disruption_events.py \\
        --symbols STLD,PSX,DOW,FCX --gte 2019-01-01 --firms

    # Optional manual site overrides still win when provided
    python tracks/physical_facility_disruption/scripts/fetch_disruption_events.py \\
        --symbols X --sites tracks/physical_facility_disruption/data/sites.example.json --firms
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

TRACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRACK_ROOT.parents[1]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))
sys.path.insert(0, str(TRACK_ROOT))

from facility_geocode import NominatimGeocoder, apply_geocode_to_events  # noqa: E402
from facility_groups import label_event  # noqa: E402
from massive_disruptions import (  # noqa: E402
    DisruptionEvent,
    apply_site_map,
    fetch_disruption_filings,
    load_site_map,
    save_disruption_events,
)
from webull_bt.firms import FirmsClient, label_site_with_firms  # noqa: E402
from webull_bt.logging_utils import get_logger, setup_logging  # noqa: E402

logger = get_logger("fetch_disruption_events")


def _enrich_firms(
    events: list[DisruptionEvent],
    *,
    persist_days: int,
    radius_km: float,
    source: str,
) -> list[DisruptionEvent]:
    client = FirmsClient(source=source)
    out: list[DisruptionEvent] = []
    for event in events:
        row = event.to_dict()
        if event.site_lat is None or event.site_lon is None:
            row["has_satellite_coverage"] = False
            labeled = label_event(row, persist_days=persist_days)
            out.append(DisruptionEvent.from_dict(labeled))
            continue
        try:
            summary = label_site_with_firms(
                client,
                site_lat=float(event.site_lat),
                site_lon=float(event.site_lon),
                filing_date=event.filing_date,
                persist_days=persist_days,
                radius_km=radius_km,
            )
        except Exception:
            logger.exception(
                "[FIRMS] failed for %s %s", event.ticker, event.accession_number
            )
            row["has_satellite_coverage"] = False
            labeled = label_event(row, persist_days=persist_days)
            out.append(DisruptionEvent.from_dict(labeled))
            continue
        row.update({
            "has_site": True,
            "has_satellite_coverage": True,
            "anomaly_detected": summary["anomaly_detected"],
            "anomaly_persist_days": summary["anomaly_persist_days"],
            "extras": {
                **event.extras,
                "anomaly_dates": summary.get("anomaly_dates"),
                "hotspot_count": summary.get("hotspot_count"),
                "firms_source": summary.get("firms_source"),
            },
        })
        labeled = label_event(row, persist_days=persist_days)
        out.append(DisruptionEvent.from_dict(labeled))
        logger.info(
            "  %s %s group=%s detected=%s persist_days=%s hotspots=%s",
            event.ticker,
            event.filing_date,
            labeled.get("facility_group"),
            summary["anomaly_detected"],
            summary["anomaly_persist_days"],
            summary.get("hotspot_count"),
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--symbols",
        default=os.environ.get("WEBULL_SYMBOLS", "X,NUE,CLF"),
        help="Comma-separated tickers (industrials with plants are a good start)",
    )
    parser.add_argument("--gte", default=os.environ.get("MASSIVE_FILING_DATE_GTE", "2022-01-01"))
    parser.add_argument("--lte", default=os.environ.get("MASSIVE_FILING_DATE_LTE", ""))
    parser.add_argument(
        "--out",
        default=str(TRACK_ROOT / "data" / "events" / "disruption_events.json"),
    )
    parser.add_argument(
        "--sites",
        default=os.environ.get("FACILITY_SITES", ""),
        help="Optional JSON map of ticker → {lat, lon}; overrides geocode when set",
    )
    parser.add_argument(
        "--geocode",
        action="store_true",
        default=True,
        help="Auto-geocode site from filing text via OpenStreetMap Nominatim (default on)",
    )
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="Skip Nominatim geocoding",
    )
    parser.add_argument(
        "--firms",
        action="store_true",
        help="Query NASA FIRMS for thermal persistence (needs FIRMS_MAP_KEY + coords)",
    )
    parser.add_argument("--persist-days", type=int, default=int(os.environ.get("FACILITY_PERSIST_DAYS", "3")))
    parser.add_argument("--radius-km", type=float, default=5.0)
    parser.add_argument(
        "--firms-source",
        default=os.environ.get("FIRMS_SOURCE", "VIIRS_SNPP_NRT"),
        help="FIRMS product source (NRT for recent; SP products for deep history)",
    )
    parser.add_argument("--no-disclosures", action="store_true")
    parser.add_argument("--limit", type=int, default=100, help="Massive filings limit per ticker")
    args = parser.parse_args()

    load_dotenv(INFRA_ROOT / "backtest" / ".env")
    load_dotenv(TRACK_ROOT / ".env", override=True)
    setup_logging()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    events = fetch_disruption_filings(
        symbols,
        filing_date_gte=args.gte or None,
        filing_date_lte=args.lte or None,
        limit_per_ticker=args.limit,
        enrich_disclosures=not args.no_disclosures,
    )

    sites = load_site_map(args.sites or None)
    if sites:
        events = apply_site_map(events, sites)
        logger.info("Applied site map (%d ticker(s))", len(sites))

    do_geocode = bool(args.geocode) and not bool(args.no_geocode)
    if do_geocode:
        cache = TRACK_ROOT / "data" / "geocode_cache.json"
        geocoder = NominatimGeocoder(cache_path=cache)
        before = sum(1 for e in events if e.site_lat is not None)
        events = apply_geocode_to_events(events, geocoder=geocoder, only_missing=True)
        after = sum(1 for e in events if e.site_lat is not None)
        logger.info("Geocoded sites: %d → %d event(s) with coordinates", before, after)

    if args.firms:
        events = _enrich_firms(
            events,
            persist_days=args.persist_days,
            radius_km=args.radius_km,
            source=args.firms_source,
        )
    else:
        events = [
            DisruptionEvent.from_dict(label_event(e.to_dict(), persist_days=args.persist_days))
            for e in events
        ]

    path = save_disruption_events(
        events, args.out, persist_days_threshold=args.persist_days
    )
    logger.info("Wrote %d disruption event(s) → %s", len(events), path)
    for event in events[:30]:
        logger.info(
            "  %s filing=%s type=%s site=(%s,%s) group=%s snippet=%s",
            event.ticker,
            event.filing_date,
            event.disruption_type or "n/a",
            event.site_lat,
            event.site_lon,
            event.facility_group or "n/a",
            (event.match_snippet or "")[:80],
        )
    if len(events) > 30:
        logger.info("  ... %d more", len(events) - 30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
