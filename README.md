# Gator Quant Hacks (GQHacks)

Multi-person workspace for **Form 8-K event strategies** with shared
infrastructure and one folder per research track.

## Layout

```
GQHacks/
├── infrastructure/          # Shared engines (do not fork per person)
│   ├── webull_bt/           # Webull + Backtrader feeds, broker, reports
│   ├── eightk/              # EDGAR/Massive event-study + options book
│   ├── backtest/            # Common Backtrader runner + shared .env
│   ├── live/
│   └── examples/strategies/ # Reference demos (dual_ma, portfolio)
├── tracks/                  # One folder per researcher / 8-K topic
│   ├── _template/
│   ├── item_202_results_ops/       # Item 2.02 → synthetic calls/puts (Backtrader)
│   ├── disclosure_advantage/       # 5.02 / 2.05-2.06 / novelty event-study
│   ├── item_502_officer_changes/   # overview → exec_put strategy
│   ├── item_205_restructuring/     # overview → efficiency collar
│   └── …
└── run.py                   # CLI for Backtrader tracks (+ helpers)
```

Each **track** owns:
- `STRATEGY.md` — thesis and approach (the overall view)
- `strategy.py` — Backtrader `STRATEGY_CLASS` **or** a stub that points at the event-study runner
- optional `scripts/`, `data/`, `tests/`, track-local `.env`

## Quickstart

```bash
cd infrastructure
uv sync
cp backtest/.env.example backtest/.env   # WEBULL_* + MASSIVE_APP_KEY

cd ..
python run.py --list-tracks

# Backtrader track (Item 2.02)
python run.py --track item_202_results_ops

# Event-study track (8-K disclosure advantage — from former gqh-8k-options-research)
python tracks/disclosure_advantage/scripts/fetch_events.py
python tracks/disclosure_advantage/scripts/run_backtest.py
# or:
python run.py --track disclosure_advantage --engine event
```

## Adding a new 8-K track

1. Copy `tracks/_template` → `tracks/<your_track_name>`
2. Fill in `STRATEGY.md`
3. Implement `strategy.py` **or** add `scripts/` that use `infrastructure/eightk`
4. Run via `run.py --track …` (Backtrader) or the track’s scripts (event-study)

See [`tracks/README.md`](./tracks/README.md).
