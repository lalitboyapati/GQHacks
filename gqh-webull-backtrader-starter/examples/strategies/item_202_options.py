"""Item 2.02 / earnings-results event strategy (options-impact proxy).

SEC Form 8-K **Item 2.02** discloses "Results of Operations and Financial
Condition" — the formal filing that accompanies scheduled earnings releases.
Options traders care about these events because:

  * Implied volatility typically rises into the scheduled print.
  * After the release, IV usually crushes while the stock gaps (realized move).
  * Post-earnings announcement drift (PEAD) is a durable directional edge
    that also informs whether long calls/puts or short straddles were favored.

This Webull/Backtrader starter only trades **equities**, so the strategy
implements a researched equity proxy for those options effects:

  **mode=momentum (default / PEAD)**
      After an Item 2.02 event, if the overnight gap is large vs ATR, buy
      (gap up) or sell-short (gap down) and hold for ``hold_bars`` sessions.
      Options analogy: directional long calls / long puts after the print.

  **mode=fade**
      Take the opposite side of the gap (mean reversion). Options analogy:
      short-straddle / short-strangle style fade when the initial move is
      expected to exhaust after IV crush.

Events come from the Massive API (8-K Item 2.02 text, optionally enriched
with Benzinga earnings schedule + EPS surprise). Set ``MASSIVE_API_KEY``
or point ``MASSIVE_EVENTS_CACHE`` at a JSON cache (a sample cache ships
under ``examples/data/``).
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import backtrader as bt

from webull_bt.logging_utils import get_logger
from webull_bt.massive_filings import (
    Item202Event,
    events_by_ticker,
    load_item_202_events,
)
from webull_bt.timeutils import to_market_tz


logger = get_logger("strategy.item_202")


def _default_cache_path() -> Path:
    # examples/strategies/ -> examples/data/item_202_events_sample.json
    return Path(__file__).resolve().parent.parent / "data" / "item_202_events_sample.json"


def _parse_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip()[:10]


class Item202OptionsImpactStrategy(bt.Strategy):
    """Trade the underlying around Massive Item 2.02 / earnings events.

    Params
    ------
    hold_bars : int
        Sessions to hold after entry (PEAD literature often uses 5–60 days;
        default 5 fits short Webull history windows).
    atr_period : int
        ATR lookback used to normalize the event gap.
    min_gap_atr : float
        Require |gap| / ATR >= this threshold before trading (filters noise).
    mode : str
        ``momentum`` (follow the gap / PEAD) or ``fade`` (fade the gap).
    allow_short : bool
        If False, only take long-side trades.
    min_surprise_pct : float
        If Benzinga EPS surprise is present, require
        abs(eps_surprise_percent) >= this value. 0 disables the filter.
    require_surprise : bool
        If True, skip events that lack an EPS surprise value.
    target_pct : float
        Portfolio weight per position via ``order_target_percent``.
    events_cache : str
        Optional JSON cache path. Empty string uses MASSIVE_EVENTS_CACHE env
        or the shipped sample file.
    refresh_events : bool
        Force a live Massive refetch even when a cache exists.
    enrich_benzinga : bool
        Attempt Benzinga earnings enrichment when fetching live. Default False
        because Benzinga is a separate Massive entitlement; 8-K Item 2.02 alone
        is enough for the strategy.
    filing_date_gte / filing_date_lte : str
        Optional YYYY-MM-DD bounds for live Massive pulls.
    """

    params = dict(
        hold_bars=5,
        atr_period=14,
        min_gap_atr=0.5,
        mode="momentum",  # momentum | fade
        allow_short=True,
        min_surprise_pct=0.0,
        require_surprise=False,
        target_pct=0.2,
        events_cache="",
        refresh_events=False,
        enrich_benzinga=False,
        filing_date_gte="",
        filing_date_lte="",
    )

    def __init__(self):
        mode = str(self.p.mode).strip().lower()
        if mode not in ("momentum", "fade"):
            raise ValueError("mode must be 'momentum' or 'fade'")
        self._mode = mode

        self.inds = {}
        self.orders = {}
        self._exit_bar = {}  # data -> bar index when we should flatten
        self._pending_entry = {}  # data -> signal meta for next-bar entry
        self.event_log = []  # analytics for options-impact review
        self.closed_trades = []
        self.set_tradehistory(True)

        for data in self.datas:
            self.inds[data] = {
                "atr": bt.ind.ATR(data, period=self.p.atr_period),
            }
            self.orders[data] = None
            self._exit_bar[data] = None
            self._pending_entry[data] = None

        tickers = [
            (d._name or d._dataname or "").upper()
            for d in self.datas
        ]
        cache = (
            self.p.events_cache
            or os.environ.get("MASSIVE_EVENTS_CACHE", "")
            or str(_default_cache_path())
        )
        cache_path = Path(cache)
        if not cache_path.is_absolute():
            # Resolve relative caches from the starter package root.
            starter_root = Path(__file__).resolve().parents[2]
            candidate = starter_root / cache_path
            cache_path = candidate if candidate.exists() else Path.cwd() / cache_path
        cache = str(cache_path)
        gte = _parse_iso_date(self.p.filing_date_gte) or _parse_iso_date(
            os.environ.get("MASSIVE_FILING_DATE_GTE")
        )
        lte = _parse_iso_date(self.p.filing_date_lte) or _parse_iso_date(
            os.environ.get("MASSIVE_FILING_DATE_LTE")
        )

        events = load_item_202_events(
            tickers,
            filing_date_gte=gte,
            filing_date_lte=lte,
            cache_path=cache,
            refresh=bool(self.p.refresh_events),
            enrich_benzinga=bool(self.p.enrich_benzinga),
        )
        self._events = events_by_ticker(events)
        self._events_by_trade_date: dict[str, dict[date, list[Item202Event]]] = {}
        for ticker, rows in self._events.items():
            by_day: dict[date, list[Item202Event]] = {}
            for event in rows:
                by_day.setdefault(event.event_date, []).append(event)
            self._events_by_trade_date[ticker] = by_day

        total = sum(len(v) for v in self._events.values())
        logger.info(
            "[Item2.02] mode=%s hold_bars=%s min_gap_atr=%s events=%d cache=%s",
            self._mode, self.p.hold_bars, self.p.min_gap_atr, total, cache,
        )
        if total == 0:
            logger.warning(
                "[Item2.02] no events loaded for %s — strategy will stay flat. "
                "Set MASSIVE_API_KEY to fetch live filings or provide a cache.",
                tickers,
            )

    def notify_order(self, order: bt.Order):
        if order.status in (order.Submitted, order.Accepted):
            return
        symbol = order.data._name or order.data._dataname
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            logger.info(
                "[Order] %s %s completed: price=%.2f size=%s",
                symbol, side, order.executed.price, order.executed.size,
            )
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            logger.warning(
                "[Order] %s %s: %s", symbol, order.getstatusname(), order.info,
            )
            # If an entry failed, clear the scheduled exit.
            if self._exit_bar.get(order.data) is not None and not self.getposition(order.data):
                self._exit_bar[order.data] = None
        self.orders[order.data] = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        entry_size = trade.history[0].event.size if trade.history else trade.size
        exit_price = trade.history[-1].event.price if trade.history else trade.price
        self.closed_trades.append({
            "symbol": trade.getdataname(),
            "direction": "LONG" if trade.long else "SHORT",
            "size": entry_size,
            "entry_price": trade.price,
            "exit_price": exit_price,
            "open_dt": to_market_tz(trade.open_datetime()),
            "close_dt": to_market_tz(trade.close_datetime()),
            "pnl": trade.pnl,
            "pnlcomm": trade.pnlcomm,
            "commission": trade.commission,
            "bars_held": trade.barlen,
        })

    def next(self):
        for data in self.datas:
            self._handle_data(data)

    def stop(self):
        if not self.event_log:
            return
        logger.info(
            "[Item2.02] Event analytics (%d signal(s)) — realized moves proxy "
            "what options straddles captured around Item 2.02:",
            len(self.event_log),
        )
        for i, row in enumerate(self.event_log, start=1):
            logger.info(
                "  #%d %s trade_date=%s gap=%.2f%% gap/ATR=%.2f "
                "surprise=%s session=%s action=%s",
                i, row["symbol"], row["trade_date"], row["gap_pct"] * 100.0,
                row["gap_atr"],
                "n/a" if row["eps_surprise_percent"] is None
                else f"{row['eps_surprise_percent']:.2f}%",
                row["session"] or "n/a",
                row["action"],
            )

    def _handle_data(self, data):
        symbol = (data._name or data._dataname or "").upper()
        if len(data) < self.p.atr_period + 2:
            return
        if self.orders[data] is not None:
            return

        # Time-based exit for open event trades.
        if self.getposition(data) and self._exit_bar[data] is not None:
            if len(data) >= self._exit_bar[data]:
                self.orders[data] = self.close(data=data)
                self._exit_bar[data] = None
                return

        # Execute entry planned on a prior bar (gap measured on event day).
        pending = self._pending_entry[data]
        if pending is not None and not self.getposition(data):
            self._pending_entry[data] = None
            self._enter(data, pending)
            return

        bar_dt = data.datetime.datetime(0)
        if isinstance(bar_dt, datetime):
            bar_day = bar_dt.date()
        else:
            bar_day = date.fromisoformat(str(bar_dt)[:10])

        day_events = self._events_by_trade_date.get(symbol, {}).get(bar_day, [])
        if not day_events or self.getposition(data):
            return

        event = day_events[0]
        if not self._passes_surprise_filter(event):
            logger.info(
                "[Item2.02] %s %s skipped (surprise filter)",
                symbol, bar_day.isoformat(),
            )
            return

        prev_close = float(data.close[-1])
        open_px = float(data.open[0])
        if prev_close <= 0:
            return
        gap = (open_px / prev_close) - 1.0
        atr = float(self.inds[data]["atr"][0])
        gap_atr = abs(gap * prev_close / atr) if atr > 0 else 0.0

        action = "skip_small_gap"
        direction = 0
        if gap_atr >= float(self.p.min_gap_atr):
            direction = 1 if gap > 0 else -1
            if self._mode == "fade":
                direction *= -1
            if direction < 0 and not self.p.allow_short:
                action = "skip_short_disabled"
                direction = 0
            else:
                action = "long" if direction > 0 else "short"

        self.event_log.append({
            "symbol": symbol,
            "trade_date": bar_day.isoformat(),
            "filing_date": event.filing_date,
            "session": event.session,
            "gap_pct": gap,
            "gap_atr": gap_atr,
            "atr": atr,
            "eps_surprise_percent": event.eps_surprise_percent,
            "action": action,
            "mode": self._mode,
            "accession_number": event.accession_number,
        })

        if direction == 0:
            return

        # Enter on this bar (event-day open already observed via gap).
        self._enter(data, {"direction": direction, "event": event, "gap": gap})

    def _passes_surprise_filter(self, event: Item202Event) -> bool:
        surprise = event.eps_surprise_percent
        if self.p.require_surprise and surprise is None:
            return False
        if surprise is None:
            return True
        return abs(float(surprise)) >= float(self.p.min_surprise_pct)

    def _enter(self, data, signal: dict):
        direction = signal["direction"]
        weight = abs(float(self.p.target_pct))
        if direction < 0:
            weight = -weight
        self.orders[data] = self.order_target_percent(data=data, target=weight)
        self._exit_bar[data] = len(data) + int(self.p.hold_bars)
        logger.info(
            "[Item2.02] %s enter %s gap=%.2f%% hold_until_bar=%s",
            data._name or data._dataname,
            "LONG" if direction > 0 else "SHORT",
            signal["gap"] * 100.0,
            self._exit_bar[data],
        )


# Dynamic loader convention used by examples/backtest/main.py
STRATEGY_CLASS = Item202OptionsImpactStrategy
