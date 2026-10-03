"""The option structures under test, one per research question.

Each strategy answers a specific question about whether 8-K disclosure can
be traded, and each is paired with the structure a desk would actually use
rather than a generic long-option bet:

``exec_put``
    *If I had seen the 8-K when MongoDB's CEO left and acted on it, would I
    have made money?* A long put on a senior departure at a thinly covered
    issuer. Chosen over shorting the stock because the downside is what is
    being bought, the borrow is avoided, and the loss is capped at premium.

``efficiency_collar``
    *Does the market take time to price a restructuring whose costs land now
    and whose savings land in years?* Long stock, long put, short call. The
    collar is the structure named in the hypothesis: it funds downside
    protection by giving up upside, which is the right shape when the
    direction is uncertain but the distribution is skewed.

``novelty_shortvol``
    *Do options stay expensive relative to the move that actually follows a
    filing that revealed nothing new?* A short strangle on repeat filings.
    This is the only strategy that is short premium, and it is the direct
    test of whether the event premium was ever earned.

``combo``
    The combination requested: restructuring filings routed by novelty — a
    collar when the filing genuinely reveals the cost/savings mismatch, and
    short premium when it merely re-files a known announcement.

Two stock-only benchmarks are included so every option result can be judged
against the far simpler trade of just buying or shorting the underlying.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from eightk.events import EventRecord
from eightk.options_book import OptionBook
from eightk.options_model import Leg, Structure, delta_to_strike
from eightk.prices import PriceSeries

logger = logging.getLogger(__name__)


@dataclass
class TradeContext:
    """Everything a strategy needs to construct a position."""

    event: EventRecord
    series: PriceSeries
    book: OptionBook
    entry_day: date
    entry_spot: float
    reference_spot: float
    expiry: date | None
    baseline_vol: float
    target_notional: float = 10_000.0

    @property
    def days_to_expiry(self) -> int:
        return (self.expiry - self.entry_day).days if self.expiry else 0

    def contracts_for_notional(self) -> int:
        """Contract count approximating ``target_notional`` of exposure.

        Sizing every trade to the same underlying notional is what makes
        dollar P&L comparable across a $400 stock and an $8 stock.
        """
        per_contract = max(1.0, self.entry_spot * 100.0)
        return max(1, int(round(self.target_notional / per_contract)))


@dataclass
class StrategyConfig:
    """Tunable knobs shared by the option strategies."""

    min_days_to_expiry: int = 21
    max_days_to_expiry: int = 60
    put_delta: float = 0.35          # long put for the directional test
    collar_put_delta: float = 0.25
    collar_call_delta: float = 0.25
    strangle_delta: float = 0.20     # short strangle wings
    # Event selection
    min_severity: float = 0.35
    max_market_cap: float = 20e9     # "smaller company" ceiling
    min_market_cap: float = 1e8      # below this, options are untradable
    exclude_earnings_confounded: bool = True
    repeat_threshold: float = 0.40
    novel_threshold: float = 0.60


class Strategy:
    """Base class: decide whether an event qualifies, then build the trade."""

    name = "base"
    description = ""
    #: True when the position collects premium rather than paying it.
    is_short_premium = False

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()

    def applies(self, event: EventRecord) -> tuple[bool, str]:
        """Return ``(qualifies, reason)`` for one event."""
        raise NotImplementedError

    def build(self, ctx: TradeContext) -> Structure | None:
        """Construct the position, or ``None`` if it cannot be priced."""
        raise NotImplementedError

    # -------------------------------------------------------------- #
    # Shared selection helpers
    # -------------------------------------------------------------- #
    def _cap_ok(self, event: EventRecord) -> tuple[bool, str]:
        cap = event.market_cap
        if cap is None:
            # Unknown caps are kept: dropping them would quietly discard the
            # smallest, least-covered issuers, which are the population of
            # interest. They are tagged so results can be split later.
            return True, "cap_unknown"
        if cap > self.config.max_market_cap:
            return False, f"cap_too_large({cap/1e9:.1f}B)"
        if cap < self.config.min_market_cap:
            return False, f"cap_too_small({cap/1e6:.0f}M)"
        return True, "cap_ok"

    def _pick_expiry(self, ctx: TradeContext) -> date | None:
        return ctx.expiry


class ExecPutStrategy(Strategy):
    """Long put on a senior executive departure at a smaller issuer."""

    name = "exec_put"
    description = "Long put after an Item 5.02 senior departure"

    def applies(self, event: EventRecord) -> tuple[bool, str]:
        change = event.exec_change
        if change is None or not change.is_senior_departure:
            return False, "not_senior_departure"
        if change.comp_only:
            return False, "comp_only"
        if change.severity < self.config.min_severity:
            return False, f"severity_low({change.severity:.2f})"
        if self.config.exclude_earnings_confounded and event.confounded_by_earnings:
            return False, "earnings_confounded"
        ok, reason = self._cap_ok(event)
        if not ok:
            return False, reason
        return True, f"severity={change.severity:.2f},{reason}"

    def build(self, ctx: TradeContext) -> Structure | None:
        if ctx.expiry is None:
            return None
        tau = max(1, ctx.days_to_expiry) / 365.0
        target = delta_to_strike(
            ctx.entry_spot, self.config.put_delta, tau,
            ctx.baseline_vol, ctx.book.rate, kind="put",
        )
        contract = ctx.book.nearest_strike(
            ctx.entry_day, ctx.expiry, target, "put",
            min_days=self.config.min_days_to_expiry,
            max_days=self.config.max_days_to_expiry,
        )
        strike = contract.strike if contract else round(target, 1)
        priced = ctx.book.price_leg(
            as_of=ctx.entry_day, expiry=ctx.expiry, strike=strike, kind="put",
            spot=ctx.entry_spot, contract=contract, reference_spot=ctx.reference_spot,
        )
        fill = ctx.book.costs.fill_premium(priced.premium, side=+1)
        quantity = ctx.contracts_for_notional()
        return Structure(
            name=self.name,
            legs=[Leg(
                kind="put", strike=strike, quantity=quantity, entry_price=fill,
                expiry=ctx.expiry.isoformat(), ticker=contract.ticker if contract else None,
                entry_iv=priced.iv, priced_from=priced.source,
            )],
        )


class EfficiencyCollarStrategy(Strategy):
    """Collar around a restructuring / efficiency-plan disclosure."""

    name = "efficiency_collar"
    description = "Long stock + long put + short call after an efficiency plan 8-K"

    def applies(self, event: EventRecord) -> tuple[bool, str]:
        plan = event.plan
        if plan is None or not plan.is_plan:
            return False, "not_a_plan"
        if "efficiency_plan" not in event.event_types:
            return False, "plan_not_quantified"
        if self.config.exclude_earnings_confounded and event.confounded_by_earnings:
            return False, "earnings_confounded"
        ok, reason = self._cap_ok(event)
        if not ok:
            return False, reason
        detail = []
        if plan.charge_usd:
            detail.append(f"charge={plan.charge_usd/1e6:.0f}M")
        if plan.savings_usd:
            detail.append(f"savings={plan.savings_usd/1e6:.0f}M")
        if plan.payback_years:
            detail.append(f"payback={plan.payback_years:.1f}y")
        return True, ",".join(detail) or reason

    def build(self, ctx: TradeContext) -> Structure | None:
        if ctx.expiry is None:
            return None
        tau = max(1, ctx.days_to_expiry) / 365.0
        quantity = ctx.contracts_for_notional()
        shares = quantity * 100

        put_target = delta_to_strike(
            ctx.entry_spot, self.config.collar_put_delta, tau,
            ctx.baseline_vol, ctx.book.rate, kind="put",
        )
        call_target = delta_to_strike(
            ctx.entry_spot, self.config.collar_call_delta, tau,
            ctx.baseline_vol, ctx.book.rate, kind="call",
        )
        put_contract = ctx.book.nearest_strike(
            ctx.entry_day, ctx.expiry, put_target, "put",
            min_days=self.config.min_days_to_expiry, max_days=self.config.max_days_to_expiry,
        )
        call_contract = ctx.book.nearest_strike(
            ctx.entry_day, ctx.expiry, call_target, "call",
            min_days=self.config.min_days_to_expiry, max_days=self.config.max_days_to_expiry,
        )
        put_strike = put_contract.strike if put_contract else round(put_target, 1)
        call_strike = call_contract.strike if call_contract else round(call_target, 1)

        put_priced = ctx.book.price_leg(
            as_of=ctx.entry_day, expiry=ctx.expiry, strike=put_strike, kind="put",
            spot=ctx.entry_spot, contract=put_contract, reference_spot=ctx.reference_spot,
        )
        call_priced = ctx.book.price_leg(
            as_of=ctx.entry_day, expiry=ctx.expiry, strike=call_strike, kind="call",
            spot=ctx.entry_spot, contract=call_contract, reference_spot=ctx.reference_spot,
        )

        stock_fill = ctx.entry_spot * (1.0 + ctx.book.costs.stock_spread_bps / 10000.0)
        return Structure(
            name=self.name,
            legs=[
                Leg(kind="stock", strike=None, quantity=shares, entry_price=stock_fill),
                Leg(
                    kind="put", strike=put_strike, quantity=quantity,
                    entry_price=ctx.book.costs.fill_premium(put_priced.premium, side=+1),
                    expiry=ctx.expiry.isoformat(),
                    ticker=put_contract.ticker if put_contract else None,
                    entry_iv=put_priced.iv, priced_from=put_priced.source,
                ),
                Leg(
                    kind="call", strike=call_strike, quantity=-quantity,
                    entry_price=ctx.book.costs.fill_premium(call_priced.premium, side=-1),
                    expiry=ctx.expiry.isoformat(),
                    ticker=call_contract.ticker if call_contract else None,
                    entry_iv=call_priced.iv, priced_from=call_priced.source,
                ),
            ],
        )


class NoveltyShortVolStrategy(Strategy):
    """Short strangle on a filing that revealed nothing new."""

    name = "novelty_shortvol"
    description = "Short strangle after a low-novelty (repeat) 8-K"
    is_short_premium = True

    def applies(self, event: EventRecord) -> tuple[bool, str]:
        novelty = event.novelty
        if novelty is None:
            return False, "no_novelty_score"
        if novelty.score >= self.config.repeat_threshold:
            return False, f"novel({novelty.score:.2f})"
        if self.config.exclude_earnings_confounded and event.confounded_by_earnings:
            return False, "earnings_confounded"
        ok, reason = self._cap_ok(event)
        if not ok:
            return False, reason
        return True, f"novelty={novelty.score:.2f},lag={novelty.report_lag_days}d"

    def build(self, ctx: TradeContext) -> Structure | None:
        if ctx.expiry is None:
            return None
        tau = max(1, ctx.days_to_expiry) / 365.0
        quantity = ctx.contracts_for_notional()

        put_target = delta_to_strike(
            ctx.entry_spot, self.config.strangle_delta, tau,
            ctx.baseline_vol, ctx.book.rate, kind="put",
        )
        call_target = delta_to_strike(
            ctx.entry_spot, self.config.strangle_delta, tau,
            ctx.baseline_vol, ctx.book.rate, kind="call",
        )
        put_contract = ctx.book.nearest_strike(
            ctx.entry_day, ctx.expiry, put_target, "put",
            min_days=self.config.min_days_to_expiry, max_days=self.config.max_days_to_expiry,
        )
        call_contract = ctx.book.nearest_strike(
            ctx.entry_day, ctx.expiry, call_target, "call",
            min_days=self.config.min_days_to_expiry, max_days=self.config.max_days_to_expiry,
        )
        put_strike = put_contract.strike if put_contract else round(put_target, 1)
        call_strike = call_contract.strike if call_contract else round(call_target, 1)

        put_priced = ctx.book.price_leg(
            as_of=ctx.entry_day, expiry=ctx.expiry, strike=put_strike, kind="put",
            spot=ctx.entry_spot, contract=put_contract, reference_spot=ctx.reference_spot,
        )
        call_priced = ctx.book.price_leg(
            as_of=ctx.entry_day, expiry=ctx.expiry, strike=call_strike, kind="call",
            spot=ctx.entry_spot, contract=call_contract, reference_spot=ctx.reference_spot,
        )
        return Structure(
            name=self.name,
            legs=[
                Leg(
                    kind="put", strike=put_strike, quantity=-quantity,
                    entry_price=ctx.book.costs.fill_premium(put_priced.premium, side=-1),
                    expiry=ctx.expiry.isoformat(),
                    ticker=put_contract.ticker if put_contract else None,
                    entry_iv=put_priced.iv, priced_from=put_priced.source,
                ),
                Leg(
                    kind="call", strike=call_strike, quantity=-quantity,
                    entry_price=ctx.book.costs.fill_premium(call_priced.premium, side=-1),
                    expiry=ctx.expiry.isoformat(),
                    ticker=call_contract.ticker if call_contract else None,
                    entry_iv=call_priced.iv, priced_from=call_priced.source,
                ),
            ],
        )


class ComboStrategy(Strategy):
    """Efficiency-plan filings routed by whether they actually revealed news.

    This is the requested combination of the first two ideas. A restructuring
    8-K that genuinely discloses the cost/savings mismatch gets the collar —
    protection against a market that has not finished reading it. One that
    merely re-files a known announcement gets short premium instead, because
    there the option market is charging for an event that already happened.
    """

    name = "combo"
    description = "Efficiency-plan 8-K: collar when novel, short strangle when repeat"

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config)
        self._collar = EfficiencyCollarStrategy(self.config)
        self._shortvol = NoveltyShortVolStrategy(self.config)

    def _route(self, event: EventRecord) -> Strategy:
        novelty = event.novelty
        if novelty is not None and novelty.score < self.config.repeat_threshold:
            return self._shortvol
        return self._collar

    def applies(self, event: EventRecord) -> tuple[bool, str]:
        plan = event.plan
        if plan is None or "efficiency_plan" not in event.event_types:
            return False, "not_a_plan"
        if self.config.exclude_earnings_confounded and event.confounded_by_earnings:
            return False, "earnings_confounded"
        ok, reason = self._cap_ok(event)
        if not ok:
            return False, reason
        route = self._route(event)
        score = event.novelty.score if event.novelty else float("nan")
        return True, f"route={route.name},novelty={score:.2f}"

    def build(self, ctx: TradeContext) -> Structure | None:
        route = self._route(ctx.event)
        structure = route.build(ctx)
        if structure is not None:
            # Keep the routed leg shape but report under the combo name so
            # the blended track record is readable on its own.
            structure.name = f"{self.name}:{route.name}"
        return structure


class StockBenchmark(Strategy):
    """Stock-only control: hold the underlying over the same window.

    Every option result has to beat the obvious alternative of simply taking
    the position in the stock, so the same event set is run through this.
    """

    name = "stock_long"
    description = "Long the underlying over the same holding window"
    _direction = 1

    def __init__(self, config: StrategyConfig | None = None, selector: Strategy | None = None):
        super().__init__(config)
        # Mirrors another strategy's event selection so the comparison is
        # like-for-like rather than across different event sets.
        self.selector = selector or ExecPutStrategy(self.config)

    def applies(self, event: EventRecord) -> tuple[bool, str]:
        return self.selector.applies(event)

    def build(self, ctx: TradeContext) -> Structure | None:
        shares = ctx.contracts_for_notional() * 100 * self._direction
        slippage = 1.0 + (ctx.book.costs.stock_spread_bps / 10000.0) * self._direction
        return Structure(
            name=self.name,
            legs=[Leg(kind="stock", strike=None, quantity=shares,
                      entry_price=ctx.entry_spot * slippage)],
        )


class StockShortBenchmark(StockBenchmark):
    """Short the underlying — the direct alternative to buying a put."""

    name = "stock_short"
    description = "Short the underlying over the same holding window"
    _direction = -1


def default_strategies(config: StrategyConfig | None = None) -> list[Strategy]:
    """The full test set, including controls."""
    cfg = config or StrategyConfig()
    exec_strategy = ExecPutStrategy(cfg)
    return [
        exec_strategy,
        EfficiencyCollarStrategy(cfg),
        NoveltyShortVolStrategy(cfg),
        ComboStrategy(cfg),
        StockShortBenchmark(cfg, selector=exec_strategy),
        StockBenchmark(cfg, selector=EfficiencyCollarStrategy(cfg)),
    ]
