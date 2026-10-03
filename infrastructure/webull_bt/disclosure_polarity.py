"""Map Massive 8-K disclosure taxonomy categories to call/put polarity.

Massive ``primary_category`` values are thematic labels (e.g. ``risk_events``,
``financial_results``), not the literal strings \"positive\" / \"negative\".
This module assigns each taxonomy node a signed polarity:

  +1  → treat as a bullish disclosure → buy calls
  -1  → treat as a bearish disclosure → buy puts
   0  → unsigned / context-dependent (use market gap for Item 2.02 prints)

Item 2.02 earnings releases are almost always ``financial_results`` /
``quarterly_earnings`` (unsigned). For those, polarity is taken from the
overnight gap on the trade date.
"""

from __future__ import annotations

# Tertiary categories that are structurally bullish / bearish.
POSITIVE_TERTIARY = {
    "acquisition_agreement",
    "acquisition_completion",
    "merger_agreement",
    "merger_completion",
    "joint_venture_agreement",
    "licensing_agreement",
    "listing_compliance_regained",
    "share_repurchase_program",
    "dividend_declaration",
    "ceo_appointment",
    "cfo_appointment",
    "executive_officer_appointment",
    "bankruptcy_emergence",
    "guidance_issuance_or_update",  # overrides only when text/gap confirm; treated soft+
}

NEGATIVE_TERTIARY = {
    "voluntary_bankruptcy",
    "involuntary_bankruptcy",
    "receivership_appointment",
    "going_concern",
    "material_litigation",
    "class_action_filing",
    "regulatory_investigation",
    "cybersecurity_incident",
    "goodwill_impairment",
    "asset_impairment",
    "investment_impairment",
    "financial_restatement",
    "accounting_error_correction",
    "audit_opinion_withdrawal",
    "internal_control_weakness",
    "guidance_withdrawal",
    "deal_termination",
    "deal_breach_default",
    "deal_withdrawal",
    "listing_deficiency_notice",
    "delisting_determination",
    "voluntary_delisting",
    "auditor_resignation",
    "auditor_dismissal",
    "auditor_disagreement",
    "payment_default",
    "covenant_violation",
    "debt_acceleration",
    "rating_downgrade_trigger",
    "ceo_departure",
    "cfo_departure",
    "executive_officer_departure",
}

# Primary-level fallback when tertiary is unknown / unsigned.
POSITIVE_PRIMARY = {
    "strategic_transactions",
}
NEGATIVE_PRIMARY = {
    "risk_events",
}

# Earnings Item 2.02 nodes — polarity comes from the print (gap), not taxonomy.
UNSIGNED_EARNINGS_TERTIARY = {
    "quarterly_earnings",
    "annual_earnings",
    "preliminary_results",
    "nav_per_share",
    "material_charge_or_gain",
}
UNSIGNED_EARNINGS_PRIMARY = {
    "financial_results",
}


def category_polarity(
    primary_category: str | None,
    tertiary_category: str | None = None,
    *,
    secondary_category: str | None = None,
) -> int:
    """Return +1 / -1 / 0 from Massive disclosure categories."""
    del secondary_category  # reserved for future finer rules
    tertiary = (tertiary_category or "").strip().lower()
    primary = (primary_category or "").strip().lower()

    if tertiary in NEGATIVE_TERTIARY:
        return -1
    if tertiary in POSITIVE_TERTIARY:
        return +1
    if tertiary in UNSIGNED_EARNINGS_TERTIARY or primary in UNSIGNED_EARNINGS_PRIMARY:
        return 0
    if primary in NEGATIVE_PRIMARY:
        return -1
    if primary in POSITIVE_PRIMARY:
        return +1
    return 0


def resolve_signal_polarity(
    *,
    primary_category: str | None,
    tertiary_category: str | None,
    gap_pct: float,
    min_gap_pct: float = 0.005,
) -> int:
    """Final trade polarity for options: +1 call, -1 put, 0 flat.

    Taxonomy polarity wins when signed. Unsigned earnings/Item 2.02 events
    use the overnight gap sign once |gap| clears ``min_gap_pct``.
    """
    cat = category_polarity(primary_category, tertiary_category)
    if cat != 0:
        return cat
    if abs(gap_pct) < min_gap_pct:
        return 0
    return 1 if gap_pct > 0 else -1


def polarity_label(polarity: int) -> str:
    if polarity > 0:
        return "positive"
    if polarity < 0:
        return "negative"
    return "unsigned"
