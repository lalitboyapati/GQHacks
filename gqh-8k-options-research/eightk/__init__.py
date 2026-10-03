"""8-K disclosure-advantage research harness.

Tests whether SEC Form 8-K filings carry tradable information that the
options market has not already priced, across three disclosure families:

  * **Executive change** (Item 5.02) — officer departures at small/mid-cap
    issuers, where analyst coverage is thin and the reaction may be slow.
  * **Efficiency plan** (Items 2.05 / 2.06) — restructuring filings whose
    text reveals large upfront charges against savings that arrive years
    later, a mismatch that headlines usually compress away.
  * **Disclosure novelty** — whether a filing genuinely reveals something
    new or merely re-files a press release the market already saw, which
    determines whether event-rich option premium was ever justified.

The event layer is sourced from SEC EDGAR (free, exact acceptance
timestamps, full filing text) with Massive as an optional accelerator; the
pricing layer runs on modeled options by default and on real Databento OPRA
quotes when a budget is granted.
"""

__version__ = "0.1.0"
