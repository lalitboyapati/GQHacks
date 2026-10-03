# Strategy overview — Item 5.02 Officer / Director Changes

**Owner:** TBD  
**8-K Item(s):** 5.02 Departure of Directors or Certain Officers; Election; Comp Arrangements  
**Status:** overview → see `disclosure_advantage` for the live event-study

## Thesis

CEO/CFO departures and unexpected appointments carry persistent drift and
options skew effects. The production test of this idea is the `exec_put`
strategy in [`disclosure_advantage`](../disclosure_advantage/) (EDGAR timing +
real option bars).

This folder remains a Backtrader stub if someone wants a Webull-feed
simplification of the same Item.

## Data

- Event-study path: EDGAR + Massive via `infrastructure/eightk`
- Backtrader stub: Massive disclosures + Webull bars (not implemented)

## Signal

Use `disclosure_advantage` / `exec_put` until this stub is replaced.

## Exits & risk

Documented in `tracks/disclosure_advantage/STRATEGY.md` and `HANDOFF.md`.

## Backtest notes

```bash
# live event-study (recommended)
python run.py --track disclosure_advantage --engine event -- --strategies exec_put

# this stub (flat until implemented)
python run.py --track item_502_officer_changes
```
