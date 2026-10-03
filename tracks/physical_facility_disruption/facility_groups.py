"""Assign treatment vs control from satellite / thermal anomaly fields.

Group A (``brief``): sell-premium candidates — no lasting anomaly.
Group B (``persistent``): control / skip — anomaly still on after persist_days.
``unknown``: missing site or sensor coverage — exclude from both arms.
"""

from __future__ import annotations

from typing import Any, Mapping


BRIEF = "brief"
PERSISTENT = "persistent"
UNKNOWN = "unknown"

VALID_GROUPS = frozenset({BRIEF, PERSISTENT, UNKNOWN})


def assign_facility_group(
    *,
    anomaly_detected: bool | None,
    anomaly_persist_days: int | None,
    persist_days: int = 3,
    has_site: bool = True,
    has_satellite_coverage: bool = True,
) -> str:
    """Map raw anomaly stats to ``brief`` | ``persistent`` | ``unknown``.

    Rules
    -----
    * No site or no satellite coverage → ``unknown``.
    * ``anomaly_detected`` is False / None with coverage → ``brief``
      (filing without a lasting thermal footprint).
    * Detected and ``anomaly_persist_days >= persist_days`` → ``persistent``.
    * Detected but clears sooner → ``brief``.
    """
    if persist_days < 1:
        raise ValueError("persist_days must be >= 1")

    if not has_site or not has_satellite_coverage:
        return UNKNOWN

    if anomaly_detected is None:
        return UNKNOWN

    if not anomaly_detected:
        return BRIEF

    days = 0 if anomaly_persist_days is None else int(anomaly_persist_days)
    if days < 0:
        return UNKNOWN
    if days >= persist_days:
        return PERSISTENT
    return BRIEF


def label_event(event: Mapping[str, Any], *, persist_days: int = 3) -> dict[str, Any]:
    """Return a shallow copy of ``event`` with ``facility_group`` filled."""
    row = dict(event)
    group = assign_facility_group(
        anomaly_detected=row.get("anomaly_detected"),
        anomaly_persist_days=row.get("anomaly_persist_days"),
        persist_days=persist_days,
        has_site=bool(row.get("has_site", row.get("site_lat") is not None)),
        has_satellite_coverage=bool(row.get("has_satellite_coverage", True)),
    )
    row["facility_group"] = group
    row["persist_days_threshold"] = persist_days
    return row


def partition_events(
    events: list[Mapping[str, Any]],
    *,
    persist_days: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Split events into brief / persistent / unknown lists."""
    out: dict[str, list[dict[str, Any]]] = {
        BRIEF: [],
        PERSISTENT: [],
        UNKNOWN: [],
    }
    for event in events:
        labeled = label_event(event, persist_days=persist_days)
        out[labeled["facility_group"]].append(labeled)
    return out


def tradeable_events(
    events: list[Mapping[str, Any]],
    *,
    persist_days: int = 3,
) -> list[dict[str, Any]]:
    """Group A only — candidates for covered call / cash-secured put."""
    return partition_events(events, persist_days=persist_days)[BRIEF]
