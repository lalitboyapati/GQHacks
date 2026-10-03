# Shared Backtesting Infrastructure

> Part of **Gator Quant Hacks (GQHacks)** — the common Webull + Backtrader engine
> used by every research track under [`../tracks/`](../tracks/).
>
> Research strategies do **not** live here. Put novel 8-K work in `tracks/<name>/`
> and run with `python run.py --track <name>` from the repo root.

---

# Webull Backtrader Engine (formerly starter kit)

> **Gator Quant Hacks (GQHacks) 2026 · Systematic Trading Track**  
> A production-ready quantitative backtesting and simulated live trading starter kit combining the [Webull OpenAPI](https://developer.webull.com/apis/docs) with [Backtrader](https://github.com/mementum/backtrader).

---

## 📌 Overview

Developing algorithmic trading strategies often requires juggling fragmented data scrapers, formatting CSVs, and wrestling with backtesting plumbing. This starter kit eliminates that friction by pairing Webull's official OpenAPI market data and order routing interfaces directly with Backtrader's battle-tested event-driven simulation engine.

Whether you are participating in **GQHacks 2026** or researching systematic strategies, this project lets you focus strictly on **alpha generation, factor research, and risk management**.

---

## 🎯 Intended Use Cases

1. **Systematic Trading Competition & Research (GQHacks)**
   - Research and backtest equity/ETF trading strategies on genuine US market data.
   - Optimize key portfolio performance metrics: **Annualized Sharpe Ratio**, **Max Drawdown**, **Calmar Ratio**, and **Win Rate**.
   - Perform strict in-sample parameter tuning and validate on out-of-sample (OOS) testing intervals.

2. **Multi-Asset Portfolio Allocation & Momentum Rotation**
   - Ingest multiple asset feeds simultaneously (e.g. `AAPL`, `MSFT`, `GOOG`, `NVDA`).
   - Run periodic cross-sectional ranking (e.g. relative strength, momentum, volatility parity) and automate rebalancing using target percentage weights.

3. **Intraday & Session-Specific Quantitative Models**
   - Backtest with minute-level bars (`M1`, `M5`, `M15`, `M30`, `M60`).
   - Utilize Webull's native trading session tagging (`PRE` Pre-Market, `RTH` Regular Trading Hours, `ATH` After-Hours, `OVN` Overnight) to design session-sensitive trading logic.

4. **Paper Trading & Pre-Production Deployment**
   - Test strategy behavior against incoming real-time bars using the simulated-live polling feed.
   - Connect to Webull's Sandbox/Pre environment to validate order placement, fills, cancellations, and order guards before deploying real capital.

---

## ⚡ Capabilities Matrix

| Area | Capability | Implementation / Details |
| :--- | :--- | :--- |
| **Market Data** | Historical K-Lines | Fetches OHLCV directly via Webull OpenAPI (`/market-data/stocks/bars/get`). |
| | Granularities | `M1`, `M5`, `M15`, `M30`, `M60`, `M120`, `M240`, `D`, `W`, `M`, `Y`. |
| | Resampling & Compression | Inferred automatically from Webull timespans into Backtrader timeframes. |
| | Session Awareness | Bars carry encoded session IDs (`PRE`, `RTH`, `ATH`, `OVN`). |
| | Date Filtering | Native ISO 8601 filtering (`WEBULL_FROMDATE` to `WEBULL_TODATE`) with UTC normalization. |
| **Live Trading** | Simulated Live Feed | Background polling thread (`WebullLiveData`) streams newly closed bars. |
| | Bar Deduplication | Strictly monotonic timestamp verification; guarantees chronological ordering. |
| | Indicator Warmup | Optional historical backfilling (`backfill=N`) on start. |
| **Execution** | Order Types | `Market`, `Limit`, `Stop Loss`, `Stop Limit`, `Trailing Stop` (amount/%), `MOC`. |
| | Time In Force | `DAY` and `GTC` order durations. |
| | Order Status Polling | Threaded status tracker (`SUBMITTED`, `PARTIAL_FILLED`, `FILLED`, `CANCELLED`, `FAILED`). |
| | Account Sync | Pulls live cash balance, liquidation value, and existing positions from Webull account. |
| | Sandbox Support | Single-flag toggle (`WEBULL_ENV=sandbox` vs `prod`) to test risk-free. |
| **Visuals & Analytics** | Dual Visualization | Plotly dashboard (`visualize.py`) or TradingView Lightweight Charts (`visualize_lwc.py`). |
| | Interactive Charts | Candlesticks, volume sub-panels, buy/sell markers, indicator overlays, equity curves. |
| | Judged Metrics | Annualized Sharpe Ratio, Max Drawdown ($ / %), Net P&L, Win Rate, Holding Periods. |
| **Extensibility** | Zero-Code Tuning | Control all strategy parameters, symbols, and dates via `.env`. |
| | Pluggable Strategies | Drop `.py` files into `examples/strategies/` with standard `STRATEGY_CLASS` export. |

---

## 📂 Repository Structure

```
gqh-webull-backtrader-starter/
├── webull_bt/                   # Reusable Core Library
│   ├── feed.py                  # WebullData (Backtest) & WebullLiveData (Polling)
│   ├── broker.py                # WebullBroker (Order routing, account sync, polling)
│   ├── visualize.py             # Plotly HTML Report + RecorderAnalyzer
│   ├── visualize_lwc.py         # TradingView Lightweight Charts HTML Report
│   ├── timeutils.py             # Timezone conversions (US Eastern/DST) & session codecs
│   ├── logging_utils.py         # Standardized logging setup
│   └── massive_filings.py       # Massive 8-K Item 2.02 + Benzinga earnings helpers
├── examples/
│   ├── backtest/
│   │   ├── main.py              # Backtest CLI runner & report orchestrator
│   │   └── .env.example         # Backtest credentials & hyperparameter template
│   ├── live/
│   │   ├── main.py              # Simulated live runner & broker interface
│   │   └── .env.example         # Live & Sandbox execution credentials template
│   ├── data/
│   │   └── item_202_events_sample.json  # Offline Item 2.02 event cache
│   ├── scripts/
│   │   └── fetch_item_202_events.py     # Pull/cache Massive Item 2.02 events
│   └── strategies/              # Strategy catalog
│       ├── dual_ma.py           # Multi-symbol Dual Moving Average crossover
│       ├── portfolio.py         # Multi-symbol Momentum Rotation & Rebalancing
│       └── item_202_options.py  # Item 2.02 earnings / options-impact PEAD proxy
├── docs/
│   ├── README.md                # Quickstart documentation (Chinese)
│   ├── USAGE.md                 # Detailed guide (Chinese)
│   ├── USAGE_EN.md              # Participant guide (English)
│   └── ITEM_202_OPTIONS.md      # Item 2.02 strategy + options interpretation
├── pyproject.toml               # Package metadata and dependencies
└── uv.lock                      # Locked dependency versions
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **Python 3.11+**
- **Webull OpenAPI Credentials**: Obtain your `app_key` and `app_secret` via your Webull account under **Developer Tool** → **OpenAPI Management**.
- Package manager: [`uv`](https://docs.astral.sh/uv/) (recommended) or standard `pip`.

### 2. Installation

Using `uv`:
```bash
cd gqh-webull-backtrader-starter
uv sync
```

Or using `pip`:
```bash
cd gqh-webull-backtrader-starter
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -e .
```

### 3. Configure Credentials

Copy `examples/backtest/.env.example` to `examples/backtest/.env` and fill in your keys:

```dotenv
WEBULL_APP_KEY=your_app_key_here
WEBULL_APP_SECRET=your_app_secret_here
WEBULL_API_ENDPOINT=api.webull.com
WEBULL_REGION_ID=us

# Backtest target configuration
WEBULL_SYMBOLS=AAPL
WEBULL_CATEGORY=US_STOCK
WEBULL_TIMESPAN=D
WEBULL_COUNT=200
```

> ⚠️ **Security Warning**: Never commit `.env` files to git. They are already listed in `.gitignore`.

### 4. Run a Backtest

```bash
uv run python examples/backtest/main.py
```

Upon completion, you will see a detailed terminal summary:
```text
============================================================
[Backtest] Result Summary
============================================================
Starting cash    : 100000.00
Final cash       : 103250.00
Net P&L          : 3250.00 (3.25%)
Max drawdown     : 4.10% (4100.00)
Sharpe ratio     : 1.2500 (annualized)
Total trades     : 12 (won=7, lost=5, win rate=58.33%)
Trades net P&L   : 3250.00
============================================================
```
An interactive HTML report (`backtest_report.html` or `backtest_report_lwc.html`) is automatically generated in `examples/backtest/` showing candlestick charts, overlaid indicators, trades, and equity drawdown.

### 5. Run the Automated Pipeline Test

To verify your installation and test data ingestion, strategy execution, analyzers, and HTML reporting in one command (works with or without live Webull API keys):

```bash
python -m uv run python tests/test_backtester.py
```
*(Add `--mock` to explicitly test with simulated Webull OpenAPI response).*

---

## ⚙️ Configuration Options (`examples/backtest/.env`)

| Variable | Description | Default | Example |
| :--- | :--- | :--- | :--- |
| `WEBULL_SYMBOLS` | Ticker symbols (comma-separated) | `AAPL` | `AAPL,MSFT,NVDA` |
| `WEBULL_TIMESPAN` | K-line timeframe | `D` | `M1`, `M5`, `M15`, `D` |
| `WEBULL_COUNT` | Number of historical bars to load | `200` | `1200` |
| `WEBULL_FROMDATE` | Starting range (ISO 8601) | *None* | `2026-09-01T09:30:00-04:00` |
| `WEBULL_TODATE` | Ending range (ISO 8601) | *None* | `2026-09-30T16:00:00-04:00` |
| `WEBULL_STRATEGY` | Strategy file name from `examples/strategies/` | `dual_ma` | `portfolio` or custom |
| `WEBULL_STRATEGY_PARAMS` | Dynamic parameter overrides | *None* | `short_period=10,long_period=30` |
| `WEBULL_VISUALIZE` | Enable/disable HTML chart report | `true` | `true` or `false` |
| `WEBULL_VISUALIZE_ENGINE` | Charting engine (`plotly` or `lwc`) | `plotly` | `lwc` (TradingView style) |
| `WEBULL_DISPLAY_TZ` | Display timezone for logs and charts | `America/New_York` | `UTC`, `America/Chicago` |

---

## 💡 Implementing Custom Strategies

To test your own quant algorithm:

1. Create a Python file in `examples/strategies/`, e.g., `examples/strategies/rsi_strategy.py`:
   ```python
   import backtrader as bt

   class RsiStrategy(bt.Strategy):
       params = dict(period=14, oversold=30, overbought=70)

       def __init__(self):
           self.rsi = bt.ind.RSI(self.data.close, period=self.p.period)
           self.set_tradehistory(True)
           self.closed_trades = []

       def next(self):
           if not self.position:
               if self.rsi[0] < self.p.oversold:
                   self.buy()
           elif self.rsi[0] > self.p.overbought:
               self.close()

       def notify_trade(self, trade):
           if trade.isclosed:
               entry_size = trade.history[0].event.size if trade.history else trade.size
               exit_price = trade.history[-1].event.price if trade.history else trade.price
               self.closed_trades.append({
                   "symbol": trade.data._name or trade.data._dataname,
                   "direction": "BUY" if entry_size > 0 else "SELL",
                   "size": entry_size,
                   "entry_price": trade.price,
                   "open_dt": trade.dtopen,
                   "exit_price": exit_price,
                   "close_dt": trade.dtclose,
                   "pnl": trade.pnl,
                   "pnlcomm": trade.pnlcomm,
                   "commission": trade.commission,
                   "bars_held": trade.barlen,
               })

   # Required: Export STRATEGY_CLASS
   STRATEGY_CLASS = RsiStrategy
   ```

2. Point your `.env` to the strategy:
   ```dotenv
   WEBULL_STRATEGY=rsi_strategy
   WEBULL_STRATEGY_PARAMS=period=21,oversold=25,overbought=75
   ```

3. Run `python examples/backtest/main.py`.

### Item 2.02 / earnings options-impact strategy

`examples/strategies/item_202_options.py` trades the underlying around SEC
**Item 2.02** earnings filings from the [Massive](https://massive.com) API
(PEAD momentum or gap-fade). See [`docs/ITEM_202_OPTIONS.md`](docs/ITEM_202_OPTIONS.md).

```bash
# Uses shipped sample events by default (no Massive key required)
python ../run.py AAPL --strategy item_202_options --count 1200 \
  --params hold_bars=5,min_gap_atr=0.5,mode=momentum
```

Set `MASSIVE_API_KEY` and run `examples/scripts/fetch_item_202_events.py` to
refresh the event cache from live 8-K filings.

---

## 📊 Using `WebullData` Directly in Custom Scripts

You can also use the `webull_bt` package as a standalone module inside your own Jupyter notebooks or scripts:

```python
import backtrader as bt
from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull_bt import WebullData

# Initialize Webull DataClient
api_client = ApiClient("YOUR_APP_KEY", "YOUR_APP_SECRET", "us")
api_client.add_endpoint("us", "api.webull.com")
data_client = DataClient(api_client)

cerebro = bt.Cerebro()
cerebro.adddata(
    WebullData(
        dataname="AAPL",
        data_client=data_client,
        timespan="M5",
        count=500
    )
)
cerebro.broker.setcash(100000.0)
cerebro.run()
```

---

## 🏆 Competition Best Practices (GQHacks Rubric)

- **Net of Transaction Costs**: Backtest results submitted to the judges must factor in realistic commissions and slippage. Configure fees in Backtrader using:
  ```python
  cerebro.broker.setcommission(commission=0.001)  # e.g., 10 bps
  ```
- **Out-of-Sample (OOS) Testing**: Divide your historical data into training (in-sample) and testing (out-of-sample) windows. Never evaluate or tune strategy hyperparameters on data the model was fitted on.
- **Risk Management**: Relying solely on raw return without considering volatility is penalized. Ensure your strategy optimizes the **Sharpe Ratio** while curbing **Max Drawdown**.
- **Sandbox Validation**: If experimenting with `examples/live/main.py`, verify all order flows in `WEBULL_ENV=sandbox` before deploying.
