# Two ways to trade a company filing: factory disruptions checked by satellite, and drug-trial results read by an AI

*Gator Quant Hacks 2026 · Trade the 8-K. An 8-K is the form a public company must file when something material happens. We built two strategies around two kinds of 8-K. Strategy A: a company reports a fire, outage or shutdown at a plant, and we check NASA satellite heat data to see whether anything is actually still burning. Strategy B: a small biotech reports drug-trial results, and we have an AI model read the announcement and grade it. Both are fully scripted: give either one a start and end date and it reproduces every number below.*

<div class="glance">
<div><b>45 · 24 · 8</b><span>A: disruption filings found · used to build the strategy · held back to test it</span></div>
<div><b>11.5% vs 5.3%</b><span>A: move the options market expected vs the move that actually happened</span></div>
<div><b>+2.4%</b><span>A: extra return of the best trade over ordinary days, per $1 of stock</span></div>
<div><b>1,140 / 333</b><span>B: trial-result filings used to build the strategy / held back to test it</span></div>
<div><b>0.38 · −23%</b><span>B: how well the AI's grade tracks the stock move · how much cheaper the insurance is after the news</span></div>
</div>

## 1 · The idea, and what is new about it

Both strategies start from the same observation. When a company files an 8-K, the options market puts a price on how big the stock's reaction should be. Our question is whether an **outside source of information** — one the market is not using — says that price is wrong. The two strategies use different outside sources and bet in opposite directions.

<div class="two">
<div>
<p><b>A · Plant disruptions: the market braces for a disaster the satellite cannot see.</b> A filing about a plant fire or shutdown sounds alarming, and options traders price in a stock move of around 11% over the next month. NASA's FIRMS satellites detect heat on the ground every day. If the plant shows no lasting heat signature (nothing burning for 3 or more days) we call the event <code>brief</code>; if it does, <code>persistent</code>. Our claim: after a <code>brief</code> filing the stock is calmer than the market fears, so we should <i>sell</i> that over-priced protection — with a cap on our own downside.</p>
</div>
<div>
<p><b>B · Drug-trial results: the AI reads it right, the market catches up fast, and insurance gets cheaper after.</b> A small biotech is usually one or two drugs, so a trial result re-prices the whole company. Three claims: (1) an AI model (Jev) can read the announcement — with company and drug names hidden — and grade it from very bad to very good; (2) the stock has not fully moved by the end of the day the filing lands, so there is more to come; (3) once the result is out, the price of protective options drops, so hedging a position is cheaper <i>after</i> the news than before.</p>
</div>
</div>

**What is new.** Neither signal comes from market data: one is a satellite reading, the other is a language model reading the filing itself. Neither trade is the obvious "buy a call option and hope." A sells over-priced protection with a safety cap; B is a stock bet with insurance attached — and <i>when</i> to buy that insurance turned out to be the real finding.

## 2 · How we tested it

| | **A · Plant disruptions + satellite** | **B · Drug trials + AI reader** |
|---|---|---|
| **Finding events** | Searched 8-K text for plant fires, explosions, outages, shutdowns, storm damage and similar. Located each plant on a map, pulled the satellite heat record, and labelled each filing <code>brief</code>, <code>persistent</code> or <code>unknown</code> (no location or coverage). We trade <code>brief</code>; <code>persistent</code> is the comparison group. 55 industrial, materials and energy companies. | Every drug-trial-result 8-K from all 1,499 pharmaceutical and biotech filers, including companies that no longer exist (so we are not only looking at survivors). Entry is the market close on the first day the filing was public. |
| **The signal** | Did the satellite see heat at the site for 3 or more days after the filing? | Nine yes/no and multiple-choice questions put to the AI about each filing, scored into a single grade from −1 (clearly bad) to +1 (clearly good). |
| **The trade** | At the close on filing day, sell a one-month option package (an "iron condor") that profits if the stock stays within roughly ±5–10% and loses a fixed, known amount if it does not. Five simpler option strategies were tested alongside it. | If the grade is strongly positive or negative <i>and</i> the stock has moved less than half of what the market expected, buy (or short) the stock and attach a one-month protective option as insurance. |
| **Keeping ourselves honest** | Returns measured at fixed points (1 to 21 trading days, and option expiry). Every result compared against the same stocks on ordinary days with no filing. Error bars from resampling. A separate 2025 test period never used to design the strategy. Trading costs of 5% of the option price each way. Stress-tested across option strike, expiry, entry time and the 3-day heat rule. | Same ordinary-day comparison, plus: random-direction trades, a "just follow the day-one move" baseline with no AI, filings that merely repeated old data, a 2026 test period with every setting frozen, and a 224-cell grid of alternative settings. |

<div class="row">
<figure><img src="02_implied_vs_realized.png"><figcaption><b>Fig. 1 · A: what the market expected vs what happened.</b> Left: the one-month move priced in by options vs the typical actual move after a <code>brief</code> disruption filing. Right: actual ÷ expected by holding period, with the shaded error bands, for filing days (orange) and ordinary days (blue). Below 1.0 means the market over-estimated the move.</figcaption></figure>
<figure><img src="paths_by_sentiment.png"><figcaption><b>Fig. 2 · B: the AI's grade vs the stock.</b> Average stock path from the day before the news, grouped by the AI's grade (green = good, red = bad), across 586 trial results. The lines separate immediately and then stay flat: the AI is right about direction, and the market has fully reacted by the first close.</figcaption></figure>
</div>

