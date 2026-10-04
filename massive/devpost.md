# Devpost · Project details

## Project name

**Read the Filing: two 8-K event trades, checked from space and read by an AI**

## Elevator pitch (≤ 200 chars)

When a company files an 8-K, options traders price the reaction. We ask a satellite and a language model whether that price is wrong — and show where the edge is (and where it isn't).

---

## About the project

### Inspiration

An 8-K is the form a public company has to file when something material happens: a plant catches fire, a drug trial reads out, a factory is shut down. The options market reacts within minutes and puts a price on how big the stock move "should" be. We wanted to know whether an **outside source of information** — something the market isn't already using — could tell us when that price is too high or too low.

Two sources jumped out. NASA's FIRMS satellites see heat on the ground every day, so they can tell you whether a "plant fire" filing describes something still burning or a line that was quietly idled. And a language model can read a trial-results press release — with the company and drug names hidden — and grade it before anyone on a desk has finished the first paragraph.

### What it does

**Strategy A · Factory disruptions × satellite.** We pull every 8-K that mentions a fire, explosion, outage, shutdown or storm damage at a plant, geocode the site, and check NASA FIRMS for a persistent heat signature. If nothing is burning for 3+ days the filing is labelled `brief`. On `brief` filings the options market prices a ~11.5% one-month move; the stock actually moves ~5.3%. We sell that over-priced protection with a capped-risk iron condor and measure it against ordinary days on the same stocks.

**Strategy B · Drug-trial readouts × AI reader.** We pull every `clinical_trial_results` 8-K from 1,499 pharma/biotech filers (dead companies included), have Jev grade the masked press release on a five-level scale, and test whether a hedged long/short on the grade earns anything after the first close. It doesn't — but the AI's grade tracks the day-one move (ρ = 0.38, 0.75 vs blind hand labels), and the protective put is 23% cheaper the evening *after* the result than before. The edge is in the reader and in the timing of the hedge.

Both pipelines take only a start date and an end date, and reproduce every number on any window — including the judges' sealed one.

### How we built it

- **Data:** Massive's 8-K text and options APIs (OPRA chains, filing metadata), SEC EDGAR acceptance timestamps, NASA FIRMS VIIRS hotspot archive, OpenStreetMap geocoding for plant sites.
- **Classifier:** Jev (`jev-1.13.0`, pinned) via TypeSafe — nine typed questions per filing in one request, answers cached on disk and committed so results reproduce without an API key.
- **Pricing:** synthetic spot recovered from the ATM call/put pair, so no separate stock feed is needed; NBBO mid → last trade → intrinsic fallbacks for option marks.
- **Rigor:** fixed horizons (1–21 sessions + expiry), placebo trades on the same names on non-event days, bootstrap confidence intervals, frozen out-of-sample years (2025 for A, 2026 for B), trading-cost haircuts, and parameter grids over strike, expiry, entry time and the heat-persistence rule.
- **Stack:** Python 3.10, pandas, NumPy, matplotlib, requests, Jupyter. Every API response is cached; a cold run is ~20 minutes, a warm one a few.
- **Deliverables:** four reproducible notebooks, a 45-event labelled disruption panel, a plain-language two-page paper and a technical one, and a figure pipeline that regenerates every chart from one script.

### Challenges we ran into

- **The satellite turned out to be a filter, not a signal.** Most "disruption" 8-Ks are planned closures, so FIRMS almost always says "no heat." We built a fire/weather-only cut to test whether thermal data was load-bearing — it wasn't at the sample size we had, and we said so in the paper.
- **Options on tiny biotechs barely trade.** Median quoted spread was 53% of mid, and a liquidity gate cut 94 candidate trades to 9. We separated a "signal layer" (bare stock, all events) from a "trade layer" (only where a hedge was actually quoted) so the two questions didn't contaminate each other.
- **Dates are hard.** Press releases precede 8-Ks by 0–1 sessions, EDGAR acceptance can be pre-market or after the close, and a filing on a holiday needs the *next* session. Getting `t_pre`, `t_news` and `t_0` right was most of the debugging.
- **Keeping ourselves honest.** The in-sample winner for B flipped sign on every out-of-sample horizon. The temptation to tune was real; we froze the parameters and reported the failure instead.

### Accomplishments that we're proud of

- A clean, replicated **short-vol edge** on disruption filings: iron condor +2.42% over placebo (significant at h=10 and expiry), sign holding mid-horizon on the 2025 hold-out.
- A **language-model classifier that provably works** on masked filings — and an honest demonstration that being right about direction isn't enough when the market agrees within the session.
- A **hedge-timing finding** that a PM can act on tomorrow: buy the protective put after the readout, not before.
- Two papers written for two audiences, with every figure regenerable and every claim tied to a notebook cell.

### What we learned

- The gap between *implied* and *realized* is where event edges live; directional calls on well-covered events are already in the price.
- "Novel data" is only novel if it changes the sample. We learned to ask how many decisions a signal actually flips before calling it a signal.
- Placebo controls and frozen out-of-sample windows are not decoration — they changed our conclusions on both strategies.
- Writing the plain-language version forced us to understand which numbers really mattered.

### What's next

- Widen the disruption panel beyond 55 names and 45 events so the thermal signal can be tested at a sample size where it could matter.
- Add live FIRMS polling so the `brief`/`persistent` label is available at the filing close, not the next morning.
- Run both pipelines on the judges' sealed window and publish the prediction scorecard we committed to in the paper.
- Extend the reader to other 8-K categories (restructurings, executive departures) where text sentiment might lead the tape.

---

## Built with (tags)

```
python · jupyter · pandas · numpy · matplotlib · massive-api · sec-edgar · nasa-firms · satellite-data · jev · llm · options-trading · quantitative-finance · backtesting · openstreetmap
```

(15 tags — paste individually into Devpost's "Built With" field.)

## Links

- Notebooks: `massive/gqh-massive-8k-starter/thermal-based options pricing.ipynb`, `physical-facility-disruption-fire-weather.ipynb`, `massive/biotech-final.ipynb`
- Papers: `massive/summary_graphics/combined_writeup_plain.pdf` (judges / recruiters), `combined_writeup.pdf` (technical)
- Figures: `massive/summary_graphics/` (regenerate with `make_summary_graphics.py`)
