"""SEC EDGAR client for 8-K discovery.

EDGAR is the authoritative source for two fields the vendor APIs do not
expose and that this research depends on:

  * ``acceptanceDateTime`` — the exact moment the filing became public,
    in true UTC despite EDGAR's "Z"-suffixed-ET-looking formatting. It is
    what separates a pre-market disclosure from an after-close one, and
    therefore which session can actually be traded.
  * the full filing text — needed to tell a genuine revelation from a
    re-filed press release, and to pull charge/savings figures out of a
    restructuring disclosure.

The submissions endpoint returns the most recent 1,000 filings inline and
pages older history into companion files, both of which are followed here.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from eightk.http import CachedSession

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"

# Regular trading hours, used to bucket a filing into a tradable session.
MARKET_OPEN = (9, 30)
MARKET_CLOSE = (16, 0)


@dataclass
class Filing:
    """One 8-K filing with everything needed to place a trade around it."""

    ticker: str
    cik: str
    accession: str
    form: str
    filing_date: str               # YYYY-MM-DD, EDGAR's calendar filing date
    acceptance_utc: datetime       # exact publication instant
    items: tuple[str, ...]         # ("5.02", "7.01", ...)
    primary_document: str
    report_date: str | None = None  # "Date of earliest event reported"
    text: str | None = field(default=None, repr=False)

    @property
    def acceptance_et(self) -> datetime:
        return self.acceptance_utc.astimezone(EASTERN)

    @property
    def session_bucket(self) -> str:
        """Which trading session the disclosure lands in.

        ``PRE`` (before 09:30 ET) and ``POST`` (at/after 16:00 ET) both mean
        the first tradable print is a gap; ``RTH`` means the tape was live
        when it hit, so the reaction begins intraday.
        """
        et = self.acceptance_et
        minutes = et.hour * 60 + et.minute
        if minutes < MARKET_OPEN[0] * 60 + MARKET_OPEN[1]:
            return "PRE"
        if minutes >= MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]:
            return "POST"
        return "RTH"

    @property
    def filing_url(self) -> str:
        accn = self.accession.replace("-", "")
        return f"{SEC_ARCHIVE_BASE}/{int(self.cik)}/{accn}/{self.primary_document}"

    @property
    def index_url(self) -> str:
        accn = self.accession.replace("-", "")
        return f"{SEC_ARCHIVE_BASE}/{int(self.cik)}/{accn}/{self.accession}-index.htm"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "cik": self.cik,
            "accession": self.accession,
            "form": self.form,
            "filing_date": self.filing_date,
            "acceptance_utc": self.acceptance_utc.isoformat(),
            "acceptance_et": self.acceptance_et.isoformat(),
            "session_bucket": self.session_bucket,
            "items": list(self.items),
            "primary_document": self.primary_document,
            "report_date": self.report_date,
            "filing_url": self.filing_url,
        }

    @classmethod
    def from_dict(cls, row: dict) -> "Filing":
        return cls(
            ticker=row["ticker"],
            cik=row["cik"],
            accession=row["accession"],
            form=row["form"],
            filing_date=row["filing_date"],
            acceptance_utc=datetime.fromisoformat(row["acceptance_utc"]),
            items=tuple(row["items"]),
            primary_document=row["primary_document"],
            report_date=row.get("report_date"),
        )


def _parse_acceptance(raw: str) -> datetime:
    """Parse EDGAR's acceptanceDateTime into an aware UTC datetime.

    The field looks like ``2025-11-03T13:31:10.000Z``. Verified against the
    filing-index page (which renders 08:31:10 ET for that accession), so the
    Z really is UTC and a plain conversion is correct.
    """
    cleaned = raw.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _split_items(raw: str | None) -> tuple[str, ...]:
    """Normalize EDGAR's ``items`` string into bare item codes.

    The field arrives as ``"2.02,5.02,9.01"`` on modern filings but older
    ones embed prose like ``"Item 5.02 Departure of Directors"``, so codes
    are extracted by pattern rather than by splitting alone.
    """
    if not raw:
        return ()
    codes = re.findall(r"\b(\d{1,2}\.\d{2})\b", raw)
    # Preserve filing order while removing duplicates.
    seen: dict[str, None] = {}
    for code in codes:
        seen.setdefault(code, None)
    return tuple(seen)


class EdgarClient:
    """Read-only EDGAR access over a cached, rate-limited session."""

    def __init__(self, session: CachedSession):
        self.session = session
        self._ticker_map: dict[str, str] | None = None

    # ---------------------------------------------------------------- #
    # Ticker / CIK resolution
    # ---------------------------------------------------------------- #
    def ticker_to_cik(self, ticker: str) -> str | None:
        """Map a ticker to its zero-padded 10-digit CIK."""
        if self._ticker_map is None:
            body = self.session.get_text(SEC_TICKERS_URL)
            payload = json.loads(body or "{}")
            self._ticker_map = {
                str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
                for row in payload.values()
            }
            logger.info("resolved %d ticker->CIK pairs", len(self._ticker_map))
        return self._ticker_map.get(ticker.strip().upper())

    # ---------------------------------------------------------------- #
    # Filing discovery
    # ---------------------------------------------------------------- #
    def list_8k(
        self,
        ticker: str,
        *,
        date_gte: str | None = None,
        date_lte: str | None = None,
        items: set[str] | None = None,
        include_history: bool = True,
    ) -> list[Filing]:
        """List a company's 8-K filings, newest-first history included.

        :param items: keep only filings disclosing at least one of these
            item codes (e.g. ``{"5.02"}``). ``None`` keeps every 8-K.
        """
        cik = self.ticker_to_cik(ticker)
        if cik is None:
            logger.warning("no CIK for ticker %s", ticker)
            return []

        body = self.session.get_text(SEC_SUBMISSIONS_URL.format(cik=cik))
        payload = json.loads(body or "{}")
        company = payload.get("name", ticker)

        blocks = [payload.get("filings", {}).get("recent", {})]
        if include_history:
            for extra in payload.get("filings", {}).get("files", []):
                name = extra.get("name")
                if not name:
                    continue
                older = self.session.get_text(f"https://data.sec.gov/submissions/{name}")
                if older:
                    blocks.append(json.loads(older))

        out: list[Filing] = []
        for block in blocks:
            forms = block.get("form") or []
            for i, form in enumerate(forms):
                if not str(form).startswith("8-K"):
                    continue
                filing_date = str(block["filingDate"][i])
                if date_gte and filing_date < date_gte:
                    continue
                if date_lte and filing_date > date_lte:
                    continue
                codes = _split_items(block.get("items", [None] * len(forms))[i])
                if items and not (set(codes) & items):
                    continue
                raw_accept = block.get("acceptanceDateTime", [None] * len(forms))[i]
                if not raw_accept:
                    continue
                out.append(Filing(
                    ticker=ticker.upper(),
                    cik=cik,
                    accession=str(block["accessionNumber"][i]),
                    form=str(form),
                    filing_date=filing_date,
                    acceptance_utc=_parse_acceptance(str(raw_accept)),
                    items=codes,
                    primary_document=str(block.get("primaryDocument", [""] * len(forms))[i] or ""),
                    report_date=(str(block.get("reportDate", [""] * len(forms))[i]) or None),
                ))

        out.sort(key=lambda f: f.acceptance_utc, reverse=True)
        logger.info("%s (%s): %d matching 8-K filings", ticker, company, len(out))
        return out

    # ---------------------------------------------------------------- #
    # Document text
    # ---------------------------------------------------------------- #
    def filing_text(self, filing: Filing) -> str:
        """Return the primary 8-K document as plain text (cached)."""
        if filing.text is not None:
            return filing.text
        raw = self.session.get_text(filing.filing_url, allow_404=True)
        if raw is None:
            logger.warning("primary doc missing for %s", filing.accession)
            filing.text = ""
            return ""
        filing.text = html_to_text(raw)
        return filing.text

    def exhibit_urls(self, filing: Filing) -> list[str]:
        """List exhibit documents (press releases live in EX-99.x).

        The press release attached to an 8-K is what hit the wire; comparing
        it with the filing body is how the novelty test distinguishes a true
        disclosure from a restatement of an earlier announcement.
        """
        accn = filing.accession.replace("-", "")
        base = f"{SEC_ARCHIVE_BASE}/{int(filing.cik)}/{accn}"
        body = self.session.get_text(f"{base}/index.json", allow_404=True)
        if not body:
            return []
        try:
            items = json.loads(body)["directory"]["item"]
        except (KeyError, ValueError, TypeError):
            return []
        urls = []
        for item in items:
            name = str(item.get("name", ""))
            if re.search(r"ex-?99", name, re.IGNORECASE) and name.lower().endswith((".htm", ".html", ".txt")):
                urls.append(f"{base}/{name}")
        return urls

    def exhibit_text(self, filing: Filing) -> str:
        """Concatenated plain text of the filing's EX-99 exhibits."""
        chunks = []
        for url in self.exhibit_urls(filing):
            raw = self.session.get_text(url, allow_404=True)
            if raw:
                chunks.append(html_to_text(raw))
        return "\n\n".join(chunks)


_TAG_RE = re.compile(r"(?is)<(script|style|xbrl)[^>]*>.*?</\1>")
_BR_RE = re.compile(r"(?i)<(br|/p|/div|/tr|/h\d)[^>]*>")
_ANYTAG_RE = re.compile(r"<[^>]+>")


def html_to_text(raw: str) -> str:
    """Flatten filing HTML to readable text.

    Block-level close tags become newlines first so that item headings stay
    on their own lines; that structure is what the item-section splitter in
    ``classify`` relies on.
    """
    text = _TAG_RE.sub(" ", raw)
    text = _BR_RE.sub("\n", text)
    text = _ANYTAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
