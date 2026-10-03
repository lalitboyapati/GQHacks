# Footprints before the 8-K

Gator Quant Hacks 2026 · Massive Challenge. Notebook: `footprints-before-the-8k.ipynb`; `run_study(start, end)` reruns everything on any window.

## 1 · Hypothesis

Material events leak before they are public, and the people who know trade options. That leaves a **footprint** in the sessions before the announcement: abnormal option volume, tilted toward OTM calls or OTM puts, with the risk reversal moving the same way. The 8-K is filed up to four business days later. **Claim:** when the 8-K category says the news was the leakable kind (deals, CEO/CFO exits, guidance, restructurings, impairments, settlements and 27 other tags chosen by one rule: material, unscheduled, known to insiders first), the market under-uses the footprint, and the stock keeps moving the way the flow pointed.

- **Study 1 (pre-registered before any data was pulled):** a bullish footprint means **1 · Long call**; a bearish one means **3 · Protective put**.
- **Study 2 (formed after a first run):** the footprint is *visible*. Call buyers bid up IV, so after a bullish footprint you should **sell** the call (**2 · Covered call**). After a bearish one, the **protective put's hedge leg** should pay.

## 2 · Method

- **Universe and windows.** Top 100 US companies. In-sample 2024–2025 (520 leak-prone 8-Ks, 98 tickers); out-of-sample Jan–Aug 2026 (190 events). The sealed window has never been pulled.
- **Announcement date.** The earliest date written in the filing text, up to 14 days before the filing (28% of events). The signal window ends the session before it.
- **Footprint.** Sixteen contracts are fixed from the chain *before* the baseline: two expiries × ATM, 3%, 6% and 10% OTM on each side.
  - Abnormal volume: the 5-session window against a 20-session baseline.
  - Direction: the change in OTM call share and the change in the risk reversal (BS IV from closes, spot from put-call parity).
  - The abnormal threshold is the 80th percentile of **ordinary days**, learned once in-sample and frozen for every later window.
- **Entry.** Close of the session *after* the filing. Massive has no acceptance timestamps, and a filing accepted 16:00–17:30 carries that day's date, so entering at that day's close would be look-ahead.
- **Design.** A 2 × 2 difference-in-differences: (8-K + footprint − 8-K + quiet) − (ordinary + footprint − ordinary + quiet), on 764 ordinary days for the same names, kept clear of every known 8-K.
  - Negative controls: earnings, director appointments, equity grants, charter amendments.
  - **Five headline numbers**, fixed in advance: P&L averaged over h = 5, 10, 21, with a week-clustered bootstrap, a 5,000-draw permutation test and Holm correction.
  - Sensitivity: 19 one-knob variants. Costs: real closing NBBO spreads from options quotes.

## 3 · Result: a careful null with a short decay curve

**Headline numbers** (per $1 of spot, 3–6m options; [95% CI, week-clustered]):

| | In-sample (n in A) | perm. p / Holm | Out-of-sample (n in A) | perm. p |
|---|---|---|---|---|
| S1a Stock drifts with the footprint | +0.34% [−1.81, +2.45] (43) | 0.74 / 1.00 | −1.38% [−5.30, +2.54] (26) | 0.48 |
| S1b BULL → long call | +0.17% [−1.75, +2.15] (25) | 0.85 / 1.00 | −0.73% [−4.38, +3.07] (17) | 0.78 |
| S1c BEAR → protective put | −0.75% [−2.69, +1.11] (18) | 0.53 / 1.00 | +2.69% [−0.97, +6.54] (8) | 0.43 |
| S2a BULL → covered call | +0.47% [−2.09, +2.71] (24) | 0.65 / 1.00 | +1.44% [−1.97, +5.20] (17) | 0.35 |
| S2b BEAR → put hedge leg | −0.17% [−0.92, +0.62] (18) | 0.76 / 1.00 | −1.94% [−4.45, +0.26] (8) | 0.08 |

**Decay across every fixed horizon**, BULL → long call DiD (\* = 95% CI excludes 0):

