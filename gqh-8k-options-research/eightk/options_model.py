"""Black-Scholes pricing, implied-vol inversion, and trade structures.

Real option bars from Massive drive the backtest wherever they exist. This
module covers the three jobs that market bars alone cannot do:

  * **Invert** a traded premium into an implied vol, so "were options
    expensive relative to the move that followed?" becomes a measurable
    question rather than a vibe.
  * **Interpolate** a fair premium when a specific strike did not trade on
    the day an event required it — thin small-cap chains have gaps, and
    dropping those events would bias the sample toward liquid names.
  * **Decompose** a structure (collar, straddle, strangle) into legs with
    known greeks, so the P&L attributes to direction versus volatility.

Every modeled premium is tagged as modeled in the results, so a reader can
always separate measured fills from inferred ones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq
from scipy.stats import norm

# Trading days per calendar year, used to annualize realized vol.
TRADING_DAYS = 252
# Floor on time-to-expiry so pricing stays finite on expiration day.
MIN_TAU = 1.0 / (TRADING_DAYS * 6.5 * 60)


def year_fraction(days: float) -> float:
    """Convert calendar days to a year fraction, floored to stay positive."""
    return max(MIN_TAU, float(days) / 365.0)


# ---------------------------------------------------------------------- #
# Black-Scholes
# ---------------------------------------------------------------------- #


def bs_price(
    spot: float,
    strike: float,
    tau: float,
    vol: float,
    rate: float = 0.04,
    dividend: float = 0.0,
    kind: str = "call",
) -> float:
    """Black-Scholes-Merton price for a European option.

    ``tau`` is in years, ``vol`` and ``rate`` are annualized decimals. At
    zero vol or zero time the formula degenerates, so the discounted
    intrinsic value is returned instead of dividing by zero.
    """
    spot = float(spot)
    strike = float(strike)
    is_call = kind.lower().startswith("c")

    if tau <= MIN_TAU or vol <= 0.0:
        intrinsic = (spot - strike) if is_call else (strike - spot)
        return max(0.0, intrinsic)

    sqrt_tau = math.sqrt(tau)
    d1 = (math.log(spot / strike) + (rate - dividend + 0.5 * vol * vol) * tau) / (vol * sqrt_tau)
    d2 = d1 - vol * sqrt_tau
    disc_r = math.exp(-rate * tau)
    disc_q = math.exp(-dividend * tau)

    if is_call:
        return spot * disc_q * norm.cdf(d1) - strike * disc_r * norm.cdf(d2)
    return strike * disc_r * norm.cdf(-d2) - spot * disc_q * norm.cdf(-d1)


@dataclass(frozen=True)
class Greeks:
    """First- and second-order sensitivities, per one contract-share."""

    delta: float
    gamma: float
    vega: float      # per 1.00 (100 vol points) change in vol
    theta: float     # per calendar day
    rho: float


def bs_greeks(
    spot: float,
    strike: float,
    tau: float,
    vol: float,
    rate: float = 0.04,
    dividend: float = 0.0,
    kind: str = "call",
) -> Greeks:
    """Analytic Black-Scholes greeks."""
    is_call = kind.lower().startswith("c")
    if tau <= MIN_TAU or vol <= 0.0:
        # At expiry delta is a step function and the rest vanish.
        if is_call:
            return Greeks(1.0 if spot > strike else 0.0, 0.0, 0.0, 0.0, 0.0)
        return Greeks(-1.0 if spot < strike else 0.0, 0.0, 0.0, 0.0, 0.0)

    sqrt_tau = math.sqrt(tau)
    d1 = (math.log(spot / strike) + (rate - dividend + 0.5 * vol * vol) * tau) / (vol * sqrt_tau)
    d2 = d1 - vol * sqrt_tau
    pdf_d1 = norm.pdf(d1)
    disc_r = math.exp(-rate * tau)
    disc_q = math.exp(-dividend * tau)

    gamma = disc_q * pdf_d1 / (spot * vol * sqrt_tau)
    vega = spot * disc_q * pdf_d1 * sqrt_tau
    if is_call:
        delta = disc_q * norm.cdf(d1)
        theta = (
            -spot * disc_q * pdf_d1 * vol / (2 * sqrt_tau)
            - rate * strike * disc_r * norm.cdf(d2)
            + dividend * spot * disc_q * norm.cdf(d1)
        ) / 365.0
        rho = strike * tau * disc_r * norm.cdf(d2) / 100.0
    else:
        delta = -disc_q * norm.cdf(-d1)
        theta = (
            -spot * disc_q * pdf_d1 * vol / (2 * sqrt_tau)
            + rate * strike * disc_r * norm.cdf(-d2)
            - dividend * spot * disc_q * norm.cdf(-d1)
        ) / 365.0
        rho = -strike * tau * disc_r * norm.cdf(-d2) / 100.0

    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def implied_vol(
    price: float,
    spot: float,
    strike: float,
    tau: float,
    rate: float = 0.04,
    dividend: float = 0.0,
    kind: str = "call",
    lo: float = 1e-4,
    hi: float = 6.0,
) -> float | None:
    """Invert a premium into an implied volatility.

    Returns ``None`` when the quote is not invertible: below intrinsic,
    above the no-arbitrage ceiling, or outside the ``[lo, hi]`` vol bracket.
    Thin small-cap option bars produce such quotes often enough that silently
    clamping them would corrupt the expensive-vs-cheap comparison this
    research turns on.
    """
    price = float(price)
    if price <= 0 or tau <= MIN_TAU:
        return None

    is_call = kind.lower().startswith("c")
    disc_r = math.exp(-rate * tau)
    disc_q = math.exp(-dividend * tau)
    intrinsic = max(0.0, (spot * disc_q - strike * disc_r) if is_call else (strike * disc_r - spot * disc_q))
    ceiling = spot * disc_q if is_call else strike * disc_r
    if price < intrinsic - 1e-9 or price > ceiling + 1e-9:
        return None

    def objective(vol: float) -> float:
        return bs_price(spot, strike, tau, vol, rate, dividend, kind) - price

    try:
        if objective(lo) > 0 or objective(hi) < 0:
            return None
        return float(brentq(objective, lo, hi, xtol=1e-6, maxiter=100))
    except (ValueError, RuntimeError):
        return None


def delta_to_strike(
    spot: float,
    target_delta: float,
    tau: float,
    vol: float,
    rate: float = 0.04,
    dividend: float = 0.0,
    kind: str = "call",
) -> float:
    """Strike whose Black-Scholes delta equals ``target_delta``.

    Collars are specified in delta terms ("25-delta put, 25-delta call")
    because that keeps the structure comparable across names with very
    different volatilities, which a fixed percentage moneyness would not.
    """
    target = abs(float(target_delta))
    target = min(max(target, 1e-4), 0.9999)
    sqrt_tau = math.sqrt(tau)
    # Invert the closed form for delta: N(d1) = target (calls).
    if kind.lower().startswith("c"):
        d1 = norm.ppf(target * math.exp(dividend * tau))
    else:
        d1 = -norm.ppf(target * math.exp(dividend * tau))
    return float(spot * math.exp(-(d1 * vol * sqrt_tau) + (rate - dividend + 0.5 * vol * vol) * tau))


# ---------------------------------------------------------------------- #
# Realized volatility and an event-aware vol estimate
# ---------------------------------------------------------------------- #


def realized_vol(closes: list[float], window: int = 20) -> float | None:
    """Annualized close-to-close realized volatility over ``window`` days."""
    prices = [float(p) for p in closes if p and p > 0]
    if len(prices) < window + 1:
        return None
    rets = [math.log(prices[i] / prices[i - 1]) for i in range(len(prices) - window, len(prices))]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var * TRADING_DAYS)


def modeled_event_iv(
    base_vol: float,
    *,
    event_premium: float = 0.35,
    days_to_expiry: float = 30.0,
) -> float:
    """Estimate pre-event implied vol from realized vol plus a premium.

    Single-name options trade above realized vol into a scheduled catalyst,
    and the shorter the remaining life the more of that event risk the
    quoted vol has to carry. This is a stand-in used only when a strike has
    no traded bar; it is deliberately conservative, since overstating
    pre-event IV would flatter every short-volatility result here.
    """
    base = max(0.05, float(base_vol))
    # Concentration factor: a 7-day option carries the event in a fifth of
    # the calendar a 35-day option spreads it over.
    concentration = math.sqrt(30.0 / max(5.0, float(days_to_expiry)))
    return base * (1.0 + event_premium * concentration)


# ---------------------------------------------------------------------- #
# Structures
# ---------------------------------------------------------------------- #


@dataclass
class Leg:
    """One option or stock leg of a structure.

    ``quantity`` is signed in contracts (or shares for stock): positive is
    long, negative is short. ``entry_price`` is per share, so a premium of
    4.20 means $420 for a 100-share contract.
    """

    kind: str                  # "call" | "put" | "stock"
    strike: float | None
    quantity: float
    entry_price: float
    expiry: str | None = None
    ticker: str | None = None
    multiplier: int = 100
    entry_iv: float | None = None
    priced_from: str = "model"  # "market" | "model"

    @property
    def notional_cost(self) -> float:
        """Signed cash paid at entry (negative means premium received)."""
        mult = 1 if self.kind == "stock" else self.multiplier
        return self.quantity * self.entry_price * mult

    def payoff_at(self, spot: float) -> float:
        """Terminal value of the leg if held to expiry at ``spot``."""
        mult = 1 if self.kind == "stock" else self.multiplier
        if self.kind == "stock":
            value = spot
        elif self.kind == "call":
            value = max(0.0, spot - float(self.strike))
        else:
            value = max(0.0, float(self.strike) - spot)
        return self.quantity * value * mult

    def value_at(
        self,
        spot: float,
        tau: float,
        vol: float,
        rate: float = 0.04,
        dividend: float = 0.0,
    ) -> float:
        """Mark-to-model value of the leg before expiry."""
        if self.kind == "stock":
            return self.quantity * spot
        price = bs_price(spot, float(self.strike), tau, vol, rate, dividend, self.kind)
        return self.quantity * price * self.multiplier


@dataclass
class Structure:
    """A named multi-leg position with cash-flow and payoff accounting."""

    name: str
    legs: list[Leg]

    @property
    def entry_cost(self) -> float:
        """Net cash outlay at entry; negative is a net credit."""
        return sum(leg.notional_cost for leg in self.legs)

    @property
    def net_premium(self) -> float:
        """Net option premium only, excluding any stock leg."""
        return sum(leg.notional_cost for leg in self.legs if leg.kind != "stock")

    @property
    def used_market_prices(self) -> bool:
        """True when every option leg was filled from a traded bar."""
        option_legs = [leg for leg in self.legs if leg.kind != "stock"]
        return bool(option_legs) and all(leg.priced_from == "market" for leg in option_legs)

    def payoff_at(self, spot: float) -> float:
        return sum(leg.payoff_at(spot) for leg in self.legs)

    def pnl_at_expiry(self, spot: float) -> float:
        return self.payoff_at(spot) - self.entry_cost

    def pnl_marked(
        self,
        spot: float,
        tau: float,
        vol: float,
        rate: float = 0.04,
        dividend: float = 0.0,
    ) -> float:
        """P&L if the structure were closed now at modeled values."""
        value = sum(leg.value_at(spot, tau, vol, rate, dividend) for leg in self.legs)
        return value - self.entry_cost

    def delta(self, spot: float, tau: float, vol: float, rate: float = 0.04) -> float:
        """Net position delta in share-equivalents."""
        total = 0.0
        for leg in self.legs:
            if leg.kind == "stock":
                total += leg.quantity
                continue
            greeks = bs_greeks(spot, float(leg.strike), tau, vol, rate, 0.0, leg.kind)
            total += leg.quantity * greeks.delta * leg.multiplier
        return total

    def describe(self) -> str:
        parts = []
        for leg in self.legs:
            side = "+" if leg.quantity > 0 else "-"
            if leg.kind == "stock":
                parts.append(f"{side}{abs(leg.quantity):.0f}sh @{leg.entry_price:.2f}")
            else:
                tag = "" if leg.priced_from == "market" else "~"
                parts.append(
                    f"{side}{abs(leg.quantity):.0f} {leg.kind[0].upper()}"
                    f"{leg.strike:.1f} @{tag}{leg.entry_price:.2f}"
                )
        return f"{self.name}[{' '.join(parts)}]"
