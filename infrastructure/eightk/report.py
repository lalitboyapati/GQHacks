"""Aggregate trades into statistics that survive a small sample.

Event studies on a single disclosure type produce tens of trades, not
thousands, and at that size an attractive mean return is routinely noise. So
every strategy is reported with the evidence needed to discount it:

* a **t-statistic** on mean return-on-capital,
* a **bootstrap confidence interval**, which makes no normality assumption
  and is the honest choice for option P&L whose distribution is violently
  skewed (a long put is mostly small losses and rare large wins),
* the **share of trades priced from real option bars**, because a result
  resting mostly on modeled premiums is a hypothesis rather than a finding,
* and **hit rate alongside mean**, since one outlier can carry a mean while
  the strategy loses most of the time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Below this many trades, a result is reported but flagged as unreliable.
MIN_TRADES_FOR_INFERENCE = 8
BOOTSTRAP_SAMPLES = 10_000


@dataclass
class StrategyStats:
    """Summary statistics for one strategy's trade set."""

    strategy: str
    n_trades: int
    total_pnl: float
    mean_pnl: float
    median_pnl: float
    mean_return: float
    median_return: float
    std_return: float
    hit_rate: float
    best: float
    worst: float
    t_stat: float | None
    p_value: float | None
    ci_low: float | None
    ci_high: float | None
    sharpe_per_trade: float | None
    market_priced_share: float
    mean_capital: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _bootstrap_ci(
    values: np.ndarray, alpha: float = 0.05, samples: int = BOOTSTRAP_SAMPLES,
    seed: int = 7,
) -> tuple[float, float]:
    """Percentile bootstrap interval for the mean."""
    rng = np.random.default_rng(seed)
    n = len(values)
    draws = rng.choice(values, size=(samples, n), replace=True).mean(axis=1)
    return float(np.quantile(draws, alpha / 2)), float(np.quantile(draws, 1 - alpha / 2))


def _t_test(values: np.ndarray) -> tuple[float | None, float | None]:
    """Two-sided one-sample t-test against a zero mean."""
    n = len(values)
    if n < 3:
        return None, None
    std = values.std(ddof=1)
    if std == 0:
        return None, None
    t_stat = float(values.mean() / (std / math.sqrt(n)))
    try:
        from scipy import stats
        p = float(2 * (1 - stats.t.cdf(abs(t_stat), df=n - 1)))
    except Exception:
        p = None
    return t_stat, p


def summarize_strategy(frame, strategy: str) -> StrategyStats | None:
    """Compute statistics for one strategy within a trades frame."""
    subset = frame[frame["strategy"] == strategy]
    if subset.empty:
        return None

    returns = subset["return_on_capital"].to_numpy(dtype=float)
    pnl = subset["pnl"].to_numpy(dtype=float)
    returns = returns[np.isfinite(returns)]
    if len(returns) == 0:
        return None

    t_stat, p_value = _t_test(returns)
    ci_low, ci_high = (_bootstrap_ci(returns) if len(returns) >= 3 else (None, None))
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0

    # Stock-only controls have no option legs, so a "share priced from real
    # option bars" figure is meaningless for them rather than merely low.
    stock_only = (
        "priced_from" in subset
        and bool((subset["priced_from"] == "stock_only").all())
    )
    if stock_only:
        market_share = float("nan")
    elif "priced_from" in subset:
        market_share = float((subset["priced_from"].isin(["market", "mixed"])).mean())
    else:
        market_share = float("nan")

    notes: list[str] = []
    if len(returns) < MIN_TRADES_FOR_INFERENCE:
        notes.append(f"only {len(returns)} trades - treat as anecdote, not evidence")
    if not stock_only and market_share == market_share and market_share < 0.5:
        notes.append(f"{market_share:.0%} of fills from real option bars - rest modeled")
    if ci_low is not None and ci_low < 0 < (ci_high or 0):
        notes.append("bootstrap interval spans zero")

    return StrategyStats(
        strategy=strategy,
        n_trades=int(len(subset)),
        total_pnl=float(pnl.sum()),
        mean_pnl=float(pnl.mean()),
        median_pnl=float(np.median(pnl)),
        mean_return=float(returns.mean()),
        median_return=float(np.median(returns)),
        std_return=std,
        hit_rate=float((pnl > 0).mean()),
        best=float(pnl.max()),
        worst=float(pnl.min()),
        t_stat=t_stat,
        p_value=p_value,
        ci_low=ci_low,
        ci_high=ci_high,
        sharpe_per_trade=(float(returns.mean() / std) if std > 0 else None),
        market_priced_share=market_share,
        mean_capital=float(subset["capital_at_risk"].mean()),
        notes=notes,
    )


