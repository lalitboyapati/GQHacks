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

## Run

```bash
cd gqh-webull-backtrader-starter
uv run python examples/backtest/main.py
```

Refresh events (disclosures included by default):

```bash
uv run python examples/scripts/fetch_item_202_events.py \
  --symbols DDOG,RBLX,SHOP,SOFI,U,UBER,PLTR,AI \
  --gte 2023-01-01 \
  --out examples/data/item_202_events_high_vol.json
```

## Key params

| Param | Meaning |
| --- | --- |
| `premium_pct` | Portfolio fraction risked per option ticket |
| `take_profit` / `stop_loss` | Premium return exits |
| `max_hold_bars` / `min_hold_bars` | Time bounds |
| `dead_money_atr` | Exit if follow-through &lt; this · ATR after min hold |
| `invalidate_atr` | Exit if underlying moves against by this · ATR |
| `expiry_weeks` | Synthetic option tenor |
