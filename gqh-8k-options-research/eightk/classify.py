"""Turn raw 8-K text into structured, tradable event descriptions.

Two families are parsed here, each with its own failure mode to defend
against:

**Item 5.02 (executive change).** The item code alone is almost useless as
a signal: issuers file 5.02 for routine director elections and option-grant
housekeeping far more often than for a chief executive walking out. The
parser therefore reads the 5.02 section itself to recover *who* left, *how
abruptly*, whether a successor was already lined up, and whether the filing
admits a disagreement — the distinctions that separate a repriceable shock
from boilerplate.

**Items 2.05 / 2.06 (efficiency plan).** Here the text carries numbers the
headline usually drops: the upfront charge, the promised annualized saving,
and the horizon over which that saving arrives. Extracting all three is what
makes it possible to ask whether the market discounted a cost landing now
against a benefit landing in two years.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------- #
# Item-section splitting
# ---------------------------------------------------------------------- #

# Matches an item heading at the start of a line: "Item 5.02", "ITEM 5.02."
_ITEM_HEADING_RE = re.compile(
    r"(?im)^\s*item\s+(\d{1,2}\.\d{2})\b[.:\s—-]*",
)


def split_items(text: str) -> dict[str, str]:
    """Split filing text into ``{item_code: section_text}``.

    An 8-K body repeats its item headings in order, so each section runs
    from its heading to the next one. The signature/exhibit tail after the
    final section is kept with that section, which is harmless for keyword
    work and avoids dropping short disclosures.
    """
    matches = list(_ITEM_HEADING_RE.finditer(text))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        code = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = strip_item_title(code, text[start:end].strip())
        # A filing lists items twice (cover checkbox list, then body); keep
        # whichever occurrence carries the most prose.
        if code not in sections or len(body) > len(sections[code]):
            sections[code] = body
    return sections


# Official Form 8-K item titles. These are reproduced verbatim at the top of
# each section in the filing, and several of them contain the very verbs the
# parsers look for -- Item 5.02's own title says both "Departure" and
# "Appointment" -- so a section must have its title removed before any
# keyword test runs, or every 5.02 filing looks like a departure *and* a
# succession.
_ITEM_TITLES = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation or an Obligation under an "
            "Off-Balance Sheet Arrangement of a Registrant",
    "2.04": "Triggering Events That Accelerate or Increase a Direct Financial "
            "Obligation or an Obligation under an Off-Balance Sheet Arrangement",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule "
            "or Standard; Transfer of Listing",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements or a Related "
            "Audit Report or Completed Interim Review",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure of Directors or Certain Officers; Election of Directors; "
            "Appointment of Certain Officers; Compensatory Arrangements of "
            "Certain Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year",
    "5.04": "Temporary Suspension of Trading Under Registrant's Employee Benefit Plans",
    "5.05": "Amendments to the Registrant's Code of Ethics, or Waiver of a "
            "Provision of the Code of Ethics",
    "5.06": "Change in Shell Company Status",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "5.08": "Shareholder Director Nominations",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def strip_item_title(code: str, body: str) -> str:
    """Remove the official item title from the head of a section body.

    Matching is done on a punctuation- and case-insensitive normalization so
    that filings which re-wrap, re-capitalize, or re-punctuate the title
    (nearly all of them do at least one) still line up. Only a genuine
    prefix match is removed, so a section whose title was already absent is
    returned untouched.
    """
    title = _ITEM_TITLES.get(code)
    if not title or not body:
        return body
    target = _NON_ALNUM_RE.sub("", title.lower())
    if not target:
        return body

    matched = []
    for index, char in enumerate(body.lower()):
        if char.isalnum():
            matched.append(char)
            if len(matched) > len(target):
                return body  # overran without matching: no title present
            if not target.startswith("".join(matched)):
                return body  # diverged from the title
            if len(matched) == len(target):
                return body[index + 1:].lstrip(" \t\n.:;-\u2014")
    return body


# ---------------------------------------------------------------------- #
# Executive-change parsing (Item 5.02)
# ---------------------------------------------------------------------- #

# Role patterns, ordered most-senior-first so the first hit wins.
_ROLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("CEO", re.compile(r"(?i)\bchief\s+executive\s+officer\b|\bCEO\b")),
    ("CFO", re.compile(r"(?i)\bchief\s+financial\s+officer\b|\bCFO\b")),
    ("COO", re.compile(r"(?i)\bchief\s+operating\s+officer\b|\bCOO\b")),
    ("PRESIDENT", re.compile(r"(?i)\bpresident\b")),
    ("CHAIR", re.compile(r"(?i)\bchair(?:man|woman|person)?\s+of\s+the\s+board\b|\bexecutive\s+chair")),
    ("CTO", re.compile(r"(?i)\bchief\s+technology\s+officer\b|\bCTO\b")),
    ("CRO", re.compile(r"(?i)\bchief\s+revenue\s+officer\b|\bCRO\b")),
    ("CAO", re.compile(r"(?i)\bchief\s+accounting\s+officer\b|\bCAO\b")),
    ("DIRECTOR", re.compile(r"(?i)\b(?:a\s+)?(?:member\s+of\s+the\s+board|director)\b")),
]

# Language indicating someone is leaving.
_DEPARTURE_RE = re.compile(
    r"(?i)\b(?:resign(?:ed|ation|s|ing)?|depart(?:ure|ed|ing|s)?|step(?:ped|ping|s)?\s+down"
    r"|terminat(?:ed|ion|e)|separat(?:ion|ed|e)\s+(?:from|of|agreement)|dismiss(?:ed|al)"
    r"|removed\s+(?:as|from)|retire(?:d|ment|s)?|will\s+no\s+longer\s+serve"
    r"|ceased?\s+to\s+(?:be|serve)|relinquish(?:ed|es)?|transition(?:ed|ing)?\s+out"
    r"|mutually\s+agreed\s+to\s+part|placed\s+on\s+(?:administrative\s+)?leave)\b"
)

# Language indicating someone is arriving (used to detect orderly succession).
_APPOINTMENT_RE = re.compile(
    r"(?i)\b(?:appoint(?:ed|ment|s)?|promot(?:ed|ion)|elect(?:ed|ion)\s+(?:as|to)"
    r"|named\s+(?:as\s+)?(?:the\s+)?(?:new\s+)?(?:interim\s+)?(?:president|chief|CEO|CFO)"
    r"|hired|succeed(?:s|ed|ing)?|will\s+serve\s+as|assume(?:s|d)?\s+the\s+role)\b"
)

# A filing that only moves compensation around is not an event.
_COMP_ONLY_RE = re.compile(
    r"(?i)\b(?:compensatory\s+arrangement|equity\s+award|restricted\s+stock\s+unit|RSU"
    r"|option\s+grant|annual\s+bonus|salary\s+increase|severance\s+plan\s+amendment"
    r"|employment\s+agreement\s+amendment|incentive\s+plan)\b"
)

# Hard red flags: these materially change how a departure should be read.
#
# Item 5.02(a) requires an issuer to say whether a departure involved a
# disagreement, so almost every clean resignation contains the word inside a
# denial -- "not due to any disagreement", "did not involve any
# disagreement", "was not the result of a disagreement". Enumerating those
# phrasings is a losing game, so detection is inverted: find the word, then
# look back to the start of its sentence for any negation cue. Only an
# un-negated mention counts, which is the rare and genuinely material case.
_DISAGREEMENT_WORD_RE = re.compile(r"(?i)\bdisagreement")
_NEGATION_CUE_RE = re.compile(
    r"(?i)\b(?:not|no|nor|without|never|absence\s+of|unrelated\s+to)\b"
)
_FOR_CAUSE_RE = re.compile(
    r"(?i)\b(?:for\s+cause|terminated\s+for\s+cause|misconduct|violation\s+of\s+(?:the\s+)?company\s+polic"
    r"|code\s+of\s+(?:business\s+)?conduct|investigation|restat(?:e|ement)|material\s+weakness"
    r"|accounting\s+irregularit)\b"
)
_IMMEDIATE_RE = re.compile(
    r"(?i)\b(?:effective\s+immediately|with\s+immediate\s+effect|immediately\s+resign)\b"
)
_INTERIM_RE = re.compile(r"(?i)\binterim\b")
_RETIREMENT_RE = re.compile(r"(?i)\bretire(?:d|ment|s)?\b")

# Officer names are recovered from the construction these filings almost
# always use -- "Dev Ittycheria, the Company's President and Chief Executive
# Officer" -- rather than by taking the first capitalized pair in the
# section, which reliably picks up a heading like "Chief Executive" instead.
# The optional parenthetical absorbs quoted nicknames: Chirantan ("CJ") Desai.
_NAME_BEFORE_ROLE_RE = re.compile(
    "([A-Z][A-Za-z.’'-]+(?:\\s+(?:\\(\\s*[“”\"']?[A-Za-z.]+[“”\"']?\\s*\\)\\s+)?"
    "[A-Z][A-Za-z.’'-]+){0,3})\\s*,\\s*(?:the\\s+)?"
    "(?:Company[’']?s?\\s+|Registrant[’']?s?\\s+)?"
    "(?=(?:President|Chief|Interim|Executive|Senior|Vice|Chair|Principal|Founder|Co-Founder))"
)

# Fallback: an honorific-qualified surname.
_HONORIFIC_RE = re.compile("\\b(?:Mr|Ms|Mrs|Dr)\\.\\s+([A-Z][A-Za-z’'-]+)")

# Words that begin a sentence or heading and are never part of a person's
# name, used to reject matches such as "On December" or "The Company".
_NAME_STOPWORDS = {
    "on", "the", "in", "as", "at", "effective", "pursuant", "company",
    "registrant", "our", "additionally", "separately", "concurrently",
    "departure", "appointment", "election", "chief", "president", "interim",
    "this", "there", "following", "accordingly", "if", "subject", "during",
}


def _strip_possessive(name: str) -> str:
    """Drop a trailing possessive so "Wilderotter's" reads as a name."""
    return re.sub(r"(?i)[’']s?$", "", name.strip()).strip()


def _extract_person(window: str) -> str | None:
    """Pull the officer's name out of a departure sentence."""
    for match in _NAME_BEFORE_ROLE_RE.finditer(window):
        candidate = _strip_possessive(" ".join(match.group(1).split()))
        parts = candidate.split()
        if len(parts) < 2:
            continue
        if parts[0].lower().strip(".,") in _NAME_STOPWORDS:
            continue
        return candidate
    honorific = _HONORIFIC_RE.search(window)
    if honorific:
        return _strip_possessive(honorific.group(1)) or None
    return None


