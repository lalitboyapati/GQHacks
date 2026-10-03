# Gator Quant Hacks (GQHacks) Workspace

Welcome to the Gator Quant Hacks repository.

## Subprojects

- **[`gqh-webull-backtrader-starter/`](./gqh-webull-backtrader-starter/README.md)**: Production-ready Backtrader quantitative backtesting and simulated-live trading engine powered by the Webull OpenAPI.
  - Includes an **Item 2.02 / earnings options-impact** strategy that pulls SEC 8-K events from the Massive API and backtests PEAD / gap-fade rules on Webull bars ([docs](./gqh-webull-backtrader-starter/docs/ITEM_202_OPTIONS.md)).

 8kadv-test
For full setup instructions, capabilities matrix, and use cases, see the [Webull Backtrader Starter Kit README](./gqh-webull-backtrader-starter/README.md).- **[`gqh-8k-options-research/`](./gqh-8k-options-research/README.md)**: Event-study and options backtest harness for SEC Form 8-K disclosures — executive changes (Item 5.02), efficiency/restructuring plans (Items 2.05/2.06), and disclosure novelty. Sources events from SEC EDGAR with Massive for prices, option chains, and news.

