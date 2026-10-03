# Strategy overview — Item 7.01 Regulation FD

**Owner:** TBD  
**8-K Item(s):** 7.01 Regulation FD Disclosure  
**Status:** stub

## Thesis
Reg FD furnishing (slides, metrics, guidance teasers) can leak tradeable
information with lower formal “earnings” labeling. Detect high-signal FD
disclosures and trade shorter-horizon options around them.

## Data
- Massive 8-K text containing Item 7.01 / disclosure taxonomy FD nodes
- Shared Webull bars

## Signal
TBD — replace `strategy.py` stub.

## Exits & risk
TBD

## Backtest notes

```bash
python run.py --track item_701_reg_fd
```
