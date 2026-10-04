# Read the readout: small-cap biotech clinical-trial 8-Ks, long/short with an option hedge

*Gator Quant Hacks 2026 · Trade the 8-K · category `clinical_trial_results` · library strategies 3 (protective put) and 1 (long call, hedging a short) · universe: all 1,499 SIC 2834/2836 filers by CIK, dead names included · pre-registered in `STRATEGY_PLAN.md`; `run_study(start, end)` reproduces everything on any window.*

<div class="glance">
<div><b>1,140 / 333</b><span>readout 8-Ks, in-sample 2024–25 / out-of-sample 2026</span></div>
<div><b>ρ = 0.38</b><span>Jev sentiment vs day-0 move; 0.75 vs blind hand labels</span></div>
<div><b>−1.1% / −4.0%</b><span>rule vs placebo at 5 sessions, in / out of sample</span></div>
<div><b>−23%</b><span>cost of the same put the evening after the news vs before</span></div>
<div><b>$548</b><span>median capacity per trade (hedge-leg volume)</span></div>
</div>

## 1 · Hypothesis

A small-cap biotech is one or two drug programs; a readout re-prices the whole company, and the 8-K is where it is disclosed. Three claims:

1. **The text carries the signal.** Jev (`jev-1.13.0`, pinned) can grade the masked press release on a five-level scale.
2. **The market under-reacts by the close of the 8-K session**, so good readouts drift up and bad ones down. Long stock + put on under-reacted positives, short stock + call on under-reacted negatives.
3. **The hedge is cheapest right after the event**, because implied volatility collapses once the result is out. That is the category-to-strategy link.

The mechanism is concentration, and disclosure shows it: in 2024–25 LLY, JNJ, MRK, PFE, AMGN, BMY, GILD, REGN, VRTX, BIIB and MRNA filed **zero** `clinical_trial_results` 8-Ks (ABBV one). The top-100 universe would hold no events.

## 2 · Method

| | |
|---|---|
| **Events** | One per accession, filer matched on CIK. EDGAR acceptance minute (69% pre-market, 27% after the close) sets `t_0`, the first session at whose **close** the 8-K was public; entry at that close. Jev's announcement date sets the news session; `t_pre` is the session before it, so `S_pre` and the implied move are pre-news. |
| **Classifier** | Nine typed questions per filing in one request: new human readout, first disclosure, five-level outcome (`sentiment = (score − 2)/2`), primary endpoint met, safety signal, next step, phase, lead asset, big-pharma partner, announcement date. Company, ticker and drug codes masked. |
| **Rule** | `expected = BETA × sentiment × IM`, IM = pre-news 1-month ATM straddle ÷ spot (BETA = 0.78, fitted in-sample, frozen). Trade when P(readout) ≥ 0.7, P(new) ≥ 0.6, \|sentiment\| ≥ 0.5, no safety signal on longs, and `r0` is short of 0.5 × expected. 10%-OTM, 21–45-day hedge. |
| **Layers** | *Signal*: bare stock, every gated event (n = 94 / 31). *Trade*: stock + hedge where the leg is quoted on `t_0` (n = 51 / 24); marks = NBBO mid → last trade → intrinsic at expiry. |
| **Controls** | Placebo (same names, random non-event sessions, random direction); sign-shuffle; momentum baseline (follow `r0`, no Jev); stale readouts; 2026 out-of-sample with everything frozen; the sealed window. 95% bootstrap intervals. |
| **Exit, costs** | Time stop `H*` (in-sample peak, frozen), earlier if the gap closes or the filer files again; the option is the stop. Real quoted spreads, 10 bp stock, 5/25/75% borrow on shorts. |

<div class="row">
<figure><img src="figures/paths_by_sentiment.png"><figcaption><b>Fig. 1a · In-sample.</b> Cumulative return from the pre-news close by Jev sentiment, 586 new readouts, 95% bands. The reaction is complete at the entry close (session 0).</figcaption></figure>
<figure><img src="figures/paths_by_sentiment_out_of_sample.png"><figcaption><b>Fig. 1b · Out-of-sample 2026.</b> 184 readouts never touched in-sample: the day-0 separation replicates, the drift does not appear.</figcaption></figure>
</div>

## 3 · Results

### 3.1 · The classifier works

- Spearman 0.38 with the day-0 return (n = 586); mean `r0` by level −31%, −26%, +3%, +12%, +26%. ρ = 0.51 above the median Jev confidence, 0.18 below.
- 60 filings hand-labelled blind to Jev: ρ = 0.75, 98% within one level; P(met primary) 0.89 when the reader said met, 0.02 when not. Unmasking the text changes 1% of directions.
- Dose-response: slope of `r0` on sentiment 0.41 [0.23, 0.61] micro, 0.38 small, 0.16 [0.08, 0.27] mid+; 0.54 for lead assets vs 0.30; 0.14 for stale readouts. Biotech median |`r0`| 14.0% vs 1.5% for its big-pharma partner on the same day (n = 34).

### 3.2 · The strategy does not: nothing is left after the entry close

