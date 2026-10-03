# 8-K Disclosure Advantage — Options Research

> Picking this up for refinement? Read **[HANDOFF.md](./HANDOFF.md)** first:
> current state, data contracts, deliberate choices not to "fix", bugs
> already found, and the ranked list of open gaps.

Does an SEC Form 8-K carry information the options market has not yet
priced — and if so, can it be traded?

This subproject tests that question on **options specifically**, on
**smaller companies** where analyst coverage is thin, across three
disclosure families.

## The three ideas under test

| # | Strategy | Question | Structure |
|---|----------|----------|-----------|
| 1 | `exec_put` | A senior officer leaves (Item 5.02). If I had seen the 8-K when MongoDB's CEO resigned and acted on it, would I have made money? | Long put |
| 2 | `efficiency_collar` | A company announces an "efficiency plan"; the 8-K reveals large upfront costs against savings years away. Does the market take time to price that mismatch? | Long stock + long put + short call |
| 3 | `novelty_shortvol` | Is this actually news, or the same announcement again? Do options stay expensive relative to the move that actually follows? | Short strangle |
| 1+2 | `combo` | The requested combination: restructuring filings routed by whether they genuinely revealed anything. | Collar when novel, short strangle when repeat |

Two stock-only controls (`stock_long`, `stock_short`) run on the same event
sets, because an options result only matters if it beats simply trading the
underlying.

## Why the event layer uses SEC EDGAR

Massive's parsed `Filing8K` rows carry only `items_text` and a filing
*date*. Two fields this research depends on are missing from every vendor
feed and come from EDGAR instead:

- **`acceptanceDateTime`** — the exact publication instant. It decides
  whether a disclosure was tradable at the open, at the close, or not until
  the next session. Verified as true UTC against the filing-index page
  (`13:31:10Z` renders as `08:31:10` ET).
- **The full filing text** — needed to tell a genuine revelation from a
  re-filed press release, and to pull charge and savings figures out of a
  restructuring disclosure.

Massive then supplies what EDGAR has not: daily bars, the historical option
chain *including expired contracts*, per-contract option bars, timestamped
news for the novelty test, and market caps for universe selection.

## Design decisions that protect the result

Event studies on one disclosure type produce tens of trades, not thousands,
and at that size it is easy to manufacture an edge by accident. The
following choices all cost apparent performance on purpose.

**Entry timing is pessimistic.** A filing accepted pre-market is entered at
that session's open; after the close, at the *next* session's open. A filing
accepted *during* the session is entered at that day's **close** — with
daily bars there is no honest way to claim a fill moments after it hit, and
assuming one would hand the backtest the very reaction it is measuring.

**Exits never reuse the entry volatility.** Where a contract traded, the
exit is marked from its real bar. Where it did not, implied vol is assumed
to have reverted to its pre-event baseline — i.e. the post-event IV collapse
is applied in full. Carrying the entry vol forward would hand every
long-option trade a free profit.

**Option prices come from real bars wherever they exist.** A traded premium
is inverted into an implied vol against that session's underlying reference
price, then re-priced at the actual entry spot. Market data sets the
volatility; the model only transports the premium across the timing gap.
Legs with no tradable bar are priced from a volatility estimate and tagged
`model`, and every report shows what share of fills were real.

**Short volatility is charged real margin.** A naked strangle's capital is
approximated as 20% of underlying notional, not the credit received —
reporting return on premium collected would flatter it enormously.

**Spreads are paid twice.** A half-spread (default 4% of premium, floored at
$0.02) is charged adversely on entry and again on exit, plus $0.65 per
contract commission.

**Earnings-confounded filings are separated.** MongoDB's CEO departure was
filed alongside preliminary Q3 results (Items 2.02 + 5.02). That reaction
cannot be attributed to the departure, so such filings are excluded by
default and reportable separately via `--include-earnings-confound`.

**Delisted names are kept.** Excluding them would introduce survivorship
bias exactly where it hurts: a company whose CEO left and which then
collapsed is the observation the strategy most needs to see.

## What the event set actually contains

Measured over the committed 1,054-event set (86 issuers, Items 5.02/2.05/2.06,
2019-01-02 to 2026-10-02):

| | count | share |
|---|---|---|
| senior departures (CEO/CFO/President/COO) | 761 | 72% |
| ...clearing the 0.35 severity threshold | 481 | |
| of which CEO | 350 | |
| restructuring plans | 97 | 8% |
| filings scoring as recycled disclosure | 201 | 19% |

**Timing is favourable.** 75% of filings are accepted after the close and
14% pre-market — both give a clean next-session entry. Only 11% land
intraday, where entry is forced to that day's close.

**Genuinely forced exits are rare.** Just 15 filings (1.5%) admit cause or
an investigation and 7 (0.7%) an actual disagreement. Succession is named in
64%. Severity is median 0.32, max 0.82, and only 20 events exceed 0.60 — so
the "dramatic exit" subsample is small by construction, not by filtering.

