"""Webull daily underlyings for explicitly modeled option event studies.

No trading endpoints are used. Historical chains are deliberately unavailable:
returning an empty chain invokes the engine's labeled Black–Scholes simulation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from eightk.massive_src import Bar
from webull_bt.feed import WebullBar, _locate_price_records


class WebullPriceClient:
    source = "webull"
    option_pricing = "model"

    def __init__(self, cache_dir: Path, *, client=None, offline=False):
        self.cache_dir = Path(cache_dir) / "webull_daily_v1"
        self.client = client
        self.offline = offline
        self.coverage = []
        self._memory = {}

    def _client(self):
        if self.client is None:
            key = os.getenv("WEBULL_APP_KEY", "")
            secret = os.getenv("WEBULL_APP_SECRET", "")
            if not all(v and not v.startswith("your_") for v in (key, secret)):
                raise RuntimeError("Set WEBULL_APP_KEY and WEBULL_APP_SECRET in infrastructure/backtest/.env")
            # SDK errors can log signed request headers. Keep those out of reports.
            logging.getLogger("webull").setLevel(logging.CRITICAL)
            from webull.core.client import ApiClient
            from webull.data.data_client import DataClient
            region = os.getenv("WEBULL_REGION_ID", "us")
            api = ApiClient(key, secret, region)
            api.add_endpoint(region, os.getenv("WEBULL_API_ENDPOINT", "api.webull.com"))
            self.client = DataClient(api)
        return self.client

    def daily_bars(self, ticker, start, end, *, adjusted=True):
        if ticker.startswith("O:") or not adjusted:
            raise ValueError("Webull event simulation supports adjusted stock bars only")
        lo, hi = date.fromisoformat(start), date.fromisoformat(end)
        # Exclude today's incomplete daily candle, using the exchange timezone.
        hi = min(hi, datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=1))
        if lo > hi:
            return []
        identity = (ticker.upper(), lo.isoformat(), hi.isoformat())
        if identity in self._memory:
            return self._memory[identity]
        bars = {}
        cursor = lo
        while cursor <= hi:
            stop = min(cursor + timedelta(days=30), hi)
            request = dict(symbol=ticker.upper(), category="US_STOCK", timespan="D",
                           count="100", real_time_required=False,
                           start_time=int(datetime.combine(cursor, datetime.min.time(), timezone.utc).timestamp()*1000),
                           end_time=int(datetime.combine(stop + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp()*1000)-1)
            digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
            path = self.cache_dir / f"{digest}.json"
            cached = path.exists()
            if cached:
                payload = json.loads(path.read_text())
            else:
                if self.offline:
                    raise RuntimeError(f"Webull offline cache miss: {ticker} {cursor}..{stop}")
                try:
                    response = self._client().market_data.get_history_bar(**request)
                except Exception:
                    raise RuntimeError(f"Webull request failed for {ticker}; check credentials, network and entitlement") from None
                if response.status_code != 200:
                    raise RuntimeError(f"Webull HTTP {response.status_code} for {ticker}; check OpenAPI data entitlement")
                payload = response.json()
                # Validate before storing; never cache business errors as empty data.
                records = _locate_price_records(payload)
                if not records and (stop - cursor).days >= 7:
                    raise RuntimeError(f"No Webull history for {ticker} {cursor}..{stop}; coverage cannot be assumed")
                time.sleep(0.2)
            records = _locate_price_records(payload)
            selected = 0
            for record in records:
                raw = WebullBar.from_api(record)
                # Daily timestamps are session-date labels (UTC), not intraday fills.
                day = raw.datetime.astimezone(timezone.utc).date()
                if not cursor <= day <= stop:
                    continue
                values = (raw.open, raw.high, raw.low, raw.close, raw.volume)
                if not all(math.isfinite(v) for v in values) or min(values[:4]) <= 0 or raw.volume < 0:
                    raise ValueError(f"Invalid Webull OHLCV: {ticker} {day}")
                if raw.high < max(raw.open, raw.close, raw.low) or raw.low > min(raw.open, raw.close):
                    raise ValueError(f"Inconsistent Webull OHLC: {ticker} {day}")
                bar = Bar(day, *values)
                if day in bars and bars[day] != bar:
                    raise ValueError(f"Conflicting Webull bars: {ticker} {day}")
                bars[day] = bar
                selected += 1
            if not selected and (stop - cursor).days >= 7:
                raise RuntimeError(f"Webull returned no bars inside requested window: {ticker} {cursor}..{stop}")
            if not cached:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload))
            cursor = stop + timedelta(days=1)
        result = sorted(bars.values(), key=lambda b: b.day)
        self.coverage.append(dict(symbol=ticker.upper(), requested_start=start, requested_end=end,
                                  first=str(result[0].day) if result else None,
                                  last=str(result[-1].day) if result else None, bars=len(result)))
        self._memory[identity] = result
        return result

    def option_contracts(self, *args, **kwargs):
        """Explicit model mode: do not substitute today's chain for a past chain."""
        return []
