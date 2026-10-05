"""Spend ledger enforcing a hard ceiling on metered data purchases.

Databento historical data is billed by volume, and OPRA is the
highest-volume feed in existence: a single careless full-chain request can
cost more than this project's entire budget. The ledger persists every
charge to disk so the cap survives process restarts, and the guard refuses
any query whose *quoted* cost would breach it — the decision is made before
the bytes are requested, not after they are billed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class BudgetExceeded(RuntimeError):
    """Raised when a query would push spend past the configured ceiling."""


@dataclass
class SpendLedger:
    """Append-only record of metered data spend."""

    path: Path
    total_budget_usd: float = 225.0
    run_budget_usd: float = 25.0

    def __post_init__(self):
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._run_spend = 0.0

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    def _entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text())
        except (ValueError, OSError):
            logger.warning("spend ledger at %s is unreadable; treating as empty", self.path)
            return []

    @property
    def total_spent(self) -> float:
        return sum(float(entry.get("cost_usd", 0.0)) for entry in self._entries())

    @property
    def run_spent(self) -> float:
        return self._run_spend

    @property
    def remaining(self) -> float:
        return max(0.0, self.total_budget_usd - self.total_spent)

    @property
    def run_remaining(self) -> float:
        return max(0.0, self.run_budget_usd - self._run_spend)

    # ------------------------------------------------------------------ #
    # Enforcement
    # ------------------------------------------------------------------ #
    def check(self, quoted_usd: float, description: str = "") -> None:
        """Raise unless ``quoted_usd`` fits both the run and total caps."""
        if quoted_usd < 0:
            raise ValueError("quoted cost cannot be negative")
        if quoted_usd > self.run_remaining:
            raise BudgetExceeded(
                f"query would cost ${quoted_usd:.2f}, exceeding this run's "
                f"remaining ${self.run_remaining:.2f} ({description}). "
                f"Raise DATABENTO_RUN_BUDGET_USD only if that is intended."
            )
        if quoted_usd > self.remaining:
            raise BudgetExceeded(
                f"query would cost ${quoted_usd:.2f}, exceeding the total "
                f"remaining budget of ${self.remaining:.2f} ({description})"
            )

    def record(self, cost_usd: float, description: str = "", **meta) -> None:
        """Append a completed charge to the ledger."""
        entries = self._entries()
        entries.append({
            "at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            "cost_usd": float(cost_usd),
            "description": description,
            **meta,
        })
        self.path.write_text(json.dumps(entries, indent=2))
        self._run_spend += float(cost_usd)
        logger.info(
            "spend: $%.4f for %s (run $%.2f/$%.2f, total $%.2f/$%.2f)",
            cost_usd, description, self._run_spend, self.run_budget_usd,
            self.total_spent, self.total_budget_usd,
        )

    def summary(self) -> str:
        return (
            f"spent ${self.total_spent:.2f} of ${self.total_budget_usd:.2f} "
            f"(${self.remaining:.2f} left); this run ${self._run_spend:.2f}"
        )