## Known limitations

- **The cost-now/savings-later comparison rests on ~10 observations.** Of 97
  restructuring plans, 66 (68%) disclose a charge but only 13 (13%) disclose
  annualized savings and just **10 (10%) disclose both**. The explicit
  mismatch behind the efficiency-plan hypothesis is therefore not directly
  measurable at statistical scale on this universe. Widen it, extend the
  window, or fall back to charge-size and horizon as the signal — but do not
  read a mean over ten trades as evidence.
- **The opening gap is not capturable.** When a filing lands pre-market or
  after the close, entry is at the already-gapped open. These strategies
  therefore trade *post-gap drift*, not the initial reaction. This is the
  single most important thing to understand about the results, and it is
  asserted directly in `tests/test_integration.py`.
- **Many restructuring 8-Ks are filed intraday**, forcing the conservative
  close entry and weakening that strategy's measurable edge.
- **Daily option bars, not quotes.** Massive bars are session aggregates.
  Use the Databento path below to re-price promising signals on true OPRA
  bid/ask before trusting any of it.
- **Novelty currently ignores news.** Without `MASSIVE_API_KEY` the score
  uses filing text and EDGAR report-lag only; prior-coverage evidence is the
  strongest of its four signals and needs the key.

## Setup

```bash
cd gqh-8k-options-research
uv venv --python 3.11
uv pip install -e .
cp .env.example .env     # then add MASSIVE_API_KEY
```

Set `SEC_USER_AGENT` to `"Your Name you@domain.com"` — the SEC asks
automated clients to identify themselves, and returns a rate-limit page to
clients that do not.

## Running

```bash
# 1. Build the event set (EDGAR only; works with no API key at all)
python scripts/fetch_events.py --symbols MDB --start 2019-01-01
python scripts/fetch_events.py --universe default --start 2019-01-01

# 2. Backtest it (needs MASSIVE_API_KEY for prices and chains)
python scripts/run_backtest.py --hold 5 --hold 10 --hold 21

# Narrow the cut
python scripts/run_backtest.py --strategies exec_put,stock_short --max-cap 10e9
python scripts/run_backtest.py --spread-pct 0.08    # stress wider spreads
```

Events are written to `data/events/events.json` as flat JSON so every
classification can be audited by hand before any money logic touches it.
Results land in `data/results/`.

Every HTTP response and API payload is cached to disk, so a re-run issues no
network calls and results are reproducible. `EIGHTK_OFFLINE=1` turns a cache
miss into an error, which is how a frozen run is enforced.

## Validating on real OPRA quotes (Databento)

Databento is deliberately *not* on the main path. It holds true OPRA bid/ask,
which is what the modeled spread assumption should be checked against — but
OPRA is the highest-volume feed in existence and the available credit is
finite, so `eightk/databento_opra.py` enforces:

- `metadata.get_cost()` is consulted **before** any data request, and the
  quote is checked against a persistent ledger (`eightk/budget.py`) carrying
  both a total and a per-run cap;
- only explicitly named contract symbols are requestable — parent symbology
  (`MDB.OPT`) would pull every strike and expiry and is unreachable;
- only coarse schemas are permitted (`ohlcv-1d`, `bbo-1m`, …); `mbp-1` and
  `trades` are rejected before a client is even constructed;
- `validate_contracts()` defaults to `dry_run=True`, so calling it prices
  the query without buying it.

## Layout

```
eightk/
  config.py           environment, paths, budget caps
  http.py             rate-limited, permanently disk-cached HTTP
  edgar.py            8-K discovery: item codes, acceptance instants, text
  classify.py         Item 5.02 executive changes; Item 2.05/2.06 plans
  novelty.py          repeat-versus-new disclosure scoring
  events.py           joins filings, text, news, and market caps
  massive_src.py      prices, option chains, option bars, news
  prices.py           daily series with a data-derived trading calendar
  options_model.py    Black-Scholes, IV inversion, trade structures
  options_book.py     contract resolution and leg pricing with costs
  backtest.py         entry/exit timing and P&L accounting
  strategies.py       the four strategies plus stock controls
  report.py           t-stats, bootstrap intervals, split tables
  budget.py           spend ledger with a hard ceiling
  databento_opra.py   budget-guarded OPRA validation
  universe.py         the smaller-company universe
scripts/
  fetch_events.py     build and save the event set
  run_backtest.py     run strategies over a saved event set
tests/                68 tests
```

## Reading the output

`report.py` prints per-strategy mean return on capital with a t-statistic, a
bootstrap confidence interval, hit rate, and the share of fills that came
from real option bars — then splits by market-cap bucket, filing session,
and price source.

Treat any strategy with fewer than 8 trades, a bootstrap interval spanning
zero, or a low market-priced share as a hypothesis rather than a finding.
The report flags all three automatically.
