"""Scale session-based horizons to bar counts for a Webull timespan.

Strategies should express holds in **trading sessions** (or hours). This
module converts those horizons into bar counts so ``-t M5`` and ``-t D``
keep the same economic clock when capturing post-8-K market gaps.
"""

from __future__ import annotations

import math
import os
import re

# Regular-session length used for US equities (09:30–16:00 ET).
RTH_MINUTES = 390.0

# Approximate bars per RTH session for each Webull timespan.
_BARS_PER_SESSION: dict[str, float] = {
    "M1": RTH_MINUTES / 1.0,
    "M5": RTH_MINUTES / 5.0,
    "M15": RTH_MINUTES / 15.0,
    "M30": RTH_MINUTES / 30.0,
    "M60": RTH_MINUTES / 60.0,
    "M120": RTH_MINUTES / 120.0,
    "M240": RTH_MINUTES / 240.0,
    "D": 1.0,
    "W": 1.0 / 5.0,   # ~1 bar per week vs 5 sessions
    "M": 1.0 / 21.0,  # rough
    "Y": 1.0 / 252.0,
}

_TIMESPAN_RE = re.compile(r"^M(\d+)$", re.IGNORECASE)


def normalize_timespan(timespan: str | None) -> str:
    raw = (timespan or "").strip().upper()
    return raw or "D"


def resolve_timespan(
    timespan: str | None = None,
    *,
    env_var: str = "WEBULL_TIMESPAN",
) -> str:
    """Prefer an explicit timespan, else ``WEBULL_TIMESPAN``, else daily."""
    if timespan and str(timespan).strip():
        return normalize_timespan(timespan)
    return normalize_timespan(os.environ.get(env_var, "D"))


def bars_per_session(timespan: str | None) -> float:
    """How many bars equal one RTH session at this timespan."""
    key = normalize_timespan(timespan)
    if key in _BARS_PER_SESSION:
        return float(_BARS_PER_SESSION[key])
    match = _TIMESPAN_RE.match(key)
    if match:
        minutes = float(match.group(1))
        if minutes > 0:
            return RTH_MINUTES / minutes
    return 1.0


def sessions_to_bars(sessions: float, timespan: str | None) -> int:
    """Convert a session horizon to a whole bar count (minimum 1 if sessions > 0)."""
    if sessions <= 0:
        return 0
    bars = sessions * bars_per_session(timespan)
    return max(1, int(math.ceil(bars)))


def hours_to_bars(hours: float, timespan: str | None) -> int:
    """Convert RTH hours to bars (e.g. 2h on M5 → 24 bars)."""
    if hours <= 0:
        return 0
    key = normalize_timespan(timespan)
    if key in {"D", "W", "M", "Y"}:
        # Sub-session horizons collapse to a single daily bar.
        return 1 if hours > 0 else 0
    minutes = hours * 60.0
    bps = bars_per_session(key)
    bar_minutes = RTH_MINUTES / bps if bps > 0 else RTH_MINUTES
    return max(1, int(math.ceil(minutes / bar_minutes)))


def scale_hold_params(
    *,
    timespan: str | None,
    min_hold_sessions: float = 2.0,
    max_hold_sessions: float = 10.0,
    atr_sessions: float = 14.0,
    min_hold_bars: int | None = None,
    max_hold_bars: int | None = None,
    atr_period: int | None = None,
    max_hold_hours: float = 0.0,
) -> dict[str, int | str | float]:
    """Resolve effective bar-based knobs for a strategy.

    Explicit ``*_bars`` / ``atr_period`` overrides (when > 0) win. Otherwise
    session horizons are scaled to the active timespan. Optional
    ``max_hold_hours`` caps the scaled max hold on intraday feeds so a
    post-8-K gap trade can be limited to the first few hours.
    """
    ts = resolve_timespan(timespan)
    bps = bars_per_session(ts)

    min_bars = (
        int(min_hold_bars)
        if min_hold_bars is not None and int(min_hold_bars) > 0
        else sessions_to_bars(min_hold_sessions, ts)
    )
    max_bars = (
        int(max_hold_bars)
        if max_hold_bars is not None and int(max_hold_bars) > 0
        else sessions_to_bars(max_hold_sessions, ts)
    )
    if max_hold_hours and max_hold_hours > 0:
        hour_cap = hours_to_bars(max_hold_hours, ts)
        max_bars = min(max_bars, hour_cap) if max_bars > 0 else hour_cap

    if max_bars > 0 and min_bars > max_bars:
        min_bars = max_bars

    atr = (
        int(atr_period)
        if atr_period is not None and int(atr_period) > 0
        else sessions_to_bars(atr_sessions, ts)
    )

    return {
        "timespan": ts,
        "bars_per_session": bps,
        "min_hold_bars": int(min_bars),
        "max_hold_bars": int(max_bars),
        "atr_period": int(atr),
        "min_hold_sessions": float(min_hold_sessions),
        "max_hold_sessions": float(max_hold_sessions),
        "atr_sessions": float(atr_sessions),
        "max_hold_hours": float(max_hold_hours or 0.0),
    }