# Compensation boilerplate routinely contains "terminated for cause" inside a
# clawback condition describing a *hypothetical* future firing of the incoming
# officer. Reading that as an admission of cause mislabels ordinary
# successions, so a match preceded by conditional language is discarded.
_HYPOTHETICAL_RE = re.compile(
    r"(?i)\b(?:if|unless|in\s+the\s+event|should\s+(?:he|she|they)|subject\s+to"
    r"|would\s+be|were\s+to|in\s+case|provided\s+that)\b"
)


def _affirmative_match(pattern: re.Pattern, window: str, lookback: int = 90) -> bool:
    """True when ``pattern`` matches without conditional framing before it."""
    for match in pattern.finditer(window):
        prefix = window[max(0, match.start() - lookback): match.start()]
        if _HYPOTHETICAL_RE.search(prefix):
            continue
        return True
    return False

_SENIOR_ROLES = {"CEO", "CFO", "PRESIDENT", "COO"}


@dataclass
class ExecChange:
    """A parsed executive-change disclosure."""

    is_departure: bool
    is_appointment: bool
    roles: tuple[str, ...]              # roles touched, senior-first
    top_role: str | None                # most senior role involved
    person: str | None
    # Modifiers that drive expected severity.
    abrupt: bool = False                # "effective immediately"
    successor_named: bool = False       # orderly transition
    interim_successor: bool = False     # a caretaker, i.e. no plan
    disagreement: bool = False          # 5.02(a) disagreement language
    for_cause: bool = False             # misconduct / investigation / restatement
    retirement: bool = False            # framed as a retirement
    comp_only: bool = False             # housekeeping, not an event
    severity: float = 0.0               # 0..1 expected-shock score
    evidence: str = field(default="", repr=False)

    @property
    def is_senior_departure(self) -> bool:
        """A departure of an officer whose exit can move the stock."""
        return self.is_departure and self.top_role in _SENIOR_ROLES

    def to_dict(self) -> dict:
        return {
            "is_departure": self.is_departure,
            "is_appointment": self.is_appointment,
            "roles": list(self.roles),
            "top_role": self.top_role,
            "person": self.person,
            "abrupt": self.abrupt,
            "successor_named": self.successor_named,
            "interim_successor": self.interim_successor,
            "disagreement": self.disagreement,
            "for_cause": self.for_cause,
            "retirement": self.retirement,
            "comp_only": self.comp_only,
            "severity": self.severity,
            "is_senior_departure": self.is_senior_departure,
        }


