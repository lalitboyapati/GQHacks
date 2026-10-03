"""Tests for the Databento spend guard.

The ceiling exists because OPRA volume can turn one request into the whole
budget, so these verify the guard refuses *before* spending and that the
ledger survives a restart.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eightk.budget import BudgetExceeded, SpendLedger
from eightk.databento_opra import ALLOWED_SCHEMAS, DatabentoOpra


@pytest.fixture
def ledger(tmp_path):
    return SpendLedger(tmp_path / "spend.json", total_budget_usd=225.0, run_budget_usd=10.0)


class TestSpendLedger:
    def test_starts_empty(self, ledger):
        assert ledger.total_spent == 0.0
        assert ledger.remaining == 225.0

    def test_allows_a_query_within_both_caps(self, ledger):
        ledger.check(5.0, "ok")  # must not raise

    def test_refuses_above_the_run_cap(self, ledger):
        with pytest.raises(BudgetExceeded):
            ledger.check(10.01, "over run cap")

    def test_refuses_above_the_total_cap(self, tmp_path):
        ledger = SpendLedger(tmp_path / "s.json", total_budget_usd=3.0, run_budget_usd=100.0)
        with pytest.raises(BudgetExceeded):
            ledger.check(4.0, "over total cap")

    def test_spend_accumulates_within_a_run(self, ledger):
        ledger.record(6.0, "first")
        assert ledger.run_remaining == pytest.approx(4.0)
        with pytest.raises(BudgetExceeded):
            ledger.check(5.0, "would breach")

    def test_ledger_persists_across_instances(self, tmp_path):
        path = tmp_path / "s.json"
        SpendLedger(path, total_budget_usd=225.0).record(12.5, "earlier run")
        reloaded = SpendLedger(path, total_budget_usd=225.0)
        assert reloaded.total_spent == pytest.approx(12.5)
        assert reloaded.remaining == pytest.approx(212.5)
        # A fresh run starts with its own per-run allowance.
        assert reloaded.run_spent == 0.0

    def test_corrupt_ledger_does_not_crash(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text("{not json")
        assert SpendLedger(path).total_spent == 0.0

    def test_negative_quote_is_rejected(self, ledger):
        with pytest.raises(ValueError):
            ledger.check(-1.0)


class TestSchemaGuard:
    def test_tick_level_schemas_are_refused(self, ledger, tmp_path):
        """mbp-1 and trades on OPRA are orders of magnitude too large.

        The check must happen before any client construction so that an
        accidental call cannot reach the network at all.
        """
        reader = DatabentoOpra("unused-key", tmp_path, ledger)
        for schema in ("mbp-1", "trades", "mbo"):
            with pytest.raises(ValueError):
                reader.quote_cost(["O:MDB251121C00400000"], "2025-11-20", "2025-11-21", schema)

    def test_allowed_schemas_are_coarse(self):
        assert "mbp-1" not in ALLOWED_SCHEMAS
        assert "trades" not in ALLOWED_SCHEMAS
        assert "ohlcv-1d" in ALLOWED_SCHEMAS

    def test_empty_symbol_list_costs_nothing(self, ledger, tmp_path):
        reader = DatabentoOpra("unused-key", tmp_path, ledger)
        assert reader.quote_cost([], "2025-11-20", "2025-11-21", "bbo-1m") == 0.0
