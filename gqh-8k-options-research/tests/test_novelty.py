"""Tests for disclosure-novelty scoring.

The scorer must be computable at the filing instant. The look-ahead test
below is the important one: if news published *after* acceptance leaked into
the score, the "is this actually news?" strategy would be using tomorrow's
information to decide today's trade.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eightk.novelty import assess_novelty, similarity

ACCEPT = datetime(2025, 11, 6, 21, 5, tzinfo=timezone.utc)


class FakeNews:
    def __init__(self, published, title, description=""):
        self.published_utc = published
        self.title = title
        self.description = description


class TestSimilarity:
    def test_identical_text_scores_one(self):
        assert similarity("CEO resigns abruptly", "CEO resigns abruptly") == 1.0

    def test_unrelated_text_scores_zero(self):
        assert similarity("CEO resigns abruptly", "quarterly dividend declared") == 0.0

    def test_short_headline_matches_long_filing(self):
        """Containment, not Jaccard: a headline is far shorter than a filing."""
        headline = "Acme announces restructuring plan"
        filing = (
            "On Monday, Acme announced a restructuring plan affecting its "
            "workforce. " * 20
        )
        assert similarity(headline, filing) > 0.5

    def test_empty_input_is_safe(self):
        assert similarity("", "anything") == 0.0


class TestNovelty:
    def test_refiled_press_release_scores_as_repeat(self):
        result = assess_novelty(
            filing_text=(
                "As previously announced on November 3, 2025, the Company adopted a "
                "restructuring plan. A copy of the press release is attached hereto "
                "as Exhibit 99.1."
            ),
            acceptance_utc=ACCEPT,
            filing_date="2025-11-06",
            report_date="2025-11-03",
            prior_news=[FakeNews(
                datetime(2025, 11, 3, 13, 0, tzinfo=timezone.utc),
                "Company announces restructuring plan",
                "restructuring plan announced today",
            )],
        )
        assert result.is_repeat
        assert result.self_reported_repeat
        assert result.report_lag_days == 3
        assert result.max_prior_similarity > 0.2

    def test_same_day_surprise_scores_as_novel(self):
        result = assess_novelty(
            filing_text=(
                "On November 6, 2025, the Chief Executive Officer notified the "
                "Company of his resignation, effective immediately. " * 40
            ),
            acceptance_utc=ACCEPT,
            filing_date="2025-11-06",
            report_date="2025-11-06",
            prior_news=[],
        )
        assert not result.is_repeat
        assert result.fresh_markers
        assert result.report_lag_days == 0
        assert result.score > 0.6

    def test_ignores_news_published_after_the_filing(self):
        """No look-ahead: coverage after acceptance must not affect the score."""
        after = FakeNews(ACCEPT + timedelta(hours=3), "CEO resigns at Company")
        text = "The Chief Executive Officer notified the Company of his resignation."
        with_future = assess_novelty(
            filing_text=text, acceptance_utc=ACCEPT, filing_date="2025-11-06",
            report_date="2025-11-06", prior_news=[after],
        )
        without = assess_novelty(
            filing_text=text, acceptance_utc=ACCEPT, filing_date="2025-11-06",
            report_date="2025-11-06", prior_news=[],
        )
        assert with_future.score == without.score
        assert with_future.prior_news_count == 0

    def test_news_outside_the_lookback_is_ignored(self):
        stale = FakeNews(ACCEPT - timedelta(days=45), "Company announces plan")
        result = assess_novelty(
            filing_text="The Company announces a plan.", acceptance_utc=ACCEPT,
            filing_date="2025-11-06", report_date="2025-11-06",
            prior_news=[stale], lookback_days=10,
        )
        assert result.prior_news_count == 0

    def test_score_is_bounded(self):
        for report_date in ("2025-11-06", "2025-10-01"):
            result = assess_novelty(
                filing_text="As previously announced. " * 200,
                acceptance_utc=ACCEPT, filing_date="2025-11-06",
                report_date=report_date, prior_news=[],
            )
            assert 0.0 <= result.score <= 1.0

    def test_longer_lag_lowers_novelty(self):
        def score_for(report_date: str) -> float:
            return assess_novelty(
                filing_text="The Company adopted a plan affecting operations.",
                acceptance_utc=ACCEPT, filing_date="2025-11-06",
                report_date=report_date, prior_news=[],
            ).score

        assert score_for("2025-11-06") > score_for("2025-11-04") > score_for("2025-10-28")
