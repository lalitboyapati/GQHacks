"""NASA FIRMS thermal hotspot client for facility-disruption labeling.

Uses the free Area CSV API (requires ``FIRMS_MAP_KEY`` / ``MAP_KEY``)::

    GET /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{DATE}

VIIRS observes each location ~twice per day at 375 m resolution. Latency is
typically a few hours after a satellite pass. Industrial combustion can be
misclassified or missed — algorithms are tuned for wildfire; treat labels as
noisy external evidence, not ground truth.

Docs: https://firms.modaps.eosdis.nasa.gov/api/area/
"""

from __future__ import annotations

import csv
import io
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from webull_bt.logging_utils import get_logger

logger = get_logger("firms")

FIRMS_AREA_CSV = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
DEFAULT_SOURCE = "VIIRS_SNPP_NRT"
# ~5 km half-box at mid-latitudes (degrees).
DEFAULT_HALF_BOX_DEG = 0.05


@dataclass(frozen=True)
class FirmsHotspot:
    latitude: float
    longitude: float
    acq_date: str
    acq_time: str | None = None
    brightness: float | None = None
    frp: float | None = None
    confidence: str | None = None
    satellite: str | None = None
    daynight: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "FirmsHotspot | None":
        try:
            lat = float(row.get("latitude") or row.get("Latitude") or "")
            lon = float(row.get("longitude") or row.get("Longitude") or "")
            acq = (row.get("acq_date") or row.get("Acq_Date") or "").strip()
        except (TypeError, ValueError):
            return None
        if not acq:
            return None

        def _opt_float(key: str) -> float | None:
            raw = row.get(key)
            if raw is None or raw == "":
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        return cls(
            latitude=lat,
            longitude=lon,
            acq_date=acq[:10],
            acq_time=(row.get("acq_time") or row.get("Acq_Time") or None),
            brightness=_opt_float("brightness") or _opt_float("bright_ti4"),
            frp=_opt_float("frp") or _opt_float("FRP"),
            confidence=(row.get("confidence") or row.get("Confidence") or None),
            satellite=(row.get("satellite") or row.get("Satellite") or None),
            daynight=(row.get("daynight") or row.get("DayNight") or None),
        )


def _get_map_key() -> str | None:
    return (
        os.environ.get("FIRMS_MAP_KEY")
        or os.environ.get("MAP_KEY")
        or os.environ.get("NASA_FIRMS_MAP_KEY")
        or ""
    ).strip() or None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bbox_around(
    lat: float,
    lon: float,
    *,
    half_box_deg: float = DEFAULT_HALF_BOX_DEG,
) -> str:
    """Return FIRMS ``west,south,east,north`` string."""
    west = max(-180.0, lon - half_box_deg)
    east = min(180.0, lon + half_box_deg)
    south = max(-90.0, lat - half_box_deg)
    north = min(90.0, lat + half_box_deg)
    return f"{west:.5f},{south:.5f},{east:.5f},{north:.5f}"


def parse_firms_csv(text: str) -> list[FirmsHotspot]:
    """Parse FIRMS area CSV body into hotspots."""
    text = (text or "").strip()
    if not text or text.lower().startswith("invalid") or text.lower().startswith("error"):
        return []
    # Some error bodies are plain text without CSV headers.
    first = text.splitlines()[0].lower() if text else ""
    if "latitude" not in first:
        logger.warning("[FIRMS] non-CSV response: %s", text[:160])
        return []
    reader = csv.DictReader(io.StringIO(text))
    out: list[FirmsHotspot] = []
    for row in reader:
        spot = FirmsHotspot.from_row(row)
        if spot is not None:
            out.append(spot)
    return out


