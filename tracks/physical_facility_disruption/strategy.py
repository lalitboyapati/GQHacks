"""Physical facility disruption track — event-study premium selling.

Hypothesis: disruption 8-K + brief/non-persistent thermal anomaly → sell
premium (CSP / covered call); persistent anomaly → skip / control.

Run metadata for ``run.py``::

    ENGINE = \"event\"

Backtest entry point will be ``scripts/run_backtest.py`` once the event set
and satellite labels are joined. Until then, use ``facility_groups`` and
``scripts/describe_groups.py`` to validate the A/B split.
"""

from __future__ import annotations

ENGINE = "event"

# Not a Backtrader strategy — premium legs will go through eightk.
STRATEGY_CLASS = None
