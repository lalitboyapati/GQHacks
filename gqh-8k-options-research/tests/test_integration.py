"""End-to-end backtest run against a synthetic data source.

Exercises the full path -- event selection, contract resolution, leg
pricing, exit marking, cost application, and statistics -- without touching
the network. The fake source returns a deterministic price path with a known
gap, so the sign and rough magnitude of each strategy's P&L can be asserted
rather than merely "it ran".
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eightk.backtest import BacktestConfig, run_backtest, trades_frame
from eightk.classify import EfficiencyPlan, ExecChange
from eightk.edgar import Filing
from eightk.events import EventRecord
from eightk.massive_src import Bar, OptionContract, option_ticker
from eightk.novelty import NoveltyAssessment
from eightk.report import summarize, volatility_premium_table
from eightk.strategies import StrategyConfig, default_strategies

EVENT_DAY = date(2025, 6, 16)       # a Monday
START_PRICE = 100.0
GAP_FACTOR = 0.80                   # the stock drops 20% on the event


def _sessions(first: date, count: int) -> list[date]:
    """Weekday-only session list."""
    days, cursor = [], first
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


class FakeMassive:
    """Deterministic stand-in for ``MassiveClient``.

    The underlying drifts mildly for 60 sessions, gaps down 20% on the
    event, then stays near the new level. Option bars are generated from
    Black-Scholes at a fixed 60% vol pre-event and 40% after, which
    reproduces the IV crush a real event shows.
    """

    def __init__(self, post_event_drift: float = 0.001):
        """:param post_event_drift: per-session drift after the event.

        The 20% drop lands in the event day's *opening gap*, i.e. before any
        strategy here can enter. What a trade reacting to the filing actually
        captures is this drift, so it is the knob the tests vary.
        """
        self.calls = 0
        all_days = _sessions(EVENT_DAY - timedelta(days=120), 200)
        self.days = all_days
        self._prices: dict[date, float] = {}
        price = START_PRICE
        for day in all_days:
            if day == EVENT_DAY:
                price *= GAP_FACTOR
            elif day > EVENT_DAY:
                price *= (1.0 + post_event_drift)
            else:
                price *= 1.0005
            self._prices[day] = price

    # --- equity bars ------------------------------------------------- #
    def daily_bars(self, ticker, start, end, adjusted=True):
        if ticker.startswith("O:"):
            return self._option_bars(ticker, start, end)
        lo, hi = date.fromisoformat(start), date.fromisoformat(end)
        bars = []
        for day in self.days:
            if lo <= day <= hi:
                close = self._prices[day]
                # On the event day the open already reflects the gap.
                open_px = close if day != EVENT_DAY else close * 0.995
                bars.append(Bar(day=day, open=open_px, high=max(open_px, close) * 1.01,
                                low=min(open_px, close) * 0.99, close=close,
                                volume=1e6, vwap=(open_px + close) / 2))
        return bars

    # --- option chain ------------------------------------------------ #
    def option_contracts(self, underlying, *, as_of, expiration_gte,
                         expiration_lte, contract_type=None, limit=1000):
        expiry = date.fromisoformat(expiration_gte)
        while expiry.weekday() != 4:      # snap to a Friday
            expiry += timedelta(days=1)
        if expiry > date.fromisoformat(expiration_lte):
            return []
        spot = self._prices[date.fromisoformat(as_of)]
        kinds = (["call", "put"] if contract_type is None else [contract_type])
        out = []
        for kind in kinds:
            for pct in (0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 1.0,
                        1.05, 1.10, 1.15, 1.20, 1.30, 1.40):
                strike = round(spot * pct, 0)
                out.append(OptionContract(
                    ticker=option_ticker(underlying, expiry, kind, strike),
                    underlying=underlying, expiration=expiry,
                    strike=strike, contract_type=kind,
                ))
        return out

    def _option_bars(self, ticker, start, end):
        """Synthetic option bars priced off the underlying."""
        from eightk.options_model import bs_price, year_fraction
        body = ticker[2:]
        underlying_len = len(body) - 15
        expiry = datetime.strptime(body[underlying_len:underlying_len + 6], "%y%m%d").date()
        kind = "call" if body[underlying_len + 6] == "C" else "put"
        strike = int(body[underlying_len + 7:]) / 1000.0

        lo, hi = date.fromisoformat(start), date.fromisoformat(end)
        bars = []
        for day in self.days:
            if not (lo <= day <= hi) or day >= expiry:
                continue
            spot = self._prices[day]
            vol = 0.60 if day < EVENT_DAY else 0.40     # post-event IV crush
            tau = year_fraction((expiry - day).days)
            px = bs_price(spot, strike, tau, vol, 0.04, 0.0, kind)
            px = max(0.05, px)
            bars.append(Bar(day=day, open=px, high=px * 1.05, low=px * 0.95,
                            close=px, volume=500, vwap=px))
        return bars

    def news(self, *args, **kwargs):
        return []

    def ticker_details(self, ticker, as_of=None):
        return {"ticker": ticker, "name": "Test Co", "market_cap": 3.0e9,
                "sic_description": "Software"}


def make_event(event_types, *, exec_change=None, plan=None, novelty_score=0.8) -> EventRecord:
    # Accepted 12:31 UTC = 08:31 ET on the event day: a pre-market filing,
    # tradable at that session's open.
    filing = Filing(
        ticker="TEST", cik="0000000001", accession="0000000001-25-000001",
        form="8-K", filing_date=EVENT_DAY.isoformat(),
        acceptance_utc=datetime(2025, 6, 16, 12, 31, tzinfo=timezone.utc),
        items=("5.02",), primary_document="t.htm",
        report_date=EVENT_DAY.isoformat(),
    )
    return EventRecord(
        filing=filing, exec_change=exec_change, plan=plan,
        novelty=NoveltyAssessment(score=novelty_score, is_repeat=novelty_score < 0.40),
        market_cap=3.0e9, company_name="Test Co", text_chars=9000,
        event_types=tuple(event_types),
    )


SENIOR_DEPARTURE = ExecChange(
    is_departure=True, is_appointment=False, roles=("CEO",), top_role="CEO",
    person="Jane Doe", abrupt=True, for_cause=True, severity=0.92,
)
QUANTIFIED_PLAN = EfficiencyPlan(
    is_plan=True, charge_usd=75e6, savings_usd=140e6, savings_horizon_years=2.0,
    headcount=1200, headcount_pct=8.0, cash_charge=True, quantified=True,
    cost_front_loaded=True, payback_years=0.54,
)


@pytest.fixture
def massive():
    return FakeMassive()


class TestEndToEnd:
    def test_long_put_profits_only_on_post_entry_drift(self):
        """The opening gap is not capturable; continued decline is.

        This is the central timing fact of the whole study. A trader reading
        the 8-K pre-market buys at the already-gapped open, so the put pays
        off only if the stock keeps falling afterwards -- and loses to IV
        crush and spreads if the slide stops at the gap.
        """
        event = make_event(["exec_departure"], exec_change=SENIOR_DEPARTURE)
        strategies = [s for s in default_strategies() if s.name == "exec_put"]
        config = BacktestConfig(hold_sessions=5)

        keeps_falling = run_backtest(
            [event], strategies, massive=FakeMassive(post_event_drift=-0.02),
            config=config,
        )[0]
        stabilises = run_backtest(
            [event], strategies, massive=FakeMassive(post_event_drift=0.001),
            config=config,
        )[0]

        assert keeps_falling.pnl > 0
        assert stabilises.pnl < 0
        assert keeps_falling.priced_from == "market"
        assert keeps_falling.entry_iv is not None

    def test_entry_ignores_the_opening_gap(self, massive):
        """Entry spot must be the post-gap open, not the prior close."""
        event = make_event(["exec_departure"], exec_change=SENIOR_DEPARTURE)
        strategies = [s for s in default_strategies() if s.name == "stock_short"]
        trade = run_backtest([event], strategies, massive=massive,
                             config=BacktestConfig(hold_sessions=5))[0]
        # The gap took the price to ~0.8x; entry must be near there, not 100.
        assert trade.entry_spot < START_PRICE * 0.85

    def test_collar_bounds_the_outcome_versus_plain_stock(self, massive):
        event = make_event(["efficiency_plan"], plan=QUANTIFIED_PLAN)
        strategies = [s for s in default_strategies()
                      if s.name in ("efficiency_collar", "stock_long")]
        trades = run_backtest([event], strategies, massive=massive,
                              config=BacktestConfig(hold_sessions=10))
        by_name = {t.strategy: t for t in trades}
        assert {"efficiency_collar", "stock_long"} <= set(by_name)
        # The collar dampens the outcome in whichever direction the stock
        # went: the short call caps the gain here, and the long put would
        # floor the loss on the downside. Either way its move is smaller.
        assert abs(by_name["efficiency_collar"].pnl) < abs(by_name["stock_long"].pnl)

    def test_collar_floors_the_loss_when_the_stock_keeps_falling(self):
        event = make_event(["efficiency_plan"], plan=QUANTIFIED_PLAN)
        strategies = [s for s in default_strategies()
                      if s.name in ("efficiency_collar", "stock_long")]
        trades = run_backtest(
            [event], strategies, massive=FakeMassive(post_event_drift=-0.03),
            config=BacktestConfig(hold_sessions=10),
        )
        by_name = {t.strategy: t for t in trades}
        assert by_name["stock_long"].pnl < 0
        # Protection must actually protect.
        assert by_name["efficiency_collar"].pnl > by_name["stock_long"].pnl

    def test_short_strangle_runs_on_a_repeat_filing(self, massive):
        event = make_event(["efficiency_plan"], plan=QUANTIFIED_PLAN, novelty_score=0.2)
        strategies = [s for s in default_strategies() if s.name == "novelty_shortvol"]
        trades = run_backtest([event], strategies, massive=massive,
                              config=BacktestConfig(hold_sessions=10))
        assert len(trades) == 1
        trade = trades[0]
        assert trade.entry_cost < 0          # a net credit
        assert trade.capital_at_risk > abs(trade.entry_cost)   # margin, not credit

    def test_combo_routes_on_novelty(self, massive):
        novel = make_event(["efficiency_plan"], plan=QUANTIFIED_PLAN, novelty_score=0.85)
        repeat = make_event(["efficiency_plan"], plan=QUANTIFIED_PLAN, novelty_score=0.15)
        strategies = [s for s in default_strategies() if s.name == "combo"]
        trades = run_backtest([novel, repeat], strategies, massive=massive,
                              config=BacktestConfig(hold_sessions=10))
        structures = {t.structure.split("[")[0] for t in trades}
        assert structures == {"combo:efficiency_collar", "combo:novelty_shortvol"}

    def test_severity_filter_excludes_routine_filings(self, massive):
        routine = make_event(
            ["other_departure"],
            exec_change=ExecChange(
                is_departure=True, is_appointment=True, roles=("DIRECTOR",),
                top_role="DIRECTOR", person="A Director", severity=0.08,
            ),
        )
        strategies = [s for s in default_strategies() if s.name == "exec_put"]
        assert run_backtest([routine], strategies, massive=massive) == []

    def test_market_cap_ceiling_excludes_large_issuers(self, massive):
        event = make_event(["exec_departure"], exec_change=SENIOR_DEPARTURE)
        event.market_cap = 500e9
        config = BacktestConfig(strategy_config=StrategyConfig(max_market_cap=20e9))
        strategies = [s for s in default_strategies(config.strategy_config)
                      if s.name == "exec_put"]
        assert run_backtest([event], strategies, massive=massive, config=config) == []

    def test_costs_reduce_pnl(self, massive):
        """Wider assumed spreads must lower P&L for a premium-paying trade."""
        from eightk.options_book import CostModel
        event = make_event(["exec_departure"], exec_change=SENIOR_DEPARTURE)
        strategies = [s for s in default_strategies() if s.name == "exec_put"]
        cheap = run_backtest([event], strategies, massive=massive, config=BacktestConfig(
            hold_sessions=5, cost_model=CostModel(spread_pct_of_premium=0.01)))[0]
        dear = run_backtest([event], strategies, massive=massive, config=BacktestConfig(
            hold_sessions=5, cost_model=CostModel(spread_pct_of_premium=0.15)))[0]
        assert dear.pnl < cheap.pnl

    def test_report_tables_build(self, massive):
        events = [make_event(["exec_departure"], exec_change=SENIOR_DEPARTURE)]
        trades = run_backtest(events, default_strategies(), massive=massive,
                              config=BacktestConfig(hold_sessions=10))
        frame = trades_frame(trades)
        assert not frame.empty
        table = summarize(frame)
        assert {"strategy", "n_trades", "mean_return", "hit_rate"} <= set(table.columns)
        vrp = volatility_premium_table(frame)
        assert "mean_gap" in vrp.columns