class FirmsClient:
    """Thin HTTP client for NASA FIRMS area queries."""

    def __init__(
        self,
        map_key: str | None = None,
        *,
        source: str = DEFAULT_SOURCE,
        timeout_s: float = 60.0,
    ):
        self.map_key = (map_key or _get_map_key() or "").strip()
        if not self.map_key:
            raise SystemExit(
                "missing FIRMS_MAP_KEY (or MAP_KEY): get a free key at "
                "https://firms.modaps.eosdis.nasa.gov/api/map_key/"
            )
        self.source = source
        self.timeout_s = timeout_s
        self._cache: dict[str, list[FirmsHotspot]] = {}

    def area_url(
        self,
        *,
        area: str,
        day_range: int,
        start: date | None = None,
    ) -> str:
        if not 1 <= day_range <= 5:
            raise ValueError("FIRMS day_range must be 1..5")
        base = f"{FIRMS_AREA_CSV}/{self.map_key}/{self.source}/{area}/{day_range}"
        if start is not None:
            return f"{base}/{start.isoformat()}"
        return base

    def fetch_area(
        self,
        *,
        area: str,
        day_range: int = 5,
        start: date | None = None,
    ) -> list[FirmsHotspot]:
        url = self.area_url(area=area, day_range=day_range, start=start)
        if url in self._cache:
            return self._cache[url]
        logger.info("[FIRMS] GET area=%s range=%s start=%s", area, day_range, start)
        req = Request(url, headers={"User-Agent": "GQHacks-facility-disruption/0.1"})
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            logger.warning("[FIRMS] HTTP %s for %s", exc.code, url)
            return []
        except URLError as exc:
            logger.warning("[FIRMS] network error (%s)", exc)
            return []
        spots = parse_firms_csv(body)
        self._cache[url] = spots
        return spots

    def hotspots_near(
        self,
        lat: float,
        lon: float,
        *,
        start: date,
        days: int,
        radius_km: float = 5.0,
        half_box_deg: float | None = None,
    ) -> list[FirmsHotspot]:
        """Hotspots within ``radius_km`` of (lat, lon) over ``days`` from ``start``."""
        if days < 1:
            return []
        box = half_box_deg if half_box_deg is not None else max(
            DEFAULT_HALF_BOX_DEG, radius_km / 111.0
        )
        area = bbox_around(lat, lon, half_box_deg=box)
        collected: list[FirmsHotspot] = []
        # API allows at most 5 days per call — chunk the window.
        cursor = start
        remaining = days
        while remaining > 0:
            chunk = min(5, remaining)
            collected.extend(
                self.fetch_area(area=area, day_range=chunk, start=cursor)
            )
            cursor = cursor + timedelta(days=chunk)
            remaining -= chunk
        return [
            h for h in collected
            if haversine_km(lat, lon, h.latitude, h.longitude) <= radius_km
        ]


def summarize_anomaly(
    hotspots: Iterable[FirmsHotspot],
    *,
    persist_days: int = 3,
) -> dict[str, Any]:
    """Compute anomaly_detected / anomaly_persist_days from hotspot dates."""
    spots = list(hotspots)
    days = sorted({h.acq_date for h in spots if h.acq_date})
    detected = bool(days)
    # Persistence = number of distinct calendar days with ≥1 detection.
    persist = len(days) if detected else 0
    return {
        "anomaly_detected": detected,
        "anomaly_persist_days": persist,
        "anomaly_dates": days,
        "hotspot_count": len(spots),
        "persist_days_threshold": persist_days,
    }


def label_site_with_firms(
    client: FirmsClient,
    *,
    site_lat: float,
    site_lon: float,
    filing_date: str,
    persist_days: int = 3,
    lookback_days: int = 0,
    radius_km: float = 5.0,
) -> dict[str, Any]:
    """Query FIRMS around a site from filing_date (optional lookback) forward.

    Window length is ``lookback_days + persist_days`` so a spike on day 0 and
    clear days afterward still scores as brief when distinct hit-days < threshold.
    """
    start = date.fromisoformat(filing_date[:10]) - timedelta(days=max(0, lookback_days))
    window = max(1, lookback_days + persist_days)
    spots = client.hotspots_near(
        site_lat,
        site_lon,
        start=start,
        days=window,
        radius_km=radius_km,
    )
    # Count only dates on/after the filing date for persistence of the event.
    filing = date.fromisoformat(filing_date[:10])
    post = [h for h in spots if date.fromisoformat(h.acq_date) >= filing]
    summary = summarize_anomaly(post, persist_days=persist_days)
    summary["hotspot_count"] = len(post)
    summary["has_satellite_coverage"] = True
    summary["firms_source"] = client.source
    summary["query_start"] = start.isoformat()
    summary["query_days"] = window
    return summary
