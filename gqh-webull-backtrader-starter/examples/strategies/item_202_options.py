"""Item 2.02 disclosure-polarity options strategy.

Massive 8-K disclosure ``primary_category`` / ``tertiary_category`` values are
mapped to a signed polarity:

  * **positive** taxonomy (or unsigned earnings + up-gap) → buy **calls**
  * **negative** taxonomy (or unsigned earnings + down-gap) → buy **puts**

Instead of a fixed 5-day equity hold, this strategy trades **synthetic
ATM options** (Black–Scholes marks on the Webull underlying path) and exits on
rule-based conditions: take-profit, stop-loss, underlying invalidation, dead
money after IV crush, or max hold / near-expiry — not a calendar lag.

Webull's starter feed is equity-only; option premiums are simulated so the
backtester can evaluate call/put P&L without a Massive Options entitlement.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import backtrader as bt

from webull_bt.disclosure_polarity import polarity_label, resolve_signal_polarity
from webull_bt.logging_utils import get_logger
from webull_bt.massive_filings import Item202Event, events_by_ticker, load_item_202_events
from webull_bt.options_sim import (
    OptionPosition,
    annualized_vol_from_atr,
    nearest_friday,
    round_strike,
)
from webull_bt.timeutils import to_market_tz


logger = get_logger("strategy.item_202")


def _default_cache_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "item_202_events_high_vol.json"


def _parse_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip()[:10]


def _bar_day(data) -> date:
    bar_dt = data.datetime.datetime(0)
    if isinstance(bar_dt, datetime):
        return bar_dt.date()
    return date.fromisoformat(str(bar_dt)[:10])


class Item202OptionsImpactStrategy(bt.Strategy):
    """Buy calls on positive disclosure polarity, puts on negative.

    Exit logic (no fixed 5-day lag)
    -------------------------------
    * ``take_profit`` / ``stop_loss`` on option premium %
    * Underlying invalidation vs entry ± ``invalidate_atr`` · ATR
    * Dead-money exit after ``min_hold_bars`` if favorable move < ``dead_money_atr`` · ATR
    * Hard ``max_hold_bars`` and/or DTE < ``min_dte_exit``
    """

    params = dict(
        atr_period=14,
        min_gap_pct=0.005,  # 0.5% min gap when taxonomy is unsigned
        min_gap_atr=0.35,
        premium_pct=0.02,  # fraction of portfolio spent on each option ticket
        expiry_weeks=4,
        take_profit=0.60,
        stop_loss=0.40,
        invalidate_atr=1.0,
        dead_money_atr=0.25,
        min_hold_bars=2,
        max_hold_bars=10,
        min_dte_exit=5,
        events_cache="",
        refresh_events=False,
        enrich_benzinga=False,
        enrich_disclosures=True,
        filing_date_gte="",
        filing_date_lte="",
    )

    def __init__(self):
        self.inds = {}
        self.option_positions: dict = {}
        self._last_opt_value: dict = {}
        self.event_log = []
        self.option_trades = []  # closed option tickets (for report)
        self.closed_trades = []  # equity trades unused; kept for report compat
        self.set_tradehistory(True)

        for data in self.datas:
            self.inds[data] = {"atr": bt.ind.ATR(data, period=self.p.atr_period)}
            self.option_positions[data] = None
            self._last_opt_value[data] = 0.0

        tickers = [(d._name or d._dataname or "").upper() for d in self.datas]
        cache = (
            self.p.events_cache
            or os.environ.get("MASSIVE_EVENTS_CACHE", "")
            or str(_default_cache_path())
        )
        cache_path = Path(cache)
        if not cache_path.is_absolute():
            starter_root = Path(__file__).resolve().parents[2]
            candidate = starter_root / cache_path
            cache_path = candidate if candidate.exists() else Path.cwd() / cache_path

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
            cache_path=str(cache_path),
            refresh=bool(self.p.refresh_events),
            enrich_benzinga=bool(self.p.enrich_benzinga),
            enrich_disclosures=bool(self.p.enrich_disclosures),
        )
        self._events_by_trade_date: dict[str, dict[date, list[Item202Event]]] = {}
        for ticker, rows in events_by_ticker(events).items():
            by_day: dict[date, list[Item202Event]] = {}
            for event in rows:
                by_day.setdefault(event.event_date, []).append(event)
            self._events_by_trade_date[ticker] = by_day

        logger.info(
            "[Item2.02/Options] events=%d cache=%s tp=%.0f%% sl=%.0f%% max_hold=%s",
            sum(len(v) for v in self._events_by_trade_date.values()),
            cache_path,
            self.p.take_profit * 100.0,
            self.p.stop_loss * 100.0,
            self.p.max_hold_bars,
        )

    def next(self):
        for data in self.datas:
            self._mark_option(data)
            self._maybe_exit(data)
            self._maybe_enter(data)

    def stop(self):
        # Force-close any open options at last mark for clean accounting.
        for data in self.datas:
            if self.option_positions[data] is not None:
                self._close_option(data, reason="eod_force")

        if self.event_log:
            logger.info(
                "[Item2.02/Options] %d signal(s); closed option tickets=%d",
                len(self.event_log), len(self.option_trades),
            )
            for i, row in enumerate(self.event_log[:20], start=1):
                logger.info(
                    "  #%d %s %s primary=%s tertiary=%s gap=%.2f%% -> %s",
                    i, row["symbol"], row["trade_date"],
                    row.get("primary_category") or "n/a",
                    row.get("tertiary_category") or "n/a",
                    row["gap_pct"] * 100.0,
                    row["action"],
                )
            if len(self.event_log) > 20:
                logger.info("  ... %d more signal(s)", len(self.event_log) - 20)

        if self.option_trades:
            wins = sum(1 for t in self.option_trades if t["pnl"] > 0)
            logger.info(
                "[Item2.02/Options] option win rate=%.1f%% (%d/%d) total_pnl=%.2f",
                100.0 * wins / len(self.option_trades),
                wins, len(self.option_trades),
                sum(t["pnl"] for t in self.option_trades),
            )

    def notify_trade(self, trade):
        # Equity legs are not used; keep hook for report compatibility.
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

    # ------------------------------------------------------------------ #
    # Option lifecycle
    # ------------------------------------------------------------------ #

    def _vol(self, data) -> float:
        atr = float(self.inds[data]["atr"][0])
        spot = float(data.close[0])
        return annualized_vol_from_atr(atr, spot)

    def _mark_option(self, data) -> None:
        pos = self.option_positions[data]
        if pos is None:
            return
        asof = _bar_day(data)
        value = pos.market_value(float(data.close[0]), asof, self._vol(data))
        prev = self._last_opt_value[data]
        self.broker.add_cash(value - prev)
        self._last_opt_value[data] = value

    def _maybe_enter(self, data) -> None:
        if self.option_positions[data] is not None:
            return
        if len(data) < self.p.atr_period + 2:
            return

        symbol = (data._name or data._dataname or "").upper()
        bar_day = _bar_day(data)
        day_events = self._events_by_trade_date.get(symbol, {}).get(bar_day, [])
        if not day_events:
            return

        event = day_events[0]
        prev_close = float(data.close[-1])
        open_px = float(data.open[0])
        if prev_close <= 0:
            return
        gap = (open_px / prev_close) - 1.0
        atr = float(self.inds[data]["atr"][0])
        gap_atr = abs(gap * prev_close / atr) if atr > 0 else 0.0

        # Prefer taxonomy polarity stored on the event; fall back to resolver.
        if event.category_polarity != 0:
            polarity = int(event.category_polarity)
        else:
            polarity = resolve_signal_polarity(
                primary_category=event.primary_category,
                tertiary_category=event.tertiary_category,
                gap_pct=gap,
                min_gap_pct=float(self.p.min_gap_pct),
            )

        action = "skip"
        if polarity == 0:
            action = "skip_unsigned_flat"
        elif gap_atr < float(self.p.min_gap_atr) and event.category_polarity == 0:
            # Unsigned earnings still need a meaningful print.
            action = "skip_small_gap"
            polarity = 0
        else:
            action = "buy_call" if polarity > 0 else "buy_put"

        self.event_log.append({
            "symbol": symbol,
            "trade_date": bar_day.isoformat(),
            "filing_date": event.filing_date,
            "primary_category": event.primary_category,
            "secondary_category": event.secondary_category,
            "tertiary_category": event.tertiary_category,
            "category_polarity": event.category_polarity,
            "polarity_label": polarity_label(polarity if action.startswith("buy") else event.category_polarity),
            "gap_pct": gap,
            "gap_atr": gap_atr,
            "action": action,
        })

        if polarity == 0 or not action.startswith("buy"):
            return

        spot = float(data.close[0])
        vol = self._vol(data)
        option_type = "call" if polarity > 0 else "put"
        strike = round_strike(spot)
        expiry = nearest_friday(bar_day, weeks=int(self.p.expiry_weeks))
        # Temporary 1-contract probe for premium, then size to premium_pct.
        probe = OptionPosition(
            symbol=symbol,
            option_type=option_type,
            strike=strike,
            expiry=expiry,
            contracts=1,
            entry_premium=0.0,
            entry_underlying=spot,
            entry_date=bar_day,
            entry_bar=len(data),
            polarity=polarity,
            primary_category=event.primary_category,
            tertiary_category=event.tertiary_category,
            entry_vol=vol,
        )
        premium = probe.premium(spot, bar_day, vol)
        if premium <= 0.05:
            logger.warning("[Options] %s premium too small (%.4f); skip", symbol, premium)
            return

        budget = float(self.broker.getvalue()) * float(self.p.premium_pct)
        contracts = max(1, int(budget // (premium * 100.0)))
        pos = OptionPosition(
            symbol=symbol,
            option_type=option_type,
            strike=strike,
            expiry=expiry,
            contracts=contracts,
            entry_premium=premium,
            entry_underlying=spot,
            entry_date=bar_day,
            entry_bar=len(data),
            polarity=polarity,
            primary_category=event.primary_category,
            tertiary_category=event.tertiary_category,
            entry_vol=vol,
            meta={"gap_pct": gap, "gap_atr": gap_atr},
        )
        cost = pos.cost_basis()
        if cost > float(self.broker.getcash()):
            contracts = max(1, int(float(self.broker.getcash()) * 0.95 // (premium * 100.0)))
            if contracts < 1:
                return
            pos.contracts = contracts
            cost = pos.cost_basis()

        self.broker.add_cash(-cost)
        self.option_positions[data] = pos
        # Premium left cash; credit current mark so equity stays continuous.
        self._last_opt_value[data] = 0.0
        self._mark_option(data)
        logger.info(
            "[Options] %s BUY %s x%d strike=%.2f prem=%.2f cost=%.2f "
            "primary=%s tertiary=%s polarity=%s",
            symbol, option_type.upper(), contracts, strike, premium, cost,
            event.primary_category or "n/a",
            event.tertiary_category or "n/a",
            polarity_label(polarity),
        )

    def _maybe_exit(self, data) -> None:
        pos = self.option_positions[data]
        if pos is None:
            return

        asof = _bar_day(data)
        spot = float(data.close[0])
        atr = float(self.inds[data]["atr"][0])
        vol = self._vol(data)
        premium_now = pos.premium(spot, asof, vol)
        ret = (premium_now / pos.entry_premium) - 1.0 if pos.entry_premium > 0 else 0.0
        bars_held = len(data) - pos.entry_bar
        dte = (pos.expiry - asof).days
        move = spot - pos.entry_underlying
        favorable = move if pos.option_type == "call" else -move

        reason = None
        if ret >= float(self.p.take_profit):
            reason = f"take_profit:{ret:.0%}"
        elif ret <= -float(self.p.stop_loss):
            reason = f"stop_loss:{ret:.0%}"
        elif dte <= int(self.p.min_dte_exit):
            reason = f"dte:{dte}"
        elif bars_held >= int(self.p.max_hold_bars):
            reason = f"max_hold:{bars_held}"
        elif favorable <= -float(self.p.invalidate_atr) * atr:
            reason = "underlying_invalidation"
        elif (
            bars_held >= int(self.p.min_hold_bars)
            and favorable < float(self.p.dead_money_atr) * atr
        ):
            reason = "dead_money_iv_crush"

        if reason:
            self._close_option(data, reason=reason)

    def _close_option(self, data, *, reason: str) -> None:
        pos = self.option_positions[data]
        if pos is None:
            return
        asof = _bar_day(data)
        spot = float(data.close[0])
        vol = self._vol(data)
        # Ensure cash reflects final mark, then flatten tracking state.
        value = pos.market_value(spot, asof, vol)
        prev = self._last_opt_value[data]
        self.broker.add_cash(value - prev)

        pnl = value - pos.cost_basis()
        bars_held = len(data) - pos.entry_bar
        ticket = {
            "symbol": pos.symbol,
            "direction": "CALL" if pos.option_type == "call" else "PUT",
            "size": pos.contracts,
            "entry_price": pos.entry_premium,
            "exit_price": pos.premium(spot, asof, vol),
            "open_dt": pos.entry_date.isoformat(),
            "close_dt": asof.isoformat(),
            "pnl": pnl,
            "pnlcomm": pnl,
            "commission": 0.0,
            "bars_held": bars_held,
            "reason": reason,
            "primary_category": pos.primary_category,
            "tertiary_category": pos.tertiary_category,
            "strike": pos.strike,
            "expiry": pos.expiry.isoformat(),
        }
        self.option_trades.append(ticket)
        # Surface in the standard trade report as well.
        self.closed_trades.append({
            "symbol": ticket["symbol"],
            "direction": ticket["direction"],
            "size": ticket["size"],
            "entry_price": ticket["entry_price"],
            "exit_price": ticket["exit_price"],
            "open_dt": ticket["open_dt"],
            "close_dt": ticket["close_dt"],
            "pnl": ticket["pnl"],
            "pnlcomm": ticket["pnlcomm"],
            "commission": 0.0,
            "bars_held": ticket["bars_held"],
        })
        logger.info(
            "[Options] %s CLOSE %s x%d pnl=%.2f reason=%s",
            pos.symbol, pos.option_type.upper(), pos.contracts, pnl, reason,
        )
        self.option_positions[data] = None
        self._last_opt_value[data] = 0.0


STRATEGY_CLASS = Item202OptionsImpactStrategy
