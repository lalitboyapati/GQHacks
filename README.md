# Gator Quant Hacks (GQHacks)

Multi-person workspace for **Form 8-K event strategies** with one shared
Webull + Backtrader backtesting stack.

## Layout

```
GQHacks/
├── infrastructure/          # Shared backtest engine (do not fork per person)
│   ├── webull_bt/           # Feeds, broker, Massive helpers, options sim, reports
│   ├── backtest/            # Common backtest runner + shared .env
│   ├── live/                # Optional simulated-live / broker wiring
│   ├── examples/strategies/ # Reference demos (dual_ma, portfolio)
│   └── docs/                # Engine usage docs
├── tracks/                  # One folder per researcher / 8-K topic
│   ├── _template/           # Copy this to start a new track
│   ├── item_202_results_ops/
│   ├── item_101_material_agreements/
│   ├── item_201_acquisitions/
│   ├── item_502_officer_changes/
│   └── item_701_reg_fd/
└── run.py                   # One CLI for every track
```

Each **track** owns:
- `STRATEGY.md` — thesis and approach (the “overall view”)
- `strategy.py` — Backtrader `STRATEGY_CLASS` (required to run)
- optional `scripts/`, `data/`, `tests/`, track-local `.env`

Everyone shares the same backtester under `infrastructure/`.

## Quickstart

```bash
cd infrastructure
uv sync

# Shared credentials (gitignored)
cp backtest/.env.example backtest/.env
# fill WEBULL_* and MASSIVE_APP_KEY

cd ..
python run.py --list-tracks
python run.py --track item_202_results_ops
python run.py --example dual_ma AAPL
```

## Adding a new 8-K track

1. Copy `tracks/_template` → `tracks/<your_track_name>`
2. Fill in `STRATEGY.md` (what Item / angle you study, signal, risk)
3. Implement `strategy.py` exporting `STRATEGY_CLASS`
4. Run: `python run.py --track <your_track_name>`

See [`tracks/README.md`](./tracks/README.md) for conventions.
