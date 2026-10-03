"""Facility-disruption premium-selling strategy (Webull / Backtrader).

Hypothesis
----------
A disruption 8-K that FIRMS labels ``brief`` (no persistent thermal anomaly)
is an over-reaction candidate: implied move tends to exceed realized move.
With no long-put in the menu, the clean trade is **sell premium**:

* ``csp`` (default) — cash-secured short put
* ``covered_call`` — long stock + short call

``persistent`` / ``unknown`` events are logged and skipped (control / no site).

Options are **synthetic** Black–Scholes marks on Webull equity bars (same
constraint as Item 2.02). Entry vol is stressed vs ATR so short premium can
earn a modeled IV crush when spot stays calm.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

import backtrader as bt

from webull_bt.logging_utils import get_logger
from webull_bt.options_sim import (
    OptionPosition,
    annualized_vol_from_atr,
    nearest_friday,
    round_strike,
)
from webull_bt.timespan_scale import resolve_timespan, scale_hold_params
from webull_bt.timeutils import to_market_tz

logger = get_logger("strategy.facility_disruption")

BRIEF = "brief"
TRADEABLE = frozenset({BRIEF})


def _default_events_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "events" / "disruption_events.json"


def _bar_day(data) -> date:
    bar_dt = data.datetime.datetime(0)
    if isinstance(bar_dt, datetime):
        return bar_dt.date()
    return date.fromisoformat(str(bar_dt)[:10])


def _bar_day_ago(data, ago: int = -1) -> date | None:
    try:
        bar_dt = data.datetime.datetime(ago)
    except Exception:
        return None
    if isinstance(bar_dt, datetime):
        return bar_dt.date()
    return date.fromisoformat(str(bar_dt)[:10])


def _is_first_bar_of_day(data) -> bool:
    if len(data) < 2:
        return True
    today = _bar_day(data)
    prev = _bar_day_ago(data, -1)
    return prev is None or prev != today


def load_disruption_event_rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("events", payload if isinstance(payload, list) else [])
    return [dict(r) for r in rows]


class FacilityDisruptionPremiumStrategy(bt.Strategy):
    """Sell synthetic premium on FIRMS-``brief`` disruption 8-Ks."""

    params = dict(
        atr_sessions=14.0,
        atr_period=0,
        min_hold_sessions=2.0,
        max_hold_sessions=5.0,
        min_hold_bars=0,
        max_hold_bars=0,
        max_hold_hours=0.0,
        timespan="",
        # csp | covered_call
        structure="csp",
        # Only trade these facility_group labels (comma-separated).
        trade_groups="brief",
        premium_pct=0.02,
        # Stress entry IV vs ATR vol so crush can show up in marks.
        event_iv_mult=1.35,
        expiry_weeks=4,
        take_profit=0.50,   # fraction of credit earned
        stop_loss=1.00,     # lose 1x credit
        invalidate_atr=1.5,
        min_dte_exit=5,
        events_cache="",
        filing_date_gte="",
        filing_date_lte="",
        # Accepted so shared WEBULL_STRATEGY_PARAMS from other tracks do not crash.
        min_gap_atr=0.35,
        min_gap_pct=0.005,
        dead_money_atr=0.25,
        enrich_benzinga=False,
        enrich_disclosures=True,
        refresh_events=False,
    )

    def __init__(self):
        self.inds = {}
        self.option_positions: dict = {}
        self._last_opt_value: dict = {}
        self._csp_collateral: dict = {}
        self._stock_target: dict = {}
        self.event_log = []
        self.option_trades = []
        self.closed_trades = []
        self.set_tradehistory(True)

        feed_ts = None
        if self.datas:
            feed_ts = getattr(self.datas[0].p, "timespan", None)
        self._scale = scale_hold_params(
            timespan=self.p.timespan or feed_ts or resolve_timespan(None),
            min_hold_sessions=float(self.p.min_hold_sessions),
            max_hold_sessions=float(self.p.max_hold_sessions),
            atr_sessions=float(self.p.atr_sessions),
            min_hold_bars=int(self.p.min_hold_bars) or None,
            max_hold_bars=int(self.p.max_hold_bars) or None,
            atr_period=int(self.p.atr_period) or None,
            max_hold_hours=float(self.p.max_hold_hours or 0.0),
        )
        self._min_hold_bars = int(self._scale["min_hold_bars"])
        self._max_hold_bars = int(self._scale["max_hold_bars"])
        self._atr_period = int(self._scale["atr_period"])
        self._trade_groups = {
            g.strip().lower()
            for g in str(self.p.trade_groups).split(",")
            if g.strip()
        } or set(TRADEABLE)

        for data in self.datas:
            self.inds[data] = {"atr": bt.ind.ATR(data, period=self._atr_period)}
            self.option_positions[data] = None
            self._last_opt_value[data] = 0.0
            self._csp_collateral[data] = 0.0
            self._stock_target[data] = 0

        cache = (
            self.p.events_cache
            or os.environ.get("FACILITY_EVENTS", "")
            or str(_default_events_path())
        )
        cache_path = Path(cache)
        if not cache_path.is_absolute():
            repo_root = Path(__file__).resolve().parents[2]
            candidate = repo_root / cache_path
            cache_path = candidate if candidate.exists() else Path.cwd() / cache_path

        rows = load_disruption_event_rows(cache_path) if cache_path.exists() else []
        gte = (self.p.filing_date_gte or os.environ.get("MASSIVE_FILING_DATE_GTE") or "").strip()[:10]
        lte = (self.p.filing_date_lte or os.environ.get("MASSIVE_FILING_DATE_LTE") or "").strip()[:10]

        self._events_by_trade_date: dict[str, dict[date, list[dict]]] = {}
        kept = 0
        for row in rows:
            fd = str(row.get("filing_date") or "")[:10]
            if gte and fd and fd < gte:
                continue
            if lte and fd and fd > lte:
                continue
            ticker = str(row.get("ticker") or "").upper()
            raw_day = row.get("trade_date") or row.get("filing_date")
            if not ticker or not raw_day:
                continue
            day = date.fromisoformat(str(raw_day)[:10])
            self._events_by_trade_date.setdefault(ticker, {}).setdefault(day, []).append(row)
            kept += 1

        logger.info(
            "[FacilityDisruption] events=%d cache=%s structure=%s groups=%s "
            "timespan=%s hold=%d..%d bars atr=%d",
            kept,
            cache_path,
            self.p.structure,
            sorted(self._trade_groups),
            self._scale["timespan"],
            self._min_hold_bars,
            self._max_hold_bars,
            self._atr_period,
        )
        if kept == 0:
            logger.warning(
                "[FacilityDisruption] no events loaded — run fetch_disruption_events.py first"
            )

    def next(self):
        for data in self.datas:
            self._mark_option(data)
            self._maybe_exit(data)
            self._maybe_enter(data)

    def stop(self):
        for data in self.datas:
            if self.option_positions[data] is not None:
                self._close_option(data, reason="eod_force")
            if self.getposition(data).size:
                self.close(data=data)

        if self.event_log:
            logger.info(
                "[FacilityDisruption] %d signal(s); closed option tickets=%d",
                len(self.event_log),
                len(self.option_trades),
            )
            for i, row in enumerate(self.event_log[:25], start=1):
                logger.info(
                    "  #%d %s %s group=%s type=%s -> %s",
                    i,
                    row["symbol"],
                    row["trade_date"],
                    row.get("facility_group"),
                    row.get("disruption_type"),
                    row["action"],
                )

        if self.option_trades:
            wins = sum(1 for t in self.option_trades if t["pnl"] > 0)
            logger.info(
                "[FacilityDisruption] option win rate=%.1f%% (%d/%d) total_pnl=%.2f",
                100.0 * wins / len(self.option_trades),
                wins,
                len(self.option_trades),
                sum(t["pnl"] for t in self.option_trades),
            )

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

    def _vol(self, data) -> float:
        atr = float(self.inds[data]["atr"][0])
        spot = float(data.close[0])
        return annualized_vol_from_atr(atr, spot)

    def _mark_vol(self, data, pos: OptionPosition) -> float:
        # Mark at current ATR vol (typically below stressed entry) → crush for shorts.
        return self._vol(data)

    def _mark_option(self, data) -> None:
        pos = self.option_positions[data]
        if pos is None:
            return
        asof = _bar_day(data)
        value = pos.market_value(float(data.close[0]), asof, self._mark_vol(data, pos))
        prev = self._last_opt_value[data]
        self.broker.add_cash(value - prev)
        self._last_opt_value[data] = value

    def _maybe_enter(self, data) -> None:
        if self.option_positions[data] is not None:
            return
        if self.getposition(data).size:
            return
        if len(data) < self._atr_period + 2:
            return
        if not _is_first_bar_of_day(data):
            return

        symbol = (data._name or data._dataname or "").upper()
        bar_day = _bar_day(data)
        day_events = self._events_by_trade_date.get(symbol, {}).get(bar_day, [])
        if not day_events:
            return

        event = day_events[0]
        group = str(event.get("facility_group") or "unknown").lower()
        action = "skip"
        if group not in self._trade_groups:
            action = f"skip_{group}"
        else:
            action = f"sell_{self.p.structure}"

        self.event_log.append({
            "symbol": symbol,
            "trade_date": bar_day.isoformat(),
            "filing_date": event.get("filing_date"),
            "facility_group": group,
            "disruption_type": event.get("disruption_type"),
            "anomaly_detected": event.get("anomaly_detected"),
            "anomaly_persist_days": event.get("anomaly_persist_days"),
            "site_lat": event.get("site_lat"),
            "site_lon": event.get("site_lon"),
            "action": action,
        })
        if not action.startswith("sell_"):
            return

        structure = str(self.p.structure).strip().lower()
        if structure == "covered_call":
            self._enter_covered_call(data, event, bar_day)
        else:
            self._enter_csp(data, event, bar_day)

    def _enter_csp(self, data, event: dict, bar_day: date) -> None:
        symbol = (data._name or data._dataname or "").upper()
        spot = float(data.close[0])
        atr_vol = self._vol(data)
        entry_vol = atr_vol * float(self.p.event_iv_mult)
        strike = round_strike(spot)
        expiry = nearest_friday(bar_day, weeks=int(self.p.expiry_weeks))

        probe = OptionPosition(
            symbol=symbol,
            option_type="put",
            strike=strike,
            expiry=expiry,
            contracts=1,
            entry_premium=0.0,
            entry_underlying=spot,
            entry_date=bar_day,
            entry_bar=len(data),
            side="short",
            entry_vol=entry_vol,
        )
        premium = probe.premium(spot, bar_day, entry_vol)
        if premium <= 0.05:
            logger.warning("[FacilityDisruption] %s CSP premium too small (%.4f)", symbol, premium)
            return

        # Size by premium budget and cash for strike collateral.
        budget = float(self.broker.getvalue()) * float(self.p.premium_pct)
        by_premium = max(1, int(budget // (premium * 100.0)))
        cash = float(self.broker.getcash())
        by_collateral = max(0, int(cash // (strike * 100.0)))
        contracts = max(1, min(by_premium, by_collateral)) if by_collateral else 0
        if contracts < 1:
            logger.warning("[FacilityDisruption] %s insufficient cash for CSP collateral", symbol)
            return

        pos = OptionPosition(
            symbol=symbol,
            option_type="put",
            strike=strike,
            expiry=expiry,
            contracts=contracts,
            entry_premium=premium,
            entry_underlying=spot,
            entry_date=bar_day,
            entry_bar=len(data),
            side="short",
            entry_vol=entry_vol,
            meta={
                "structure": "csp",
                "facility_group": event.get("facility_group"),
                "disruption_type": event.get("disruption_type"),
                "accession_number": event.get("accession_number"),
            },
        )
        credit = -pos.cost_basis()  # positive dollars received
        collateral = strike * 100.0 * contracts
        self.broker.add_cash(credit)
        self.broker.add_cash(-collateral)
        self._csp_collateral[data] = collateral
        self.option_positions[data] = pos
        self._last_opt_value[data] = 0.0
        self._mark_option(data)
        logger.info(
            "[FacilityDisruption] %s SELL PUT x%d strike=%.2f prem=%.2f credit=%.2f "
            "collateral=%.2f group=%s",
            symbol, contracts, strike, premium, credit, collateral,
            event.get("facility_group"),
        )

    def _enter_covered_call(self, data, event: dict, bar_day: date) -> None:
        symbol = (data._name or data._dataname or "").upper()
        spot = float(data.close[0])
        atr_vol = self._vol(data)
        entry_vol = atr_vol * float(self.p.event_iv_mult)
        strike = round_strike(spot)
        expiry = nearest_friday(bar_day, weeks=int(self.p.expiry_weeks))

        probe = OptionPosition(
            symbol=symbol,
            option_type="call",
            strike=strike,
            expiry=expiry,
            contracts=1,
            entry_premium=0.0,
            entry_underlying=spot,
            entry_date=bar_day,
            entry_bar=len(data),
            side="short",
            entry_vol=entry_vol,
        )
        premium = probe.premium(spot, bar_day, entry_vol)
        if premium <= 0.05:
            logger.warning("[FacilityDisruption] %s CC premium too small (%.4f)", symbol, premium)
            return

        budget = float(self.broker.getvalue()) * float(self.p.premium_pct)
        # One contract covers 100 shares — size by stock notional budget.
        contracts = max(1, int(budget // (spot * 100.0)))
        shares = contracts * 100
        if shares * spot > float(self.broker.getcash()) * 0.95:
            contracts = max(0, int((float(self.broker.getcash()) * 0.95) // (spot * 100.0)))
            shares = contracts * 100
        if contracts < 1:
            logger.warning("[FacilityDisruption] %s insufficient cash for covered call", symbol)
            return

        self.buy(data=data, size=shares)
        self._stock_target[data] = shares
        pos = OptionPosition(
            symbol=symbol,
            option_type="call",
            strike=strike,
            expiry=expiry,
            contracts=contracts,
            entry_premium=premium,
            entry_underlying=spot,
            entry_date=bar_day,
            entry_bar=len(data),
            side="short",
            entry_vol=entry_vol,
            meta={
                "structure": "covered_call",
                "facility_group": event.get("facility_group"),
                "disruption_type": event.get("disruption_type"),
                "accession_number": event.get("accession_number"),
            },
        )
        credit = -pos.cost_basis()
        self.broker.add_cash(credit)
        self.option_positions[data] = pos
        self._last_opt_value[data] = 0.0
        self._mark_option(data)
        logger.info(
            "[FacilityDisruption] %s COVERED CALL stock=%d sell call x%d strike=%.2f "
            "prem=%.2f credit=%.2f group=%s",
            symbol, shares, contracts, strike, premium, credit,
            event.get("facility_group"),
        )

    def _maybe_exit(self, data) -> None:
        pos = self.option_positions[data]
        if pos is None:
            return

        asof = _bar_day(data)
        spot = float(data.close[0])
        atr = float(self.inds[data]["atr"][0])
        vol = self._mark_vol(data, pos)
        premium_now = pos.premium(spot, asof, vol)
        credit = pos.entry_premium
        # Short P&L as fraction of credit received.
        short_ret = (credit - premium_now) / credit if credit > 0 else 0.0
        bars_held = len(data) - pos.entry_bar
        dte = (pos.expiry - asof).days

        # Adverse underlying move vs short structure.
        move = spot - pos.entry_underlying
        adverse = -move if pos.option_type == "put" else move

        reason = None
        if short_ret >= float(self.p.take_profit):
            reason = f"take_profit:{short_ret:.0%}"
        elif short_ret <= -float(self.p.stop_loss):
            reason = f"stop_loss:{short_ret:.0%}"
        elif dte <= int(self.p.min_dte_exit):
            reason = f"dte:{dte}"
        elif bars_held >= self._max_hold_bars:
            reason = f"max_hold:{bars_held}"
        elif adverse >= float(self.p.invalidate_atr) * atr:
            reason = "underlying_invalidation"

        if reason:
            self._close_option(data, reason=reason)

    def _close_option(self, data, *, reason: str) -> None:
        pos = self.option_positions[data]
        if pos is None:
            return
        asof = _bar_day(data)
        spot = float(data.close[0])
        vol = self._mark_vol(data, pos)
        value = pos.market_value(spot, asof, vol)
        prev = self._last_opt_value[data]
        self.broker.add_cash(value - prev)

        # Release CSP collateral.
        collateral = float(self._csp_collateral.get(data) or 0.0)
        if collateral > 0:
            self.broker.add_cash(collateral)
            self._csp_collateral[data] = 0.0

        # Flatten stock for covered calls.
        if self.getposition(data).size:
            self.close(data=data)
        self._stock_target[data] = 0

        pnl = value - pos.cost_basis()
        bars_held = len(data) - pos.entry_bar
        ticket = {
            "symbol": pos.symbol,
            "direction": f"SHORT_{pos.option_type.upper()}",
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
            "structure": (pos.meta or {}).get("structure"),
            "facility_group": (pos.meta or {}).get("facility_group"),
            "disruption_type": (pos.meta or {}).get("disruption_type"),
            "strike": pos.strike,
            "expiry": pos.expiry.isoformat(),
        }
        self.option_trades.append(ticket)
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
            "[FacilityDisruption] %s CLOSE %s x%d pnl=%.2f reason=%s",
            pos.symbol, ticket["direction"], pos.contracts, pnl, reason,
        )
        self.option_positions[data] = None
        self._last_opt_value[data] = 0.0


STRATEGY_CLASS = FacilityDisruptionPremiumStrategy
