# The Quant Note — Physical Facility Disruption 8-Ks

**Track:** Physical facility disruption · **Data:** Massive OPRA + Massive 8-Ks + NASA FIRMS  
**Primary notebook:** `physical-facility-disruption-condor-plus-sweep.ipynb`  
**Windows:** in-sample 2019–2024 · OOS 2025 · entry = close of filing session (`post`) · baseline expiry ≈ 1m

---

## 0. Why we left the starter “core five”

The Massive 8-K options framework’s default structures are:

1. long ATM call · 2. covered call · 3. protective put · 4. collar · 5. cash-secured put  

Those five are built for **directional / stock-linked** event bets. On FIRMS-`brief` facility filings we instead measured a **volatility** fact: chains priced ~11–12% moves while realized paths were much smaller. The core five **do not harvest that**. CSP and covered call rode the stock, lost or tied placebo, and failed OOS; long call / put / collar are the wrong side of rich event vol.

So we kept the same 8-K + FIRMS event engine and **expanded the structure search** through short ATM straddles/strangles, credit spreads, iron flies, iron condors, delta-hedge approximations, and a 1m/2m calendar (dispersion and listed variance swaps remain out of scope).

---

## 1. Hypothesis

**Finding.** Industrials file disruption 8-Ks (fires, outages, shutdowns, force majeure). Options often price a large near-term move even when the event looks temporary.

**Categories.** Text-filtered physical disruptions, labeled with NASA FIRMS at the geocoded site:

| `facility_group` | Rule | Action |
|---|---|---|
| **`brief`** | No lasting hotspot, or heat clears before 3 days | **Sell premium** |
| `persistent` | Hotspot still on ≥ 3 days | Skip (control) |
| `unknown` | Missing site / coverage | Skip |

**Why mispricing.** Filing language is salient; satellite persistence is not. Brief thermal footprint → **implied move > realized** → short event vol with defined risk.

**Strategy chosen after the sweep.** **Iron condor 3/10** (short ~3% OTM strangle, long ~10% wings) on ~1m options, managed on fixed mid horizons—not the core five, and not naked short straddles despite their in-sample rank.

---

## 2. Method

1. **Events:** Massive 8-K text filter → geocode → FIRMS → `disruption_events.json`. Expanded universe/patterns: raw pull ~90 filings → **45** after boilerplate FP cleanup (**36** `brief`).
2. **Options:** OPRA marks; synthetic spot from ATM call/put; horizons \(h \in \{1,2,3,5,10,21\}\) + expiry; ordinary-day placebo; sealed 2025 OOS.
3. **Usable panel after liquidity drops:** ~**15** in-sample / ~**5** OOS events with 1m books (24 brief IS events → 41 priced bucket pairs; many thin names drop).

| Stage | Structures | Outcome on expanded sample |
|---|---|---|
| Core five (starter) | Long call, CC, protective put, collar, CSP | **Miss the vol edge** (stock-linked) |
| Straddle / strangle | Short ATM / OTM | Best IS placebo rank; **OOS expiry reverses** |
| Shortvol / condor+ | Condors, flies, credits, Δ-hedge, calendar | **Condor 3/10** least broken OOS mid-horizon |

---

## 3. Results (with uncertainty)

**Overpricing (1m ATM on \(t_{pre}\)).** Median implied **11.5%** vs |realized| **5.3%**; realized beat implied in **13%** of events. Gap still there vs the old ~11%/4% panel, but **narrower**—expansion softened, did not erase, the thesis.

### In-sample mean P&L (% of spot), brief, 1m, post, OTM 5% — \(n{\approx}15\)
\* = bootstrap 95% CI excludes zero.

| Structure | h=1 | h=5 | h=10 | h=21 | expiry |
|---|---:|---:|---:|---:|---:|
| Condor 5/10 | +0.39 | −0.11 | +0.23 | −0.15 | **+1.62\*** |
| Condor 3/10 | +0.20 | +0.84 | +0.13 | +0.10 | +1.96 |
| Short ATM straddle | **−1.28\*** | 0.00 | −0.20 | +0.28 | +2.90 |
| Iron fly 10% | +0.22 | +0.92 | +0.01 | +0.33 | **+3.46\*** |
| Cash-secured put | −0.63 | +0.12 | +0.03 | −0.65 | +0.79 |
| Covered call | −0.68 | +0.03 | −0.51 | −2.71 | −0.15 |

**Placebo edge (events − ordinary days; ranked on h=21 + expiry):** short straddle **+2.90%** > iron fly 10% **+2.81%** > condor 3/10 **+2.42%** > condor 5/10 **+1.85%** ≫ CSP **+1.10%** ≫ covered call **−3.85%**. After a 5% premium haircut, the straddle “winner” is **net negative at h=21 (−0.66%)**.

### Out-of-sample 2025 — \(n{\approx}5\) priced brief events

| Structure | h=5 | h=21 | expiry | Sign stable vs IS (h=5, h=21)? |
|---|---:|---:|---:|---|
| Condor 3/10 | +0.03 | +1.76 | −1.69 | **Yes / Yes** |
| Condor 5/10 | −0.02 | +2.15 | −0.86 | Yes / **No** |
| Short ATM straddle | −1.53 | −4.77 | −5.98 | (weak) / **No** |
| Iron fly 10% | −1.62\* | +1.62 | −1.76 | No / Yes |
| Cash-secured put | +0.07 | +0.21 | −3.29 | Yes / **No** |

**Read.** Expansion **confirmed** that core-five / stock-linked premium and naked short vol are not tradable expressions of this edge. Overpricing remains, but mid-horizons are closer to fair than in the tiny panel. **Condor 3/10** is still the least-broken OOS mid-horizon shape; **hold-to-expiry flips** for almost everything, including condors. Treat as exploratory (\(n\) small).

---

## 4. What would break it

- FIRMS / geocode mislabels (`brief` when damage persists).
- True operational shocks → realized ≫ implied (wings bound loss, not gap risk).
- Thin single-name OTM liquidity; haircuts already wipe h=21 edges.
- 2025-style paths that keep moving through h=21 even when terminal vol looked rich in-sample.
- More clean events reversing the condor 3/10 OOS pattern.
- Managing to **expiry** after OOS sign flips.

---

## 5. How we would trade it

1. Detect disruption-like 8-Ks in the industrial universe (same text rules as the fetch script).
2. Trade only FIRMS-**`brief`**; skip persistent/unknown.
3. Enter near filing-session close: **iron condor ~3% short / ~10% long**, ~21–45 DTE.
4. Hold toward **h=5–21**; do not rely on expiry. Exit if shorts are breached or FIRMS turns persistent.
5. Size to wing width − credit; assume poor wing fills.
6. **Do not** use the starter core five as the alpha expression; **do not** promote naked short straddles from in-sample rank alone.

**One line.** Core five missed a real but fragile FIRMS-brief vol overpricing; after expanding structures and events, the least-broken capture is a **3/10 iron condor** managed on a fixed mid horizon—not hold-to-expiry.