| Signed return per $1, events − placebo (%) | h=1 | h=2 | h=3 | h=5 | h=10 | h=21 | h=42 | h=63 |
|---|---|---|---|---|---|---|---|---|
| **In-sample** signal layer (n = 94: 74 long / 20 short) | −0.1 | −0.8 | −1.0 | −1.1 | −3.0 | −5.8 | −9.8 | −7.8 |
| In-sample trade layer, hedged (n = 51) | −1.2 | −1.2 | −0.7 | +1.6 | +1.6 | +0.5 | −10.8 | −7.1 |
| **Out-of-sample** signal layer (n = 31: 26 / 5) | −2.2* | −3.7* | −4.6* | −4.0 | −6.2 | −4.1 | +3.3 | +5.3 |
| Out-of-sample trade layer, hedged (n = 24) | −2.6* | −2.7* | −3.1* | −4.6* | −2.4 | +0.1 | +3.1 | +1.0 |
| *Variant:* follow Jev's sign, no day-0 gate (in / out, n = 212 / 64) | +0.6 / −1.2 | −0.3 / −2.1 | −0.7 / −2.6 | +0.4 / −1.8 | −0.5 / −4.7 | −1.3 / −5.8 | −2.3 / +2.6 | −1.4 / +5.5 |
| *Exploratory:* over-reaction, `r0` beyond expected (n = 87 / 25) | +1.2 / +2.8 | +0.3 / +1.9 | −0.4 / +2.2 | +2.5 / +3.6 | +2.2 / −0.3 | +3.6 / −5.7 | +5.5 / +4.8 | +5.5 / +6.5 |

*\* = 95% bootstrap CI excludes zero (intervals in notebook §9, §13; typical half-width ±3% at 5 sessions, ±7% at 21). Cells at 42/63 are past the hedge's expiry and are moved by a few short squeezes.*

- The gate selects events where the market **disagreed** with the text (mean `r0` −9% on longs, +13% on shorts), and the market was right (Fig. 3). Random directions on the same events beat the rule 77% (in) and 94% (out) of the time; the no-Jev momentum baseline does as well (+1.6% in, +2.6% out, n.s.).
- Following Jev's sign with no gate is also flat: the information is real, but it is in the price by the close (Fig. 2).
- `H*` = 5 is the best of eight in-sample horizons, hence optimistic; the out-of-sample column is the honest read.

<div class="row">
<figure><img src="figures/minute_event_study.png"><figcaption><b>Fig. 2 · Who moves first.</b> Minute path around EDGAR acceptance (n = 164). Positives are mostly priced before the 8-K prints; negatives jump at acceptance. Either way the move is over hours before the close.</figcaption></figure>
<figure><img src="figures/paths_traded.png"><figcaption><b>Fig. 3 · What the rule buys.</b> Traded events, signal layer. Positives that fell on day 0 keep falling; negatives that rose keep rising.</figcaption></figure>
</div>

### 3.3 · The hedge: cheaper after the news, and it buys the tail, not the mean

- ATM IV: median 117% on `t_pre`, 100% on `t_0` (down in 65% of readouts). Like for like, a put 10% below that day's spot at the measured ATM vol costs 8.6% of spot the evening before the news and 6.3% after (cheaper in 75% of cases, median −23%); the leg actually listed on `t_0` cost 3.8%.
- Against the full pre-news straddle the median readout moves *less* than implied (0.6 at one session, 0.8 at 21; means 0.8–1.1 from the right tail). A square-root-of-time benchmark would say the opposite and is wrong for a scheduled jump.
- At the 5-session stop the long book's worst decile goes from −16% to −9% and the worst trade from −29% to −10% (n = 33); strike-implied max loss 15% of notional. The mean is unchanged.

### 3.4 · Sensitivity

<figure><img src="figures/sensitivity_heatmap_compact.png" style="width:62%; margin:0 auto;"><figcaption><b>Fig. 4 · Selected rows of the 28 × 8 grid</b> (full grid in notebook §14). No threshold, gate variant, confidence cut, size, entry time, category definition, OTM distance or hedge expiry turns the rule positive at 21 sessions; entering 30 minutes after acceptance is worse. 224 overlapping cells imply about 11 chance stars, so the grid is read for its sign pattern. The one positive cell, continuation after an <i>over</i>-reaction (+3.6% at 21 in-sample, n.s.), reverses out-of-sample (−5.7%).</figcaption></figure>

## 4 · What would break it, and what broke it

<div class="verdict"><p><b>Verdict.</b> Claim 1 held everywhere. Claim 2 failed in-sample, out-of-sample and in every neighbouring specification. Claim 3 holds, as a hedge for a position one already has.</p></div>

- **Coverage.** 94 trades → 51 with a quoted 1-month hedge → 9 through the pre-registered liquidity gate (2 of 31 out-of-sample). Most micro-caps have no chain.
- **Costs and capacity.** Median quoted spread 53% of mid, about 2% of notional each way: +0.9% gross at 5 sessions becomes −3.2% net. 10% of day-0 hedge-leg volume is $548 per trade, about $2M a year in the whole universe; the stock would allow $8M.
- **Model and data.** Jev drift (pinned version, committed answer cache); same-day financings; reverse splits (excluded from the trade layer); no borrow data (grid moves the 21-session result by about a point).
- **Sealed-window prediction, on record:** no edge over placebo at any horizon; the day-0 correlation, the size dose-response and the post-event IV drop replicate.

## 5 · How we would trade it

Not as a directional 8-K trade: no horizon or specification survives costs. What is usable is **Jev as a same-day classifier** (sign of the day-0 move right 71% of the time on directional readouts, from the masked text in one request) and **the post-event put as the hedge**: hold the stock, buy the 10%-OTM 1-month put at the `t_0` close rather than before the readout, cross the spread, size to the hedge leg's volume. The full desk specification is in notebook §15.
