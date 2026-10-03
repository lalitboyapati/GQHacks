"""Massive API client: prices, option chains, option bars, and news.

Massive exposes a Polygon-compatible surface, which makes it the cheapest
complete source for this research — it covers all four things the backtest
needs beyond the filings themselves:

  * daily bars for the underlying (event-window returns),
  * the historical option chain *including expired contracts*, which is what
    makes a dated backtest possible at all,
  * daily bars for individual option contracts (real premium paid/received,
    rather than a model's guess), and
  * timestamped ticker news, which is how a filing that merely restates
    Monday's press release is told apart from one that breaks new ground.

Every response is cached to disk keyed by the full request, so a re-run of
the backtest issues no API calls and results stay reproducible.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def option_ticker(underlying: str, expiry: date, kind: str, strike: float) -> str:
    """Build an OCC-style option symbol in Massive/Polygon form.

    Example: ``O:MDB251121C00400000`` is an MDB call expiring 2025-11-21
    struck at $400. The strike is encoded as the price in thousandths,
    zero-padded to eight digits.
    """
    side = "C" if kind.upper().startswith("C") else "P"
    strike_int = int(round(float(strike) * 1000))
    return f"O:{underlying.upper()}{expiry:%y%m%d}{side}{strike_int:08d}"


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar for an underlying or an option contract."""

    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    transactions: int | None = None

    @property
    def mid_proxy(self) -> float:
        """Best single-price estimate for a fill on this bar.

        Option bars are thin and their close can print at one side of a wide
        spread; VWAP, when present, is a steadier estimate of where the
        contract actually traded.
        """
        return float(self.vwap) if self.vwap else float(self.close)


@dataclass(frozen=True)
class OptionContract:
    """A listed option contract as reported by the reference endpoint."""

    ticker: str
    underlying: str
    expiration: date
    strike: float
    contract_type: str          # "call" | "put"
    shares_per_contract: int = 100

    @property
    def is_call(self) -> bool:
        return self.contract_type.lower().startswith("c")


@dataclass(frozen=True)
class NewsItem:
    """A timestamped news article, used for disclosure-novelty scoring."""

    published_utc: datetime
    title: str
    publisher: str | None = None
    description: str | None = None
    url: str | None = None
    tickers: tuple[str, ...] = ()