## 3 · What we found

<div class="two">
<div>
<p><b>A · The edge is in the over-priced protection.</b> The actual move beat the expected move in only 13% of filings. Compared with ordinary days on the same stocks, the <b>iron condor earned +2.4% per $1 of stock</b> (7 trades), a cash-secured put +1.1% (12 trades), a plain call +0.8%; the covered call (−3.9%), collar (−4.8%) and protective put (−6.7%) all lost. The condor's advantage over ordinary days is statistically clear at 10 days and at expiry; the put and collar losses are clear at 21 days. The underlying "expected vs actual" ratio alone is not statistically decisive — the edge shows up in the profit of the right structure.</p>
<p><b>On the held-back 2025 data</b> (about 5 trades): the condor still made money at 21 days (+0.1% became +1.8%), but holding to expiry flipped from +2.0% to −1.7%, and so did the cash-secured put. After trading costs the condor is −0.8% at 21 days and +0.8% at expiry, with 22% of trades profitable at 21 days.</p>
</div>
<div>
<p><b>B · The edge is in the AI reader and in the timing of the insurance — not in the stock bet.</b> Claim 1 held everywhere: the AI's grade and the day-one stock move agree with a correlation of 0.38 across 586 results; against 60 filings graded by hand by someone who could not see the AI's answer, correlation 0.75 and 98% within one grade. The effect is bigger for the smallest companies (as it should be if one drug <i>is</i> the company) and almost absent for their large-pharma partners on the same day. Claim 2 failed: the stock bet lost 1.1% vs ordinary days in the design period and 4.0% in the 2026 test; random directions beat it 77% and 94% of the time; no alternative setting fixed it. Claim 3 held: option prices fell after the news in 65% of cases, and the same protective put cost 8.6% of the stock price the evening <i>before</i> the result and 6.3% <i>after</i> — cheaper 75% of the time, by 23% on average.</p>
</div>
</div>

<div class="row">
<figure><img src="03_structure_ranking.png"><figcaption><b>Fig. 3 · A: which option strategy worked.</b> Extra return over ordinary days for each strategy tested on <code>brief</code> disruption filings. Selling capped protection (the condor) comes out on top; strategies that are really just bets on the stock going up lose.</figcaption></figure>
<figure><img src="iv_crush.png"><figcaption><b>Fig. 4 · B: insurance is cheaper after the news.</b> Left: how much option prices changed from the day before the result to the day after (mostly down). Right: the cost of a protective option package before vs after; dots below the diagonal line are cases where it got cheaper.</figcaption></figure>
</div>

## 4 · What we expect on the judges' hidden test period

- **A.** The gap between the move the market expects and the move that happens should reappear on <code>brief</code> filings. The 21-day condor edge may hold weakly or not at all with only a handful of events; the hold-to-expiry result will likely flip sign again. If the satellite mis-labels a real disaster as <code>brief</code>, that trade loses — but only up to the capped amount.
- **B.** The stock bet will show no advantage over ordinary days at any holding period. The AI's accuracy, the "smaller company, bigger move" pattern, and the drop in option prices after the news will all reappear.
- Both pipelines take only a start and end date. The event lists, the AI model version, and every fitted number are frozen.

<div class="row">
<figure><img src="04_oos_and_costs.png"><figcaption><b>Fig. 5 · A: held-back data and costs.</b> Left: design-period vs 2025 returns at 21 days and at expiry for three strategies. Right: the condor's return before and after a 5% trading-cost assumption. The 21-day result survives the test period; the expiry result does not.</figcaption></figure>
<figure><img src="trade_layer_vs_placebo.png"><figcaption><b>Fig. 6 · B: the stock bet vs ordinary days.</b> Average profit of the drug-trial trades, with and without insurance, against ordinary days on the same stocks (shaded = error band). The two lines never separate — which is exactly what we predict for the hidden test.</figcaption></figure>
</div>

## 5 · Could you actually trade this?

<div class="two">
<div>
<p><b>A.</b> Yes, in small size. Enter at the close of filing day once the satellite label is in; one-month options, wings about 5% away from the stock price; take profits around days 10–21 rather than waiting for expiry. These stocks' options trade thinly (about 21 contracts on the legs we need), and trading costs erase the 21-day edge, so this is a modest, carefully-sized trade. Skip anything the satellite flags as <code>persistent</code> or cannot see.</p>
</div>
<div>
<p><b>B.</b> Not as a stock bet — the bid-ask spread on these tiny options averages 53% of the price, which turns a +0.9% gross gain into −3.2% net, and the volume caps each trade at about $548. What is usable: the AI as a same-day reader (right about direction 71% of the time) and the <b>timing of the insurance</b> — if you already hold the stock, buy the protective put at the close <i>after</i> the result, not before.</p>
</div>
</div>

<div class="verdict"><p><b>What a portfolio manager should take away.</b> Two independent outside signals, and two different places the edge turned up. For plant disruptions the satellite tells us the market is over-paying for protection, and a capped short-protection trade collects that — mid-horizon, before costs. For drug trials the AI is right about direction, but the market agrees within the day; the real saving is paying less for the hedge after the result is public. Both findings rest on small numbers of events, both are sensitive to trading costs, and both are stated with the holding period and the failure mode a desk would need to act on them.</p></div>
