"""Build a 2-page portrait PDF submission summary with natively drawn charts.

Letter portrait (8.5 x 11). All figures are drawn directly (no embedded PNGs)
so typography and spacing stay consistent. Numbers come from the validated
runs of the thermal and fire-weather notebooks.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle

OUT = Path(__file__).resolve().parent
PDF = OUT / "facility_disruption_2page_summary.pdf"

# ---------------------------------------------------------------- palette
INK = "#17202A"
INK_2 = "#2B3645"
MUTED = "#6B7786"
RULE = "#DDE3EA"
PANEL = "#F5F7FA"
HEAT = "#E0762A"
HEAT_LT = "#F8DCC4"
COOL = "#2C6E91"
COOL_LT = "#D5E6EF"
GOOD = "#2F7A5B"
BAD = "#A33A3A"
WHITE = "#FFFFFF"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "axes.edgecolor": RULE,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "axes.labelsize": 6.8,
        "axes.titlesize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": WHITE,
        "savefig.facecolor": WHITE,
        "pdf.fonttype": 42,
    }
)

W, H = 8.5, 11.0
LM, RM = 0.07, 0.93  # left/right margins in figure fraction
CW = RM - LM


# ---------------------------------------------------------------- helpers
def ax_box(fig, x, y, w, h):
    """Blank axes used as a drawing surface (figure fractions)."""
    ax = fig.add_axes([x, y, w, h])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return ax


def header(fig, title, subtitle, page, chips=None):
    band_h = 0.085
    fig.patches.append(
        Rectangle((0, 1 - band_h), 1, band_h, transform=fig.transFigure, facecolor=INK, edgecolor="none")
    )
    fig.patches.append(
        Rectangle((0, 1 - band_h - 0.004), 1, 0.004, transform=fig.transFigure, facecolor=HEAT, edgecolor="none")
    )
    fig.text(LM, 1 - 0.028, title, fontsize=13.2, fontweight="bold", color=WHITE, va="top")
    fig.text(LM, 1 - 0.058, subtitle, fontsize=7.8, color="#C9D2DC", va="top")
    fig.text(RM, 1 - 0.058, f"Massive 8-K × NASA FIRMS   ·   page {page} of 2",
             fontsize=7, color="#9AA7B5", va="top", ha="right")

    if chips:
        n = len(chips)
        gap = 0.012
        cw = (CW - gap * (n - 1)) / n
        y0 = 1 - band_h - 0.004 - 0.072
        for i, (big, small) in enumerate(chips):
            x0 = LM + i * (cw + gap)
            fig.patches.append(
                FancyBboxPatch(
                    (x0, y0),
                    cw,
                    0.058,
                    transform=fig.transFigure,
                    boxstyle="round,pad=0,rounding_size=0.006",
                    facecolor=PANEL,
                    edgecolor=RULE,
                    lw=0.8,
                )
            )
            fig.text(x0 + 0.012, y0 + 0.036, big, fontsize=12, fontweight="bold", color=HEAT if i == 0 else INK, va="center")
            fig.text(x0 + 0.012, y0 + 0.014, small, fontsize=6.4, color=MUTED, va="center")


def footer(fig):
    fig.add_artist(plt.Line2D([LM, RM], [0.040, 0.040], transform=fig.transFigure, color=RULE, lw=0.8))
    fig.text(LM, 0.030, "GQHacks · facility-disruption options study · exploratory research, not investment advice",
             fontsize=6.3, color=MUTED, va="center")
    fig.text(LM, 0.018, "Artifacts: thermal-based options pricing.ipynb · physical-facility-disruption-fire-weather.ipynb · "
             "disruption_events.json · .env", fontsize=6.0, color=MUTED, va="center")


def section_label(fig, x, y, num, title):
    fig.patches.append(
        FancyBboxPatch((x, y - 0.006), 0.022, 0.016, transform=fig.transFigure,
                       boxstyle="round,pad=0,rounding_size=0.003", facecolor=HEAT, edgecolor="none")
    )
    fig.text(x + 0.011, y + 0.002, str(num), fontsize=7.2, fontweight="bold", color=WHITE, ha="center", va="center")
    fig.text(x + 0.030, y + 0.002, title, fontsize=9.2, fontweight="bold", color=INK, va="center")


def body(fig, x, y, text, size=7.0, color=INK_2, ls=1.42, w=None):
    fig.text(x, y, text, fontsize=size, color=color, va="top", ha="left", linespacing=ls, wrap=False)


def card(fig, x, y, w, h, fill=WHITE, edge=RULE, lw=0.8):
    fig.patches.append(
        FancyBboxPatch((x, y), w, h, transform=fig.transFigure,
                       boxstyle="round,pad=0,rounding_size=0.007", facecolor=fill, edgecolor=edge, lw=lw)
    )


def chart_title(ax, text, sub=None):
    if sub:
        ax.set_title(text, loc="left", fontsize=8.2, fontweight="bold", color=INK, pad=14)
        ax.text(0, 1.025, sub, transform=ax.transAxes, fontsize=6.2, color=MUTED, va="bottom")
    else:
        ax.set_title(text, loc="left", fontsize=8.2, fontweight="bold", color=INK, pad=5)


def pct_label(ax, bars, vals, fmt="{:+.2f}%", dy=0.0, size=6.4, bold_idx=None):
    for i, (b, v) in enumerate(zip(bars, vals)):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v + (dy if v >= 0 else -dy),
            fmt.format(v),
            ha="center",
            va="bottom" if v >= 0 else "top",
            fontsize=size,
            fontweight="bold" if bold_idx == i else "normal",
            color=INK,
        )


# ---------------------------------------------------------------- page 1
def pipeline(fig, x, y, w, h):
    ax = ax_box(fig, x, y, w, h)
    steps = [
        ("8-K text", "Massive items_text\nmostly Items 2.05 / 7.01", PANEL),
        ("Disruption filter", "plant · fire · shutdown\nphrases, FP cuts", PANEL),
        ("FIRMS label", "brief · persistent ·\nunknown (3-day rule)", HEAT_LT),
        ("Trade brief only", "iron condor 3/10\n1m · post · 5% OTM", "#FBE8D6"),
    ]
    n = len(steps)
    gap = 0.045
    bw = (1 - gap * (n - 1)) / n
    for i, (t, s, fc) in enumerate(steps):
        x0 = i * (bw + gap)
        ax.add_patch(FancyBboxPatch((x0, 0.12), bw, 0.76, boxstyle="round,pad=0,rounding_size=0.03",
                                    facecolor=fc, edgecolor=INK_2, lw=0.9))
        ax.text(x0 + bw / 2, 0.66, t, ha="center", va="center", fontsize=8, fontweight="bold", color=INK)
        ax.text(x0 + bw / 2, 0.36, s, ha="center", va="center", fontsize=6.3, color=MUTED, linespacing=1.3)
        if i < n - 1:
            ax.annotate("", xy=(x0 + bw + gap - 0.004, 0.5), xytext=(x0 + bw + 0.004, 0.5),
                        arrowprops=dict(arrowstyle="-|>", color=HEAT, lw=1.4, mutation_scale=9))


def chart_implied(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h])
    vals = [11.5, 5.3]
    bars = ax.bar(["Implied move\n(1m ATM, t_pre)", "|Realized|\n(median)"], vals,
                  color=[HEAT, COOL], width=0.56)
    ax.set_ylim(0, 14.5)
    ax.set_ylabel("% of spot")
    ax.set_yticks([0, 5, 10])
    chart_title(ax, "Priced vs delivered", "Realized beat implied in only 13% of events")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.35, f"{v:.1f}%", ha="center", fontsize=8.5, fontweight="bold")
    ax.spines["left"].set_color(RULE)
    ax.spines["bottom"].set_color(RULE)


def chart_ratio(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h])
    hz = ["1", "2", "3", "5", "10", "21", "exp"]
    ev = [0.83, 0.97, 1.03, 1.05, 1.07, 0.97, 0.74]
    ev_lo = [0.50, 0.62, 0.68, 0.68, 0.69, 0.55, 0.33]
    ev_hi = [1.34, 1.37, 1.40, 1.42, 1.52, 1.41, 1.29]
    pl = [0.68, 0.72, 0.87, 0.83, 1.04, 0.99, 0.98]
    pl_lo = [0.55, 0.57, 0.70, 0.64, 0.82, 0.58, 0.74]
    pl_hi = [0.81, 0.90, 1.06, 1.03, 1.27, 1.53, 1.25]
    xs = np.arange(len(hz))
    ax.axhline(1.0, color=INK_2, lw=0.8, ls=(0, (3, 3)))
    ax.fill_between(xs, ev_lo, ev_hi, color=HEAT, alpha=0.14, lw=0)
    ax.fill_between(xs, pl_lo, pl_hi, color=COOL, alpha=0.12, lw=0)
    ax.plot(xs, ev, "o-", color=HEAT, lw=1.8, ms=3.6, label="Events")
    ax.plot(xs, pl, "s--", color=COOL, lw=1.3, ms=3.0, label="Placebo (ordinary days)")
    ax.set_xticks(xs)
    ax.set_xticklabels(hz)
    ax.set_xlabel("Horizon (sessions · expiry)")
    ax.set_ylabel("|realized| / implied")
    ax.set_ylim(0.2, 1.7)
    ax.legend(frameon=False, fontsize=6.2, loc="upper left", ncol=2, handlelength=1.6)
    chart_title(ax, "Ratio yardstick with bootstrap CIs", "Below 1 ⇒ quieter than the chain priced. Event CIs still include 1 (small n)")
    ax.spines["left"].set_color(RULE)
    ax.spines["bottom"].set_color(RULE)


def chart_ranking(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h])
    names = ["Iron condor 3/10", "Cash-secured put", "Long call (diag.)", "Covered call", "Collar (diag.)", "Protective put (diag.)"]
    edge = np.array([2.42, 1.10, 0.81, -3.85, -4.75, -6.68])
    n_ev = [7, 12, 12, 9, 8, 9]
    ys = np.arange(len(names))[::-1]
    cols = [HEAT if i == 0 else (GOOD if v > 0 else BAD) for i, v in enumerate(edge)]
    ax.barh(ys, edge, color=cols, height=0.62)
    ax.axvline(0, color=INK_2, lw=0.8)
    ax.set_yticks(ys)
    ax.set_yticklabels(names, fontsize=7)
    ax.set_xlim(-8.6, 4.6)
    ax.set_xlabel("Event − placebo edge, avg of h=21 and expiry (% of spot)")
    for yi, v, n in zip(ys, edge, n_ev):
        label = f"{v:+.2f}%  ·  n={n}"
        if v >= 0:
            ax.text(v + 0.14, yi, label, va="center", ha="left", fontsize=6.6, color=INK,
                    fontweight="bold" if v == edge[0] else "normal")
        elif v < -5.5:
            # long bar: label inside so it clears the y-axis labels
            ax.text(v + 0.18, yi, label, va="center", ha="left", fontsize=6.6, color=WHITE)
        else:
            ax.text(v - 0.14, yi, label, va="center", ha="right", fontsize=6.6, color=INK)
    chart_title(ax, "In-sample structure search · FIRMS-brief · 1m · entry = post · OTM 5%",
                "Short premium with defined risk wins; stock-linked and long-vol structures lose vs placebo")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.spines["bottom"].set_color(RULE)


def page1(pdf):
    fig = plt.figure(figsize=(W, H))
    header(
        fig,
        "Facility-disruption 8-Ks × FIRMS: short event-vol on brief filings",
        "Submission write-up · hypothesis · method · in-sample evidence",
        1,
        chips=[
            ("+2.42%", "Condor 3/10 edge vs placebo (IS)"),
            ("11.5% → 5.3%", "Implied move vs |realized| (median)"),
            ("45 · 24 · 8", "Events · IS brief · OOS brief"),
            ("13%", "Events where realized beat implied"),
        ],
    )

    # --- Section 1 & 2 text columns
    top = 0.805
    section_label(fig, LM, top, 1, "Hypothesis & novelty")
    body(
        fig, LM, top - 0.022,
        "After a facility-related 8-K that FIRMS labels brief (no lasting\n"
        "thermal anomaly), listed options overprice the event move. The\n"
        "right expression is defined-risk short event-vol — an iron condor —\n"
        "not a long call or a stock-linked structure.\n\n"
        "Novelty: Massive 8-K text joined to NASA FIRMS persistence, so the\n"
        "trade set is filings that read like plant shocks but show no heat.\n\n"
        "Honest refinement: a fire/weather-only cut does not replicate the\n"
        "edge. FIRMS behaves as a negative screen on a shutdown-heavy panel,\n"
        "not a positive “we saw a fire from space” signal (see page 2).",
    )

    xr = LM + CW * 0.52
    section_label(fig, xr, top, 2, "Method")
    body(
        fig, xr, top - 0.022,
        "Events  8-K items_text → disruption phrases → geocode → FIRMS →\n"
        "brief / persistent / unknown. Trade only brief (PERSIST_DAYS = 3).\n\n"
        "Pricing  1m chain, entry = filing close, 5% OTM wings; synthetic\n"
        "spot from the ATM pair; horizons 1…21 sessions + expiry.\n\n"
        "Inference  Event P&L minus placebo ordinary days on the same\n"
        "names; bootstrap CIs; rank on h=21 + expiry; 2025 out-of-sample;\n"
        "5% premium haircut; sensitivity on OTM / bucket / entry / persist.\n\n"
        "Replication  run_study(start, end) for the judges’ sealed window.",
    )

    # --- Pipeline
    pipeline(fig, LM, 0.565, CW, 0.075)

    # --- Charts row
    chart_implied(fig, LM + 0.012, 0.345, 0.26, 0.16)
    chart_ratio(fig, LM + 0.345, 0.345, CW - 0.345, 0.16)

    # --- Ranking (axes start far enough right for the y labels to clear the card)
    chart_ranking(fig, LM + 0.31, 0.095, CW - 0.31, 0.19)

    # --- Result callout (left of ranking)
    card(fig, LM, 0.095, 0.165, 0.215, fill="#FFF6EE", edge=HEAT, lw=0.9)
    fig.text(LM + 0.012, 0.298, "Read", fontsize=8.2, fontweight="bold", color=HEAT, va="top")
    body(
        fig, LM + 0.012, 0.276,
        "Chains price ~11% moves;\npaths deliver ~5%.\n\n"
        "The core five structures\nare stock-linked and miss\nthe vol edge.\n\n"
        "Condor 3/10 is starred vs\nplacebo at h=10 & expiry.\n\n"
        "Exploratory: n is small\nand CIs are wide.",
        size=6.5, ls=1.35,
    )

    footer(fig)
    pdf.savefig(fig)
    plt.close(fig)


# ---------------------------------------------------------------- page 2
def chart_oos(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h])
    structs = ["Condor 3/10", "Cash-secured put", "Covered call"]
    is_h21 = [0.10, -0.65, -2.71]
    oos_h21 = [1.76, 0.21, 5.00]
    is_exp = [1.96, 0.79, -0.15]
    oos_exp = [-1.69, -3.29, -0.71]
    xs = np.arange(len(structs))
    bw = 0.19
    ax.bar(xs - 1.5 * bw, is_h21, bw, color=COOL_LT, edgecolor=COOL, lw=0.7, label="IS h=21")
    ax.bar(xs - 0.5 * bw, oos_h21, bw, color=COOL, label="OOS h=21")
    ax.bar(xs + 0.5 * bw, is_exp, bw, color=HEAT_LT, edgecolor=HEAT, lw=0.7, label="IS expiry")
    ax.bar(xs + 1.5 * bw, oos_exp, bw, color=HEAT, label="OOS expiry")
    ax.axhline(0, color=INK_2, lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels(structs, fontsize=6.8)
    ax.set_ylabel("Mean P&L per $1 spot (%)")
    ax.legend(frameon=False, fontsize=6.0, ncol=4, loc="upper left", columnspacing=1.0, handlelength=1.2)
    ax.set_ylim(-4.2, 6.4)
    chart_title(ax, "Out-of-sample transfer · 2025 · n ≈ 5 priced",
                "Condor keeps sign mid-horizon; hold-to-expiry flips for condor and CSP")
    ax.spines["left"].set_color(RULE)
    ax.spines["bottom"].set_color(RULE)


def chart_costs(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h])
    cats = ["Gross\nh=21", "Net\nh=21", "Gross\nexpiry", "Net\nexpiry"]
    vals = [0.10, -0.78, 1.96, 0.84]
    cols = [COOL_LT, BAD, HEAT_LT, GOOD]
    edges = [COOL, BAD, HEAT, GOOD]
    bars = ax.bar(cats, vals, color=cols, edgecolor=edges, lw=0.8, width=0.62)
    ax.axhline(0, color=INK_2, lw=0.8)
    ax.set_ylim(-1.5, 2.7)
    ax.set_ylabel("% of spot")
    pct_label(ax, bars, vals, dy=0.08, size=7)
    chart_title(ax, "Condor 3/10 after costs", "5% of premium each way · share net-positive at h=21 = 22%")
    ax.spines["left"].set_color(RULE)
    ax.spines["bottom"].set_color(RULE)


def chart_acute(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h])
    labels = ["Stock\nh=21", "CSP\nh=21", "Condor\nh=21", "Stock\nexpiry", "CSP\nexpiry"]
    is_v = [5.23, -0.12, 1.30, 7.60, 4.14]
    oos_v = [-10.07, -7.06, 9.33, -22.75, -13.47]
    xs = np.arange(len(labels))
    bw = 0.38
    ax.bar(xs - bw / 2, is_v, bw, color=COOL, label="IS acute (n ≈ 4 priced)")
    ax.bar(xs + bw / 2, oos_v, bw, color=HEAT, label="OOS · single PBF fire")
    ax.axhline(0, color=INK_2, lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=6.3)
    ax.set_ylabel("% of spot")
    ax.set_ylim(-26, 12)
    ax.legend(frameon=False, fontsize=6.0, loc="lower left")
    chart_title(ax, "Fire / weather cut · IS vs OOS", "Six IS events; the lone OOS fire moved hard")
    ax.spines["left"].set_color(RULE)
    ax.spines["bottom"].set_color(RULE)


def chart_sensitivity(fig, x, y, w, h):
    """Heat-table of mean P&L at h=21 across OTM (1m, entry=post)."""
    ax = fig.add_axes([x, y, w, h])
    rows = ["Long call", "Covered call", "Protective put", "Collar", "Cash-secured put", "Iron condor 3/10"]
    cols = ["OTM 3%", "OTM 5%", "OTM 10%", "pre 3%", "pre 5%", "pre 10%"]
    data = np.array(
        [
            [2.28, 2.28, 2.28, 1.80, 1.80, 1.80],
            [-2.12, -2.71, -3.47, -1.75, -2.30, -2.87],
            [-7.02, -7.11, -9.09, -6.49, -6.87, -8.36],
            [-3.72, -4.63, -7.94, -3.46, -4.44, -7.21],
            [-0.75, -0.65, 1.18, -0.71, -0.81, 1.16],
            [0.10, 0.10, 0.10, -0.24, -0.24, -0.24],
        ]
    )
    stars = {(2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (4, 2), (4, 5)}
    vmax = 7.5
    cmap = plt.get_cmap("RdBu")
    im = ax.imshow(data, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, fontsize=6.3)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=6.6)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            txt = f"{v:+.1f}" + ("*" if (i, j) in stars else "")
            ax.text(j, i, txt, ha="center", va="center", fontsize=6.3,
                    color=WHITE if abs(v) > 3.8 else INK, fontweight="bold" if i == 5 else "normal")
    chart_title(ax, "Sensitivity · mean P&L at h=21 (1m) across OTM and entry session",
                "* = 95% CI excludes zero · entry = post unless marked pre · PERSIST_DAYS 2/3/5 leaves brief count ~unchanged (24→25)")
    ax.text(len(cols) - 0.5, len(rows) - 0.3, "", fontsize=6)


def page2(pdf):
    fig = plt.figure(figsize=(W, H))
    header(
        fig,
        "Robustness, the fire-weather stress test, and how to trade it",
        "Out-of-sample · costs · acute-only cut · sensitivity · what breaks · sealed-window forecast",
        2,
    )

    # --- Row 1: OOS + costs
    top = 0.885
    section_label(fig, LM, top, 3, "Out-of-sample and trading costs")
    chart_oos(fig, LM + 0.012, 0.675, 0.50, 0.155)
    chart_costs(fig, LM + 0.60, 0.675, CW - 0.60, 0.155)

    # --- Row 2: acute cut card + chart
    y2 = 0.615
    section_label(fig, LM, y2, 4, "Is the thermal signal load-bearing?  Fire / weather / outage cut")
    card(fig, LM, 0.43, 0.50, 0.17, fill=PANEL, edge=RULE)
    body(
        fig, LM + 0.014, 0.588,
        "Keep only facility_fire · explosion · weather_disruption ·\n"
        "plant_outage → 6 IS / 1 OOS events, ~4 with a usable 1m chain.\n\n"
        "• Placebo ranking is empty at this n; the notebook falls back to\n"
        "  “winner = long call” — not a strategy result.\n"
        "• In-sample names tended to rally (stock ≈ +5% at h=21); the\n"
        "  quiet-path story weakens.\n"
        "• Sole OOS fire (PBF Martinez) moved −10% / −23%: adverse for\n"
        "  short premium.\n\n"
        "Conclusion  The full-panel edge is mainly salient shutdown /\n"
        "restructuring 8-K language. Only one persistent event sits in-\n"
        "window (VLO), so FIRMS barely reshapes the sample.",
        size=6.7, ls=1.38,
    )
    chart_acute(fig, LM + 0.565, 0.445, CW - 0.565, 0.125)

    # --- Row 3: sensitivity heat-table
    y3 = 0.395
    section_label(fig, LM, y3, 5, "Parameter sensitivity")
    chart_sensitivity(fig, LM + 0.135, 0.245, CW - 0.135, 0.112)

    # --- Row 4: three cards
    y4 = 0.205
    section_label(fig, LM, y4, 6, "What breaks it · how we would trade · sealed window")
    cards = [
        (
            "What would break it",
            BAD,
            "• True disasters / persistent FIRMS → short\n"
            "  vol loses; wings only bound the loss\n"
            "• FIRMS false negatives contaminate brief\n"
            "• Thin OTM liquidity; haircuts already\n"
            "  erase the h=21 edge\n"
            "• Treating shutdowns as satellite fires\n"
            "• Automatic hold-to-expiry (OOS flips)",
        ),
        (
            "How we would trade it",
            COOL,
            "• Only as a small, full-panel expression:\n"
            "  iron condor 3/10, 1m, entry near filing\n"
            "  close, exit by ~h=10–21\n"
            "• Skip persistent and unknown labels\n"
            "• Do not size a book on the fire/weather\n"
            "  set — too few events, placebo broken\n"
            "• Research-grade, not production",
        ),
        (
            "Sealed-window forecast",
            HEAT,
            "We predict fragility, not replication:\n"
            "• Expiry P&L likely flips sign again\n"
            "• Mid-horizon condor may hold weakly\n"
            "• Any true fire in the window will hurt\n"
            "  short premium\n"
            "• n will be single-digit; CIs will include 0\n"
            "Rubric: 30 · 30 · 20 · 10 · 10",
        ),
    ]
    gap = 0.014
    cw = (CW - gap * 2) / 3
    for i, (t, accent, txt) in enumerate(cards):
        x0 = LM + i * (cw + gap)
        card(fig, x0, 0.055, cw, 0.135, fill=WHITE, edge=RULE)
        fig.patches.append(Rectangle((x0, 0.055 + 0.135 - 0.006), cw, 0.006, transform=fig.transFigure,
                                     facecolor=accent, edgecolor="none"))
        fig.text(x0 + 0.012, 0.176, t, fontsize=7.8, fontweight="bold", color=INK, va="top")
        body(fig, x0 + 0.012, 0.158, txt, size=6.3, ls=1.36)

    footer(fig)
    pdf.savefig(fig)
    plt.close(fig)


def main() -> None:
    with PdfPages(PDF) as pdf:
        page1(pdf)
        page2(pdf)
        d = pdf.infodict()
        d["Title"] = "Facility disruption 8-Ks × FIRMS — 2-page summary"
        d["Author"] = "GQHacks"
        d["Subject"] = "Submission write-up for the Massive facility-disruption options study"
    print("wrote", PDF)


if __name__ == "__main__":
    main()
