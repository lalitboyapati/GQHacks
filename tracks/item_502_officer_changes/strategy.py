"""Template research strategy for a Form 8-K track.

Replace this with your signal logic. The shared runner loads this module when
``GQH_TRACK`` points at this folder and expects ``STRATEGY_CLASS``.
"""

from __future__ import annotations

import backtrader as bt

from webull_bt.logging_utils import get_logger


logger = get_logger("strategy.template")


class TemplateStrategy(bt.Strategy):
    """Placeholder — stays flat until you implement entries/exits."""

    params = dict(
        # example_param=1,
    )

    def __init__(self):
        self.set_tradehistory(True)
        self.closed_trades = []
        logger.warning(
            "[Template] %s is a stub track — implement STRATEGY.md + next() before judging results",
            self.__class__.__name__,
        )

    def next(self):
        return

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        entry_size = trade.history[0].event.size if trade.history else trade.size
        exit_price = trade.history[-1].event.price if trade.history else trade.price
        self.closed_trades.append({
            "symbol": trade.getdataname(),
            "direction": "LONG" if trade.long else "SHORT",
            "size": entry_size,
            "entry_price": trade.price,
            "exit_price": exit_price,
            "open_dt": trade.open_datetime(),
            "close_dt": trade.close_datetime(),
            "pnl": trade.pnl,
            "pnlcomm": trade.pnlcomm,
            "commission": trade.commission,
            "bars_held": trade.barlen,
        })


STRATEGY_CLASS = TemplateStrategy
