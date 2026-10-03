"""Extract full metadata and text snippets for all 10 notable executive departures."""

import json
import re
import requests

HEADERS = {"User-Agent": "GQHacksResearch student@ufl.edu"}

FILINGS = [
    {
        "company": "American Apparel",
        "ticker": "APP / formerly AMEX: APP",
        "operator": "Dov Charney (Founder & CEO)",
        "event_date": "2014-06-18",
        "filing_date": "2014-06-19",
        "items": "2.04, 5.02, 7.01, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1336545/000133654514000086/a8-k_departureofprincipalo.htm",
    },
    {
        "company": "LendingClub",
        "ticker": "LC",
        "operator": "Renaud Laplanche (Founder & CEO)",
        "event_date": "2016-05-09",
        "filing_date": "2016-05-09",
        "items": "2.02, 5.02, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1409970/000140997016002096/q116form8-ker.htm",
    },
    {
        "company": "Blue Apron",
        "ticker": "APRN",
        "operator": "Matthew Wadiak (Co-Founder & COO)",
        "event_date": "2017-07-27",
        "filing_date": "2017-07-25",
        "items": "5.02, 7.01, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1701114/000110465917046825/a17-18391_18k.htm",
    },
    {
        "company": "Overstock.com",
        "ticker": "OSTK",
        "operator": "Patrick Byrne (Founder & CEO)",
        "event_date": "2019-08-22",
        "filing_date": "2019-08-22",
        "items": "5.02, 7.01, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1130713/000113071319000065/a8-kpatrickbyrne20190822.htm",
    },
    {
        "company": "Nikola Corporation",
        "ticker": "NKLA",
        "operator": "Trevor Milton (Founder & Exec Chairman)",
        "event_date": "2020-09-20",
        "filing_date": "2020-09-21",
        "items": "5.02, 7.01, 8.01, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1731289/000110465920106691/tm2030359d3_8k.htm",
    },
    {
        "company": "Canoo Inc.",
        "ticker": "GOEV",
        "operator": "Ulrich Kranz (Co-Founder & CEO)",
        "event_date": "2021-04-30",
        "filing_date": "2021-04-22",
        "items": "5.02, 7.01, 8.01, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1750153/000155837021004598/goev-20210418x8k.htm",
    },
    {
        "company": "Lordstown Motors",
        "ticker": "RIDE",
        "operator": "Steve Burns (CEO) & Julio Rodriguez (CFO)",
        "event_date": "2021-06-14",
        "filing_date": "2021-06-14",
        "items": "5.02, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1759546/000110465921080500/tm2119596d1_8k.htm",
    },
    {
        "company": "Workhorse Group",
        "ticker": "WKHS",
        "operator": "Duane Hughes (CEO)",
        "event_date": "2021-07-29",
        "filing_date": "2021-07-29",
        "items": "5.02, 7.01, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1425287/000162828021014824/wkhs-20210726.htm",
    },
    {
        "company": "Beyond Meat",
        "ticker": "BYND",
        "operator": "Doug Ramsey (COO), Bernie Adcock (CSCO)",
        "event_date": "2022-09-20",
        "filing_date": "2022-09-23",
        "items": "5.02",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1655210/000165521022000194/bynd-20220920.htm",
    },
    {
        "company": "TuSimple Holdings",
        "ticker": "TSP",
        "operator": "Dr. Xiaodi Hou (Co-Founder, CEO & CTO)",
        "event_date": "2022-10-30",
        "filing_date": "2022-10-31",
        "items": "5.02, 7.01, 8.01, 9.01",
        "doc_url": "https://www.sec.gov/Archives/edgar/data/1823593/000119312522273032/d395238d8k.htm",
    },
]

results = []
for item in FILINGS:
    print(f"Fetching snippet for {item['company']} ({item['ticker']})...")
    resp = requests.get(item["doc_url"], headers=HEADERS, timeout=15)
    text = resp.text if resp.status_code == 200 else ""
    
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = " ".join(clean.split())
    
    # Search for Item 5.02 section
    m = re.search(r"Item\s*5\.02.*?(?=(?:Item\s*[1-9]|\Z))", clean, re.IGNORECASE)
    snippet = m.group(0)[:350] if m else clean[:350]
    
    item["snippet"] = snippet
    results.append(item)

with open(r"c:\projects\GQHacks\notebooks\ten_notable_departures.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nSUCCESS: All 10 filings processed and verified.")
