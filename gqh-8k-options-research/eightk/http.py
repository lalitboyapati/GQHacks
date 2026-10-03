"""Rate-limited HTTP with on-disk caching.

Filing text is immutable once accepted, so every GET is cached permanently
keyed by URL hash. That makes repeated backtests free and keeps us well
inside SEC's fair-access limits: a full re-run touches the network zero
times. ``offline=True`` turns a cache miss into an error instead of a
request, which is how reproducible runs are enforced.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import threading
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class CacheMiss(RuntimeError):
    """Raised when offline mode is on and a URL is not cached."""


class RateLimiter:
    """Simple blocking token spacer shared across threads."""

    def __init__(self, requests_per_second: float):
        self._min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            delta = time.monotonic() - self._last
            if delta < self._min_interval:
                time.sleep(self._min_interval - delta)
            self._last = time.monotonic()


class CachedSession:
    """A requests session that persists gzipped response bodies to disk."""

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        requests_per_second: float = 6.0,
        offline: bool = False,
        max_retries: int = 4,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.max_retries = max_retries
        self._limiter = RateLimiter(requests_per_second)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })
        self.stats = {"hits": 0, "misses": 0, "errors": 0}

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        # Shard by first two chars so no single directory holds 100k files.
        sub = self.cache_dir / digest[:2]
        sub.mkdir(parents=True, exist_ok=True)
        return sub / f"{digest}.gz"

    def get_text(self, url: str, *, allow_404: bool = False) -> str | None:
        """Fetch ``url`` as text, using the disk cache when possible.

        Returns ``None`` only when ``allow_404`` and the resource is absent
        (that absence is itself cached, so we never re-ask).
        """
        path = self._cache_path(url)
        if path.exists():
            self.stats["hits"] += 1
            body = gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")
            return None if body == "\x00404" else body

        if self.offline:
            raise CacheMiss(f"offline mode: {url} is not cached")

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._limiter.wait()
            try:
                response = self._session.get(url, timeout=45)
            except requests.RequestException as exc:  # transient network fault
                last_error = exc
                time.sleep(2.0 * (attempt + 1))
                continue

            if response.status_code == 200:
                self.stats["misses"] += 1
                path.write_bytes(gzip.compress(response.content))
                return response.text

            if response.status_code == 404 and allow_404:
                self.stats["misses"] += 1
                path.write_bytes(gzip.compress(b"\x00404"))
                return None

            # 403 from SEC is their rate-limit page; back off and retry.
            if response.status_code in (403, 429, 500, 502, 503, 504):
                last_error = requests.HTTPError(f"{response.status_code} for {url}")
                time.sleep(3.0 * (attempt + 1))
                continue

            self.stats["errors"] += 1
            raise requests.HTTPError(f"{response.status_code} for {url}")

        self.stats["errors"] += 1
        raise requests.HTTPError(f"exhausted retries for {url}: {last_error}")