| h | 2 | 3 | 5 | 10 | 21 | 42 | 63 | expiry |
|---|---|---|---|---|---|---|---|---|
| In-sample | **+0.57%\*** | **+0.96%\*** | +0.81% | +0.15% | −0.40% | −2.36% | −1.90% | −6.18%\* |
| Out-of-sample | −0.54% | −0.28% | +0.22% | +0.71% | −3.49% | +0.27% | +9.39% | +12.68% |

(h = 1 is absent because the trade enters one session after the filing. Full tables for all four trades, in-sample and out-of-sample, are in notebook sections 8, 9 and 13.)

**What the evidence says:**
1. **Footprints are barely more common before leak-prone 8-Ks** than on ordinary days: 22% vs 20% cross the threshold. On the 100 largest names, most leakage doesn't show up in daily option volume.
2. **In-sample, the value is short-lived:** about +0.6% to +1.0% at 2–3 sessions, gone by 10, with the signed stock drift following the same shape. **Out-of-sample this doesn't reappear** (−0.5% at h = 2, 17 events).
3. **None of the five headline numbers is significant** in either window. S2a (the covered call) is the only one with the same sign in both. Negative controls are equally null.
4. **The Study 2 mechanism isn't there.** IV at entry after a bullish footprint is +3.1% relative to quiet flow, and that difference isn't significant. The implied-vol part of the long call's P&L is a few basis points.
5. **The first run's "findings" were a small-sample artefact.**
   - That run used 9 tags, entry at the filing-session close and a per-cell bootstrap. It showed the long call and protective put losing, with stars at several horizons.
   - The notebook records it verbatim in Appendix A. Rerunning with the first run's own settings (sensitivity row) brings back one starred cell, on 12 events.
   - With 520 events and proper inference, every headline number is within about one standard error of zero.

## 4 · What would make it break, and what we predict for the sealed window

- **Sample size is the binding constraint:** 25 BULL / 18 BEAR in-sample, 17 / 8 out-of-sample. A sealed window of a few months will hold a handful of each.
- **Predictions (also in notebook §15, written before the sealed run):**
  - Every headline number insignificant (P ≈ 0.95 each).
  - Signs: S1a +, S1b +, S1c −, S2a +, S2b −, each with roughly coin-flip confidence (0.50–0.55).
  - The one we'd bet on: with ≥ 10 BULL events, the long call's DiD is positive at h = 2–3 and smaller at h = 10 (P ≈ 0.6).
- **False-positive risks:** one or two large deals carrying a short window; a volatility regime that moves the frozen threshold; leaks reported in the press before the filing, which we can't date with Massive data. A significant number in a short window is more likely a few events than a discovery; the notebook's "which events carry it" table is where to check.

## 5 · How we would trade it: we wouldn't, yet

- **Costs exceed the edge.** Round-trip closing spreads on the 5% OTM legs cost 0.28% (covered call) and 0.39% (put) of spot. That's more than the gross edge at 10 sessions: +0.05% and −0.19%.
- **Capacity is tiny.** The legs trade tens of contracts on the entry day, which is tens of thousands of dollars of stock at 10% of volume. That's about 12 BULL events a year.
- **A version worth testing live:**
  - Signal computed nightly across the top 100.
  - 1-month ATM call bought at the next-session close and exited at 3 sessions, where the in-sample curve peaks.
  - ATM spreads measured before sizing.
  - Kill it if the sealed-window or live sign at h = 2–3 is negative over the first 20 events.

**Limitations:**
- Volume is unsigned. Lee-Ready signing from trades and quotes would be several GB of cache, so the risk reversal stands in as the signing proxy.
- 16 sampled contracts per event, not the full chain.
- Announcement dates come from regex on the filing text.
- Synthetic stock, parity spot, last-trade marks.
- Static universe (survivorship), no earnings calendar. Mitigated: ordinary days avoid all earnings 8-Ks, and a sensitivity row drops events near earnings.
