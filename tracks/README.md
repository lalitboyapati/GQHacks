# Research tracks

Each directory here is an independent **8-K research track**. Contributors
share `infrastructure/` for data, brokerage simulation, metrics, and charts.

| Track | 8-K focus | Status |
| --- | --- | --- |
| [`item_202_results_ops`](./item_202_results_ops/) | Item 2.02 Results of Operations → synthetic calls/puts | Active |
| [`item_101_material_agreements`](./item_101_material_agreements/) | Item 1.01 / 1.02 material agreements | Stub |
| [`item_201_acquisitions`](./item_201_acquisitions/) | Item 2.01 completion of acquisition/disposition | Stub |
| [`item_502_officer_changes`](./item_502_officer_changes/) | Item 5.02 officer/director changes | Stub |
| [`item_701_reg_fd`](./item_701_reg_fd/) | Item 7.01 Regulation FD | Stub |
| [`_template`](./_template/) | Blank starter for a new track | Template |

## Required files

| File | Purpose |
| --- | --- |
| `STRATEGY.md` | Human-readable thesis, data, signal, exits, risks |
| `strategy.py` | Must export `STRATEGY_CLASS = YourBtStrategy` |

## Optional files

- `scripts/` — fetch/cache Massive events for this Item
- `data/` — event caches (JSON); keep secrets out
- `tests/` — track-specific unit tests
- `.env` — track overrides (symbols, params); shared keys stay in `infrastructure/backtest/.env`

## Run a track

```bash
python run.py --track item_202_results_ops
python run.py --track item_202_results_ops DDOG,PLTR -c 1200 -p take_profit=0.5
```

## Conventions

1. Do **not** copy `webull_bt` into your track — import it from infrastructure.
2. Keep strategy logic and narrative in the track; keep engine bugs fixed upstream.
3. Name tracks `item_<SEC>_short_slug` when they map to a Form 8-K item.
4. Update this table when you add a track.
