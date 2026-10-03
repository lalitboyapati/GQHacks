"""Tests for option pricing, structures, and risk accounting."""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))
os.environ.setdefault("GQH_TRACK", "disclosure_advantage")

from eightk.options_model import (
    Leg,
    Structure,
    bs_greeks,
    bs_price,
    delta_to_strike,
    implied_vol,
    modeled_event_iv,
    realized_vol,
)


class TestBlackScholes:
    def test_put_call_parity(self):
        spot, strike, tau, vol, rate = 100.0, 95.0, 0.5, 0.35, 0.04
        call = bs_price(spot, strike, tau, vol, rate, kind="call")
        put = bs_price(spot, strike, tau, vol, rate, kind="put")
        assert call - put == pytest.approx(spot - strike * math.exp(-rate * tau), abs=1e-9)

    def test_zero_vol_is_intrinsic(self):
        assert bs_price(100, 90, 0.5, 0.0, 0.0, kind="call") == pytest.approx(10.0)
        assert bs_price(100, 110, 0.5, 0.0, 0.0, kind="put") == pytest.approx(10.0)

    def test_price_increases_with_vol(self):
        prices = [bs_price(100, 100, 0.25, v, 0.04, kind="call") for v in (0.2, 0.4, 0.8)]
        assert prices == sorted(prices)

    def test_implied_vol_round_trip(self):
        for vol in (0.15, 0.45, 1.2):
            price = bs_price(100, 105, 0.3, vol, 0.04, kind="put")
            assert implied_vol(price, 100, 105, 0.3, 0.04, kind="put") == pytest.approx(vol, abs=1e-5)

    def test_uninvertible_quotes_return_none(self):
        """Below-intrinsic and above-ceiling quotes must not be forced.

        Thin small-cap option bars produce these regularly, and clamping
        them to a bracket endpoint would corrupt the implied-vs-realized
        comparison the research depends on.
        """
        assert implied_vol(0.01, 100, 50, 0.25, kind="call") is None   # below intrinsic
        assert implied_vol(500.0, 100, 100, 0.25, kind="call") is None  # above ceiling
        assert implied_vol(-1.0, 100, 100, 0.25, kind="call") is None

    def test_delta_to_strike_inverts_delta(self):
        for target in (0.1, 0.25, 0.5):
            for kind in ("call", "put"):
                strike = delta_to_strike(100, target, 0.25, 0.4, 0.04, kind=kind)
                delta = bs_greeks(100, strike, 0.25, 0.4, 0.04, kind=kind).delta
                assert abs(delta) == pytest.approx(target, abs=1e-6)

    def test_greeks_signs(self):
        call = bs_greeks(100, 100, 0.25, 0.4, kind="call")
        put = bs_greeks(100, 100, 0.25, 0.4, kind="put")
        assert 0 < call.delta < 1
        assert -1 < put.delta < 0
        assert call.gamma > 0 and put.gamma > 0
        assert call.vega > 0
        assert call.theta < 0  # long options decay


class TestVolEstimates:
    def test_realized_vol_of_constant_series_is_zero(self):
        assert realized_vol([100.0] * 30, window=20) == pytest.approx(0.0)

    def test_realized_vol_needs_enough_history(self):
        assert realized_vol([100.0, 101.0], window=20) is None

    def test_event_iv_exceeds_baseline_and_rises_as_expiry_nears(self):
        near = modeled_event_iv(0.40, days_to_expiry=7)
        far = modeled_event_iv(0.40, days_to_expiry=60)
        assert near > far > 0.40


class TestStructures:
    def test_long_put_costs_premium_and_pays_on_a_drop(self):
        put = Structure("p", [Leg("put", 90.0, 1, 4.0)])
        assert put.entry_cost == pytest.approx(400.0)
        assert put.pnl_at_expiry(70.0) == pytest.approx(2000.0 - 400.0)
        assert put.pnl_at_expiry(100.0) == pytest.approx(-400.0)

    def test_short_strangle_is_a_credit_capped_at_the_premium(self):
        strangle = Structure("s", [
            Leg("put", 90.0, -1, 3.0),
            Leg("call", 110.0, -1, 2.5),
        ])
        assert strangle.entry_cost == pytest.approx(-550.0)
        # Expiring between the wings keeps the full credit.
        assert strangle.pnl_at_expiry(100.0) == pytest.approx(550.0)
        # A large move loses more than the credit.
        assert strangle.pnl_at_expiry(60.0) < 0

    def test_collar_caps_both_tails(self):
        """A collar must bound the outcome on both sides.

        This is the property the efficiency-plan hypothesis relies on, so a
        sign error in the short call would invalidate that whole strategy.
        """
        collar = Structure("c", [
            Leg("stock", None, 100, 100.0),
            Leg("put", 90.0, 1, 3.0),
            Leg("call", 110.0, -1, 2.0),
        ])
        crash = collar.pnl_at_expiry(40.0)
        moon = collar.pnl_at_expiry(300.0)
        # Floor: stock loss to 90 plus net premium paid.
        assert crash == pytest.approx(-1000.0 - 100.0)
        # Ceiling: stock gain to 110 less net premium.
        assert moon == pytest.approx(1000.0 - 100.0)
        assert crash < 0 < moon

    def test_market_priced_flag_requires_every_option_leg(self):
        mixed = Structure("m", [
            Leg("put", 90.0, 1, 3.0, priced_from="market"),
            Leg("call", 110.0, -1, 2.0, priced_from="model"),
        ])
        assert not mixed.used_market_prices
        real = Structure("r", [Leg("put", 90.0, 1, 3.0, priced_from="market")])
        assert real.used_market_prices

    def test_net_premium_excludes_the_stock_leg(self):
        collar = Structure("c", [
            Leg("stock", None, 100, 100.0),
            Leg("put", 90.0, 1, 3.0),
            Leg("call", 110.0, -1, 2.0),
        ])
        assert collar.net_premium == pytest.approx(100.0)
        assert collar.entry_cost == pytest.approx(10100.0)
