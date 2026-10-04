# Whale footprints · biotech options flow, traded before the news

Systematic Trading track submission (Gator Quant Hacks 2026). The hypothesis, its parameters and the
locked out-of-sample window were committed before any data was pulled: see [`HYPOTHESIS.md`](HYPOTHESIS.md)
(commit `16e75ab`). Changes made afterwards, all before any result existed, are in
[`DEVIATIONS.md`](DEVIATIONS.md). Every backtest configuration that was run is logged in
`results/variants_log.csv`.

**Idea.** Large, one-directional option trades ("whales") in a biotech name, on a day the news has not
yet covered, predict the stock's move over the next few sessions. We buy the stock after bullish whale
flow and short it after bearish flow, hold 5 sessions, and hedge the biotech beta with XBI.

## Data, one role per vendor

| Vendor | Used for | Where |
|---|---|---|
| **Massive** | Option reference + daily option bars (the volume screen), stock grouped daily bars (spot, liquidity), **news with per-ticker sentiment** (the "already covered?" filter) | `screen.py`, `signals.py` |
| **Databento** | OPRA `tcbbo`: every option trade with the consolidated best bid/offer at that moment, used to **sign whale prints** (bought vs sold) on flagged days only | `whales.py` (spend-capped, priced before every purchase) |
| **Webull** | Daily stock and XBI bars: **the only prices the backtest trades on** (backtrader) | `backtest.py` |

Raw vendor data is cached under `data/cache/` and never committed. Derived tables (`universe.csv`,
`whale_days.csv`, `news.csv`, `signals.csv`) are committed so the backtest can be reproduced with
Webull keys alone.

## Reproduce

```bash
# from the repo root, Python 3.11+
uv venv .venv-whale && source .venv-whale/bin/activate        # or python -m venv
uv pip install -r tracks/whale_footprints/requirements.txt    # or pip install -r ...
cp tracks/whale_footprints/.env.example infrastructure/backtest/.env   # then fill in your keys

cd tracks/whale_footprints
python run_all.py --from-signals          # backtest from the committed signals: needs Webull keys only
python run_all.py --from-signals --oos    # the locked out-of-sample run (reproduces the same spec only)

python run_all.py                          # full pipeline (Massive + Databento + Webull); data stages are cached
```

Outputs go to `results/`: `{is,oos}_metrics.csv` (baseline and every variant), `{is,oos}_summary.json`
(headline numbers, factor regression, deflated Sharpe, news-status counts, symbols Webull lacks),
`{is,oos}_equity.png`, `{is,oos}_trades.csv`, `{is,oos}_decay.csv`, `{is,oos}_capacity.csv`.

## Pipeline

1. `universe.py`: the team's biotech list → one symbol per company → names with listed options (Massive).
2. `screen.py`: Massive sampled option volume per name → spike days (≥ 2× trailing 20-session median).
3. `whales.py`: stage-1 pool (≥ 1,000 sampled contracts, one-directional call/put volume, liquid), a seeded
   30% sample, Databento `tcbbo` for each day → signed whale premium per threshold.
4. `signals.py`: whale day = 3× spike, ≥ 1,000 contracts on the full tape, ≥ 65% of $50k+ whale premium on
   one side; Massive news from 3 days before through the next open; skip if the news already carried the
   same-direction sentiment.
5. `backtest.py`: backtrader on Webull bars: enter at the next open, exit 5 sessions later; risk-scaled
   sizing with name, liquidity and position caps; −15% stop; drawdown de-risking; daily XBI hedge;
   20 bps per side, 5% annual borrow on shorts.
6. `analysis.py` / `run_all.py`: metrics (return, volatility, Sharpe, max drawdown, turnover, worst month),
   ×2 costs, hedge off, every neighbouring parameter, news-rule variants, the "news already covered"
   shadow book, decay by horizon, XBI/SPY regression, deflated Sharpe, square-root-impact capacity.

## Databento spend

Capped in `config.py` (this study ≤ $60 of the team's $225; ≤ $50 per run). Every request is priced with
`metadata.get_cost` first and recorded in `data/databento_spend_ledger.json`.
