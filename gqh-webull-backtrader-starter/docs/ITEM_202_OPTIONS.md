# Item 2.02 Options-Impact Strategy

## Why Item 2.02 matters for options

Form 8-K **Item 2.02** ("Results of Operations and Financial Condition") is how
issuers furnish earnings releases to the SEC. Those filings coincide with
**scheduled earnings events** that dominate single-name options markets:

| Phase | Typical options effect | Equity proxy in this strategy |
| --- | --- | --- |
| Into the print | IV expands (implied move ↑) | Not traded (no options feed in Webull starter) |
| At the print | Large overnight gap = realized move | Measured as open vs prior close / ATR |
| After the print | IV crush + PEAD drift | `mode=momentum` follows the gap for `hold_bars` |
| After oversized gaps | Mean reversion / short-vol edge | `mode=fade` fades the gap |

Because this repository's Webull backtester trades **equities only**, the
strategy measures the **realized event move** (straddle payoff proxy) and
trades the underlying with a PEAD-style rule that options desks use when
choosing directional calls/puts vs short volatility.

## Data flow

1. **Massive** `GET /stocks/filings/8-K/vX/text` → keep filings whose
   `items_text` contains **Item 2.02**.
2. Optional **Benzinga earnings** enrichment (schedule time → BMO/AMC,
   EPS/revenue surprise) when your Massive plan includes it.
3. Events are cached to JSON (`MASSIVE_EVENTS_CACHE`) for reproducible runs.
4. **Webull** daily (or intraday) bars drive Backtrader fills via the existing
   `examples/backtest/main.py` pipeline.

## Run

```bash
cd gqh-webull-backtrader-starter

# Offline / sample events (no Massive key required)
# MASSIVE_EVENTS_CACHE defaults to examples/data/item_202_events_sample.json
python ../../run.py AAPL --strategy item_202_options --count 1200 \
  --params hold_bars=5,min_gap_atr=0.5,mode=momentum

# Live Massive pull (set MASSIVE_API_KEY in examples/backtest/.env)
uv run python examples/scripts/fetch_item_202_events.py \
  --symbols AAPL,MSFT --gte 2023-01-01 \
  --out examples/data/item_202_events.json
```

`.env` sketch:

```dotenv
WEBULL_STRATEGY=item_202_options
WEBULL_STRATEGY_PARAMS=hold_bars=5,min_gap_atr=0.5,mode=momentum,allow_short=true
WEBULL_SYMBOLS=AAPL,MSFT
WEBULL_TIMESPAN=D
WEBULL_COUNT=1200
MASSIVE_API_KEY=your_massive_key
MASSIVE_EVENTS_CACHE=examples/data/item_202_events.json
```

## Parameters

| Param | Default | Meaning |
| --- | --- | --- |
| `hold_bars` | 5 | Sessions to hold after the event entry |
| `atr_period` | 14 | ATR lookback for gap normalization |
| `min_gap_atr` | 0.5 | Minimum \|gap\|/ATR to trade |
| `mode` | momentum | `momentum` (PEAD) or `fade` |
| `allow_short` | true | Permit short entries on down gaps |
| `min_surprise_pct` | 0 | Min \|EPS surprise %\| when available |
| `require_surprise` | false | Skip events lacking Benzinga surprise |
| `target_pct` | 0.2 | Position weight via `order_target_percent` |

## Interpreting results for options

After each run, the strategy logs **event analytics**: gap %, gap/ATR, EPS
surprise, and action taken. Use that table to reason about:

- Whether realized moves were large enough to beat a typical implied move
  (long straddle would have won).
- Whether post-gap drift continued (`momentum` wins) or reversed (`fade` wins /
  short-vol friendly).
- Surprise magnitude as a filter for directional options overlays.