def _affirmative_disagreement(window: str) -> bool:
    """True only when a disagreement is asserted rather than denied.

    Negation is searched in the sentence containing the keyword. Two details
    matter for real filings:

    * Whitespace is normalized first. Filing HTML flattens with newlines in
      the middle of sentences, and treating a line break as a sentence end
      would sever "not involve any" from the "disagreement" it negates.
    * A very short sentence prefix means the boundary was almost certainly an
      abbreviation's period ("Mr."), not a real sentence end, so the lookback
      is widened rather than trusted.
    """
    text = " ".join(window.split())
    for match in _DISAGREEMENT_WORD_RE.finditer(text):
        boundary = max(
            text.rfind(". ", 0, match.start()),
            text.rfind("; ", 0, match.start()),
        )
        sentence_start = boundary + 1 if boundary != -1 else 0
        prefix = text[sentence_start:match.start()]
        if len(prefix) < 25:
            prefix = text[max(0, match.start() - 160):match.start()]
        if _NEGATION_CUE_RE.search(prefix):
            continue
        return True
    return False


def parse_exec_change(section: str) -> ExecChange:
    """Parse an Item 5.02 section into a structured executive change."""
    if not section or not section.strip():
        return ExecChange(False, False, (), None, None)

    # Work on a window: 5.02 sections can run long with full comp tables,
    # and the narrative that matters sits at the top.
    head = section[:6000]

    roles = tuple(name for name, pattern in _ROLE_PATTERNS if pattern.search(head))
    top_role = roles[0] if roles else None

    departure_match = _DEPARTURE_RE.search(head)
    appointment_match = _APPOINTMENT_RE.search(head)
    is_departure = bool(departure_match)
    is_appointment = bool(appointment_match)

    comp_only = bool(_COMP_ONLY_RE.search(head)) and not is_departure and not is_appointment

    # Every modifier below is judged inside a window centred on the departure
    # sentence rather than across the whole section. Item 5.02 bodies bundle
    # the outgoing officer's exit with the incoming officer's full pay
    # package, and that second half is dense with words -- "for cause",
    # "immediately", "retirement" -- describing the successor's contract
    # rather than the departure being reported.
    if departure_match:
        window = head[max(0, departure_match.start() - 500): departure_match.end() + 800]
    else:
        window = head[:1200]

    person = _extract_person(window) if departure_match else None

    affirmative_disagreement = _affirmative_disagreement(window)

    exec_change = ExecChange(
        is_departure=is_departure,
        is_appointment=is_appointment,
        roles=roles,
        top_role=top_role,
        person=person,
        abrupt=_affirmative_match(_IMMEDIATE_RE, window),
        successor_named=is_departure and is_appointment,
        interim_successor=bool(_INTERIM_RE.search(window)),
        disagreement=affirmative_disagreement,
        for_cause=_affirmative_match(_FOR_CAUSE_RE, window),
        retirement=bool(_RETIREMENT_RE.search(window)),
        comp_only=comp_only,
        evidence=window[:600],
    )
    exec_change.severity = score_exec_severity(exec_change)
    return exec_change


