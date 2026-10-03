"""Extract place hints from disruption 8-K text and geocode via OpenStreetMap.

Nominatim is free (no API key) but rate-limited (~1 req/s). Results are cached
under ``data/geocode_cache.json`` so re-runs do not re-hit the network.

Manual ``--sites`` maps still win when present; this fills gaps automatically.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from webull_bt.logging_utils import get_logger

logger = get_logger("facility_geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "GQHacks-facility-disruption/0.1 (research; contact: admin@gqhacks.dev)"

_US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_US_STATE_NAMES = "|".join(sorted(_US_STATES.keys(), key=len, reverse=True))
_US_STATE_ABBR = "|".join(sorted(set(_US_STATES.values()), key=len, reverse=True))

# "in Belle Chasse, Louisiana" / "in Midland, MI" / "in Böhlen, Germany"
_IN_CITY_STATE = re.compile(
    rf"""
    \bin\s+
    (?P<city>[A-Z][A-Za-z .'\-]{{1,40}}?)
    ,\s*
    (?P<region>
        (?:{_US_STATE_NAMES})
      | (?:{_US_STATE_ABBR})
      | [A-Z][A-Za-z .'\-]{{2,40}}
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# "Sinton Texas Flat Roll…" / "Gary Indiana Works"
_CITY_STATE_RUNON = re.compile(
    rf"""
    \b
    (?P<city>[A-Z][A-Za-z .'\-]{{2,30}}?)
    \s+
    (?P<region>{_US_STATE_NAMES}|{_US_STATE_ABBR})
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Named industrial sites often appear before "in City"
_FACILITY_NAME = re.compile(
    r"""
    \b(
        [A-Z][A-Za-z0-9 .'\-/]{2,60}?
        (?:Refinery|Mill|Plant|Works|Facility|Smelter|Foundry|Terminal|Complex)
    )\b
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class GeocodeHit:
    query: str
    lat: float
    lon: float
    display_name: str
    importance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "lat": self.lat,
            "lon": self.lon,
            "display_name": self.display_name,
            "importance": self.importance,
        }


def _normalize_region(region: str) -> str:
    key = region.strip().lower()
    if key in _US_STATES:
        return _US_STATES[key]
    if len(region.strip()) == 2:
        return region.strip().upper()
    return region.strip().title()


_STOP_CITIES = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "its", "their", "our", "total", "addition", "part", "item", "section",
    "united", "steel", "company", "corporation", "these", "those", "this",
    "that", "with", "from", "into", "over", "under", "after", "before",
    "incorporated", "general", "reference", "slides", "assurance",
    "individually", "noncash", "non-cash", "weak", "presented", "conditions",
    "participants", "credited", "alternatives", "account", "balances",
    "information", "material", "complete", "report", "amended", "tender",
    "some", "any", "each", "such", "other", "certain", "including",
})

_COUNTRIES = frozenset({
    "germany", "france", "italy", "spain", "uk", "united kingdom", "canada",
    "mexico", "brazil", "china", "japan", "india", "australia", "netherlands",
    "belgium", "poland", "austria", "switzerland", "sweden", "norway",
    "indonesia", "chile", "peru", "argentina", "korea", "south korea",
})


def _looks_like_place(city: str, region: str) -> bool:
    city_l = city.strip().lower()
    region_l = region.strip().lower()
    if city_l in _STOP_CITIES or len(city_l) < 3:
        return False
    if any(ch.isdigit() for ch in city):
        return False
    if region_l in _US_STATES or region_l.upper() in _US_STATES.values():
        return True
    if region_l in _COUNTRIES:
        return True
    # Allow Title-Case multi-word regions that aren't prose fragments.
    if "-" in region or "." in region or len(region.split()) > 3:
        return False
    return region[:1].isupper() and region_l not in _STOP_CITIES


def extract_location_queries(text: str | None, *, limit: int = 5) -> list[str]:
    """Build ordered Nominatim queries from filing / press-release text."""
    if not text:
        return []
    # Collapse whitespace for regex friendliness.
    blob = " ".join(text.replace("\u202f", " ").split())
    queries: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> None:
        q = " ".join(q.split()).strip(" ,.;:-")
        key = q.lower()
        if len(q) < 5 or key in seen:
            return
        if any(bad in key for bad in ("cost", "payment", "assurance", "item ", "section")):
            return
        seen.add(key)
        queries.append(q)

    for match in _IN_CITY_STATE.finditer(blob):
        city = match.group("city").strip(" ,")
        region_raw = match.group("region").strip(" ,.-")
        # Truncate region at sentence / list noise.
        region_raw = re.split(r"[.\-]| and ", region_raw, maxsplit=1)[0].strip()
        if not _looks_like_place(city, region_raw):
            continue
        region = _normalize_region(region_raw)
        start = max(0, match.start() - 80)
        window = blob[start:match.end()]
        fac = _FACILITY_NAME.search(window)
        if fac:
            _add(f"{fac.group(1)}, {city}, {region}")
        _add(f"{city}, {region}")

    for match in _CITY_STATE_RUNON.finditer(blob):
        city = match.group("city").strip(" ,")
        region_raw = match.group("region")
        if not _looks_like_place(city, region_raw):
            continue
        region = _normalize_region(region_raw)
        end = match.end()
        tail = blob[match.start(): min(len(blob), end + 40)]
        fac = _FACILITY_NAME.search(tail)
        if fac:
            _add(f"{fac.group(1)}, {city}, {region}")
        _add(f"{city}, {region}")

    for fac in _FACILITY_NAME.finditer(blob):
        name = fac.group(1).strip()
        if name.lower().split()[0] in _STOP_CITIES:
            continue
        _add(name)

    return queries[:limit]


class NominatimGeocoder:
    """Cached OpenStreetMap Nominatim client (1 request/second)."""

    def __init__(
        self,
        cache_path: Path | None = None,
        *,
        min_interval_s: float = 1.1,
        timeout_s: float = 30.0,
    ):
        self.cache_path = cache_path
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self._cache: dict[str, dict[str, Any] | None] = {}
        self._last_request = 0.0
        if cache_path and cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._cache = {}

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def geocode(self, query: str) -> GeocodeHit | None:
        key = query.strip().lower()
        if key in self._cache:
            row = self._cache[key]
            if not row:
                return None
            return GeocodeHit(
                query=query,
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                display_name=str(row.get("display_name") or ""),
                importance=float(row.get("importance") or 0.0),
            )

        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)

        params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "limit": 1,
        })
        url = f"{NOMINATIM_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        self._last_request = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("[Geocode] failed for %r (%s)", query, exc)
            self._cache[key] = None
            self._save_cache()
            return None

        if not payload:
            logger.info("[Geocode] no hit for %r", query)
            self._cache[key] = None
            self._save_cache()
            return None

        top = payload[0]
        hit = GeocodeHit(
            query=query,
            lat=float(top["lat"]),
            lon=float(top["lon"]),
            display_name=str(top.get("display_name") or ""),
            importance=float(top.get("importance") or 0.0),
        )
        self._cache[key] = hit.to_dict()
        self._save_cache()
        logger.info("[Geocode] %r → %.5f,%.5f (%s)", query, hit.lat, hit.lon, hit.display_name[:80])
        return hit

    def geocode_first(self, queries: Iterable[str]) -> GeocodeHit | None:
        for query in queries:
            hit = self.geocode(query)
            if hit is not None:
                return hit
        return None


