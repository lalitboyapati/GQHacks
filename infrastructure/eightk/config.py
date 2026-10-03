"""Runtime configuration: credentials, paths, and tunable research settings.

Everything here is read from the environment (optionally via a ``.env`` file)
so that no key is ever committed. ``Settings`` is resolved once and passed
down explicitly rather than re-read module-by-module, which keeps the
data-source wiring visible at the call site.

Data directories default to the active research track
(``tracks/<GQH_TRACK>/data``), not the ``infrastructure/`` package tree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_INFRA_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _INFRA_ROOT.parent

# SEC asks automated clients to self-identify with a contact address. The
# default below is a placeholder: set SEC_USER_AGENT to your own
# "Name you@domain" string to comply with their fair-access policy.
DEFAULT_SEC_USER_AGENT = "GQHacks Research admin@gqhacks.dev"
DEFAULT_TRACK = "disclosure_advantage"


def _default_data_dir() -> Path:
    override = (os.environ.get("GQH_EIGHTK_DATA") or "").strip()
    if override:
        return Path(override)
    track = (os.environ.get("GQH_TRACK") or DEFAULT_TRACK).strip()
    return _REPO_ROOT / "tracks" / track / "data"


def _load_dotenv() -> None:
    """Load .env from track, infra backtest, and repo root if available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    data_dir = _default_data_dir()
    track_root = data_dir.parent
    candidates = (
        track_root / ".env",
        _INFRA_ROOT / "backtest" / ".env",
        _REPO_ROOT / ".env",
        _INFRA_ROOT / ".env",
    )
    for candidate in candidates:
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

    cache_dir: Path = field(default_factory=lambda: _default_data_dir() / "cache")
    events_dir: Path = field(default_factory=lambda: _default_data_dir() / "events")
    results_dir: Path = field(default_factory=lambda: _default_data_dir() / "results")

    # Politeness: SEC rate-limits above ~10 requests/second.
    sec_requests_per_second: float = 6.0
    offline: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        data = _default_data_dir()
        return cls(
            sec_user_agent=(os.environ.get("SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT).strip(),
            massive_api_key=(
                os.environ.get("MASSIVE_API_KEY")
                or os.environ.get("MASSIVE_APP_KEY")
                or os.environ.get("POLYGON_API_KEY")
                or ""
            ).strip()
            or None,
            databento_api_key=(os.environ.get("DATABENTO_API_KEY") or "").strip() or None,
            webull_app_key=(os.environ.get("WEBULL_APP_KEY") or "").strip() or None,
            webull_app_secret=(os.environ.get("WEBULL_APP_SECRET") or "").strip() or None,
            databento_budget_usd=_env_float("DATABENTO_BUDGET_USD", 225.0),
            databento_run_budget_usd=_env_float("DATABENTO_RUN_BUDGET_USD", 25.0),
            cache_dir=data / "cache",
            events_dir=data / "events",
            results_dir=data / "results",
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


# Back-compat aliases used by older docs / imports
PROJECT_ROOT = _REPO_ROOT
DATA_DIR = _default_data_dir()
CACHE_DIR = DATA_DIR / "cache"
EVENTS_DIR = DATA_DIR / "events"
RESULTS_DIR = DATA_DIR / "results"
