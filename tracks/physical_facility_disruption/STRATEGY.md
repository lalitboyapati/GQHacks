# Strategy overview — Physical Facility Disruptions

**Owner:** TBD  
**8-K Item(s):** typically **8.01** (Other Events), sometimes **2.05** / **2.06** /
plant outage language  
**Status:** active — Webull/Backtrader premium-selling on FIRMS-`brief` events  
**Engine:** `backtrader` (`webull_bt` + synthetic options)

## Thesis

Disruption 8-Ks often read “temporary / no material impact,” but options can
still price a large move. **NASA FIRMS** checks whether the site stayed hot.

**Claim:** filing + **brief** thermal footprint → implied overstates realized →
**sell premium** (cash-secured put default, or covered call).  
**Persistent** anomaly → skip (control). **Unknown** (no site) → skip.

## Pipeline

1. `scripts/fetch_disruption_events.py` — Massive 8-Ks + Nominatim geocode + FIRMS  
2. Events JSON → `data/events/disruption_events.json`  
3. `strategy.py` — Backtrader: on trade date open, if `facility_group=brief`, sell
   synthetic CSP (or covered call)

## Signal / exits

| Group | Action |
| --- | --- |
| `brief` | Sell ATM-ish put (CSP) or covered call |
| `persistent` / `unknown` | Log + skip |

Exits (short premium): take-profit on % of credit, stop on adverse premium,
underlying invalidation, scaled max hold, near-expiry. Entry IV is stressed vs
ATR so calm post-event paths model an IV crush for the short.

## Backtest

```bash
# refresh events (Massive + geocode + FIRMS)
uv run --project infrastructure python tracks/physical_facility_disruption/scripts/fetch_disruption_events.py \
  --symbols STLD,PSX,DOW,FCX --gte 2019-01-01 --firms

# run Webull backtest (symbols should include event tickers)
python run.py --track physical_facility_disruption PSX,STLD -c 1200

# covered call instead of CSP
python run.py --track physical_facility_disruption PSX,STLD -c 1200 -p structure=covered_call
```

| Param | Default | Meaning |
| --- | --- | --- |
| `structure` | `csp` | `csp` or `covered_call` |
| `trade_groups` | `brief` | which `facility_group` values to trade |
| `event_iv_mult` | 1.35 | entry IV = ATR vol × mult (crush vs mark) |
| `min_hold_sessions` / `max_hold_sessions` | 2 / 5 | scaled to `-t` bars |
| `take_profit` / `stop_loss` | 0.50 / 1.00 | vs credit received |
| `premium_pct` | 0.02 | sizing budget |

Env: `FACILITY_EVENTS` path override; `FIRMS_MAP_KEY` for fetch; Massive key as usual.

## Limitations

- Synthetic options (no OPRA) — good for hypothesis tests, not fill realism  
- FIRMS is wildfire-tuned; industrial heat can be missed/misclassified  
- Geocode is city-level Nominatim, not exact plant footprints  
- Sample of true disruption 8-Ks is small — treat results as exploratory
