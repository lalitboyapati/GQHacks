# Strategy overview — 8-K Disclosure Advantage

**Owner:** 8kadv research  
**8-K Item(s):** 5.02 (exec changes), 2.05 / 2.06 (restructuring / impairments), novelty across items  
**Status:** active (event-study engine)  
**Engine:** `event` (`infrastructure/eightk`)

## Thesis

Does an SEC Form 8-K carry information the options market has not yet priced —
especially on smaller issuers? Three structures are tested on the same event set:

| Strategy | Idea | Structure |
| --- | --- | --- |
| `exec_put` | Senior officer leaves (5.02) → buy puts | Long put |
| `efficiency_collar` | Efficiency plan costs vs distant savings | Long stock + put − call |
| `novelty_shortvol` | Repeat disclosure → sell rich vol | Short strangle |
| `combo` | Novel restructuring → collar; repeat → short vol | Routed |

## Data

- **EDGAR** for `acceptanceDateTime` + full filing text
- **Massive** for bars, option chains/bars, news, market caps
- Event JSON under `tracks/disclosure_advantage/data/events/`

## Signal / exits

Pessimistic entry timing (in-session → close), real option bars when present,
IV mean-reversion on model exits, half-spread both ways, short-vol margin on
notional. See `README.md` and `HANDOFF.md` for contracts and open gaps.

## Backtest notes

```bash
# from repo root
python run.py --track disclosure_advantage --engine event
python run.py --track disclosure_advantage --engine event -- --events tracks/disclosure_advantage/data/events/universe_events.json

# or call scripts directly
python tracks/disclosure_advantage/scripts/fetch_events.py --universe default --start 2019-01-01
python tracks/disclosure_advantage/scripts/run_backtest.py --events tracks/disclosure_advantage/data/events/universe_events.json
```

Shared library: `infrastructure/eightk`. Track owns scripts, data, and findings.
