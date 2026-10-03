# Item 2.02 Options Strategy (disclosure polarity)

## What changed

The strategy no longer holds stock for a fixed 5 days. It:

1. Loads Massive **Item 2.02** filings + **8-K disclosure taxonomy**
   (`primary_category` / `tertiary_category`).
2. Maps taxonomy → **polarity**:
   - **positive** (e.g. `acquisition_agreement`, `share_repurchase_program`,
     `cfo_appointment`) → buy **calls**
   - **negative** (e.g. `material_litigation`, `cfo_departure`, impairments)
     → buy **puts**
   - **unsigned** earnings (`financial_results` / `quarterly_earnings`) →
     polarity from the overnight **gap** (up → calls, down → puts)
3. Trades **synthetic ATM options** (Black–Scholes marks on Webull
   underlyings). Webull’s starter kit has no options feed; this keeps
   backtests runnable on a Stocks-only Massive key.
4. Exits on **rules**, not a calendar lag:
   - take-profit / stop-loss on premium
   - underlying invalidation
   - dead-money / IV-crush exit after scaled `min_hold`
   - max hold / near expiry

## Time horizon scaling (filing → market gap)

Holds and ATR length are specified in **trading sessions**, then converted to
bars from `WEBULL_TIMESPAN` / `-t` so the economic clock stays stable:

| Timespan | Bars / session | `max_hold_sessions=5` → bars |
| --- | ---: | ---: |
| `D` | 1 | 5 |
| `M60` | ~6.5 | 33 |
| `M5` | 78 | 390 |
| `M1` | 390 | 1950 |

Defaults aim at a multi-session residual gap after the print
(`min_hold_sessions=2`, `max_hold_sessions=5`). For a **short** post-filing
gap on intraday data, cap with hours:

```bash
# hourly path — same 2–5 session thesis
python run.py --track item_202_results_ops DDOG -t M60 -c 1200

# first ~3 RTH hours only (gap capture)
python run.py --track item_202_results_ops DDOG -t M5 -c 1200 -p max_hold_hours=3,max_hold_sessions=5
```

Entry uses the **first bar of the trade date** only, so minute bars still
measure the overnight gap — not bar-to-bar noise.

## Backtest notes

```bash
# from repo root
python run.py --track item_202_results_ops
python run.py --track item_202_results_ops DDOG,PLTR -c 1200
python run.py --track item_202_results_ops DDOG -t M60 -c 1200

# refresh Massive event cache
uv run --project infrastructure python tracks/item_202_results_ops/scripts/fetch_item_202_events.py --symbols DDOG,RBLX --gte 2023-01-01
```

Key params (also via ``WEBULL_STRATEGY_PARAMS``):

| Param | Default | Meaning |
| --- | --- | --- |
| `min_hold_sessions` / `max_hold_sessions` | 2 / 5 | Hold window in RTH sessions (scaled → bars) |
| `atr_sessions` | 14 | ATR lookback in sessions (scaled → bars) |
| `max_hold_hours` | 0 (off) | Optional intraday cap on max hold |
| `min_hold_bars` / `max_hold_bars` / `atr_period` | 0 | Explicit bar overrides (when > 0) |
| `premium_pct` | 0.02 | Portfolio fraction risked per option ticket |
| `take_profit` / `stop_loss` | 0.60 / 0.40 | Premium return exits |
| `dead_money_atr` | 0.25 | Exit if follow-through < this · ATR after min hold |
| `invalidate_atr` | 1.0 | Exit if underlying moves against by this · ATR |
| `expiry_weeks` | 4 | Synthetic option tenor |
