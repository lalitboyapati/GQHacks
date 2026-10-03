"""Massive (formerly Polygon.io) Python Client.

Provides a clean interface for querying:
- Historical & intraday aggregates (bars)
- Quotes (bid/ask) and trades (tick-level)
- Market snapshots (day open, high, low, close, volume, prev close)
- Options contracts & chains
- Technical indicators (SMA, EMA, RSI, MACD computed server-side)
- Market news & sentiment
- Crypto & Forex aggregates
"""

from __future__ import annotations

import os
import requests
from typing import Any
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


class MassiveClient:
    """Client for querying the Massive (Polygon.io) Market Data API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("MASSIVE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Missing Massive API Key. Pass api_key or set MASSIVE_API_KEY in massive/.env"
            )
        self.base_url = (base_url or os.environ.get("MASSIVE_BASE_URL", "https://api.polygon.io")).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "MassiveClient-GQHacks/1.0"
        })

    def _get(self, endpoint: str, params: dict | None = None) -> dict[str, Any]:
        """Send an authenticated GET request to the Massive API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Massive API Error [{resp.status_code}] on {url}: {resp.text}"
            )
        return resp.json()

    # -------------------------------------------------------------------------
    # Stocks & Equities
    # -------------------------------------------------------------------------
    def get_bars(
        self,
        ticker: str,
        multiplier: int = 1,
        timespan: str = "day",
        from_date: str = "2026-01-01",
        to_date: str = "2026-10-02",
        adjusted: bool = True,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Fetch historical aggregate bars (OHLCV) for a ticker.

        :param timespan: 'minute', 'hour', 'day', 'week', 'month', 'quarter', 'year'
        :return: list of bar dicts: [{'t': timestamp_ms, 'o': open, 'h': high, 'l': low, 'c': close, 'v': volume, 'vw': vwap}, ...]
        """
        endpoint = f"/v2/aggs/ticker/{ticker.upper()}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {
            "adjusted": str(adjusted).lower(),
            "sort": "asc",
            "limit": limit,
        }
        res = self._get(endpoint, params=params)
        return res.get("results", [])

    def get_snapshot(self, ticker: str) -> dict[str, Any]:
        """Fetch current snapshot for a stock (day's bar, prev day, last quote, last trade)."""
        endpoint = f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}"
        res = self._get(endpoint)
        return res.get("ticker", {})

    def get_previous_close(self, ticker: str) -> dict[str, Any]:
        """Fetch previous day's close for a ticker."""
        endpoint = f"/v2/aggs/ticker/{ticker.upper()}/prev"
        res = self._get(endpoint)
        results = res.get("results", [])
        return results[0] if results else {}

    def get_quotes(self, ticker: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch latest quotes (bid/ask) for a ticker."""
        endpoint = f"/v3/quotes/{ticker.upper()}"
        res = self._get(endpoint, params={"limit": limit})
        return res.get("results", [])

    def get_trades(self, ticker: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch latest tick-by-tick executed trades for a ticker."""
        endpoint = f"/v3/trades/{ticker.upper()}"
        res = self._get(endpoint, params={"limit": limit})
        return res.get("results", [])

    # -------------------------------------------------------------------------
    # Options & Derivatives
    # -------------------------------------------------------------------------
    def get_options_contracts(self, underlying_ticker: str, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch option contracts available for an underlying stock."""
        endpoint = "/v3/reference/options/contracts"
        params = {"underlying_ticker": underlying_ticker.upper(), "limit": limit}
        res = self._get(endpoint, params=params)
        return res.get("results", [])

    # -------------------------------------------------------------------------
    # Server-Side Technical Indicators
    # -------------------------------------------------------------------------
    def get_indicator(
        self,
        indicator: str,
        ticker: str,
        timespan: str = "day",
        window: int = 20,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch pre-computed technical indicator values (e.g. sma, ema, rsi, macd)."""
        endpoint = f"/v1/indicators/{indicator.lower()}/{ticker.upper()}"
        params = {
            "timespan": timespan,
            "window": window,
            "limit": limit,
        }
        res = self._get(endpoint, params=params)
        return res.get("results", {}).get("values", [])

    # -------------------------------------------------------------------------
    # Market News
    # -------------------------------------------------------------------------
    def get_news(self, ticker: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        """Fetch financial market news articles, optionally filtered by ticker."""
        endpoint = "/v2/reference/news"
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker.upper()
        res = self._get(endpoint, params=params)
        return res.get("results", [])

    # -------------------------------------------------------------------------
    # Crypto & Forex
    # -------------------------------------------------------------------------
    def get_crypto_prev(self, pair: str = "X:BTCUSD") -> dict[str, Any]:
        """Fetch previous day close for a crypto pair."""
        endpoint = f"/v2/aggs/ticker/{pair.upper()}/prev"
        res = self._get(endpoint)
        results = res.get("results", [])
        return results[0] if results else {}

    def get_forex_prev(self, pair: str = "C:EURUSD") -> dict[str, Any]:
        """Fetch previous day close for a forex pair."""
        endpoint = f"/v2/aggs/ticker/{pair.upper()}/prev"
        res = self._get(endpoint)
        results = res.get("results", [])
        return results[0] if results else {}
