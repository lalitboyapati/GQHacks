"""Build one-pager figures for the facility-disruption / thermal options strategy.

Outputs PNG (+ combined PDF) under massive/summary_graphics/.
Numbers are taken from the validated thermal-based options pricing notebook run.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

# Palette — cool slate + heat amber (thermal / FIRMS cue)
INK = "#1B2430"
MUTED = "#5C6B7A"
RULE = "#D5DCE3"
PAPER = "#F7F5F2"
HEAT = "#E07A2F"
HEAT_DK = "#B45309"
COOL = "#2F6F8F"
GOOD = "#2F6B4F"
BAD = "#9B3B3B"
SOFT = "#E8EEF2"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "axes.edgecolor": RULE,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "text.color": INK,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.dpi": 200,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def save(fig: plt.Figure, name: str) -> Path:
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("wrote", path)
    return path


def fig_pipeline() -> None:
    fig, ax = plt.subplots(figsize=(11, 3.2))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 3.2)
    ax.axis("off")
    ax.set_title(
        "Facility-disruption strategy · signal path",
        loc="left",
        fontsize=14,
        fontweight="bold",
        color=INK,
        pad=8,
    )

    boxes = [
        (0.2, 1.0, 2.0, 1.4, "Massive 8-K\nitems_text", "Any Item\n(mostly 2.05 / 7.01)"),
        (2.8, 1.0, 2.0, 1.4, "Text filter\n+ FP cuts", "Plant / fire /\nshutdown language"),
        (5.4, 1.0, 2.0, 1.4, "NASA FIRMS\nthermal label", "brief · persistent\n· unknown"),
        (8.0, 1.0, 2.6, 1.4, "Trade FIRMS-brief\nshort event vol", "Iron condor 3/10\n(1m · post · 5% OTM)"),
    ]
    for x, y, w, h, title, sub in boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.04,rounding_size=0.12",
                linewidth=1.2,
                edgecolor=INK,
                facecolor=SOFT if "Trade" not in title else "#FFF3E6",
            )
        )
        ax.text(x + w / 2, y + h * 0.68, title, ha="center", va="center", fontsize=10, fontweight="bold")
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=8, color=MUTED)

    for x0, x1 in [(2.2, 2.8), (4.8, 5.4), (7.4, 8.0)]:
        ax.annotate(
            "",
            xy=(x1, 1.7),
            xytext=(x0, 1.7),
            arrowprops=dict(arrowstyle="-|>", color=HEAT, lw=1.8, mutation_scale=12),
        )

    ax.text(
        0.2,
        0.35,
        "Panel: 45 disruption 8-Ks · IS 24 brief · OOS 8 brief · universe 55 industrials / materials / energy",
        fontsize=8.5,
        color=MUTED,
    )
    save(fig, "01_strategy_pipeline.png")


def fig_implied_vs_realized() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), gridspec_kw={"width_ratios": [1.05, 1.35]})

    ax = axes[0]
    labels = ["Implied move\n(1m ATM, t_pre)", "|Realized|\n(to horizons)"]
    vals = [11.5, 5.3]
    colors = [HEAT, COOL]
    bars = ax.bar(labels, vals, color=colors, width=0.55, edgecolor="none")
    ax.set_ylabel("% of spot")
    ax.set_ylim(0, 14)
    ax.set_title("Market priced more than path delivered", fontsize=12, fontweight="bold", loc="left")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.35, f"{v:.1f}%", ha="center", fontsize=11, fontweight="bold")
    ax.text(
        0.5,
        -0.22,
        "Realized beat implied in only 13% of events",
        transform=ax.transAxes,
        ha="center",
        fontsize=8.5,
        color=MUTED,
    )

    ax = axes[1]
    horizons = ["1", "2", "3", "5", "10", "21", "exp"]
    ev_mean = [0.83, 0.97, 1.03, 1.05, 1.07, 0.97, 0.74]
    ev_lo = [0.50, 0.62, 0.68, 0.68, 0.69, 0.55, 0.33]
    ev_hi = [1.34, 1.37, 1.40, 1.42, 1.52, 1.41, 1.29]
    pl_mean = [0.68, 0.72, 0.87, 0.83, 1.04, 0.99, 0.98]
    pl_lo = [0.55, 0.57, 0.70, 0.64, 0.82, 0.58, 0.74]
    pl_hi = [0.81, 0.90, 1.06, 1.03, 1.27, 1.53, 1.25]
    x = np.arange(len(horizons))
    ax.axhline(1.0, color=RULE, lw=1.2, zorder=0)
    ax.fill_between(x, ev_lo, ev_hi, color=HEAT, alpha=0.15, label="Events CI")
    ax.fill_between(x, pl_lo, pl_hi, color=COOL, alpha=0.12, label="Placebo CI")
    ax.plot(x, ev_mean, "o-", color=HEAT, lw=2, ms=5, label="Events mean ratio")
    ax.plot(x, pl_mean, "s--", color=COOL, lw=1.6, ms=4, label="Placebo mean ratio")
    ax.set_xticks(x)
    ax.set_xticklabels(horizons)
    ax.set_xlabel("Horizon (sessions / expiry)")
    ax.set_ylabel(r"|realized| / implied")
    ax.set_ylim(0.2, 1.7)
    ax.set_title("Ratio yardstick · events vs ordinary days", fontsize=12, fontweight="bold", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.text(
        0.0,
        -0.28,
        "Ratio < 1 ⇒ path quieter than the chain priced. Event CIs still include 1 (small n).",
        transform=ax.transAxes,
        fontsize=8,
        color=MUTED,
    )

    fig.suptitle("Why short event-vol?  FIRMS-brief disruption 8-Ks", fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    save(fig, "02_implied_vs_realized.png")


def fig_structure_ranking() -> None:
    # Placebo edge ranked on h=21 + expiry (notebook cell 28)
    names = [
        "Iron condor 3/10",
        "Cash-secured put",
        "Long call*",
        "Covered call",
        "Collar*",
        "Protective put*",
    ]
    edge = [2.42, 1.10, 0.81, -3.85, -4.75, -6.68]
    n_ev = [7, 12, 12, 9, 8, 9]

    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    y = np.arange(len(names))[::-1]
    colors = [GOOD if v > 0 else BAD for v in edge]
    colors[0] = HEAT_DK  # highlight winner
    ax.barh(y, edge, color=colors, height=0.62, edgecolor="none")
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlabel("Event − placebo edge  (avg of h=21 + expiry), % of spot")
    ax.set_title(
        "In-sample structure search · FIRMS-brief · 1m · entry=post · OTM 5%",
        fontsize=12,
        fontweight="bold",
        loc="left",
    )
    for yi, v, n in zip(y, edge, n_ev):
        ax.text(
            v + (0.15 if v >= 0 else -0.15),
            yi,
            f"{v:+.2f}%  (n={n})",
            va="center",
            ha="left" if v >= 0 else "right",
            fontsize=9,
            fontweight="bold" if abs(v - 2.42) < 1e-6 else "normal",
            color=INK,
        )
    ax.set_xlim(-8.5, 4.5)
    ax.text(
        0.0,
        -0.14,
        "* diagnostic long-vol / hedge structures · winner = iron condor 3/10 (addendum)",
        transform=ax.transAxes,
        fontsize=8,
        color=MUTED,
    )
    fig.tight_layout()
    save(fig, "03_structure_ranking.png")


def fig_oos_and_costs() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2))

    # Left: IS -> OOS for key structures at h=21 and expiry
    ax = axes[0]
    structs = ["Condor 3/10", "CSP", "Covered call"]
    # from notebook OOS transfer table
    is_h21 = [0.10, -0.65, -2.71]
    oos_h21 = [1.76, 0.21, 5.00]
    is_exp = [1.96, 0.79, -0.15]
    oos_exp = [-1.69, -3.29, -0.71]

    x = np.arange(len(structs))
    w = 0.18
    ax.bar(x - 1.5 * w, is_h21, w, label="IS h=21", color=SOFT, edgecolor=INK, linewidth=0.6)
    ax.bar(x - 0.5 * w, oos_h21, w, label="OOS h=21", color=COOL, edgecolor="none")
    ax.bar(x + 0.5 * w, is_exp, w, label="IS expiry", color="#F3D5B5", edgecolor=INK, linewidth=0.6)
    ax.bar(x + 1.5 * w, oos_exp, w, label="OOS expiry", color=HEAT, edgecolor="none")
    ax.axhline(0, color=INK, lw=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(structs)
    ax.set_ylabel("Mean P&L / $1 spot")
    ax.set_title("Hold-out transfer (2025 OOS, n≈5 priced)", fontsize=11, fontweight="bold", loc="left")
    ax.legend(frameon=False, fontsize=7.5, ncol=2, loc="upper left")
    ax.text(
        0.0,
        -0.22,
        "Condor mid-horizon holds sign; expiry (and CSP expiry) flip — treat as exploratory.",
        transform=ax.transAxes,
        fontsize=8,
        color=MUTED,
    )

    # Right: cost haircut on winner
    ax = axes[1]
    cats = ["Gross h=21", "Net h=21\n(5% haircut)", "Gross expiry", "Net expiry\n(5% haircut)"]
    vals = [0.10, -0.78, 1.96, 0.84]
    cols = [GOOD if v > 0 else BAD for v in vals]
    bars = ax.bar(cats, vals, color=cols, width=0.65, edgecolor="none")
    ax.axhline(0, color=INK, lw=0.7)
    ax.set_ylabel("% of spot")
    ax.set_title("Iron condor 3/10 · after round-trip cost", fontsize=11, fontweight="bold", loc="left")
    for b, v in zip(bars, vals):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v + (0.12 if v >= 0 else -0.22),
            f"{v:+.2f}%",
            ha="center",
            va="bottom" if v >= 0 else "top",
            fontsize=10,
            fontweight="bold",
        )
    ax.set_ylim(-1.4, 2.6)
    ax.text(
        0.0,
        -0.22,
        "Haircut = 5% of premium each way · share net+ at h=21 only 22%",
        transform=ax.transAxes,
        fontsize=8,
        color=MUTED,
    )

    fig.suptitle("Robustness · out-of-sample and trading costs", fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    save(fig, "04_oos_and_costs.png")


def fig_one_pager() -> None:
    """Single composite board sized for a landscape one-pager."""
    fig = plt.figure(figsize=(13.5, 8.0))
    gs = fig.add_gridspec(
        3,
        3,
        height_ratios=[1.05, 1.35, 1.25],
        width_ratios=[1.15, 1.0, 1.15],
        hspace=0.42,
        wspace=0.35,
        left=0.06,
        right=0.98,
        top=0.88,
        bottom=0.07,
    )

    fig.suptitle(
        "Thermal FIRMS × Massive 8-K · short event-vol on brief facility disruptions",
        fontsize=15,
        fontweight="bold",
        x=0.06,
        ha="left",
        y=0.96,
    )
    fig.text(
        0.06,
        0.915,
        "Sell defined-risk premium when the filing looks like a plant shock but satellite heat does not persist.",
        fontsize=10,
        color=MUTED,
        ha="left",
    )

    # --- Pipeline strip (top full width) ---
    ax = fig.add_subplot(gs[0, :])
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 2.4)
    ax.axis("off")
    steps = [
        (0.15, "8-K text\n(2.05 / 7.01…)", SOFT),
        (3.1, "Disruption\nfilter", SOFT),
        (6.05, "FIRMS\nbrief only", "#FFF3E6"),
        (9.0, "Iron condor\n3/10", "#FFE8CC"),
    ]
    for x, label, face in steps:
        ax.add_patch(
            FancyBboxPatch(
                (x, 0.55),
                2.4,
                1.35,
                boxstyle="round,pad=0.03,rounding_size=0.1",
                fc=face,
                ec=INK,
                lw=1.1,
            )
        )
        ax.text(x + 1.2, 1.22, label, ha="center", va="center", fontsize=10, fontweight="bold")
    for x0 in (2.55, 5.5, 8.45):
        ax.annotate("", xy=(x0 + 0.55, 1.2), xytext=(x0, 1.2), arrowprops=dict(arrowstyle="-|>", color=HEAT, lw=1.6))
    ax.text(
        0.15,
        0.15,
        "45 events · IS 24 brief · OOS 8 · trade 1m chain, entry = filing close, 5% OTM wings",
        fontsize=8.5,
        color=MUTED,
    )

    # --- Implied vs realized ---
    ax = fig.add_subplot(gs[1, 0])
    bars = ax.bar(["Implied", "|Realized|"], [11.5, 5.3], color=[HEAT, COOL], width=0.55)
    ax.set_ylim(0, 14)
    ax.set_ylabel("%")
    ax.set_title("Priced vs path", fontweight="bold", loc="left", fontsize=11)
    for b, v in zip(bars, [11.5, 5.3]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.3, f"{v:.1f}%", ha="center", fontweight="bold")
    ax.text(0.5, -0.18, "Beat implied: 13% of events", transform=ax.transAxes, ha="center", fontsize=8, color=MUTED)

    # --- Ranking ---
    ax = fig.add_subplot(gs[1, 1:])
    names = ["Condor 3/10", "CSP", "Long call", "Covered call", "Collar", "Prot. put"]
    edge = np.array([2.42, 1.10, 0.81, -3.85, -4.75, -6.68])
    y = np.arange(len(names))[::-1]
    cols = [HEAT_DK if i == 0 else (GOOD if v > 0 else BAD) for i, v in enumerate(edge)]
    ax.barh(y, edge, color=cols, height=0.65)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Edge vs placebo (h=21 + expiry)")
    ax.set_title("Structure ranking (in-sample)", fontweight="bold", loc="left", fontsize=11)
    for yi, v in zip(y, edge):
        ax.text(v + (0.12 if v >= 0 else -0.12), yi, f"{v:+.2f}%", va="center", ha="left" if v >= 0 else "right", fontsize=8)

    # --- OOS ---
    ax = fig.add_subplot(gs[2, 0:2])
    structs = ["Condor", "CSP", "CC"]
    x = np.arange(len(structs))
    w = 0.2
    ax.bar(x - 1.5 * w, [0.10, -0.65, -2.71], w, label="IS h=21", color=SOFT, ec=INK, lw=0.5)
    ax.bar(x - 0.5 * w, [1.76, 0.21, 5.00], w, label="OOS h=21", color=COOL)
    ax.bar(x + 0.5 * w, [1.96, 0.79, -0.15], w, label="IS exp", color="#F3D5B5", ec=INK, lw=0.5)
    ax.bar(x + 1.5 * w, [-1.69, -3.29, -0.71], w, label="OOS exp", color=HEAT)
    ax.axhline(0, color=INK, lw=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(structs)
    ax.set_ylabel("% of spot")
    ax.set_title("2025 out-of-sample transfer", fontweight="bold", loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=7, ncol=4, loc="upper left")

    # --- Cost / takeaway ---
    ax = fig.add_subplot(gs[2, 2])
    ax.axis("off")
    ax.set_title("Takeaway", fontweight="bold", loc="left", fontsize=11)
    box = FancyBboxPatch((0.02, 0.08), 0.96, 0.82, transform=ax.transAxes, boxstyle="round,pad=0.03,rounding_size=0.08", fc="#FFF8F0", ec=HEAT, lw=1.2)
    ax.add_patch(box)
    ax.text(
        0.08,
        0.72,
        "Edge is overpriced event vol,\nnot directional stock.\n\n"
        "Condor 3/10 is least broken\nmid-horizon; costs wipe h=21\n(net −0.78%); expiry fragile OOS.\n\n"
        "Exploratory — small n.",
        transform=ax.transAxes,
        fontsize=9.5,
        va="top",
        color=INK,
        linespacing=1.35,
    )

    path = OUT / "00_one_pager_board.png"
    fig.savefig(path, dpi=220, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    print("wrote", path)


def main() -> None:
    fig_pipeline()
    fig_implied_vs_realized()
    fig_structure_ranking()
    fig_oos_and_costs()
    fig_one_pager()
    print(f"\nAll figures in: {OUT}")


if __name__ == "__main__":
    main()
