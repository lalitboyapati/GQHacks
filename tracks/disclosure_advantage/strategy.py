"""Disclosure-advantage track: eightk event-study (not Backtrader).

Run with::

    python run.py --track disclosure_advantage --engine event

or::

    python tracks/disclosure_advantage/scripts/run_backtest.py

``ENGINE`` tells ``run.py`` to dispatch to the event-study scripts instead of
the Webull/Backtrader runner. There is no ``STRATEGY_CLASS`` here — strategies
live in ``infrastructure/eightk/strategies.py`` (``exec_put``,
``efficiency_collar``, ``novelty_shortvol``, ``combo``, and stock controls).
"""

from __future__ import annotations

ENGINE = "event"

# Intentionally unset — this track does not plug into Backtrader.
STRATEGY_CLASS = None
