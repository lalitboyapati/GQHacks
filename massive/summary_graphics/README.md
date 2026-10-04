# Strategy summary graphics

Print-ready figures for a one-page overview of the FIRMS-brief facility-disruption options strategy.

| File | Use |
|------|-----|
| `combined_writeup_plain.pdf` | **Merged 2-page paper, plain-language edition** for judges / recruiters (source: `combined_writeup_plain.md`) |
| `combined_writeup.pdf` | Merged 2-page paper, technical edition: disruptions × FIRMS + readouts × Jev, organised by the rubric (source: `combined_writeup.md`) |
| `facility_disruption_2page_summary.pdf` | Facility-disruption write-up alone (2 letter pages + figures) |
| `writeup.pdf` | Biotech readout write-up alone (A4, from `writeup.md`) |
| `00_one_pager_board.png` | Drop-in landscape board (pipeline + metrics + takeaway) |
| `01_strategy_pipeline.png` | Signal path: 8-K → filter → FIRMS → condor |
| `02_implied_vs_realized.png` | Why short vol (implied vs path + ratio CIs) |
| `03_structure_ranking.png` | IS edge ranking across structures |
| `04_oos_and_costs.png` | 2025 OOS transfer + 5% haircut on winner |

Regenerate:

```bash
python massive/summary_graphics/make_summary_graphics.py
python massive/summary_graphics/make_two_page_summary.py
python massive/summary_graphics/make_writeup_pdf.py      # writeup.md -> writeup.pdf
python massive/summary_graphics/make_combined_pdf.py     # both combined_writeup*.md -> .pdf (or pass one filename)
```

Numbers match the saved run of `gqh-massive-8k-starter/thermal-based options pricing.ipynb`.
