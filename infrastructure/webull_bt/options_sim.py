"""Synthetic equity-options pricing for Backtrader event strategies.

Webull feeds in this starter are equity-only. When a Massive Options plan is
unavailable, positions are marked with Black–Scholes using the underlying
bar path (Webull) and realized volatility (ATR%). Contract multipliers follow
the standard US equity option (100 shares).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_price(
    spot: float,
    strike: float,
    years: float,
    rate: float,
    volatility: float,
    option_type: str,
) -> float:
    """European BS premium per share. ``option_type`` is 'call' or 'put'."""
    if spot <= 0 or strike <= 0:
        return 0.0
    years = max(years, 1.0 / 365.0)
    volatility = max(volatility, 1e-4)
    vol_sqrt_t = volatility * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * volatility * volatility) * years) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    if option_type == "call":
        return spot * _norm_cdf(d1) - strike * math.exp(-rate * years) * _norm_cdf(d2)
    return strike * math.exp(-rate * years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def annualized_vol_from_atr(atr: float, spot: float) -> float:
    """Rough annualized vol from daily ATR as a fraction of spot."""
    if spot <= 0 or atr <= 0:
        return 0.35
    daily = atr / spot
    return max(0.15, min(1.50, daily * math.sqrt(252.0)))


@dataclass
class OptionPosition:
    """Long or short call/put tracked with synthetic BS marks.

    ``side`` is ``\"long\"`` (debit) or ``\"short\"`` (credit). Short marks are
    liabilities: P&L rises when the option cheapens (IV crush / favorable spot).
    """

    symbol: str
    option_type: str  # call | put
    strike: float
    expiry: date
    contracts: int
    entry_premium: float
    entry_underlying: float
    entry_date: date
    entry_bar: int
    polarity: int = 0
    side: str = "long"  # long | short
    primary_category: str | None = None
    tertiary_category: str | None = None
    rate: float = 0.04
    entry_vol: float = 0.4
    meta: dict = field(default_factory=dict)

    def years_to_expiry(self, asof: date) -> float:
        days = max((self.expiry - asof).days, 0)
        return days / 365.0

    def premium(self, spot: float, asof: date, vol: float | None = None) -> float:
        return black_scholes_price(
            spot=spot,
            strike=self.strike,
            years=self.years_to_expiry(asof),
            rate=self.rate,
            volatility=vol if vol is not None else self.entry_vol,
            option_type=self.option_type,
        )

    def market_value(self, spot: float, asof: date, vol: float | None = None) -> float:
        """Mark-to-market equity impact of the option book.

        Long: positive asset value. Short: negative liability (premium to buy back).
        """
        raw = self.premium(spot, asof, vol) * 100.0 * self.contracts
        return raw if self.side == "long" else -raw

    def cost_basis(self) -> float:
        """Cash paid (long, positive) or received (short, negative credit)."""
        raw = self.entry_premium * 100.0 * self.contracts
        return raw if self.side == "long" else -raw

    def pnl(self, spot: float, asof: date, vol: float | None = None) -> float:
        return self.market_value(spot, asof, vol) - self.cost_basis()

    @property
    def is_short(self) -> bool:
        return self.side == "short"


def nearest_friday(after: date, weeks: int = 4) -> date:
    """Pick an expiry roughly ``weeks`` weeks out on a Friday."""
    target = after + timedelta(days=7 * weeks)
    # Friday = weekday 4
    offset = (4 - target.weekday()) % 7
    return target + timedelta(days=offset)


def round_strike(spot: float) -> float:
    """ATM-ish strike rounding by price level."""
    if spot >= 200:
        step = 5.0
    elif spot >= 50:
        step = 2.5
    elif spot >= 20:
        step = 1.0
    else:
        step = 0.5
    return round(spot / step) * step
