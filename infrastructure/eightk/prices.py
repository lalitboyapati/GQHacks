"""Daily price series with a trading calendar derived from the data itself.

Taking the calendar from the bars that exist avoids maintaining a holiday
table and, more importantly, avoids silently fabricating a session the
exchange never held — which would let a backtest "trade" on a market
holiday and book a fill that was never available.
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from eightk.massive_src import Bar

logger = logging.getLogger(__name__)


@dataclass
class PriceSeries:
    """Daily bars for one symbol, indexed for event-window lookups."""

    symbol: str
    bars: list[Bar]

    def __post_init__(self):
        self.bars = sorted(self.bars, key=lambda b: b.day)
        self._days: list[date] = [b.day for b in self.bars]
        self._by_day: dict[date, Bar] = {b.day: b for b in self.bars}

    def __len__(self) -> int:
        return len(self.bars)

    @property
    def days(self) -> list[date]:
        return self._days

    def get(self, day: date) -> Bar | None:
        return self._by_day.get(day)

    def index_of(self, day: date) -> int | None:
        """Position of ``day`` in the series, or ``None`` if not a session."""
        pos = bisect.bisect_left(self._days, day)
        if pos < len(self._days) and self._days[pos] == day:
            return pos
        return None

    def next_session(self, day: date, inclusive: bool = False) -> date | None:
        """First trading day at or after ``day`` (strictly after by default)."""
        pos = bisect.bisect_left(self._days, day) if inclusive else bisect.bisect_right(self._days, day)
        return self._days[pos] if pos < len(self._days) else None

    def prev_session(self, day: date, inclusive: bool = False) -> date | None:
        """Last trading day at or before ``day`` (strictly before by default)."""
        pos = (bisect.bisect_right(self._days, day) if inclusive
               else bisect.bisect_left(self._days, day)) - 1
        return self._days[pos] if pos >= 0 else None

    def shift(self, day: date, sessions: int) -> date | None:
        """Trading day ``sessions`` steps from ``day`` (negative looks back)."""
        pos = self.index_of(day)
        if pos is None:
            anchor = self.next_session(day, inclusive=True) if sessions >= 0 else self.prev_session(day, inclusive=True)
            if anchor is None:
                return None
            pos = self.index_of(anchor)
            if pos is None:
                return None
        target = pos + sessions
        if 0 <= target < len(self._days):
            return self._days[target]
        return None

    def closes_before(self, day: date, count: int) -> list[float]:
        """The ``count`` closes strictly before ``day``, oldest first.

        Used for pre-event realized volatility, so the window must not
        include the event bar itself.
        """
        pos = bisect.bisect_left(self._days, day)
        start = max(0, pos - count)
        return [b.close for b in self.bars[start:pos]]

    def window_returns(self, start: date, end: date) -> float | None:
        """Close-to-close simple return between two sessions."""
        a, b = self.get(start), self.get(end)
        if a is None or b is None or a.close <= 0:
            return None
        return b.close / a.close - 1.0


def load_series(massive, symbol: str, start: str, end: str, pad_days: int = 90) -> PriceSeries:
    """Fetch a padded daily series so pre-event windows are always covered."""
    start_date = date.fromisoformat(start) - timedelta(days=pad_days)
    end_date = date.fromisoformat(end) + timedelta(days=pad_days)
    bars = massive.daily_bars(symbol, start_date.isoformat(), end_date.isoformat())
    return PriceSeries(symbol=symbol.upper(), bars=bars)