def score_exec_severity(change: ExecChange) -> float:
    """Expected-shock score in ``[0, 1]`` for an executive change.

    The weights encode the standard reading of these filings: seniority sets
    the base, an unplanned exit is worse than a managed one, and admitted
    cause or disagreement is worst. A retirement with a named successor is
    the benign end. This orders events for selection; it is not a return
    forecast.
    """
    if not change.is_departure:
        return 0.0

    base = {
        "CEO": 0.55,
        "CFO": 0.40,
        "PRESIDENT": 0.30,
        "COO": 0.25,
        "CHAIR": 0.20,
        "CTO": 0.15,
        "CRO": 0.15,
        "CAO": 0.15,
        "DIRECTOR": 0.08,
    }.get(change.top_role or "", 0.10)

    score = base
    if change.for_cause:
        score += 0.25
    if change.disagreement:
        score += 0.20
    if change.abrupt:
        score += 0.12
    if change.interim_successor:
        score += 0.08      # a caretaker implies no succession plan
    if change.successor_named:
        score -= 0.10      # orderly handoff dampens the shock
    if change.retirement:
        score -= 0.08      # usually telegraphed well in advance
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------- #
# Efficiency-plan parsing (Items 2.05 / 2.06)
# ---------------------------------------------------------------------- #

