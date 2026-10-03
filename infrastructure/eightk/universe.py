"""The company universe under study: smaller, thinly covered, optionable US issuers.

The hypothesis being tested is specifically about *smaller* companies. A CEO
departure at a mega-cap is dissected by dozens of sell-side analysts within
minutes and priced into the options surface almost immediately; the same
event at a $3B issuer with four analysts covering it may take days to be
understood. MongoDB is the anchor case the research started from, so the
default list is built around names of that shape:

  * US-listed, so their 8-K filings are on EDGAR,
  * with listed options, so the structures are actually tradable,
  * roughly $100M-$20B market cap, and
  * clustered in sectors where leadership turnover and restructuring are
    frequent enough to produce a usable sample.

Delisted and acquired names are kept deliberately. Excluding them would
introduce survivorship bias precisely where it hurts most: a company whose
CEO left and which then collapsed into an acquisition is exactly the
observation the strategy needs to see.
"""

from __future__ import annotations

from pathlib import Path

#: Default research universe, grouped by sector for readability.
DEFAULT_UNIVERSE: dict[str, list[str]] = {
    "software_infra": [
        "MDB", "ESTC", "CFLT", "GTLB", "FSLY", "DOCN", "BOX", "PD", "ASAN",
        "SMAR", "ZUO", "TDC", "PRGS", "VRNS", "TENB", "RPD", "NCNO", "APPN",
        "SPT", "BL", "AI", "PATH", "DBX", "NTNX", "PEGA", "VERX", "FROG",
    ],
    "consumer_retail": [
        "ETSY", "W", "RH", "YETI", "CROX", "FIGS", "OLPX", "BBWI", "AEO",
        "URBN", "GPS", "JWN", "M", "KSS", "LEVI", "VSCO", "WOOF", "PRPL",
    ],
    "health_biotech": [
        "EXAS", "TDOC", "HIMS", "PGNY", "ACCD", "AMWL", "OSCR", "CLOV",
        "RXRX", "NTLA", "BEAM", "SDGR", "DOCS", "PHR", "EVH",
    ],
    "clean_energy_industrial": [
        "PLUG", "RUN", "ENPH", "CHPT", "BLNK", "QS", "FLNC", "AMRC", "SHLS",
        "ARRY", "NOVA", "WKHS", "HYLN", "MYRG",
    ],
    "fintech": [
        "AFRM", "UPST", "LC", "SOFI", "MQ", "PAYO", "OPRT", "ENVA", "TREE",
        "BILL", "PSFE", "DLO", "RELY",
    ],
    "media_internet": [
        "ROKU", "SNAP", "PINS", "YELP", "EB", "BMBL", "MTCH", "IAC", "ZIP",
        "CARG", "CARS", "TRIP", "YOU", "LYFT",
    ],
}


def default_tickers() -> list[str]:
    """Flattened, de-duplicated default universe."""
    seen: dict[str, None] = {}
    for group in DEFAULT_UNIVERSE.values():
        for ticker in group:
            seen.setdefault(ticker.upper(), None)
    return list(seen)


def load_tickers(spec: str | None) -> list[str]:
    """Resolve a universe specification into a ticker list.

    ``spec`` may be ``None`` or ``"default"`` for the built-in universe, a
    comma-separated list of symbols, a sector name from
    ``DEFAULT_UNIVERSE``, or a path to a file with one symbol per line.
    """
    if not spec or spec.strip().lower() in ("default", "all"):
        return default_tickers()

    spec = spec.strip()

    if spec.lower() in DEFAULT_UNIVERSE:
        return [t.upper() for t in DEFAULT_UNIVERSE[spec.lower()]]

    path = Path(spec)
    if path.exists() and path.is_file():
        tickers = []
        for line in path.read_text().splitlines():
            token = line.split("#", 1)[0].strip().upper()
            if token:
                tickers.append(token)
        return tickers

    return [t.strip().upper() for t in spec.split(",") if t.strip()]
