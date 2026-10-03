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
   - dead-money / IV-crush exit after `min_hold_bars`
   - max hold / near expiry

## Backtest notes

```bash
# from repo root
python run.py --track item_202_results_ops
python run.py --track item_202_results_ops DDOG,PLTR -c 1200

# refresh Massive event cache
uv run --project infrastructure python tracks/item_202_results_ops/scripts/fetch_item_202_events.py --symbols DDOG,RBLX --gte 2023-01-01
```

Key params (also via ``WEBULL_STRATEGY_PARAMS``):

| Param | Default | Meaning |
| --- | --- | --- |
| `premium_pct` | 0.02 | Portfolio fraction risked per option ticket |
| `take_profit` / `stop_loss` | 0.60 / 0.40 | Premium return exits |
| `max_hold_bars` / `min_hold_bars` | 10 / 2 | Time bounds |
| `dead_money_atr` | 0.25 | Exit if follow-through < this · ATR after min hold |
| `invalidate_atr` | 1.0 | Exit if underlying moves against by this · ATR |
| `expiry_weeks` | 4 | Synthetic option tenor |