_PLAN_RE = re.compile(
    r"(?i)\b(?:restructuring|reorganization|efficiency\s+(?:plan|program|initiative)"
    r"|cost[\s-]?(?:savings|reduction|optimization)\s*(?:plan|program|initiative)?"
    r"|workforce\s+reduction|reduction\s+in\s+force|headcount\s+reduction"
    r"|operational\s+(?:efficiency|realignment)|transformation\s+(?:plan|program)"
    r"|exit\s+(?:or\s+disposal\s+)?activit|plan\s+of\s+termination"
    r"|rightsiz(?:e|ing)|realignment\s+plan)\b"
)

# Financial-statement furniture. An earnings release carries balance sheets
# and cash-flow tables full of large numbers that have nothing to do with a
# restructuring; a document containing these is only trusted for plan
# figures when the issuer filed it under Item 2.05 or 2.06 explicitly.
_STATEMENT_RE = re.compile(
    r"(?i)(?:condensed\s+)?consolidated\s+(?:balance\s+sheets?|statements?\s+of"
    r"\s+(?:operations|cash\s+flows|income))|total\s+stockholders[’']?\s+equity"
)

# Money anchored to an explicit cost statement, so a figure is only read as a
# charge when the filing says it is one. Each alternative keeps the amount in
# group "amt"/"unit" via named groups on a single shared pattern body.
_MONEY = r"\$\s?(?P<amt>[\d,]+(?:\.\d+)?)\s*(?P<unit>million|billion|thousand|bn|mm)?"

_CHARGE_PATTERNS = [
    # "charges of approximately $125 million", "costs of $40 to $50 million"
    re.compile(
        r"(?i)(?:restructuring\s+|one[\s-]?time\s+|pre[\s-]?tax\s+|total\s+)?"
        r"(?:charges?|costs?|expenses?|cash\s+outlays?)\s+of\s+"
        r"(?:approximately\s+|about\s+|up\s+to\s+|an\s+aggregate\s+of\s+)?" + _MONEY
    ),
    # "expects to incur approximately $125 million"
    re.compile(
        r"(?i)(?:expects?\s+to\s+)?incur\s+(?:approximately\s+|about\s+|up\s+to\s+)?" + _MONEY
    ),
    # "$125 million of restructuring charges", "$125 million pre-tax charge"
    re.compile(
        _MONEY + r"\s+(?:of\s+|in\s+)?(?:pre[\s-]?tax\s+|one[\s-]?time\s+|total\s+)?"
        r"(?:restructuring\s+|severance\s+|exit\s+)?(?:charges?|costs?|expenses?)",
        re.IGNORECASE,
    ),
    # "aggregate charges ... estimated at $125 million"
    re.compile(r"(?i)(?:estimated|expected)\s+(?:to\s+be\s+)?(?:at\s+)?" + _MONEY
               + r"[^.]{0,60}(?:charge|cost)"),
]

