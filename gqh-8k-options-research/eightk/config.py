"""Runtime configuration: credentials, paths, and tunable research settings.

Everything here is read from the environment (optionally via a ``.env`` file
next to the project root) so that no key is ever committed. ``Settings`` is
resolved once and passed down explicitly rather than re-read module-by-module,
which keeps the data-source wiring visible at the call site.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
EVENTS_DIR = DATA_DIR / "events"
RESULTS_DIR = DATA_DIR / "results"

# SEC asks automated clients to self-identify with a contact address. The
# default below is a placeholder: set SEC_USER_AGENT to your own
# "Name you@domain" string to comply with their fair-access policy.
DEFAULT_SEC_USER_AGENT = "GQHacks Research admin@gqhacks.dev"


def _load_dotenv() -> None:
    """Load .env from the project root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass
class Settings:
    """Resolved configuration for one research run."""

    sec_user_agent: str = DEFAULT_SEC_USER_AGENT
    massive_api_key: str | None = None
    databento_api_key: str | None = None
    webull_app_key: str | None = None
    webull_app_secret: str | None = None

    # Databento spend ceiling in USD. The cost guard refuses any query that
    # would push cumulative spend past this, so a stray full-chain request
    # cannot drain the account.
    databento_budget_usd: float = 225.0
    # Fraction of the budget this run is allowed to consume.
    databento_run_budget_usd: float = 25.0

    cache_dir: Path = field(default_factory=lambda: CACHE_DIR)
    events_dir: Path = field(default_factory=lambda: EVENTS_DIR)
    results_dir: Path = field(default_factory=lambda: RESULTS_DIR)

    # Politeness: SEC rate-limits above ~10 requests/second.
    sec_requests_per_second: float = 6.0
    offline: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        return cls(
            sec_user_agent=(os.environ.get("SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT).strip(),
            massive_api_key=(os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY") or "").strip() or None,
            databento_api_key=(os.environ.get("DATABENTO_API_KEY") or "").strip() or None,
            webull_app_key=(os.environ.get("WEBULL_APP_KEY") or "").strip() or None,
            webull_app_secret=(os.environ.get("WEBULL_APP_SECRET") or "").strip() or None,
            databento_budget_usd=_env_float("DATABENTO_BUDGET_USD", 225.0),
            databento_run_budget_usd=_env_float("DATABENTO_RUN_BUDGET_USD", 25.0),
            sec_requests_per_second=_env_float("SEC_REQUESTS_PER_SECOND", 6.0),
            offline=_env_bool("EIGHTK_OFFLINE", False),
        )

    def ensure_dirs(self) -> None:
        for path in (self.cache_dir, self.events_dir, self.results_dir):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def has_databento(self) -> bool:
        return bool(self.databento_api_key)

    @property
    def has_massive(self) -> bool:
        return bool(self.massive_api_key)
