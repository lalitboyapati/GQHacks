# Handoff — 8-K Options Research Harness

Status brief for a second agent (Codex) picking this up for refinement.
Written 2026-10-03. Read this before changing anything; several design
choices look like bugs but are deliberate, and two real bugs were already
found and fixed in ways worth not regressing.

---

## 1. Where this lives

- Repo: `github.com/lalitboyapati/GQHacks`
- Branch: **`8kadv-test`** — pushed, tracking `origin/8kadv-test`
  (https://github.com/lalitboyapati/GQHacks/tree/8kadv-test)
- Subproject: `gqh-8k-options-research/`
- `main` is untouched, locally and on the remote.
- Findings page (charts + readings):
  https://claude.ai/artifact/2eF4e56avtmKgAV69iHyFx

Run `git log --oneline origin/main..HEAD` for the commit list. The sequence is:
the harness, two classifier fixes (disagreement detection, name possessives),
two committed event sets, the handoff doc, and the findings page.

---

## 2. What the project is

Tests whether SEC Form 8-K filings carry information the **options** market
has not yet priced, on **smaller companies** where analyst coverage is thin.
Four strategies plus two controls:

| Strategy | Trigger | Structure | Premium |
|---|---|---|---|
| `exec_put` | Item 5.02 senior departure, severity ≥ 0.35 | Long put (~35-delta) | pays |
| `efficiency_collar` | Item 2.05/2.06 quantified plan | Long stock + long 25d put + short 25d call | ~flat |
| `novelty_shortvol` | Novelty score < 0.40 (recycled disclosure) | Short 20d strangle | collects |
| `combo` | Plan filings, routed by novelty | Collar if novel, strangle if repeat | mixed |
| `stock_long` / `stock_short` | mirrors another strategy's selection | Underlying only | n/a |

`combo` is the user's requested combination of ideas 1 and 2.

---

## 3. Current state

**Working and verified end-to-end:** event discovery, text classification,
novelty scoring, option pricing/structures, entry-exit simulation, statistics.
85 tests pass (`pytest tests/ -q`), including a full backtest run against a
synthetic data source.

**Not yet run on real market data.** The event layer uses SEC EDGAR, which
needs no key, and two real event sets are committed (`universe_events.json`,
1,054 events, Items 5.02/2.05/2.06; and `universe_events_wide.json`, 1,070
events, adding 7.01/8.01). The *trading* layer needs `MASSIVE_API_KEY` for
prices and option chains. **No real P&L numbers exist yet.** Anyone claiming
otherwise has not run it.

```bash
cd gqh-8k-options-research
uv venv --python 3.11 && uv pip install -e .
cp .env.example .env            # add MASSIVE_API_KEY
python scripts/run_backtest.py --hold 5 --hold 10 --hold 21
```

---

## 4. Module map

```
eightk/
  config.py          105  Settings.from_env(); paths; budget caps
  http.py            121  CachedSession: rate-limited, permanently disk-cached GETs
  edgar.py           309  Filing dataclass; ticker→CIK; 8-K listing; text/exhibit fetch
  classify.py        707  split_items, strip_item_title, parse_exec_change,
                          parse_efficiency_plan, score_exec_severity
  novelty.py         279  assess_novelty + similarity (containment-based)
  events.py          277  EventRecord; build_events joins filings+text+news+caps
  massive_src.py     355  MassiveClient: daily_bars, option_contracts, news,
                          ticker_details, option_ticker (OCC encoding)
  prices.py           99  PriceSeries with a trading calendar derived from the bars
  options_model.py   361  Black-Scholes, greeks, implied_vol, delta_to_strike,
                          Leg/Structure payoff accounting
  options_book.py    256  OptionBook: contract resolution, leg pricing, CostModel
  backtest.py        435  determine_entry, simulate_trade, run_backtest, Trade
  strategies.py      440  the six strategies + StrategyConfig + TradeContext
  report.py          277  summarize, split_summary, volatility_premium_table,
                          format_report (t-stats + bootstrap CIs)
  budget.py          107  SpendLedger with total + per-run hard caps
  databento_opra.py  232  budget-guarded OPRA reader (validation path, off main path)
  universe.py         89  101-ticker small/mid-cap universe, 6 sectors
scripts/
  fetch_events.py    128  build + save the event set
  run_backtest.py    220  run strategies over a saved event set
  describe_events.py 145  descriptive stats on an event set, pre-trading
tests/               85 tests: classify 22, backtest 17, options 15,
                     budget 11, novelty 10, integration 10
```

---

## 5. Data contracts

### Event JSON — `data/events/*.json`

Flat list of 44-field records. Deliberately flat and human-readable so
classifications can be audited by eye. `scripts/run_backtest.py::_rebuild_events`
reconstructs objects from it; **if you add a field to `EventRecord`, update
that function too** or it will be silently dropped.

Key fields: `ticker`, `accession`, `filing_date`, `acceptance_utc`,
`acceptance_et`, `session_bucket` (PRE/RTH/POST), `items[]`, `report_date`,
`event_types[]`, `confounded_by_earnings`, `market_cap`, `cap_bucket`,
`exec_*` (13 fields incl. `exec_severity`, `exec_is_senior_departure`),
`plan_*` (9 fields incl. `plan_charge_usd`, `plan_savings_usd`,
`plan_payback_years`), novelty fields (`novelty_score`, `is_repeat`,
`report_lag_days`, `max_prior_similarity`, `self_reported_repeat`).

### Trade CSV — `data/results/backtest_trades.csv`

36 columns per simulated position. Beyond the obvious P&L fields, the ones
that carry the research content are `priced_from`
(`market`/`model`/`mixed`/`stock_only`), `entry_iv`, `exit_iv`,
`implied_move`, `actual_move`, `vol_risk_premium`, `capital_at_risk`,
`settled_at_expiry`, and `reason` (why the event qualified).

---

## 6. Deliberate choices — do not "fix" these

Each costs apparent performance on purpose. Reversing any one will make
results look better and be wrong.

1. **Intraday filings enter at the close, not the open.**
   `determine_entry` in `backtest.py`. With daily bars there is no honest
   way to claim a fill moments after a filing hit. Pinned by
   `test_intraday_enters_at_the_close_not_the_open`.

2. **Exits never reuse entry IV.** Where a contract has no traded bar at
   exit, vol is assumed reverted to the pre-event baseline — the IV crush
   applied in full. See `_exit_leg_premium`. Carrying entry vol forward
   would hand every long-option trade a free profit.

3. **Short premium is charged a margin proxy, not the credit received.**
   `_capital_at_risk` uses 20% of underlying notional × 0.5. Reporting
   return on premium collected would flatter short vol enormously. Pinned by
   `test_credit_structure_uses_a_margin_proxy_not_the_credit`.

4. **Half-spreads are paid twice** (entry and exit), default 4% of premium
   floored at $0.02, plus $0.65/contract.

5. **Unknown market caps are kept, not dropped.** `Strategy._cap_ok`.
   Dropping them would discard the smallest, least-covered issuers — the
   actual population of interest. They are tagged `cap_unknown`.

6. **Delisted/acquired tickers stay in the universe.** Removing them is
   survivorship bias exactly where it hurts most.

7. **Earnings-confounded filings excluded by default.** MongoDB's CEO exit
   was co-filed with preliminary results (Items 2.02 + 5.02); that reaction
   is not attributable. Toggle with `--include-earnings-confound`.

8. **Item 2.02 is absent from `PLAN_CANDIDATE_ITEMS`.** An earnings release
   mentions efficiency work in passing and carries financial statements
   whose tables yield spurious multi-billion-dollar "charges". This was a
   real observed bug, not a hypothetical.

---

## 7. Bugs already found and fixed — regression risks

Both silently corrupted the event set rather than raising.

**Item title leakage.** The official Item 5.02 title is "Departure of
Directors or Certain Officers; Election of Directors; Appointment of Certain
Officers; …" — it contains both "Departure" and "Appointment", so parsing a
raw section made *every* 5.02 filing look like a departure **and** a
succession. Fixed by `strip_item_title`, which matches the official title on
a punctuation-insensitive normalization. Guarded by
`test_title_verbs_do_not_create_phantom_events`.

**Disagreement false positives.** Item 5.02(a) requires issuers to state
whether a departure involved a disagreement, so nearly every clean
resignation contains the word inside a denial. The first implementation
enumerated denial phrasings and missed the most common one — "is **not due
to** any disagreement" — flagging routine resignations and adding 0.20 to
severity. On MongoDB alone it marked 2 of 8 departures as disagreements and
made a false positive the **highest-severity event in the set** (0.73 → 0.53
after fixing).

Now inverted: find the keyword, look for a negation cue in its sentence.
Two details real filings require, both guarded by tests:
- whitespace is normalized first, because filing HTML flattens with newlines
  mid-sentence and a line break treated as a sentence boundary severs "did
  not involve any" from the "disagreement" it negates;
- a sentence prefix under 25 chars means the boundary was an abbreviation's
  period ("Mr."), so the lookback widens instead of trusting it.

Related trap already handled: `_affirmative_match` discards "terminated for
cause" when preceded by conditional language, because that phrase lives in
the *incoming* officer's clawback clause, not the departure.

---

## 8. Measured event-set composition

From `data/events/universe_events_wide.json` — 1,070 events, 86 issuers,
Items 5.02/2.05/2.06/7.01/8.01, 2019-01-02 → 2026-10-02. (The narrower
`universe_events.json` is also committed: 1,054 events, same window.)

| | count | share |
|---|---|---|
| senior departures (CEO/CFO/President/COO) | 761 | 72% |
| …clearing severity 0.35 | 481 | |
| CEO departures | 350 | |
| restructuring plans | 113 | 11% |
| …disclosing both a charge and savings | 12 | |
| scoring as recycled disclosure | 204 | 19% |

- **Session mix:** POST 800 (75%), PRE 147 (14%), RTH 123 (11%). Favourable —
  89% give a clean next-session entry.
- **Forced exits are rare:** 15 (1.5%) admit cause/investigation, 7 (0.7%) an
  actual disagreement. Successor named in 64%; 15% framed as retirement.
- **Severity:** median 0.32, max 0.82; only 20 events exceed 0.60.
- **Filing lag:** 21% filed the same day as the event reported; **52%** three
  or more days later. (An earlier commit message said 45% — that was an
  arithmetic slip; 52% is correct.)

---

## 9. Known gaps — the actual refinement targets

Ordered by how much they limit the conclusions.

1. **The cost-now/savings-later test rests on 12 observations.** Of 113
   plans, 73 disclose a charge, 17 disclose annualized savings, **12
   disclose both**. Not measurable at statistical scale on this universe.
   **Do not read a mean over twelve trades as evidence.** See 2 and 2b below
   for what has already been tried and the reframing that looks better.

2. **DONE — the wider plan sweep did not fix gap 1.** The Items 7.01/8.01
   sweep has been run and committed as `data/events/universe_events_wide.json`
   (1,070 events). Plan filings rose 97 → 113 and plans disclosing both a
   charge and savings rose **10 → 12**. Companies do not put savings figures
   in 8-Ks and no item-code widening changes that. Remaining routes: extend
   the window before 2019, or parse the following 10-Q/10-K MD&A where
   savings against restructuring charges are actually quantified.

   Note `trust_tables` is only set for filings actually filed under
   2.05/2.06, so 7.01/8.01 money extraction stays conservative — worth
   reviewing whether that is too strict.

2b. **The premise of idea 2 is not supported by the filings.** Of the 12
   measurable plans, **10 claim payback inside one year** (median 4 months).
   Only RH (7.5y) and Wayfair (1.6y) disclose the cost-now/savings-later
   asymmetry the collar was designed for. The more promising inversion:
   test whether *implausibly fast* promised paybacks are the tradable
   signal. This reframing has not been implemented.

3. **Novelty ignores news.** Prior-coverage evidence is the strongest of its
   four signals and requires `MASSIVE_API_KEY`. Currently scored from filing
   text and EDGAR report-lag only. The weights in `assess_novelty` are
   hand-set and **have never been calibrated against outcomes** — that is
   the single largest piece of unvalidated judgment in the codebase.

4. **`score_exec_severity` weights are also hand-set.** Defensible ordering
   (seniority base, +cause, +disagreement, +abrupt, −successor, −retirement)
   but not fitted. Worth regressing against realized abnormal returns once
   prices are available, rather than trusting the priors.

5. **Daily option bars, not quotes.** Massive bars are session aggregates;
   the 4% half-spread is an assumption. Validate against real OPRA bid/ask
   via `databento_opra.py` before trusting any result. Note `CostModel`
   spread is flat across names — small-cap spreads are far wider than
   mid-cap, so this likely *understates* costs on the smallest issuers.

6. **No multiple-testing correction.** Six strategies × three holding
   periods × several splits is ~50 comparisons. The report gives per-strategy
   t-stats and bootstrap CIs but no family-wise adjustment. Add one before
   calling anything significant.

7. **No overlapping-position handling.** Each event is simulated
   independently at fixed notional; concurrent positions in the same name or
   sector are not netted, and there is no portfolio-level sequencing or
   capital constraint.

8. **`OLPX` and `NOVA` fail ticker→CIK resolution** (absent from SEC's
   `company_tickers.json`). Minor, but a CIK-override map would recover them
   and any other renamed issuer.

9. **Person extraction is imperfect** — sometimes a surname only or a first
   name. Cosmetic; affects audit readability, not selection.

10. **No intraday data path.** The 11% RTH filings are the weakest cases.
    Minute bars (Databento equities are cheap) would let those be entered
    near the filing timestamp instead of at the close, and would also
    sharpen the PRE/POST gap measurement.

---

## 10. Cost safety — read before touching Databento

The user has roughly **$225 of Databento credits**, not a plan. OPRA is the
highest-volume feed in existence; one careless full-chain request can exceed
the entire balance. `databento_opra.py` enforces, and these guards should not
be loosened:

- `metadata.get_cost()` is consulted **before** any data request, checked
  against a persistent ledger (`budget.py`) with both a total and a per-run
  cap;
- only explicitly named contract symbols are requestable — parent symbology
  (`MDB.OPT`) is unreachable by construction;
- only coarse schemas allowed (`ohlcv-1d`, `bbo-1m`, `cbbo-1s`, …);
  `mbp-1`/`trades`/`mbo` are rejected before a client is even constructed;
- `validate_contracts()` defaults to `dry_run=True`, so calling it prices a
  query without buying it;
- every fetched byte is cached to parquet, so a re-run costs nothing.

Massive turned out to be Polygon-compatible and carries expired option
contracts plus per-contract bars, so it can serve the whole backtest and the
Databento credits can stay in reserve for validation.

---

## 11. Reproducibility

Every HTTP response and API payload is cached to disk permanently (filings
are immutable once accepted). A full re-run of the committed event set is
**3,430 cache hits, 0 network calls**. `EIGHTK_OFFLINE=1` turns a cache miss
into an error, which is how a frozen run is enforced.

`data/cache/` (~25 MB) and `data/results/` are gitignored; `.env` is
gitignored and no credential appears in any commit.

Note: SEC returns a rate-limit page to clients that do not self-identify. Set
`SEC_USER_AGENT="Your Name you@domain.com"`. The committed default is a
placeholder.

---

## 12. The one thing most likely to be misread

**The opening gap is not capturable.** When a filing lands pre-market or
after the close — 89% of this sample — entry is at the already-gapped open.
These strategies trade **post-gap drift**, not the initial reaction. A long
put bought after a CEO-exit gap loses to IV crush and spreads unless the
stock keeps falling.

This is asserted directly in
`tests/test_integration.py::test_long_put_profits_only_on_post_entry_drift`,
which checks the put is profitable at −2%/session drift and unprofitable at
+0.1%/session. Any result that appears to capture the gap itself indicates a
timing bug, not an edge.
