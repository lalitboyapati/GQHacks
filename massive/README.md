# Massive (formerly Polygon.io) Starter & Backtrader Feed

> **Gator Quant Hacks 2026**  
> Comprehensive client and Backtrader integration for **Massive** (formerly Polygon.io) market data.

---

## 📌 What is Massive?

**Massive** is the new brand identity of **Polygon.io**, the industry standard financial market data provider for quants, algorithmic traders, and fintech applications. It provides institutional-grade historical and real-time data across equities, options, crypto, forex, and market news.

---

## ⚡ What You Have Access To (Your API Key)

We tested your API key (`ObDYzm2hPhBKbSYuislLV81QXO9hjNOD`). It is an **active Developer / Hackathon tier** with the following access:

| Data Type | Description | Status & Details |
| :--- | :--- | :--- |
| **Historical Bars (Aggs)** | 1-min to multi-year historical OHLCV bars | ✅ **Full Access** (adjusted & unadjusted) |
| **Bid/Ask Quotes** | Top-of-book National Best Bid and Offer (NBBO) | ✅ **Full Access** (15-min delayed stream) |
| **Tick-by-Tick Trades** | Every executed trade timestamp, price, volume, exchange | ✅ **Full Access** (15-min delayed stream) |
| **Market Snapshots** | Day open, high, low, close, volume, prev close, change % | ✅ **Full Access** |
| **Options Chains & Contracts** | Full option chains, strikes, expirations, contract types | ✅ **Full Access** |
| **SEC Filings & 8-K Reports** | Material event 8-Ks, 10-Ks, 10-Qs, item codes & full text | ✅ **Full Access** |
| **Server-Side Indicators** | Pre-computed SMA, EMA, RSI, MACD direct from API | ✅ **Full Access** |
| **Market News** | Real-time news articles from Benzinga, Zacks, etc. | ✅ **Full Access** |
| **Crypto & Forex** | Bitcoin, Ethereum, EUR/USD, and other pairs | ✅ **Full Access** |

---

## 🚦 Rate Limits

* **Requests Per Minute**: **Unlimited / High-Throughput** (tested 12+ rapid consecutive requests with 0ms cooldown without hitting limits). You are **NOT** restricted to the public 5 requests/minute free limit.
* **Max Bars Per Query**: Up to **5,000 bars** in a single API call (with pagination `next_url` for larger series).
* **Quotes & Trades**: Up to **50,000 records** per request via pagination.

---

## 🛠️ What You Can Build With Massive

1. **High-Frequency & Intraday Backtesting**:
   - Pull granular 1-minute (`minute`) or hourly bars across multiple years to backtest intraday breakout, VWAP, or mean-reversion strategies.
2. **Multi-Asset & Pairs Trading**:
   - Simultaneously stream and analyze correlations across equities, crypto (`X:BTCUSD`), and forex (`C:EURUSD`).
3. **Options Volatility & Delta-Neutral Strategies**:
   - Query option contracts across strikes and expirations to model implied volatility and option payoffs.
4. **News Sentiment-Driven Trading**:
   - Ingest live market news articles for specific tickers and use LLMs or NLP to generate sentiment signals.
5. **Direct Backtrader Simulation**:
   - Feed data straight into Backtrader using [`MassiveData`](./feed_massive.py).

---

## 📂 Folder Layout

```
massive/
├── client.py            # Typed Python wrapper for Massive REST API
├── feed_massive.py      # Backtrader DataFeed subclass (MassiveData)
├── test_massive.py      # Automated capabilities and health-check test
├── .env                 # API credentials (gitignored)
├── .env.example         # Template for team members
└── README.md            # Documentation and usage guide
```

---

## 🚀 Quickstart & Usage

### 1. Run the Health Check
Verify all endpoints and Backtrader integration:
```bash
python massive/test_massive.py
```

### 2. Query Data in Python

```python
from massive.client import MassiveClient

client = MassiveClient()

# 1. Fetch historical daily bars
bars = client.get_bars("AAPL", multiplier=1, timespan="day", from_date="2026-01-01", to_date="2026-10-02")
for bar in bars[:3]:
    print(bar["t"], bar["o"], bar["h"], bar["l"], bar["c"], bar["v"])

# 2. Fetch latest bid/ask quotes
quotes = client.get_quotes("AAPL", limit=5)

# 3. Fetch server-side technical indicators
sma = client.get_indicator("sma", "AAPL", timespan="day", window=20)

# 4. Fetch financial news
news = client.get_news("AAPL", limit=3)

# 5. Fetch 8-K material event filings
filings = client.get_8k_filings("AAPL", limit=5)
for f in filings:
    print(f"Date: {f['filing_date']} | Items: {f['items']} | Doc: {f['document_url']}")

# 6. Read raw 8-K text for NLP / sentiment analysis
doc_text = client.get_filing_content(filings[0]["document_url"])
```

### 3. Backtest with Backtrader & Massive

```python
import backtrader as bt
from massive.feed_massive import MassiveData

cerebro = bt.Cerebro()
cerebro.broker.setcash(100000.0)

# Add Massive Data Feed
feed = MassiveData(
    dataname="NVDA",
    timespan="day",
    from_date="2026-01-01",
    to_date="2026-10-02"
)
cerebro.adddata(feed)

# Add your strategy
cerebro.run()
print("Final Value:", cerebro.broker.getvalue())
```
