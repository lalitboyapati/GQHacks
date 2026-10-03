"""Price option legs from real market bars, with a documented fallback.

Two problems have to be solved to put a dated price on an option leg.

**Timing mismatch.** A daily option bar summarizes a whole session, but an
event trade enters at a specific moment — the open, after a pre-market
filing. Taking the option's own open would mean trusting the single thinnest
print of the day on a small-cap contract. Instead the observed premium is
inverted into an implied volatility against the underlying's reference price
for that session, and the leg is then re-priced at the actual entry spot
using that volatility. Market information sets the vol; the model only moves
the premium along the underlying.

**Chain gaps.** Small-cap chains are sparse, and a strike that an event
required may not have traded at all. Rather than drop those events — which
would bias the sample toward the most liquid names, exactly the ones least
likely to show a disclosure edge — the leg is priced from a volatility
estimate and tagged ``model`` so modeled and measured fills can always be
reported separately.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from eightk.massive_src import Bar, OptionContract
from eightk.options_model import (
    bs_price,
    implied_vol,
    modeled_event_iv,
    realized_vol,
    year_fraction,
)
from eightk.prices import PriceSeries

logger = logging.getLogger(__name__)


@dataclass
class PricedLeg:
    """A resolved option price for one contract on one date."""

    premium: float
    iv: float | None
    source: str              # "market" | "model"
    contract: OptionContract | None = None
    option_bar: Bar | None = None


@dataclass
class CostModel:
    """Execution costs applied to every option fill.

    Small-cap option spreads are wide, and a backtest that ignores them can
    manufacture an edge out of nothing. ``spread_pct_of_premium`` is charged
    adversely on entry *and* exit, so a round trip pays it twice.
    """

    spread_pct_of_premium: float = 0.04   # half-spread as a share of premium
    min_spread_abs: float = 0.02          # floor in dollars per share
    commission_per_contract: float = 0.65
    stock_spread_bps: float = 2.0         # on any stock leg

    def fill_premium(self, mid: float, side: int) -> float:
        """Adjust a mid premium to an executable price.

        ``side`` is +1 when buying (pay up) and -1 when selling (receive
        less).
        """
        haircut = max(self.min_spread_abs, abs(mid) * self.spread_pct_of_premium)
        filled = mid + side * haircut
        return max(0.01, filled)

    def option_commission(self, contracts: float) -> float:
        return abs(contracts) * self.commission_per_contract


class OptionBook:
    """Resolves contracts and prices legs for a single underlying."""

    def __init__(
        self,
        massive,
        underlying: str,
        series: PriceSeries,
        *,
        rate: float = 0.04,
        cost_model: CostModel | None = None,
        event_iv_premium: float = 0.35,
    ):
        self.massive = massive
        self.underlying = underlying.upper()
        self.series = series
        self.rate = rate
        self.costs = cost_model or CostModel()
        self.event_iv_premium = event_iv_premium
        self._contract_cache: dict[tuple, list[OptionContract]] = {}
        self._bar_cache: dict[tuple[str, str, str], list[Bar]] = {}
        self.stats = {"market": 0, "model": 0, "no_contract": 0}

    # ------------------------------------------------------------------ #
    # Contract discovery
    # ------------------------------------------------------------------ #
    def contracts(
        self,
        as_of: date,
        *,
        min_days: int = 21,
        max_days: int = 60,
        contract_type: str | None = None,
    ) -> list[OptionContract]:
        """Contracts listed on ``as_of`` expiring in the day-count window."""
        key = (as_of.isoformat(), min_days, max_days, contract_type)
        if key in self._contract_cache:
            return self._contract_cache[key]
        from datetime import timedelta
        try:
            found = self.massive.option_contracts(
                self.underlying,
                as_of=as_of.isoformat(),
                expiration_gte=(as_of + timedelta(days=min_days)).isoformat(),
                expiration_lte=(as_of + timedelta(days=max_days)).isoformat(),
                contract_type=contract_type,
            )
        except Exception:
            logger.debug("contract lookup failed for %s on %s",
                         self.underlying, as_of, exc_info=True)
            found = []
        self._contract_cache[key] = found
        return found

    def choose_expiry(self, as_of: date, min_days: int = 21, max_days: int = 60) -> date | None:
        """Nearest expiry at least ``min_days`` out.

        Short-dated options carry the event in the least calendar, which is
        where a disclosure edge should be largest, but anything expiring
        within days turns the trade into a coin flip on gamma.
        """
        found = self.contracts(as_of, min_days=min_days, max_days=max_days)
        if not found:
            return None
        return min(contract.expiration for contract in found)

    def nearest_strike(
        self,
        as_of: date,
        expiry: date,
        target_strike: float,
        kind: str,
        *,
        min_days: int = 21,
        max_days: int = 60,
    ) -> OptionContract | None:
        """Listed contract closest to ``target_strike`` at ``expiry``."""
        wanted = "call" if kind.lower().startswith("c") else "put"
        candidates = [
            c for c in self.contracts(as_of, min_days=min_days, max_days=max_days)
            if c.expiration == expiry and c.contract_type.lower().startswith(wanted[0])
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda c: abs(c.strike - target_strike))

    # ------------------------------------------------------------------ #
    # Option bars
    # ------------------------------------------------------------------ #
    def option_bar(self, ticker: str, day: date, search_back: int = 3) -> Bar | None:
        """The option's bar for ``day``, or the most recent one just before.

        A contract that did not trade on the exact session is common in thin
        chains; a bar from a session or two earlier still reflects real
        market vol, which is the only thing taken from it.
        """
        start = (day.toordinal() - search_back - 4)
        key = (ticker, date.fromordinal(start).isoformat(), day.isoformat())
        if key not in self._bar_cache:
            try:
                self._bar_cache[key] = self.massive.daily_bars(
                    ticker, date.fromordinal(start).isoformat(), day.isoformat(),
                    adjusted=False,
                )
            except Exception:
                logger.debug("option bars failed for %s", ticker, exc_info=True)
                self._bar_cache[key] = []
        bars = self._bar_cache[key]
        exact = [b for b in bars if b.day == day]
        if exact:
            return exact[0]
        earlier = [b for b in bars if b.day < day]
        return earlier[-1] if earlier else None

    # ------------------------------------------------------------------ #
    # Volatility
    # ------------------------------------------------------------------ #
    def baseline_vol(self, day: date, window: int = 20) -> float:
        """Pre-event realized vol, used to anchor modeled prices."""
        closes = self.series.closes_before(day, window + 5)
        vol = realized_vol(closes, window=window)
        return vol if vol and vol > 0.05 else 0.45  # small-cap default

    # ------------------------------------------------------------------ #
    # Leg pricing
    # ------------------------------------------------------------------ #
    def price_leg(
        self,
        *,
        as_of: date,
        expiry: date,
        strike: float,
        kind: str,
        spot: float,
        contract: OptionContract | None = None,
        reference_spot: float | None = None,
        fallback_iv: float | None = None,
    ) -> PricedLeg:
        """Price one option leg at ``spot`` for a trade dated ``as_of``.

        :param spot: the underlying price at the intended execution moment.
        :param reference_spot: the underlying price corresponding to the
            option bar used for inversion (that session's VWAP or close).
        """
        tau = year_fraction((expiry - as_of).days)

        if contract is not None:
            bar = self.option_bar(contract.ticker, as_of)
            if bar is not None and bar.mid_proxy > 0:
                ref = reference_spot
                if ref is None:
                    ref_bar = self.series.get(bar.day)
                    ref = (ref_bar.vwap or ref_bar.close) if ref_bar else spot
                ref_tau = year_fraction((expiry - bar.day).days)
                iv = implied_vol(
                    bar.mid_proxy, ref, strike, ref_tau, self.rate, 0.0, kind,
                )
                if iv is not None:
                    premium = bs_price(spot, strike, tau, iv, self.rate, 0.0, kind)
                    self.stats["market"] += 1
                    return PricedLeg(
                        premium=premium, iv=iv, source="market",
                        contract=contract, option_bar=bar,
                    )

        # Fallback: no tradable bar, or a quote that would not invert.
        base = self.baseline_vol(as_of)
        iv = fallback_iv or modeled_event_iv(
            base,
            event_premium=self.event_iv_premium,
            days_to_expiry=max(1.0, (expiry - as_of).days),
        )
        premium = bs_price(spot, strike, tau, iv, self.rate, 0.0, kind)
        if contract is None:
            self.stats["no_contract"] += 1
        self.stats["model"] += 1
        return PricedLeg(premium=premium, iv=iv, source="model", contract=contract)
