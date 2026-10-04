# Strategy summary graphics

Print-ready figures for a one-page overview of the FIRMS-brief facility-disruption options strategy.

| File | Use |
|------|-----|
| `00_one_pager_board.png` | Drop-in landscape board (pipeline + metrics + takeaway) |
| `01_strategy_pipeline.png` | Signal path: 8-K → filter → FIRMS → condor |
| `02_implied_vs_realized.png` | Why short vol (implied vs path + ratio CIs) |
| `03_structure_ranking.png` | IS edge ranking across structures |
| `04_oos_and_costs.png` | 2025 OOS transfer + 5% haircut on winner |

Regenerate:

```bash
python massive/summary_graphics/make_summary_graphics.py
```

Numbers match the saved run of `gqh-massive-8k-starter/thermal-based options pricing.ipynb`.
