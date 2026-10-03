# Strategy overview — Physical Facility Disruptions

**Owner:** TBD  
**8-K Item(s):** typically **8.01** (Other Events), sometimes **1.05** / **7.01** /
**2.06** when a fire, explosion, outage, or plant shutdown is furnished  
**Status:** draft — Massive fetch + FIRMS labeling live; premium backtest next  
**Engine:** `event` (intended: `infrastructure/eightk` short-premium structures)

## Thesis

Disruption 8-Ks (facility fire, explosion, major outage, plant halt) are often
vague (“temporary,” “no material impact”). Markets still tend to bid up implied
vol. **NASA FIRMS** thermal detections can independently check whether the site
stayed hot for days or the spike was brief.

**Claim:** disruption filing + **no persistent** thermal anomaly → implied move
exceeds realized move → **sell premium** (covered call or cash-secured put).
When the anomaly **persists for days**, **skip** (control group).

| Group | Satellite label | Action |
| --- | --- | --- |
| **A — brief / non-persistent** | &lt; `persist_days` distinct FIRMS hit-days (or none) | sell premium (CC or CSP) |
| **B — persistent** | ≥ `persist_days` distinct hit-days near the site | skip / control |
| **unknown** | no site coords or no FIRMS coverage | exclude |

No long put in this track’s menu: the clean trade under over-reaction is
**premium-selling**.

## Data

### Filings (Massive)

Same pull path as Item 2.02: `list_stocks_filings_8k_text`, then keyword filter
for physical disruptions (+ optional disclosures enrich).

```bash
# Massive only
uv run --project infrastructure python tracks/physical_facility_disruption/scripts/fetch_disruption_events.py \
  --symbols X,NUE,CLF --gte 2022-01-01

# + site map + FIRMS labels (needs FIRMS_MAP_KEY)
uv run --project infrastructure python tracks/physical_facility_disruption/scripts/fetch_disruption_events.py \
  --symbols X,NUE,CLF --gte 2023-01-01 \
  --sites tracks/physical_facility_disruption/data/sites.example.json \
  --firms --persist-days 3
```

Output: `data/events/disruption_events.json`

### FIRMS (NASA)

- Free **MAP_KEY**: https://firms.modaps.eosdis.nasa.gov/api/map_key/  
  Set `FIRMS_MAP_KEY` (or `MAP_KEY`) in `infrastructure/backtest/.env` or track `.env`
- Area CSV API, ~3–4h latency after a pass; VIIRS ~375 m, ~2 looks/day
- Client: `infrastructure/webull_bt/firms.py`
- Site coords: `data/sites.example.json` (replace with real plant lat/lon)

### Limitations (FIRMS)

- Algorithms are **calibrated for wildfire**; industrial combustion with unusual
  spectral signatures can be **misclassified or missed**
- Normal steel-mill / refinery heat is often filtered, but elevated damage-level
  output can still register — treat labels as noisy external evidence
- NRT products are best for recent windows; deep history may need SP sources
  (`FIRMS_SOURCE=…`)

## Signal

1. Disruption 8-K passes Massive text filter.  
2. Join FIRMS near `site_lat`/`site_lon` for `persist_days` after filing.  
3. **Group A (`brief`)** → CSP or covered call.  
4. **Group B (`persistent`)** → no trade (control).  
5. **`unknown`** → exclude until site + sat coverage exist.

## Exits & risk

- Session holds (sweep 5 / 10 / 21) once `run_backtest.py` is wired to eightk  
- Short premium: capital on notional; half-spread both ways  

## Backtest notes

```bash
uv run --project infrastructure pytest tracks/physical_facility_disruption/tests -q
python tracks/physical_facility_disruption/scripts/describe_groups.py \
  --events tracks/physical_facility_disruption/data/events/disruption_events.json
python run.py --track physical_facility_disruption --engine event   # stub until premium path lands
```

| Param | Default | Meaning |
| --- | --- | --- |
| `persist_days` | 3 | distinct FIRMS hit-days → `persistent` |
| `radius_km` | 5 | hotspot distance gate around site |
| `structure` | `csp` | planned: `csp` or `covered_call` |

## Open work

1. ~~Massive disruption fetch~~ / ~~FIRMS client~~  
2. Real plant geocodes (replace `sites.example.json`)  
3. `scripts/run_backtest.py` — short premium on group A via eightk  
4. Report implied−realized and P&amp;L **by group**
