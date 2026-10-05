# Whale Watching

> 🥇 **1st place, Databento track, Gator Quant Hacks (University of Florida Quant Hackathon).**

Two event-driven equity/options research projects, each pre-registered, tested on a locked
out-of-sample window and fully reproducible from committed data:

| Project | Question | Data | Write-up |
|---|---|---|---|
| [**Whale footprints**](whale_footprints/) | Do large one-sided option trades ("whales") in a biotech name predict the stock's move *before* the news covers it? | Databento OPRA, Massive, Webull | [`quant_note.pdf`](whale_footprints/docs/quant_note.pdf) |
| [**8-K event trading**](8k_event_trading/) | Does the text of a biotech clinical-trial 8-K, read by a language model, predict the stock after the filing, and how cheaply can the trade be hedged with options? | Massive, SEC EDGAR, Jev (TypeSafe) | [`WRITEUP.pdf`](8k_event_trading/WRITEUP.pdf) |

## Headline results

**Whale footprints** (net of costs; in-sample 2024-01 → 2026-03, out-of-sample 2026-03 → 2026-10, run once):

| | In-sample Sharpe | Out-of-sample Sharpe |
|---|---|---|
| Locked plan (with options tail hedge) | −0.56 | −0.76 |
| No options tail hedge | −0.14 | +0.70 |
| No hedges at all | −0.07 | +1.46 |

The whale signal itself carries information: the direction-signed 5-session stock move is **+1.06%** in-sample
(n = 593) and **+2.54%** out-of-sample (n = 173). The pre-registered plan loses because the options tail hedge costs
more than the edge (biotech implied volatility is extreme before catalysts). The hedge-free variants are reported,
not adopted, since choosing them after seeing the out-of-sample run would be tuning on the test set.
Details: [`whale_footprints/README.md`](whale_footprints/README.md).

**8-K event trading:** the language model reads trial readouts well (its sentiment lines up monotonically with the
day-0 move), but by the close of the filing session the move is done; the under-reaction rule shows no edge over
placebo in- or out-of-sample. The option side does hold: implied volatility collapses after the readout, so
post-event protection is far cheaper and roughly halves the worst decile of the long book.
Details: [`8k_event_trading/README.md`](8k_event_trading/README.md).

## Repository layout

```
whale_watching/
├── whale_footprints/              # options-flow strategy (Databento + Massive + Webull)
│   ├── README.md                  # results, pipeline, how to reproduce
│   ├── run_all.py                 # one entry point: data stages → backtests → every variant
│   ├── pipeline/                  # universe → screen → whales → signals → backtest (+ hedging, analysis)
│   ├── reporting/                 # diagnostics and figures for the quant note
│   ├── docs/                      # HYPOTHESIS.md (pre-registration), DEVIATIONS.md, quant_note.pdf
│   ├── data/                      # committed derived tables (raw vendor cache is gitignored)
│   ├── results/                   # metrics, equity curves, trades, OOS lock, variants log
│   └── figures/                   # figures used in the quant note
│
└── 8k_event_trading/              # 8-K filing strategies (Massive + EDGAR + Jev)
    ├── README.md
    ├── biotech-strategy-notebook.ipynb   # main study: biotech clinical-trial 8-Ks
    ├── WRITEUP.pdf                       # two-page write-up of the biotech study
    ├── jev_cache/                        # committed LLM labels, so the notebook runs without a Jev key
    ├── figures/
    └── facility_disruption/              # exploratory: facility-disruption 8-Ks × NASA FIRMS satellite heat data
```

## Quickstart

```bash
# Whale footprints (Python 3.11+): reproduce the headline numbers from committed signals
cd whale_footprints
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # add Webull + Massive keys
python run_all.py --from-signals   # in-sample;  add --oos for the locked out-of-sample run

# 8-K event trading (Python 3.10+)
cd ../8k_event_trading
./setup.sh                         # creates .venv, registers a Jupyter kernel, creates .env
# add MASSIVE_API_KEY to .env, then open biotech-strategy-notebook.ipynb and run all cells
```

API keys live in per-project `.env` files, which are gitignored.
