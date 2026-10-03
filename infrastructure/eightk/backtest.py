"""Event-driven options backtest.

Timing is the part of this design that decides whether the results mean
anything, so it is made explicit rather than assumed:

* A filing accepted **before 09:30 ET** is tradable at that session's open.
* A filing accepted **after 16:00 ET** is tradable at the *next* session's
  open.
* A filing accepted **during the session** is only entered at that day's
  close. With daily bars there is no honest way to claim a fill seconds
  after the filing hit, and assuming one would hand the backtest the
  reaction it is supposed to be measuring.

Exits are marked from real option bars where the contract traded, and
otherwise from a volatility that has reverted to its pre-event baseline —
never from the entry volatility, which would quietly hand every long-option
trade a profit by ignoring the post-event implied-vol collapse.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from eightk.events import EventRecord
from eightk.options_book import CostModel, OptionBook
from eightk.options_model import (
    Structure,
    bs_price,
    implied_vol,
    realized_vol,
    year_fraction,
)
from eightk.prices import PriceSeries
from eightk.strategies import Strategy, StrategyConfig, TradeContext

logger = logging.getLogger(__name__)

#: Strategies that hold only the underlying and need no option chain.
STOCK_ONLY_STRATEGIES = frozenset({"stock_long", "stock_short"})


@dataclass
class Trade:
    """One simulated position with its outcome and diagnostics."""

    strategy: str
    ticker: str
    accession: str
    filing_date: str
    acceptance_et: str
    session_bucket: str
    event_types: str
    entry_day: str
    exit_day: str
    expiry: str | None
    hold_sessions: int
    entry_spot: float
    exit_spot: float
    underlying_return: float
    entry_cost: float            # net debit (positive) or credit (negative)
    net_premium: float
    exit_value: float
    pnl: float
    return_on_capital: float
    capital_at_risk: float
    priced_from: str             # "market" | "model" | "mixed"
    entry_iv: float | None
    exit_iv: float | None
    realized_vol_hold: float | None
    implied_move: float | None
    actual_move: float | None
    vol_risk_premium: float | None
    market_cap: float | None
    cap_bucket: str
    novelty_score: float | None
    exec_severity: float | None
    confounded_by_earnings: bool
    settled_at_expiry: bool
    structure: str
    reason: str
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        row = {k: v for k, v in self.__dict__.items() if k != "extras"}
        row.update(self.extras)
        return row


@dataclass
class BacktestConfig:
    """Holding period and accounting choices for a run."""

    hold_sessions: int = 10
    target_notional: float = 10_000.0
    rate: float = 0.04
    vol_window: int = 20
    #: Treat an in-session filing as tradable at the close (True) or skip it.
    trade_rth_at_close: bool = True
    cost_model: CostModel = field(default_factory=CostModel)
    strategy_config: StrategyConfig = field(default_factory=StrategyConfig)


def determine_entry(
    filing, series: PriceSeries, *, allow_rth: bool = True,
) -> tuple[date, float, float, str] | None:
    """Resolve the first honestly tradable moment after a filing.

    Returns ``(entry_day, entry_spot, reference_spot, note)`` where
    ``reference_spot`` is the session price used to invert option bars into
    implied vol.
    """
    bucket = filing.session_bucket
    try:
        filing_day = date.fromisoformat(filing.filing_date)
    except (TypeError, ValueError):
        return None

    if bucket == "PRE":
        entry_day = series.next_session(filing_day, inclusive=True)
        if entry_day is None:
            return None
        bar = series.get(entry_day)
        if bar is None or bar.open <= 0:
            return None
        return entry_day, bar.open, (bar.vwap or bar.close), "pre_open"

    if bucket == "POST":
        entry_day = series.next_session(filing_day, inclusive=False)
        if entry_day is None:
            return None
        bar = series.get(entry_day)
        if bar is None or bar.open <= 0:
            return None
        return entry_day, bar.open, (bar.vwap or bar.close), "post_next_open"

    # Filed while the market was open.
    if not allow_rth:
        return None
    entry_day = series.next_session(filing_day, inclusive=True)
    if entry_day is None:
        return None
    bar = series.get(entry_day)
    if bar is None or bar.close <= 0:
        return None
    return entry_day, bar.close, (bar.vwap or bar.close), "rth_close"


def _exit_leg_premium(
    leg,
    *,
    book: OptionBook,
    exit_day: date,
    exit_spot: float,
    expiry: date,
    baseline_vol: float,
) -> tuple[float, float | None, str]:
    """Value one option leg at exit. Returns ``(premium, iv, source)``."""
    strike = float(leg.strike)

    if exit_day >= expiry:
        # Settled: intrinsic only, no spread paid on expiry.
        intrinsic = (
            max(0.0, exit_spot - strike) if leg.kind == "call"
            else max(0.0, strike - exit_spot)
        )
        return intrinsic, None, "expiry"

    tau = year_fraction((expiry - exit_day).days)

    if leg.ticker:
        bar = book.option_bar(leg.ticker, exit_day)
        if bar is not None and bar.mid_proxy > 0:
            ref_bar = book.series.get(bar.day)
            ref_spot = (ref_bar.vwap or ref_bar.close) if ref_bar else exit_spot
            ref_tau = year_fraction((expiry - bar.day).days)
            iv = implied_vol(bar.mid_proxy, ref_spot, strike, ref_tau,
                             book.rate, 0.0, leg.kind)
            if iv is not None:
                return bs_price(exit_spot, strike, tau, iv, book.rate, 0.0, leg.kind), iv, "market"

    # No usable quote: the event premium is assumed gone and vol has
    # reverted to its pre-event baseline. This is deliberately unkind to
    # long-option strategies, which is the right direction for an estimate.
    iv = max(0.05, baseline_vol)
    return bs_price(exit_spot, strike, tau, iv, book.rate, 0.0, leg.kind), iv, "model"


def _capital_at_risk(structure: Structure, entry_spot: float) -> float:
    """Denominator for return-on-capital, by structure shape.

    A debit structure risks its premium. A credit structure's true risk is
    unbounded for a naked strangle, so the margin a broker would demand is
    approximated as 20% of the underlying notional plus the credit received —
    reporting return on premium collected instead would flatter short
    volatility enormously.
    """
    stock_legs = [leg for leg in structure.legs if leg.kind == "stock"]
    if stock_legs:
        # Collar or stock benchmark: the capital is the stock itself.
        return sum(abs(leg.quantity) * entry_spot for leg in stock_legs)

    debit = structure.entry_cost
    if debit > 0:
        return debit

    option_notional = sum(
        abs(leg.quantity) * leg.multiplier * entry_spot
        for leg in structure.legs if leg.kind != "stock"
    )
    # Halved because a strangle's two short wings cannot both be breached.
    return max(abs(debit), 0.20 * option_notional * 0.5)


def simulate_trade(
    *,
    event: EventRecord,
    strategy: Strategy,
    series: PriceSeries,
    book: OptionBook,
    config: BacktestConfig,
    reason: str,
) -> Trade | None:
    """Build and simulate one strategy's position for one event."""
    entry = determine_entry(event.filing, series, allow_rth=config.trade_rth_at_close)
    if entry is None:
        return None
    entry_day, entry_spot, reference_spot, timing_note = entry
    # Limited vendor history must not move an old filing to a recent session.
    if (entry_day - date.fromisoformat(event.filing.filing_date)).days > 7:
        return None
    if len(series.closes_before(entry_day, config.vol_window + 1)) < config.vol_window + 1:
        return None

    baseline_vol = book.baseline_vol(entry_day, window=config.vol_window)

    expiry = book.choose_expiry(
        entry_day,
        min_days=config.strategy_config.min_days_to_expiry,
        max_days=config.strategy_config.max_days_to_expiry,
    )
    if expiry is None and strategy.name not in STOCK_ONLY_STRATEGIES:
        # No listed chain was found for this date. Rather than drop the event
        # -- which would discard exactly the small, thinly optioned issuers
        # under study -- fall back to a synthetic expiry roughly a month out.
        # Legs then price from the model and are tagged as such, so these
        # trades can be excluded from any market-priced-only cut.
        expiry = entry_day + timedelta(
            days=config.strategy_config.min_days_to_expiry + 9
        )

    ctx = TradeContext(
        event=event, series=series, book=book, entry_day=entry_day,
        entry_spot=entry_spot, reference_spot=reference_spot, expiry=expiry,
        baseline_vol=baseline_vol, target_notional=config.target_notional,
    )
    structure = strategy.build(ctx)
    if structure is None or not structure.legs:
        return None

    # --- exit ----------------------------------------------------------
    horizon_day = series.shift(entry_day, config.hold_sessions)
    if horizon_day is None:
        # An unfinished observation is not a completed holding-period return.
        return None
    exit_day = horizon_day
    settled = False
    if expiry is not None and exit_day >= expiry:
        capped = series.prev_session(expiry, inclusive=True)
        exit_day = capped or exit_day
        settled = True

    exit_bar = series.get(exit_day)
    if exit_bar is None:
        return None
    exit_spot = exit_bar.close

    exit_value = 0.0
    exit_ivs: list[float] = []
    sources: set[str] = set()
    for leg in structure.legs:
        if leg.kind == "stock":
            slip = 1.0 - (book.costs.stock_spread_bps / 10000.0) * (1 if leg.quantity > 0 else -1)
            exit_value += leg.quantity * exit_spot * slip
            continue
        premium, iv, source = _exit_leg_premium(
            leg, book=book, exit_day=exit_day, exit_spot=exit_spot,
            expiry=expiry, baseline_vol=baseline_vol,
        )
        if source != "expiry":
            # Pay the spread again to close: longs sell, shorts buy back.
            premium = book.costs.fill_premium(premium, side=-1 if leg.quantity > 0 else +1)
        exit_value += leg.quantity * premium * leg.multiplier
        if iv is not None:
            exit_ivs.append(iv)
        sources.add(source)

    commissions = sum(
        book.costs.option_commission(leg.quantity) * (1 if settled else 2)
        for leg in structure.legs if leg.kind != "stock"
    )
    pnl = exit_value - structure.entry_cost - commissions
    capital = _capital_at_risk(structure, entry_spot)

    # --- diagnostics ---------------------------------------------------
    entry_ivs = [leg.entry_iv for leg in structure.legs if leg.entry_iv]
    entry_iv = sum(entry_ivs) / len(entry_ivs) if entry_ivs else None
    exit_iv = sum(exit_ivs) / len(exit_ivs) if exit_ivs else None

    hold_closes = [
        bar.close for bar in series.bars
        if entry_day <= bar.day <= exit_day
    ]
    hold_rv = None
    if len(hold_closes) >= 3:
        hold_rv = realized_vol(hold_closes, window=len(hold_closes) - 1)

    calendar_days = max(1, (exit_day - entry_day).days)
    implied_move = entry_iv * math.sqrt(calendar_days / 365.0) if entry_iv else None
    actual_move = abs(exit_spot / entry_spot - 1.0) if entry_spot > 0 else None
    vrp = (entry_iv - hold_rv) if (entry_iv and hold_rv) else None

    leg_sources = {leg.priced_from for leg in structure.legs if leg.kind != "stock"}
    if not leg_sources:
        priced_from = "stock_only"
    elif leg_sources == {"market"}:
        priced_from = "market"
    elif leg_sources == {"model"}:
        priced_from = "model"
    else:
        priced_from = "mixed"

    return Trade(
        strategy=strategy.name,
        ticker=event.ticker,
        accession=event.filing.accession,
        filing_date=event.filing.filing_date,
        acceptance_et=event.filing.acceptance_et.isoformat(),
        session_bucket=event.filing.session_bucket,
        event_types="|".join(event.event_types),
        entry_day=entry_day.isoformat(),
        exit_day=exit_day.isoformat(),
        expiry=expiry.isoformat() if expiry else None,
        hold_sessions=config.hold_sessions,
        entry_spot=entry_spot,
        exit_spot=exit_spot,
        underlying_return=(exit_spot / entry_spot - 1.0) if entry_spot > 0 else 0.0,
        entry_cost=structure.entry_cost,
        net_premium=structure.net_premium,
        exit_value=exit_value,
        pnl=pnl,
        return_on_capital=(pnl / capital) if capital > 0 else 0.0,
        capital_at_risk=capital,
        priced_from=priced_from,
        entry_iv=entry_iv,
        exit_iv=exit_iv,
        realized_vol_hold=hold_rv,
        implied_move=implied_move,
        actual_move=actual_move,
        vol_risk_premium=vrp,
        market_cap=event.market_cap,
        cap_bucket=event.cap_bucket,
        novelty_score=event.novelty.score if event.novelty else None,
        exec_severity=event.exec_change.severity if event.exec_change else None,
        confounded_by_earnings=event.confounded_by_earnings,
        settled_at_expiry=settled,
        structure=structure.describe(),
        reason=reason,
        extras={"timing": timing_note, "commissions": commissions},
    )