class MassiveClient:
    """Disk-cached wrapper over the Massive REST client."""

    def __init__(self, api_key: str, cache_dir: Path, offline: bool = False):
        self.api_key = api_key
        self.cache_dir = Path(cache_dir) / "massive"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self._client: Any = None
        self.calls = 0

    @property
    def client(self):
        if self._client is None:
            from massive import RESTClient
            self._client = RESTClient(api_key=self.api_key)
        return self._client

    # ---------------------------------------------------------------- #
    # Caching
    # ---------------------------------------------------------------- #
    def _cache_file(self, kind: str, key: str) -> Path:
        import hashlib
        digest = hashlib.sha256(key.encode()).hexdigest()[:40]
        sub = self.cache_dir / kind
        sub.mkdir(parents=True, exist_ok=True)
        return sub / f"{digest}.json"

    def _cached(self, kind: str, key: str, producer) -> Any:
        """Return cached rows for ``key``, otherwise call ``producer`` once."""
        path = self._cache_file(kind, key)
        if path.exists():
            return json.loads(path.read_text())
        if self.offline:
            raise RuntimeError(f"offline mode: {kind}:{key} not cached")
        rows = producer()
        self.calls += 1
        path.write_text(json.dumps(rows))
        return rows

    # ---------------------------------------------------------------- #
    # Daily bars
    # ---------------------------------------------------------------- #
    def daily_bars(self, ticker: str, start: str, end: str, adjusted: bool = True) -> list[Bar]:
        """Daily OHLCV bars for an equity or option ticker, inclusive range."""
        key = f"{ticker}|{start}|{end}|{adjusted}|day"

        def produce() -> list[dict]:
            out = []
            for agg in self.client.list_aggs(
                ticker=ticker, multiplier=1, timespan="day",
                from_=start, to=end, adjusted=adjusted,
                sort="asc", limit=50000,
            ):
                out.append({
                    "t": getattr(agg, "timestamp", None),
                    "o": getattr(agg, "open", None),
                    "h": getattr(agg, "high", None),
                    "l": getattr(agg, "low", None),
                    "c": getattr(agg, "close", None),
                    "v": getattr(agg, "volume", None),
                    "vw": getattr(agg, "vwap", None),
                    "n": getattr(agg, "transactions", None),
                })
            return out

        rows = self._cached("aggs", key, produce)
        bars: list[Bar] = []
        for row in rows:
            if row.get("t") is None or row.get("c") is None:
                continue
            day = datetime.fromtimestamp(row["t"] / 1000.0, tz=timezone.utc).date()
            bars.append(Bar(
                day=day,
                open=float(row.get("o") or row["c"]),
                high=float(row.get("h") or row["c"]),
                low=float(row.get("l") or row["c"]),
                close=float(row["c"]),
                volume=float(row.get("v") or 0.0),
                vwap=float(row["vw"]) if row.get("vw") else None,
                transactions=int(row["n"]) if row.get("n") else None,
            ))
        bars.sort(key=lambda b: b.day)
        return bars

    # ---------------------------------------------------------------- #
    # Option reference data
    # ---------------------------------------------------------------- #
    def option_contracts(
        self,
        underlying: str,
        *,
        as_of: str,
        expiration_gte: str,
        expiration_lte: str,
        contract_type: str | None = None,
        limit: int = 1000,
    ) -> list[OptionContract]:
        """List contracts listed on ``as_of`` expiring in the given window.

        ``expired=True`` is required: by the time a backtest runs, every
        contract that was live during the event has expired, and the default
        view would return nothing.
        """
        key = f"{underlying}|{as_of}|{expiration_gte}|{expiration_lte}|{contract_type}"

        def produce() -> list[dict]:
            out = []
            for contract in self.client.list_options_contracts(
                underlying_ticker=underlying.upper(),
                as_of=as_of,
                expiration_date_gte=expiration_gte,
                expiration_date_lte=expiration_lte,
                contract_type=contract_type,
                expired=True,
                limit=limit,
                sort="expiration_date",
                order="asc",
            ):
                out.append({
                    "ticker": getattr(contract, "ticker", None),
                    "underlying_ticker": getattr(contract, "underlying_ticker", None),
                    "expiration_date": getattr(contract, "expiration_date", None),
                    "strike_price": getattr(contract, "strike_price", None),
                    "contract_type": getattr(contract, "contract_type", None),
                    "shares_per_contract": getattr(contract, "shares_per_contract", 100),
                })
            return out

        rows = self._cached("contracts", key, produce)
        contracts: list[OptionContract] = []
        for row in rows:
            if not row.get("ticker") or row.get("strike_price") is None:
                continue
            try:
                expiry = date.fromisoformat(str(row["expiration_date"])[:10])
            except (TypeError, ValueError):
                continue
            contracts.append(OptionContract(
                ticker=str(row["ticker"]),
                underlying=str(row.get("underlying_ticker") or underlying).upper(),
                expiration=expiry,
                strike=float(row["strike_price"]),
                contract_type=str(row.get("contract_type") or "call"),
                shares_per_contract=int(row.get("shares_per_contract") or 100),
            ))
        return contracts

    # ---------------------------------------------------------------- #
    # News (novelty signal)
    # ---------------------------------------------------------------- #
    def news(
        self,
        ticker: str,
        *,
        published_gte: str,
        published_lte: str,
        limit: int = 1000,
    ) -> list[NewsItem]:
        """Articles for ``ticker`` published in ``[published_gte, published_lte]``."""
        key = f"{ticker}|{published_gte}|{published_lte}|{limit}"

        def produce() -> list[dict]:
            out = []
            for article in self.client.list_ticker_news(
                ticker=ticker.upper(),
                published_utc_gte=published_gte,
                published_utc_lte=published_lte,
                limit=limit,
                sort="published_utc",
                order="asc",
            ):
                out.append({
                    "published_utc": getattr(article, "published_utc", None),
                    "title": getattr(article, "title", None),
                    "publisher": getattr(getattr(article, "publisher", None), "name", None),
                    "description": getattr(article, "description", None),
                    "article_url": getattr(article, "article_url", None),
                    "tickers": list(getattr(article, "tickers", None) or []),
                })
            return out

        rows = self._cached("news", key, produce)
        items: list[NewsItem] = []
        for row in rows:
            raw = row.get("published_utc")
            if not raw or not row.get("title"):
                continue
            try:
                published = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            items.append(NewsItem(
                published_utc=published.astimezone(timezone.utc),
                title=str(row["title"]),
                publisher=row.get("publisher"),
                description=row.get("description"),
                url=row.get("article_url"),
                tickers=tuple(row.get("tickers") or ()),
            ))
        items.sort(key=lambda n: n.published_utc)
        return items

    # ---------------------------------------------------------------- #
    # Reference / universe
    # ---------------------------------------------------------------- #
    def ticker_details(self, ticker: str, as_of: str | None = None) -> dict:
        """Company reference data, including market cap and share count."""
        key = f"{ticker}|{as_of}"

        def produce() -> dict:
            details = self.client.get_ticker_details(ticker=ticker.upper(), date=as_of)
            return {
                "ticker": getattr(details, "ticker", ticker),
                "name": getattr(details, "name", None),
                "market_cap": getattr(details, "market_cap", None),
                "share_class_shares_outstanding": getattr(details, "share_class_shares_outstanding", None),
                "weighted_shares_outstanding": getattr(details, "weighted_shares_outstanding", None),
                "primary_exchange": getattr(details, "primary_exchange", None),
                "sic_description": getattr(details, "sic_description", None),
                "total_employees": getattr(details, "total_employees", None),
            }

        return self._cached("details", key, produce)

    def list_8k_items(
        self,
        ticker: str,
        *,
        filing_date_gte: str,
        filing_date_lte: str,
        limit: int = 1000,
    ) -> list[dict]:
        """Massive's parsed 8-K rows — a fast item-code screen.

        Useful for sweeping a wide universe cheaply, but it carries only a
        filing *date* and no body text, so anything timing- or
        language-dependent still has to come from EDGAR.
        """
        key = f"{ticker}|{filing_date_gte}|{filing_date_lte}"

        def produce() -> list[dict]:
            out = []
            for filing in self.client.list_stocks_filings_8k_text(
                ticker=ticker.upper(),
                form_type="8-K",
                filing_date_gte=filing_date_gte,
                filing_date_lte=filing_date_lte,
                limit=limit,
                sort="filing_date.asc",
            ):
                out.append({
                    "ticker": getattr(filing, "ticker", ticker),
                    "filing_date": getattr(filing, "filing_date", None),
                    "accession_number": getattr(filing, "accession_number", None),
                    "items_text": getattr(filing, "items_text", None),
                    "filing_url": getattr(filing, "filing_url", None),
                })
            return out

        return self._cached("filings8k", key, produce)
