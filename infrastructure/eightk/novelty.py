"""Does this 8-K reveal anything, or re-file what the market already saw?

This is the measurement behind the second strategy. A company announces
something on Monday, files the 8-K on Thursday, and the filing generates a
fresh round of headlines — but if Thursday's document only restates Monday's
press release, option premium priced for "news on Thursday" was never
justified, and selling it should pay.

Novelty is scored from four independent kinds of evidence, deliberately
mixing cheap structural signals with textual ones so that no single noisy
detector drives the classification:

1. **Self-reported repetition.** Filings announce their own redundancy:
   "as previously announced", "previously disclosed", "reaffirms". This is
   the single most reliable marker and is weighted accordingly.
2. **Report-versus-filing lag.** EDGAR records the date of the earliest
   event reported alongside the acceptance time. A filing describing an
   event from eight days ago is far more likely to be a formality than one
   describing this morning.
3. **Prior news coverage.** Articles published before the filing instant
   that already describe the same content. Only coverage strictly earlier
   than acceptance counts, which keeps the test free of hindsight.
4. **Fresh-disclosure markers.** Language that only appears when something
   genuinely new is being said: new dollar figures, "today announced",
   first-time guidance changes.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# ---------------------------------------------------------------------- #
# Text utilities
# ---------------------------------------------------------------------- #

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "as", "at", "by", "from", "that", "this", "its", "it", "is", "was",
    "will", "be", "been", "has", "have", "had", "company", "companys",
    "inc", "corp", "corporation", "said", "says", "about", "which", "their",
    "we", "our", "us", "he", "she", "his", "her", "they", "them", "also",
    "not", "no", "per", "share", "shares", "common", "stock", "more",
    "than", "any", "all", "other", "such", "may", "would", "could", "new",
}

_WORD_RE = re.compile(r"[a-z][a-z0-9'’-]+")


def tokenize(text: str) -> list[str]:
    """Lowercase content words, stopwords removed."""
    if not text:
        return []
    return [
        word for word in _WORD_RE.findall(text.lower())
        if word not in _STOPWORDS and len(word) > 2
    ]


def _bigrams(tokens: list[str]) -> set[str]:
    return {f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)}


def similarity(text_a: str, text_b: str) -> float:
    """Blended unigram/bigram containment score in ``[0, 1]``.

    Containment (overlap divided by the *smaller* set) rather than Jaccard,
    because a short news headline is being compared against a long filing;
    Jaccard would score every headline near zero purely on length mismatch.
    Bigrams carry half the weight to reward matching phrasing, not just
    shared vocabulary.
    """
    tokens_a, tokens_b = tokenize(text_a), tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    set_a, set_b = set(tokens_a), set(tokens_b)
    uni = len(set_a & set_b) / max(1, min(len(set_a), len(set_b)))

    big_a, big_b = _bigrams(tokens_a), _bigrams(tokens_b)
    if big_a and big_b:
        bi = len(big_a & big_b) / max(1, min(len(big_a), len(big_b)))
    else:
        bi = 0.0
    return min(1.0, 0.65 * uni + 0.35 * bi)


# ---------------------------------------------------------------------- #
# Markers
# ---------------------------------------------------------------------- #

# Phrases in which a filing concedes it is repeating itself.
_REPEAT_RE = re.compile(
    r"(?i)\b(?:as\s+previously\s+(?:announced|disclosed|reported|stated)"
    r"|previously\s+(?:announced|disclosed|reported)"
    r"|reaffirm(?:s|ed|ing)?|reiterat(?:es|ed|ing)"
    r"|as\s+disclosed\s+in|described\s+in\s+(?:the\s+)?(?:company[’']?s\s+)?"
    r"(?:prior|previous|earlier)|on\s+\w+\s+\d{1,2},?\s+20\d{2},?\s+the\s+company\s+announced"
    r"|incorporated\s+(?:herein\s+)?by\s+reference\s+to\s+the\s+press\s+release"
    r"|furnish(?:ed|es)?\s+(?:herewith\s+)?(?:a\s+copy\s+of\s+)?the\s+press\s+release"
    r"|supplement(?:s|ing)?\s+the\s+(?:disclosure|information))\b"
)

# Phrases that accompany a genuinely new disclosure.
_FRESH_RE = re.compile(
    r"(?i)\b(?:today\s+announced|announced\s+today|has\s+determined"
    r"|for\s+the\s+first\s+time|newly\s+(?:appointed|identified)"
    r"|notified\s+the\s+company|informed\s+the\s+company"
    r"|entered\s+into\s+(?:a\s+)?(?:new\s+)?(?:definitive|material)"
    r"|concluded\s+that|now\s+expects|revis(?:es|ed|ing)\s+(?:its\s+)?(?:guidance|outlook)"
    r"|no\s+longer\s+expects)\b"
)

# A filing whose body is nothing but an exhibit pointer is a pure re-file.
_POINTER_ONLY_RE = re.compile(
    r"(?i)\b(?:a\s+copy\s+of\s+(?:the\s+)?(?:press\s+release|announcement)"
    r"|attached\s+(?:hereto\s+)?as\s+exhibit)\b"
)


@dataclass
class NoveltyAssessment:
    """How much new information a filing carries."""

    score: float                      # 0 = pure repeat, 1 = fully new
    is_repeat: bool                   # score below the repeat threshold
    # Evidence
    self_reported_repeat: bool = False
    fresh_markers: bool = False
    pointer_only: bool = False
    report_lag_days: int = 0          # filing date minus earliest event date
    prior_news_count: int = 0         # articles before the filing instant
    max_prior_similarity: float = 0.0
    hours_since_first_mention: float | None = None
    body_chars: int = 0
    matched_headline: str | None = None
    components: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "novelty_score": self.score,
            "is_repeat": self.is_repeat,
            "self_reported_repeat": self.self_reported_repeat,
            "fresh_markers": self.fresh_markers,
            "pointer_only": self.pointer_only,
            "report_lag_days": self.report_lag_days,
            "prior_news_count": self.prior_news_count,
            "max_prior_similarity": self.max_prior_similarity,
            "hours_since_first_mention": self.hours_since_first_mention,
            "body_chars": self.body_chars,
            "matched_headline": self.matched_headline,
        }


# Below this score a filing is treated as recycled information.
REPEAT_THRESHOLD = 0.40


def assess_novelty(
    *,
    filing_text: str,
    acceptance_utc: datetime,
    filing_date: str,
    report_date: str | None,
    prior_news: list = (),
    lookback_days: int = 10,
    similarity_floor: float = 0.22,
) -> NoveltyAssessment:
    """Score how much genuinely new information a filing contains.

    :param prior_news: ``NewsItem``-like objects with ``published_utc``,
        ``title`` and optional ``description``. Only items published strictly
        before ``acceptance_utc`` are considered, so the score is computable
        at the moment of the filing and carries no look-ahead.
    :param similarity_floor: minimum blended similarity for an article to
        count as covering the same content.
    """
    body = (filing_text or "")[:30000]

    self_repeat = bool(_REPEAT_RE.search(body))
    fresh = bool(_FRESH_RE.search(body))
    pointer_only = bool(_POINTER_ONLY_RE.search(body)) and len(body) < 4000

    # --- structural lag ------------------------------------------------
    report_lag = 0
    if report_date:
        try:
            filed = datetime.fromisoformat(filing_date).date()
            reported = datetime.fromisoformat(report_date).date()
            report_lag = max(0, (filed - reported).days)
        except (TypeError, ValueError):
            report_lag = 0

    # --- prior coverage ------------------------------------------------
    window_start = acceptance_utc - timedelta(days=lookback_days)
    best_similarity = 0.0
    matched_headline = None
    first_mention: datetime | None = None
    prior_count = 0

    for item in prior_news or ():
        published = getattr(item, "published_utc", None)
        if published is None or published >= acceptance_utc or published < window_start:
            continue
        prior_count += 1
        headline = " ".join(filter(None, [
            getattr(item, "title", "") or "",
            getattr(item, "description", "") or "",
        ]))
        score = similarity(headline, body)
        if score >= similarity_floor:
            if first_mention is None or published < first_mention:
                first_mention = published
            if score > best_similarity:
                best_similarity = score
                matched_headline = getattr(item, "title", None)

    hours_since = (
        (acceptance_utc - first_mention).total_seconds() / 3600.0
        if first_mention else None
    )

    # --- combine -------------------------------------------------------
    # Start from neutral and move toward "new" or "repeat" on evidence.
    score = 0.55

    if self_repeat:
        score -= 0.28
    if pointer_only:
        score -= 0.12
    if fresh:
        score += 0.22

    # A long gap between the event and its filing means the market has had
    # time to learn about it by other means.
    if report_lag >= 7:
        score -= 0.20
    elif report_lag >= 3:
        score -= 0.12
    elif report_lag >= 1:
        score -= 0.05
    else:
        score += 0.06  # filed same day as the event it describes

    # Prior coverage that actually resembles the filing is direct evidence
    # the information was already out.
    if best_similarity >= similarity_floor:
        score -= min(0.32, 0.32 * (best_similarity / 0.6))
        if hours_since is not None and hours_since >= 24:
            score -= 0.08  # out for more than a full session

    # A substantial body implies disclosure beyond a headline restatement.
    if len(body) >= 12000:
        score += 0.08
    elif len(body) < 2500:
        score -= 0.06

    score = max(0.0, min(1.0, score))

    return NoveltyAssessment(
        score=score,
        is_repeat=score < REPEAT_THRESHOLD,
        self_reported_repeat=self_repeat,
        fresh_markers=fresh,
        pointer_only=pointer_only,
        report_lag_days=report_lag,
        prior_news_count=prior_count,
        max_prior_similarity=best_similarity,
        hours_since_first_mention=hours_since,
        body_chars=len(body),
        matched_headline=matched_headline,
        components={
            "self_repeat": self_repeat,
            "fresh": fresh,
            "report_lag": report_lag,
            "prior_similarity": best_similarity,
        },
    )