def geocode_event_text(
    geocoder: NominatimGeocoder,
    *texts: str | None,
) -> GeocodeHit | None:
    blob = "\n".join(t for t in texts if t)
    queries = extract_location_queries(blob)
    if not queries:
        return None
    return geocoder.geocode_first(queries)


def apply_geocode_to_events(
    events: list[Any],
    *,
    geocoder: NominatimGeocoder,
    only_missing: bool = True,
) -> list[Any]:
    """Fill ``site_lat`` / ``site_lon`` on DisruptionEvent-like objects."""
    from massive_disruptions import DisruptionEvent

    out: list[DisruptionEvent] = []
    for event in events:
        row = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        if only_missing and row.get("site_lat") is not None and row.get("site_lon") is not None:
            out.append(DisruptionEvent.from_dict(row))
            continue
        hit = geocode_event_text(
            geocoder,
            row.get("items_text"),
            row.get("supporting_text"),
            row.get("match_snippet"),
            row.get("facility_name"),
        )
        if hit is None:
            out.append(DisruptionEvent.from_dict(row))
            continue
        row.update({
            "facility_name": row.get("facility_name") or hit.query,
            "site_lat": hit.lat,
            "site_lon": hit.lon,
            "has_site": True,
            "extras": {
                **(row.get("extras") or {}),
                "geocode_query": hit.query,
                "geocode_display_name": hit.display_name,
                "geocode_source": "nominatim",
            },
        })
        out.append(DisruptionEvent.from_dict(row))
    return out
