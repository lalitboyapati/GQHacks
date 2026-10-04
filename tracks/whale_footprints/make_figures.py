"""Generate the figure pack for QUANT_NOTE.md from committed result CSVs.

Figures (saved to tracks/whale_footprints/figures/):
  fig1_equity.png        IS & OOS locked-plan equity curves with drawdown shading
  fig2_decay.png         direction-signed return by horizon, IS & OOS (P4 test)
  fig3_tail_cost.png     distribution of tail-hedge premium as % of position (the killer)
  fig4_worst_trades.png  gross vs. hedged return on the right-tail disasters
  fig5_capacity.png      net mean trade return after square-root impact vs AUM
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

TRACK = Path(__file__).resolve().parent
RES = TRACK / "results"
FIG = TRACK / "figures"
FIG.mkdir(exist_ok=True)

plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
    "legend.fontsize": 8.5, "figure.dpi": 150, "savefig.dpi": 200,
    "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False,
    "axes.spines.right": False,
})
GREEN, RED, GREY, BLUE = "#1a7f37", "#c62828", "#8a8a8a", "#1565c0"


def load_equity(period: str) -> pd.DataFrame:
    df = pd.read_csv(RES / f"{period}_equity.csv")
    df.columns = ["date", "equity"]
    df["date"] = pd.to_datetime(df["date"])
    return df


# --------------------------------------------------------------------------- #
# fig 1 · locked-plan equity curves
# --------------------------------------------------------------------------- #
fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
for ax, period in zip(axes, ["is", "oos"]):
    eq = load_equity(period)
    eq["peak"] = eq["equity"].cummax()
    eq["dd"] = eq["equity"] / eq["peak"] - 1
    ax.plot(eq["date"], eq["equity"] / 1e6, color=BLUE, lw=1.2)
    ax.fill_between(eq["date"], eq["equity"] / 1e6, eq["peak"] / 1e6,
                    where=eq["dd"] < 0, color=RED, alpha=0.18, label="drawdown")
    ax.set_title(("In-sample" if period == "is" else "Out-of-sample")
                 + f" · end ${eq['equity'].iloc[-1]/1e6:.2f}M")
    ax.set_ylabel("equity ($M)")
    ax.tick_params(axis="x", rotation=25)
axes[0].legend(loc="lower left")
fig.tight_layout()
fig.savefig(FIG / "fig1_equity.png", bbox_inches="tight")
plt.close(fig)
print("fig1_equity.png")


# --------------------------------------------------------------------------- #
# fig 2 · decay by horizon (P4 test)
# --------------------------------------------------------------------------- #
dec = pd.concat([
    pd.read_csv(RES / f"{p}_decay.csv").assign(period=p)
    for p in ["is", "oos"]
])
traded = dec[dec["group"] == "traded (not covered_same)"].copy()
fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
for ax, period in zip(axes, ["is", "oos"]):
    d = traded[traded.period == period]
    x = d["horizon"].astype(int)
    ax.plot(x, d["mean"] * 100, "o-", color=BLUE, lw=1.4, ms=4)
    ax.fill_between(x, d["ci_lo"] * 100, d["ci_hi"] * 100, color=BLUE, alpha=0.15)
    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_title("In-sample" if period == "is" else "Out-of-sample")
    ax.set_xlabel("holding period (sessions)")
    ax.set_xticks(x)
    ax.tick_params(axis="x", rotation=0)
axes[0].set_ylabel("direction-signed return (%)")
axes[0].annotate("edge still rising at day 10", xy=(10, 1.8), fontsize=8, color=RED)
fig.suptitle("Whale-day drift by horizon — the edge does not fade by session 5 (P4 fails)",
             y=1.02, fontsize=10.5)
fig.tight_layout()
fig.savefig(FIG / "fig2_decay.png", bbox_inches="tight")
plt.close(fig)
print("fig2_decay.png")


# --------------------------------------------------------------------------- #
# fig 3 · tail-hedge premium distribution (the killer)
# --------------------------------------------------------------------------- #
th = pd.concat([
    pd.read_csv(RES / f"{p}_tail_hedges.csv").assign(period=p)
    for p in ["is", "oos"]
]).dropna(subset=["premium_pct_of_position"])
th["pct"] = th["premium_pct_of_position"] * 100

fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=True)
for ax, period in zip(axes, ["is", "oos"]):
    d = th[th.period == period]
    med = d["pct"].median()
    ax.hist(d["pct"], bins=40, color=BLUE, alpha=0.75)
    ax.axvline(med, color=RED, lw=1.4, ls="--")
    ax.set_title(f"{'In-sample' if period=='is' else 'Out-of-sample'} · n={len(d)}")
    ax.set_xlabel("hedge premium (% of position)")
    ax.tick_params(axis="x", rotation=0)
    ax.text(0.97, 0.9, f"median {med:.1f}%", transform=ax.transAxes,
            ha="right", color=RED, fontsize=9)
axes[0].set_ylabel("positions")
fig.suptitle("Tail-hedge cost: a median 4.4% of every position — the locked plan's self-inflicted drag",
             y=1.02, fontsize=10.5)
fig.tight_layout()
fig.savefig(FIG / "fig3_tail_cost.png", bbox_inches="tight")
plt.close(fig)
print("fig3_tail_cost.png")


# --------------------------------------------------------------------------- #
# fig 4 · worst trades, gross vs hedged (the hedge earns its keep — on tails)
# --------------------------------------------------------------------------- #
tr = pd.concat([
    pd.read_csv(RES / f"{p}_trades.csv").assign(period=p)
    for p in ["is", "oos"]
])
worst = tr.nsmallest(5, "gross_return")
xx = np.arange(len(worst))
fig, ax = plt.subplots(figsize=(6.6, 3.1))
w = 0.36
ax.bar(xx - w / 2, worst["gross_return"] * 100, w, color=RED, label="gross (no hedge)")
ax.bar(xx + w / 2, worst["return_with_hedge"] * 100, w, color=GREEN, label="with tail hedge")
ax.set_xticks(xx)
ax.set_xticklabels([f"{t}\n{row.split(' ')[0]} {row.split(' ')[1]}" if False else t
                    for t in worst["ticker"]], fontsize=8)
ax.set_ylabel("trade return (%)")
ax.legend()
ax.set_title("The five worst trades: the tail hedge cuts losses 12–47 pts "
             "(but costs 4.4% on every position)")
fig.tight_layout()
fig.savefig(FIG / "fig4_worst_trades.png", bbox_inches="tight")
plt.close(fig)
print("fig4_worst_trades.png")


# --------------------------------------------------------------------------- #
# fig 5 · capacity dial
# --------------------------------------------------------------------------- #
cap = pd.read_csv(RES / "is_capacity.csv")
fig, ax = plt.subplots(figsize=(6.6, 3.1))
ax.plot(cap["aum"], cap["net_mean_trade_return_after_impact"] * 100,
        "o-", color=BLUE, lw=1.4)
ax.axhline(0, color=GREY, lw=0.8)
ax.axvline(1e6, color=RED, ls="--", lw=1.2)
ax.set_xscale("log")
ax.set_xticks(cap["aum"])
ax.set_xticklabels([f"${v/1e6:.0f}M" if v >= 1e6 else f"${v/1e3:.0f}K"
                    for v in cap["aum"]], fontsize=8)
ax.set_xlabel("strategy AUM")
ax.set_ylabel("net mean trade return after impact (%)")
ax.set_title("Impact-bound: net trade return is below zero even at $1M AUM")
ax.annotate("edge dead at $1M", xy=(1.3e6, -0.05), fontsize=8, color=RED)
fig.tight_layout()
fig.savefig(FIG / "fig5_capacity.png", bbox_inches="tight")
plt.close(fig)
print("fig5_capacity.png")
print(f"\nFigures written to {FIG}")