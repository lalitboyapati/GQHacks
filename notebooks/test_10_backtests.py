"""Backtest stock price changes and put options returns across all 10 notable executive departures."""

import json
import math
import sys
import pathlib
from datetime import datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from massive.client import MassiveClient

def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def bs_put(S, K, T, r, sigma):
    if T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)

client = MassiveClient()
with open("c:/projects/GQHacks/notebooks/ten_notable_departures.json") as f:
    cases = json.load(f)

print("=" * 105)
print(" EMPIRICAL BACKTEST: STOCK DROPS & PUT OPTION PROFITS ON 10 EXECUTIVE DEPARTURES")
print("=" * 105)

summary_rows = []

for c in cases:
    ticker = c["ticker"].split()[0]
    fd = c["filing_date"]
    d_obj = datetime.strptime(fd, "%Y-%m-%d")
    start_str = (d_obj - timedelta(days=5)).strftime("%Y-%m-%d")
    end_str = (d_obj + timedelta(days=25)).strftime("%Y-%m-%d")
    
    bars = client.get_bars(ticker, 1, "day", start_str, end_str)
    if not bars:
        continue
        
    dates = [datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d") for b in bars]
    closes = [b["c"] for b in bars]
    
    # Entry bar
    idx_entry = [i for i, d in enumerate(dates) if d >= fd]
    if not idx_entry:
        continue
    i0 = idx_entry[0]
    S0 = closes[i0]
    date0 = dates[i0]
    
    # T+1, T+3, T+5, T+10
    i1 = min(len(closes) - 1, i0 + 1)
    i3 = min(len(closes) - 1, i0 + 3)
    i5 = min(len(closes) - 1, i0 + 5)
    i10 = min(len(closes) - 1, i0 + 10)
    
    ret1 = (closes[i1] - S0) / S0 * 100.0
    ret3 = (closes[i3] - S0) / S0 * 100.0
    ret5 = (closes[i5] - S0) / S0 * 100.0
    ret10 = (closes[i10] - S0) / S0 * 100.0
    
    min_close = min(closes[i0:i10+1])
    max_drop = (min_close - S0) / S0 * 100.0
    
    # Options calculation (30 DTE entry, 5-day hold)
    dte = 30.0 / 365.0
    t_exit = 25.0 / 365.0
    iv_in = 0.50
    iv_out = 0.65  # Post-announcement IV expansion
    r = 0.04
    
    # ITM Put (110% Strike)
    p_itm_in = bs_put(S0, S0 * 1.10, dte, r, iv_in)
    p_itm_out = bs_put(closes[i5], S0 * 1.10, t_exit, r, iv_out)
    roi_itm = (p_itm_out - p_itm_in) / p_itm_in * 100.0
    
    # ATM Put (100% Strike)
    p_atm_in = bs_put(S0, S0, dte, r, iv_in)
    p_atm_out = bs_put(closes[i5], S0, t_exit, r, iv_out)
    roi_atm = (p_atm_out - p_atm_in) / p_atm_in * 100.0
    
    # 5% OTM Put (95% Strike)
    p_otm5_in = bs_put(S0, S0 * 0.95, dte, r, iv_in)
    p_otm5_out = bs_put(closes[i5], S0 * 0.95, t_exit, r, iv_out)
    roi_otm5 = (p_otm5_out - p_otm5_in) / p_otm5_in * 100.0
    
    # 10% OTM Put (90% Strike)
    p_otm10_in = bs_put(S0, S0 * 0.90, dte, r, iv_in)
    p_otm10_out = bs_put(closes[i5], S0 * 0.90, t_exit, r, iv_out)
    roi_otm10 = (p_otm10_out - p_otm10_in) / p_otm10_in * 100.0
    
    row = {
        "ticker": ticker,
        "company": c["company"],
        "operator": c["operator"],
        "filing_date": date0,
        "S0": S0,
        "S5": closes[i5],
        "ret1": ret1,
        "ret5": ret5,
        "max_drop": max_drop,
        "roi_itm": roi_itm,
        "roi_atm": roi_atm,
        "roi_otm5": roi_otm5,
        "roi_otm10": roi_otm10,
    }
    summary_rows.append(row)
    
    print(f"{ticker:5} | {c['company'][:15]:15} | S0=${S0:6.2f} -> S5=${closes[i5]:6.2f} | 5D Ret: {ret5:+6.1f}% (Max Drop: {max_drop:+6.1f}%) | ATM: {roi_atm:+6.1f}% | 10% OTM: {roi_otm10:+6.1f}%")

print("=" * 105)
with open("c:/projects/GQHacks/notebooks/ten_cases_backtest_results.json", "w") as f:
    json.dump(summary_rows, f, indent=2)

print("Saved detailed backtest results to ten_cases_backtest_results.json")