_SAVINGS_PATTERNS = [
    # "annualized savings of approximately $200 million"
    re.compile(
        r"(?i)(?:annual(?:ized)?\s+|run[\s-]?rate\s+|net\s+|total\s+|estimated\s+)?"
        r"(?:cost\s+)?savings\s+of\s+(?:approximately\s+|about\s+|up\s+to\s+)?" + _MONEY
    ),
    # "$200 million in annualized savings"
    re.compile(
        _MONEY + r"\s+(?:of\s+|in\s+)?(?:annual(?:ized)?\s+|run[\s-]?rate\s+)?"
        r"(?:cost\s+)?savings",
        re.IGNORECASE,
    ),
    # "expects to save approximately $200 million"
    re.compile(
        r"(?i)(?:expects?\s+to\s+)?(?:save|reduce\s+(?:annual\s+)?(?:operating\s+)?"
        r"(?:expenses?|costs?)\s+by)\s+(?:approximately\s+|about\s+)?" + _MONEY
    ),
]

# Horizon language: when the promised benefit actually arrives.
_HORIZON_YEAR_RE = re.compile(r"(?i)\bby\s+(?:the\s+end\s+of\s+)?(?:fiscal\s+)?(?:year\s+)?(20\d{2})\b")
_HORIZON_SPAN_RE = re.compile(
    r"(?i)\b(?:over|within|during)\s+the\s+next\s+(\w+)\s+(year|quarter|month)s?"
    r"|\bwithin\s+(\w+)\s+(year|quarter|month)s?"
)

_HEADCOUNT_RE = re.compile(
    r"(?i)(?:approximately\s+)?([\d,]{2,9})\s*(?:employees|positions|roles|jobs)"
)
_HEADCOUNT_PCT_RE = re.compile(
    r"(?i)(?:approximately\s+)?([\d.]{1,5})\s*%\s*of\s+(?:its\s+|the\s+|our\s+)?"
    r"(?:global\s+|total\s+|current\s+)?(?:workforce|employees|headcount)"
)

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
    "eighteen": 18, "twenty-four": 24, "several": 3,
}

_MULTIPLIERS = {
    "billion": 1e9, "bn": 1e9,
    "million": 1e6, "mm": 1e6,
    "thousand": 1e3,
}

# Plausibility bounds for a disclosed restructuring charge. Anything outside
# this range is almost certainly a number lifted out of a financial table
# rather than a stated charge, so it is discarded instead of trusted.
MIN_PLAUSIBLE_CHARGE = 1e5          # $100k
MAX_PLAUSIBLE_CHARGE = 2.5e10       # $25bn


def _money_value(number: str, unit: str | None) -> float | None:
    """Convert a matched money figure into absolute dollars."""
    try:
        value = float(number.replace(",", ""))
    except (ValueError, AttributeError):
        return None
    if unit:
        return value * _MULTIPLIERS.get(unit.strip().lower(), 1.0)
    # A bare "$125" next to the word "charge" means $125 million; filings do
    # not disclose literal three-digit-dollar restructuring charges. Larger
    # bare numbers are read at face value.
    return value * 1e6 if value < 10_000 else value


def _first_anchored_amount(text: str, patterns: list[re.Pattern]) -> float | None:
    """Smallest plausible amount matched by any anchored pattern.

    The *minimum* is taken rather than the maximum because filings state
    ranges ("$40 to $50 million") and totals alongside components; the
    conservative end avoids overstating a charge, and overstating is the
    direction that would manufacture a signal.
    """
    found: list[float] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = _money_value(match.group("amt"), match.group("unit"))
            if value is None:
                continue
            if MIN_PLAUSIBLE_CHARGE <= value <= MAX_PLAUSIBLE_CHARGE:
                found.append(value)
    return min(found) if found else None


def _parse_horizon(text: str, filing_year: int | None) -> float | None:
    """Years until the promised savings arrive, measured from the filing."""
    if filing_year:
        years = [
            int(match.group(1)) for match in _HORIZON_YEAR_RE.finditer(text)
            if filing_year <= int(match.group(1)) <= filing_year + 10
        ]
        if years:
            return float(min(years) - filing_year)

    span = _HORIZON_SPAN_RE.search(text)
    if span:
        groups = [g for g in span.groups() if g]
        if len(groups) >= 2:
            count_raw, unit = groups[0], groups[1].lower()
            count = (
                float(count_raw) if count_raw.replace(".", "").isdigit()
                else float(_WORD_NUMBERS.get(count_raw.lower(), 0) or 0)
            )
            if count:
                if unit.startswith("year"):
                    return count
                if unit.startswith("quarter"):
                    return count / 4.0
                if unit.startswith("month"):
                    return count / 12.0
    return None


