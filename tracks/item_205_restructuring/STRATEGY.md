# Strategy overview — Item 2.05 / 2.06 Restructuring & Impairments

**Owner:** TBD  
**8-K Item(s):** 2.05 Cost Associated with Exit/Disposal; 2.06 Material Impairments  
**Status:** overview → see `disclosure_advantage` for the live event-study

## Thesis

Efficiency / restructuring plans often disclose large upfront charges against
savings years away. The production test is `efficiency_collar` (and `combo`
when novelty routing applies) in
[`disclosure_advantage`](../disclosure_advantage/).

## Data

- Event-study path: EDGAR + Massive via `infrastructure/eightk`
- Backtrader stub: not implemented

## Signal

Use `disclosure_advantage` / `efficiency_collar` until this stub is replaced.

## Exits & risk

Documented in `tracks/disclosure_advantage/STRATEGY.md` and `HANDOFF.md`.

## Backtest notes

```bash
python run.py --track disclosure_advantage --engine event -- --strategies efficiency_collar,combo

# this stub (flat until implemented)
python run.py --track item_205_restructuring
```
