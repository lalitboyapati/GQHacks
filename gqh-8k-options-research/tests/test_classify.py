"""Tests for 8-K text classification.

These lock down the specific misreadings that produced wrong answers during
development, since each one silently corrupts the event set rather than
raising: the item title leaking into the body, compensation boilerplate
being read as a firing, and financial-statement tables being mined for a
restructuring charge.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eightk.classify import (
    parse_efficiency_plan,
    parse_exec_change,
    split_items,
    strip_item_title,
)

# A realistic 5.02 section: departure, then the successor's pay package.
RESIGNATION = """
Departure of President and Chief Executive Officer

On November 3, 2025, the Company announced that Dev Ittycheria, the Company's
President and Chief Executive Officer, notified the Company on October 29,
2025 of his intent to resign as President and Chief Executive Officer,
effective November 9, 2025. Mr. Ittycheria's resignation did not involve any
disagreement with the Company on any matter relating to its operations,
policies or practices.

Appointment of Interim Chief Executive Officer

The Board appointed Ms. Jane Roe as Interim Chief Executive Officer. Her
annual bonus will be payable on the Company's first payroll cycle, subject to
reimbursement if Ms. Roe voluntarily resigns or is terminated for cause
within 12 months of the Effective Date.
"""


class TestItemTitles:
    def test_strips_official_title(self):
        body = strip_item_title(
            "5.02",
            "Departure of Directors or Certain Officers; Election of Directors; "
            "Appointment of Certain Officers; Compensatory Arrangements of Certain "
            "Officers. On May 1, 2024, the CFO resigned.",
        )
        assert body.startswith("On May 1, 2024")

    def test_leaves_untitled_body_alone(self):
        body = "On May 1, 2024, the CFO resigned."
        assert strip_item_title("5.02", body) == body

    def test_title_verbs_do_not_create_phantom_events(self):
        """The 5.02 title contains 'Departure' and 'Appointment' itself.

        Parsing the raw title must not look like a departure, or every 5.02
        filing in the corpus registers as one.
        """
        title_only = (
            "Item 5.02 Departure of Directors or Certain Officers; Election of "
            "Directors; Appointment of Certain Officers; Compensatory "
            "Arrangements of Certain Officers."
        )
        sections = split_items(title_only)
        change = parse_exec_change(sections.get("5.02", ""))
        assert not change.is_departure
        assert not change.is_appointment


class TestExecChange:
    def test_detects_ceo_resignation(self):
        change = parse_exec_change(RESIGNATION)
        assert change.is_departure
        assert change.top_role == "CEO"
        assert change.person == "Dev Ittycheria"

    def test_boilerplate_no_disagreement_is_not_a_red_flag(self):
        change = parse_exec_change(RESIGNATION)
        assert not change.disagreement

    @pytest.mark.parametrize("denial", [
        "did not involve any disagreement with the Company",
        "is not due to any disagreement with the Company",
        "was not the result of a disagreement with the Company",
        "There were no disagreements with the Company",
        "is unrelated to any disagreement with the Company",
    ])
    def test_every_denial_phrasing_is_not_a_red_flag(self, denial):
        """Item 5.02(a) denials are near-universal boilerplate.

        Flagging any of them would mark most of the corpus as a disagreement
        and inflate severity on routine resignations.
        """
        change = parse_exec_change(
            f"On May 1, 2024, the Chief Executive Officer resigned. His resignation {denial} "
            "on any matter relating to its operations, policies or practices."
        )
        assert change.is_departure
        assert not change.disagreement

    def test_denial_split_across_lines_is_still_a_denial(self):
        """Filing HTML flattens with newlines mid-sentence.

        Treating a line break as a sentence boundary severs "did not involve
        any" from the "disagreement" it negates, which silently marks clean
        resignations as disagreements and inflates their severity.
        """
        change = parse_exec_change(
            "On May 1, 2024, the Chief Executive Officer resigned.\n"
            "Mr. Smith's resignation did not involve any\n"
            "disagreement with the Company on any matter."
        )
        assert change.is_departure
        assert not change.disagreement

    def test_genuine_disagreement_is_flagged(self):
        change = parse_exec_change(
            "On May 1, 2024, the Chief Financial Officer resigned as a result of a "
            "disagreement with the Board regarding the Company's accounting practices."
        )
        assert change.is_departure
        assert change.disagreement
        assert change.severity > 0.5

    def test_successor_clawback_is_not_a_firing_for_cause(self):
        """'terminated for cause' here describes the incoming officer.

        It sits inside a conditional clawback clause, so reading it as the
        reason for the departure mislabels an ordinary succession.
        """
        change = parse_exec_change(RESIGNATION)
        assert not change.for_cause

    def test_genuine_for_cause_is_detected(self):
        change = parse_exec_change(
            "On March 2, 2024, the Board terminated John Smith, the Company's "
            "Chief Executive Officer, for cause following an investigation into "
            "violations of the Company's code of conduct, effective immediately."
        )
        assert change.is_departure
        assert change.for_cause
        assert change.abrupt
        assert change.severity > 0.8

    def test_appointment_only_is_not_a_departure(self):
        change = parse_exec_change(
            "On April 28, 2025, the Company announced the appointment of "
            "Michael J. Berry as the Company's Chief Financial Officer."
        )
        assert not change.is_departure
        assert change.is_appointment
        assert change.severity == 0.0

    def test_severity_ordering(self):
        """A forced abrupt CEO exit must outrank a planned CFO retirement."""
        forced = parse_exec_change(
            "The Board terminated the Chief Executive Officer for cause, "
            "effective immediately, following an investigation."
        )
        planned = parse_exec_change(
            "The Chief Financial Officer announced his retirement, and the "
            "Company appointed a successor who will assume the role in June."
        )
        assert forced.severity > planned.severity

    def test_senior_departure_excludes_directors(self):
        change = parse_exec_change(
            "On June 1, 2024, a member of the board of directors resigned."
        )
        assert change.is_departure
        assert not change.is_senior_departure


class TestEfficiencyPlan:
    PLAN = (
        "On January 10, 2024, the Company approved a restructuring plan to reduce "
        "its global workforce by approximately 1,200 employees, or about 8% of its "
        "workforce. The Company expects to incur approximately $75 million of "
        "pre-tax charges, substantially all of which are cash charges, and expects "
        "annualized savings of approximately $140 million to be fully realized by 2026."
    )

    def test_extracts_charge_savings_and_horizon(self):
        plan = parse_efficiency_plan(self.PLAN, filing_year=2024, trust_tables=True)
        assert plan.is_plan
        assert plan.charge_usd == 75e6
        assert plan.savings_usd == 140e6
        assert plan.savings_horizon_years == 2.0
        assert plan.headcount == 1200
        assert plan.headcount_pct == 8.0
        assert plan.cash_charge

    def test_payback_and_front_loading(self):
        plan = parse_efficiency_plan(self.PLAN, filing_year=2024, trust_tables=True)
        # $75m spent to save $140m a year pays back in well under a year.
        assert plan.payback_years < 1.0
        # ...but the savings still only land two years out.
        assert plan.cost_front_loaded

    def test_ignores_tables_when_not_filed_as_a_cost_item(self):
        """An earnings release must not yield a charge from its balance sheet."""
        text = (
            "CONDENSED CONSOLIDATED BALANCE SHEETS. Total stockholders' equity "
            "4,467,000. The Company continues its operational realignment plan. "
            "Total costs of $4,467,000,000 appear in the table above."
        )
        plan = parse_efficiency_plan(text, filing_year=2022, trust_tables=False)
        assert plan.is_plan
        assert plan.charge_usd is None
        assert not plan.quantified

    def test_non_plan_text_returns_nothing(self):
        plan = parse_efficiency_plan(
            "The Company declared a quarterly dividend of $0.25 per share.",
            filing_year=2024,
        )
        assert not plan.is_plan

    def test_implausible_amounts_rejected(self):
        plan = parse_efficiency_plan(
            "Restructuring plan charges of $900,000,000,000 are expected.",
            filing_year=2024, trust_tables=True,
        )
        assert plan.charge_usd is None