@dataclass
class EfficiencyPlan:
    """A parsed restructuring / efficiency-plan disclosure."""

    is_plan: bool
    charge_usd: float | None = None             # upfront cost disclosed
    savings_usd: float | None = None            # annualized benefit promised
    savings_horizon_years: float | None = None  # when the benefit lands
    headcount: int | None = None
    headcount_pct: float | None = None
    cash_charge: bool = False
    quantified: bool = False                    # a real figure was recovered
    # The asymmetry motivating the trade: cost now, benefit later.
    cost_front_loaded: bool = False
    payback_years: float | None = None
    evidence: str = field(default="", repr=False)

    def to_dict(self) -> dict:
        return {
            "is_plan": self.is_plan,
            "charge_usd": self.charge_usd,
            "savings_usd": self.savings_usd,
            "savings_horizon_years": self.savings_horizon_years,
            "headcount": self.headcount,
            "headcount_pct": self.headcount_pct,
            "cash_charge": self.cash_charge,
            "quantified": self.quantified,
            "cost_front_loaded": self.cost_front_loaded,
            "payback_years": self.payback_years,
        }


def parse_efficiency_plan(
    text: str,
    *,
    filing_year: int | None = None,
    trust_tables: bool = False,
) -> EfficiencyPlan:
    """Parse restructuring text into charge, savings, and timing.

    :param filing_year: year of the filing, used to turn "by 2027" into a
        horizon in years. Without it, absolute-year horizons are skipped
        rather than guessed.
    :param trust_tables: set only when the issuer filed under Item 2.05 or
        2.06. Otherwise a document containing full financial statements has
        its money figures ignored, because an earnings release's balance
        sheet will happily yield a multi-billion-dollar "charge" that was
        never a charge at all.
    """
    if not text or not text.strip():
        return EfficiencyPlan(False)

    body = text[:40000]
    if not _PLAN_RE.search(body):
        return EfficiencyPlan(False)

    has_statements = bool(_STATEMENT_RE.search(body))
    extract_money = trust_tables or not has_statements

    charge = savings = None
    horizon = None
    if extract_money:
        charge = _first_anchored_amount(body, _CHARGE_PATTERNS)
        savings = _first_anchored_amount(body, _SAVINGS_PATTERNS)
        horizon = _parse_horizon(body, filing_year)

    headcount = None
    match = _HEADCOUNT_RE.search(body)
    if match:
        try:
            value = int(match.group(1).replace(",", ""))
            # Guard against year-like and table-like captures.
            if 5 <= value <= 500_000:
                headcount = value
        except ValueError:
            headcount = None

    headcount_pct = None
    match = _HEADCOUNT_PCT_RE.search(body)
    if match:
        try:
            pct = float(match.group(1))
            if 0 < pct <= 100:
                headcount_pct = pct
        except ValueError:
            headcount_pct = None

    payback = None
    if charge and savings and savings > 0:
        payback = charge / savings

    # The asymmetry: a charge large relative to the annual benefit, or a
    # benefit explicitly deferred beyond the current year.
    cost_front_loaded = bool(
        (payback is not None and payback >= 1.0)
        or (horizon is not None and horizon >= 1.0 and charge is not None)
    )

    return EfficiencyPlan(
        is_plan=True,
        charge_usd=charge,
        savings_usd=savings,
        savings_horizon_years=horizon,
        headcount=headcount,
        headcount_pct=headcount_pct,
        cash_charge=bool(re.search(
            r"(?i)\bcash\s+(?:charge|outlay|expenditure|payment)", body)),
        quantified=bool(charge or savings or headcount or headcount_pct),
        cost_front_loaded=cost_front_loaded,
        payback_years=payback,
        evidence=body[:600],
    )