def summarize(frame):
    """Per-strategy statistics table, best mean return first."""
    import pandas as pd
    rows = []
    for strategy in sorted(frame["strategy"].unique()):
        stats = summarize_strategy(frame, strategy)
        if stats is not None:
            rows.append(stats.to_dict())
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values("mean_return", ascending=False).reset_index(drop=True)
    return table


def split_summary(frame, by: str):
    """Mean return and hit rate per strategy within each bucket of ``by``."""
    import pandas as pd
    if by not in frame.columns:
        return pd.DataFrame()
    rows = []
    for (strategy, bucket), group in frame.groupby(["strategy", by], dropna=False):
        returns = group["return_on_capital"].to_numpy(dtype=float)
        returns = returns[np.isfinite(returns)]
        if len(returns) == 0:
            continue
        rows.append({
            "strategy": strategy,
            by: bucket,
            "n": len(group),
            "mean_return": float(returns.mean()),
            "median_return": float(np.median(returns)),
            "hit_rate": float((group["pnl"] > 0).mean()),
            "total_pnl": float(group["pnl"].sum()),
        })
    return pd.DataFrame(rows).sort_values(["strategy", by]).reset_index(drop=True)


def volatility_premium_table(frame):
    """Was option premium expensive relative to the move that followed?

    This is the direct test behind the novelty strategy. ``implied_move`` is
    what the entry volatility priced over the holding window; ``actual_move``
    is what the underlying actually did. A positive gap means premium was
    overpriced on average and selling it should have paid.
    """
    import pandas as pd
    needed = {"implied_move", "actual_move", "entry_iv", "realized_vol_hold"}
    if not needed.issubset(frame.columns):
        return pd.DataFrame()

    rows = []
    for key, group in frame.groupby("strategy"):
        valid = group.dropna(subset=["implied_move", "actual_move"])
        if valid.empty:
            continue
        implied = valid["implied_move"].to_numpy(dtype=float)
        actual = valid["actual_move"].to_numpy(dtype=float)
        gap = implied - actual
        t_stat, p_value = _t_test(gap)
        rows.append({
            "strategy": key,
            "n": len(valid),
            "mean_implied_move": float(implied.mean()),
            "mean_actual_move": float(actual.mean()),
            "mean_gap": float(gap.mean()),
            "share_move_exceeded_implied": float((actual > implied).mean()),
            "mean_entry_iv": float(valid["entry_iv"].mean()),
            "mean_realized_vol": float(valid["realized_vol_hold"].mean(skipna=True))
            if valid["realized_vol_hold"].notna().any() else float("nan"),
            "gap_t_stat": t_stat,
            "gap_p_value": p_value,
        })
    return pd.DataFrame(rows).sort_values("mean_gap", ascending=False).reset_index(drop=True)


def format_report(frame) -> str:
    """Render a plain-text report of a completed backtest."""
    import pandas as pd
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 60)

    if frame.empty:
        return "No trades were simulated. Check event selection and data access."

    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("8-K DISCLOSURE ADVANTAGE - OPTIONS BACKTEST")
    lines.append("=" * 78)
    lines.append(f"trades: {len(frame)}   "
                 f"tickers: {frame['ticker'].nunique()}   "
                 f"window: {frame['entry_day'].min()} to {frame['exit_day'].max()}")
    real = (frame["priced_from"].isin(["market", "mixed"])).mean()
    lines.append(f"fills from real option bars: {real:.0%}")
    lines.append("")

    lines.append("-" * 78)
    lines.append("PER-STRATEGY RESULTS (return on capital at risk, per trade)")
    lines.append("-" * 78)
    table = summarize(frame)
    display_cols = [
        "strategy", "n_trades", "mean_return", "median_return", "hit_rate",
        "total_pnl", "t_stat", "p_value", "ci_low", "ci_high", "market_priced_share",
    ]
    lines.append(table[display_cols].to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
    lines.append("")

    for _, row in table.iterrows():
        if row["notes"]:
            lines.append(f"  ! {row['strategy']}: " + "; ".join(row["notes"]))
    lines.append("")

    vrp = volatility_premium_table(frame)
    if not vrp.empty:
        lines.append("-" * 78)
        lines.append("WAS PREMIUM EXPENSIVE? (implied move priced vs move realized)")
        lines.append("-" * 78)
        lines.append(vrp.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
        lines.append("")

    for dimension, title in [
        ("cap_bucket", "BY MARKET-CAP BUCKET"),
        ("session_bucket", "BY FILING SESSION (PRE / RTH / POST)"),
        ("priced_from", "BY PRICE SOURCE"),
    ]:
        split = split_summary(frame, dimension)
        if not split.empty:
            lines.append("-" * 78)
            lines.append(title)
            lines.append("-" * 78)
            lines.append(split.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
            lines.append("")

    return "\n".join(lines)
