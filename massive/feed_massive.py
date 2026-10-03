"""Backtrader Data Feed powered by Massive (Polygon.io).

Allows using Massive historical data directly in Backtrader:
    cerebro = bt.Cerebro()
    cerebro.adddata(
        MassiveData(
            dataname="AAPL",
            timespan="day",
            from_date="2026-01-01",
            to_date="2026-10-02"
        )
    )
"""

from __future__ import annotations

import queue
from datetime import datetime, timezone
from typing import Any

import backtrader as bt
from backtrader.utils import date2num

from massive.client import MassiveClient


class MassiveData(bt.feed.DataBase):
    """Backtrader data feed for Massive (Polygon.io) historical aggregate bars."""

    params = (
        ("client", None),
        ("multiplier", 1),
        ("timespan", "day"),
        ("from_date", "2026-01-01"),
        ("to_date", "2026-10-02"),
        ("adjusted", True),
    )

    def __init__(self):
        super().__init__()
        self._client: MassiveClient = self.p.client or MassiveClient()
        self._q: queue.Queue = queue.Queue()

    def start(self):
        super().start()
        with self._q.mutex:
            self._q.queue.clear()

        # Fetch historical bars
        bars = self._client.get_bars(
            ticker=self.p.dataname,
            multiplier=self.p.multiplier,
            timespan=self.p.timespan,
            from_date=self.p.from_date,
            to_date=self.p.to_date,
            adjusted=self.p.adjusted,
        )

        for b in bars:
            # Timestamp in ms -> UTC naive datetime
            dt = datetime.fromtimestamp(b["t"] / 1000.0, tz=timezone.utc).replace(tzinfo=None)
            self._q.put({
                "dt": dt,
                "open": float(b["o"]),
                "high": float(b["h"]),
                "low": float(b["l"]),
                "close": float(b["c"]),
                "volume": float(b.get("v", 0.0)),
                "openinterest": 0.0,
            })

    def _load(self):
        if self._q.empty():
            return False

        bar = self._q.get()
        self.lines.datetime[0] = date2num(bar["dt"])
        self.lines.open[0] = bar["open"]
        self.lines.high[0] = bar["high"]
        self.lines.low[0] = bar["low"]
        self.lines.close[0] = bar["close"]
        self.lines.volume[0] = bar["volume"]
        self.lines.openinterest[0] = bar["openinterest"]
        return True
