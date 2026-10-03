# Run the 8-K research with Webull

## Status

The disclosure event engine now accepts Webull stock history. Options in this
mode are **Black–Scholes simulations**, including synthetic strikes and expiries;
no result is represented as a historical Webull option fill. The existing Item
2.02 Backtrader strategy also uses Webull stocks and modeled options.

Account-backed execution is pending: this workspace has no Webull app credentials.
Offline API fixtures and end-to-end strategy tests validate the implementation,
but their generated prices are not research results. No Webull P&L is claimed.

## Account setup

1. Obtain an App Key and App Secret through the [Webull OpenAPI application
   process](https://developer.webull.com/apis/docs/market-data-api/getting-started/)
   or the hackathon sponsor's access instructions.
2. Enable US stock historical data for **OpenAPI**. Webull documents an active
   market-data subscription requirement; mobile/desktop subscriptions are separate.
   See [market-data permissions](https://developer.webull.com/apis/docs/market-data-api/overview/).
   Check sponsor access before purchasing anything.
3. From the repo root, install dependencies with `uv sync --project infrastructure --extra dev`.
4. Put credentials in the ignored `infrastructure/backtest/.env`:

   ```dotenv
   WEBULL_APP_KEY=your_actual_key
   WEBULL_APP_SECRET=your_actual_secret
   WEBULL_API_ENDPOINT=api.webull.com
   WEBULL_REGION_ID=us
   ```

The backtests only request market data. No brokerage order is submitted.

## Reproduce the disclosure strategies

From the repo root, first check access on the smaller MongoDB event cache:

```bash
uv run --project infrastructure python run.py --track disclosure_advantage --price-source webull --events tracks/disclosure_advantage/data/events/mdb_events.json --hold 10
```

Then run the committed 1,070-event universe and the original holding-period sweep:

```bash
uv run --project infrastructure python run.py --track disclosure_advantage --price-source webull --hold 5 --hold 10 --hold 21
```

This covers `exec_put` (5.02), `efficiency_collar` (2.05/2.06),
`novelty_shortvol`, `combo`, and the `stock_long` / `stock_short` controls.
Use `--strategies exec_put,stock_short` or another comma-separated subset to narrow it.
The 5.02 and 2.05 overview folders still point to these implementations;
1.01, 2.01, and 7.01 standalone folders have no implemented trading rules.

Outputs, kept out of Git, are under `tracks/disclosure_advantage/data/results/`:

- `webull_backtest_trades.csv`: per-event P&L net of configured spreads and fees,
  price source, model/market label, entry/exit dates and volatility assumptions.
- `webull_backtest_summary.csv`: per-strategy and holding-period statistics.
- `webull_backtest_manifest.json`: arguments, event-file hash, price coverage,
  model assumptions and limitations.

Add `--offline` to replay the saved Webull responses without network access.
Use `--out-prefix /path/to/run_name` to preserve separate experiments.
Use `--spread-pct 0.08` to double the baseline option half-spread assumption.
The original Massive path remains available with `--price-source massive`.

## Item 2.02

Its Webull + Backtrader path already exists. Run the symbols in the committed
high-volatility event cache (list them first if you change that cache):

```bash
uv run --project infrastructure python -c 'import json; print(",".join(sorted({e["ticker"] for e in json.load(open("tracks/item_202_results_ops/data/item_202_events_high_vol.json"))["events"]})))'
uv run --project infrastructure python run.py --track item_202_results_ops DDOG,PLTR --count 1200 --no-open
```

Replace `DDOG,PLTR` with the desired cache symbols. This runs the existing strategy
and produces the existing HTML report. Its stock feed has a 1,200-bar request
limit; verify the displayed date range before interpreting the sample.

## Data and research limits

- The new event adapter fetches at most 31 calendar days per request, below the
  1,200-bar API limit, and caches each dated request. Authentication, entitlement,
  empty long windows and out-of-range history fail the run rather than silently
  generating a successful partial-universe report. Missing/delisted symbol history
  requires investigation; do not remove those names merely to improve performance.
- [Webull daily bars](https://developer.webull.com/apis/docs/reference/broker-market-data-api/bars-using-get/)
  are forward-adjusted. Synthetic option strikes use that price scale. They are
  not actual listed contracts, and fixed-dollar fees are only an approximation
  on historical adjusted prices. Today's unfinished candle is excluded.
- [The documented option bars endpoint](https://developer.webull.com/apis/docs/reference/option-historical-bars/)
  accepts specified option codes and returns recent bars. A historical expired-chain
  discovery path has not been validated for this study. Therefore the Webull mode
  deliberately requests no option chains or option bars and labels premiums `model`.
- Filing classifications remain from the committed EDGAR/Massive event caches.
  Webull replaces underlying prices, not SEC filing discovery or novelty research.
- Old events cannot be shifted more than seven calendar days to reach available
  history. Events need prior volatility observations and a completed holding
  period. Incomplete observations are excluded rather than liquidated early.
  Missing sessions inside a window still require review; a data-derived calendar
  cannot distinguish every vendor omission from a halt.
- The engine preserves intraday close entry, post-gap entry, pre-event volatility,
  modeled IV crush, spreads on both sides, commission and short-volatility margin.
- These are independent event studies with overlapping positions, not a portfolio
  with shared capital. No annualized portfolio Sharpe or equity curve is implied.
  The original sweep has no locked out-of-sample evaluation; it remains exploratory
  and is not by itself a completed submission under the pasted track rules.

## Tests

```bash
uv run --project infrastructure python -m pytest infrastructure/tests/test_webull_prices.py tracks/disclosure_advantage/tests tracks/item_202_results_ops/tests -q
```
