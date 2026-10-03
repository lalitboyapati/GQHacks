"""Databento OPRA access for validating modeled option prices on real quotes.

Massive's option bars drive the backtest because they are complete enough and
already paid for. Databento's role here is narrower and more valuable: it
holds true OPRA bid/ask, so the handful of signals that actually look
promising can be re-priced on quotes a trader could have hit, rather than on
a session aggregate.

Every call is gated by two things, because OPRA volume is enormous and the
available credit is not:

1. ``metadata.get_cost`` is consulted *before* any data request, and the
   quote is checked against a persistent ledger (see :mod:`eightk.budget`).
2. Only explicitly named contract symbols are ever requested. Parent
   symbology (``MDB.OPT``) would pull every strike and expiry on the name
   and is deliberately unreachable through this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from eightk.budget import BudgetExceeded, SpendLedger

logger = logging.getLogger(__name__)

OPRA_DATASET = "OPRA.PILLAR"

# Coarse schemas only. Tick-level schemas (mbp-1, trades) on OPRA are orders
# of magnitude larger and are not worth the credit for event-window work.
ALLOWED_SCHEMAS = frozenset({"ohlcv-1d", "ohlcv-1h", "ohlcv-1m", "bbo-1m", "bbo-1s", "cbbo-1s"})


@dataclass
class OpraQuote:
    """One option quote or bar sourced from Databento."""

    symbol: str
    ts: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.close

    @property
    def spread_pct(self) -> float | None:
        """Quoted spread as a fraction of mid — the real cost of trading.

        This is the number that decides whether a strategy survives: a
        modeled 4% half-spread is a guess, while this is measured.
        """
        mid = self.mid
        if not mid or mid <= 0 or self.bid is None or self.ask is None:
            return None
        return (self.ask - self.bid) / mid


class DatabentoOpra:
    """Budget-guarded, disk-cached OPRA reader."""

    def __init__(
        self,
        api_key: str,
        cache_dir: Path,
        ledger: SpendLedger,
        *,
        dataset: str = OPRA_DATASET,
    ):
        self.api_key = api_key
        self.cache_dir = Path(cache_dir) / "databento"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = ledger
        self.dataset = dataset
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import databento as db
            self._client = db.Historical(self.api_key)
        return self._client

    # ------------------------------------------------------------------ #
    # Cost control
    # ------------------------------------------------------------------ #
    def quote_cost(
        self,
        symbols: list[str],
        start: str,
        end: str,
        schema: str = "bbo-1m",
    ) -> float:
        """Ask Databento what a query would cost, in USD."""
        if schema not in ALLOWED_SCHEMAS:
            raise ValueError(
                f"schema {schema!r} is not permitted here; allowed: "
                f"{sorted(ALLOWED_SCHEMAS)}"
            )
        if not symbols:
            return 0.0
        return float(self.client.metadata.get_cost(
            dataset=self.dataset,
            symbols=symbols,
            stype_in="raw_symbol",
            schema=schema,
            start=start,
            end=end,
        ))

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    def fetch(
        self,
        symbols: list[str],
        start: str,
        end: str,
        schema: str = "bbo-1m",
        *,
        dry_run: bool = False,
    ) -> list[OpraQuote]:
        """Fetch quotes for explicitly named contracts.

        :param dry_run: price the query and return ``[]`` without buying it.
            Use this to size a validation pass before committing credit.
        """
        if not symbols:
            return []

        cache_key = f"{self.dataset}|{schema}|{start}|{end}|{','.join(sorted(symbols))}"
        import hashlib
        digest = hashlib.sha256(cache_key.encode()).hexdigest()[:40]
        cache_path = self.cache_dir / f"{digest}.parquet"

        if cache_path.exists():
            import pandas as pd
            frame = pd.read_parquet(cache_path)
            return self._frame_to_quotes(frame)

        cost = self.quote_cost(symbols, start, end, schema)
        description = f"{schema} {len(symbols)} symbol(s) {start}..{end}"
        logger.info("Databento quoted $%.4f for %s", cost, description)

        if dry_run:
            logger.info("dry run: not purchasing (%s)", self.ledger.summary())
            return []

        self.ledger.check(cost, description)

        data = self.client.timeseries.get_range(
            dataset=self.dataset,
            symbols=symbols,
            stype_in="raw_symbol",
            schema=schema,
            start=start,
            end=end,
        )
        frame = data.to_df()
        # Cache before recording spend so a crash mid-write cannot leave
        # the credit charged with nothing saved to show for it.
        frame.to_parquet(cache_path)
        self.ledger.record(cost, description, symbols=len(symbols), schema=schema)
        return self._frame_to_quotes(frame)

    @staticmethod
    def _frame_to_quotes(frame) -> list[OpraQuote]:
        """Convert a Databento DataFrame into quote records."""
        quotes: list[OpraQuote] = []
        for ts, row in frame.iterrows():
            def pick(*names):
                for name in names:
                    if name in row and row[name] is not None:
                        try:
                            value = float(row[name])
                        except (TypeError, ValueError):
                            continue
                        if value == value:  # not NaN
                            return value
                return None

            quotes.append(OpraQuote(
                symbol=str(row.get("symbol", "")),
                ts=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                open=pick("open"),
                high=pick("high"),
                low=pick("low"),
                close=pick("close", "price"),
                bid=pick("bid_px_00", "bid_px"),
                ask=pick("ask_px_00", "ask_px"),
                volume=pick("volume", "size"),
            ))
        return quotes

    def validate_contracts(
        self,
        contracts: list[str],
        day: date,
        *,
        schema: str = "bbo-1m",
        dry_run: bool = True,
    ) -> dict[str, OpraQuote | None]:
        """Pull one session of quotes for named contracts.

        Defaults to ``dry_run=True`` so that merely calling this never spends
        credit; pass ``dry_run=False`` deliberately once the quoted cost has
        been reviewed.
        """
        start = day.isoformat()
        end = (day + timedelta(days=1)).isoformat()
        try:
            quotes = self.fetch(contracts, start, end, schema, dry_run=dry_run)
        except BudgetExceeded as exc:
            logger.error("budget guard refused the query: %s", exc)
            return {}

        best: dict[str, OpraQuote | None] = {symbol: None for symbol in contracts}
        for quote in quotes:
            if quote.symbol in best and best[quote.symbol] is None:
                best[quote.symbol] = quote
        return best