def run_backtest(
    events: list[EventRecord],
    strategies: list[Strategy],
    *,
    massive,
    config: BacktestConfig | None = None,
    date_gte: str | None = None,
    date_lte: str | None = None,
    fail_fast: bool = False,
) -> list[Trade]:
    """Run every strategy over every qualifying event."""
    cfg = config or BacktestConfig()
    trades: list[Trade] = []

    # Group events by ticker so each symbol's price series loads once.
    by_ticker: dict[str, list[EventRecord]] = {}
    for event in events:
        by_ticker.setdefault(event.ticker, []).append(event)

    for ticker, ticker_events in sorted(by_ticker.items()):
        start = date_gte or min(e.filing.filing_date for e in ticker_events)
        end = date_lte or max(e.filing.filing_date for e in ticker_events)
        try:
            from eightk.prices import load_series
            series = load_series(massive, ticker, start, end)
        except Exception:
            if fail_fast:
                raise
            logger.warning("price load failed for %s", ticker, exc_info=True)
            continue
        if len(series) < cfg.vol_window + 5:
            logger.info("skipping %s: only %d bars", ticker, len(series))
            continue

        book = OptionBook(
            massive, ticker, series,
            rate=cfg.rate, cost_model=cfg.cost_model,
        )

        for event in ticker_events:
            for strategy in strategies:
                qualifies, reason = strategy.applies(event)
                if not qualifies:
                    continue
                try:
                    trade = simulate_trade(
                        event=event, strategy=strategy, series=series,
                        book=book, config=cfg, reason=reason,
                    )
                except Exception:
                    if fail_fast:
                        raise
                    logger.warning(
                        "simulate failed: %s %s %s",
                        strategy.name, ticker, event.filing.accession, exc_info=True,
                    )
                    continue
                if trade is not None:
                    trades.append(trade)

        logger.info("%s: %d bars, option pricing %s", ticker, len(series), book.stats)

    logger.info("simulated %d trade(s)", len(trades))
    return trades


def trades_frame(trades: list[Trade]):
    """Trades as a pandas DataFrame."""
    import pandas as pd
    return pd.DataFrame([t.to_dict() for t in trades])
