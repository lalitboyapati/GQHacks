"""Find the exact SEC 8-K filings for the 10 small-cap executive departure events."""

import json
import re
import requests
from datetime import datetime, timedelta

HEADERS = {"User-Agent": "GQHacksResearch student@ufl.edu"}

CASES = [
    {
        "company": "American Apparel",
        "ticker": "APP",
        "cik": "0001338801",  # American Apparel Inc
        "operator": "Dov Charney (Founder & CEO)",
        "date": "2014-06-18",
    },
    {
        "company": "LendingClub",
        "ticker": "LC",
        "cik": "0001409970",
        "operator": "Renaud Laplanche (Founder & CEO)",
        "date": "2016-05-09",
    },
    {
        "company": "Blue Apron",
        "ticker": "APRN",
        "cik": "0001701114",
        "operator": "Matthew Wadiak (Co-Founder & COO)",
        "date": "2017-07-27",
    },
    {
        "company": "Overstock.com",
        "ticker": "OSTK",
        "cik": "0001130713",
        "operator": "Patrick Byrne (Founder & CEO)",
        "date": "2019-08-22",
    },
    {
        "company": "Nikola Corporation",
        "ticker": "NKLA",
        "cik": "0001731289",
        "operator": "Trevor Milton (Founder & Exec Chairman)",
        "date": "2020-09-20",
    },
    {
        "company": "Canoo Inc.",
        "ticker": "GOEV",
        "cik": "0001750153",
        "operator": "Ulrich Kranz (Co-Founder & CEO)",
        "date": "2021-04-30",
    },
    {
        "company": "Lordstown Motors",
        "ticker": "RIDE",
        "cik": "0001759546",
        "operator": "Steve Burns (CEO) & Julio Rodriguez (CFO)",
        "date": "2021-06-14",
    },
    {
        "company": "Workhorse Group",
        "ticker": "WKHS",
        "cik": "0001425287",
        "operator": "Duane Hughes (CEO)",
        "date": "2021-07-29",
    },
    {
        "company": "Beyond Meat",
        "ticker": "BYND",
        "cik": "0001655210",
        "operator": "Doug Ramsey (COO), Bernie Adcock (CSCO)",
        "date": "2022-09-20",
    },
    {
        "company": "TuSimple Holdings",
        "ticker": "TSP",
        "cik": "0001823593",
        "operator": "Dr. Xiaodi Hou (Co-Founder, CEO & CTO)",
        "date": "2022-10-30",
    },
]

def find_filing_for_case(case):
    cik_str = case["cik"].zfill(10)
    cik_int = int(case["cik"])
    event_date = datetime.strptime(case["date"], "%Y-%m-%d")
    
    url = f"https://data.sec.gov/submissions/CIK{cik_str}.json"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}
        
    data = r.json()
    filings = data.get("filings", {})
    recent = filings.get("recent", {})
    
    # Also check older files if available in files list
    all_forms = []
    
    def process_file_records(rec):
        forms = rec.get("form", [])
        filing_dates = rec.get("filingDate", [])
        report_dates = rec.get("reportDate", [])
        acc_nums = rec.get("accessionNumber", [])
        primary_docs = rec.get("primaryDocument", [])
        items_list = rec.get("items", [])
        
        matches = []
        for i in range(len(forms)):
            if forms[i] in ("8-K", "8-K/A"):
                f_date = filing_dates[i]
                dt_f = datetime.strptime(f_date, "%Y-%m-%d")
                # Look within window (-3 days to +7 days of event date)
                if abs((dt_f - event_date).days) <= 7:
                    acc = acc_nums[i]
                    acc_clean = acc.replace("-", "")
                    doc = primary_docs[i]
                    items = items_list[i] if i < len(items_list) else ""
                    doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}"
                    matches.append({
                        "form": forms[i],
                        "filing_date": f_date,
                        "report_date": report_dates[i],
                        "accession": acc,
                        "items": items,
                        "url": doc_url
                    })
        return matches

    found = process_file_records(recent)
    
    # If not found in recent, check older historical partition files
    if not found:
        older_files = filings.get("files", [])
        for f_info in older_files:
            f_name = f_info.get("name")
            if f_name:
                f_url = f"https://data.sec.gov/submissions/{f_name}"
                res_older = requests.get(f_url, headers=HEADERS, timeout=15)
                if res_older.status_code == 200:
                    found = process_file_records(res_older.json())
                    if found:
                        break

    return found

print("=" * 75)
print(" SEARCHING SEC EDGAR 8-K FILINGS FOR THE 10 KEY OPERATOR EXITS")
print("=" * 75)

results = []
for case in CASES:
    print(f"\nSearching: {case['company']} ({case['ticker']}) - Event Date: {case['date']}...")
    filings = find_filing_for_case(case)
    if isinstance(filings, list) and filings:
        match = filings[0]
        print(f"  [FOUND] Form: {match['form']} | Filing Date: {match['filing_date']} | Items: {match['items']}")
        print(f"  Doc URL: {match['url']}")
        results.append({
            "case": case,
            "match": match
        })
    else:
        print(f"  [NOT FOUND] Filings: {filings}")
        results.append({
            "case": case,
            "match": None
        })

print("\n" + "=" * 75)
print(f" SUMMARY: Located {sum(1 for r in results if r['match'])} / {len(CASES)} 8-K Filings")
print("=" * 75)

with open(r"c:\projects\GQHacks\notebooks\ten_departures_filings.json", "w") as f:
    json.dump(results, f, indent=2)
