import requests

HEADERS = {'User-Agent': 'GQHacksResearch student@ufl.edu'}

def inspect_cik(name, cik, dates):
    url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        print(f"Error {r.status_code} for {name}")
        return
    rec = r.json().get('filings', {}).get('recent', {})
    forms = rec.get('form', [])
    fdates = rec.get('filingDate', [])
    accs = rec.get('accessionNumber', [])
    docs = rec.get('primaryDocument', [])
    items_list = rec.get('items', [])
    
    print(f"\n--- {name} (CIK {cik}) ---")
    for i in range(len(forms)):
        if '8-K' in forms[i]:
            fd = fdates[i]
            if any(d in fd for d in dates):
                acc = accs[i].replace('-', '')
                doc = docs[i]
                items = items_list[i] if i < len(items_list) else ''
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
                print(f"Date: {fd} | Form: {forms[i]} | Items: {items}")
                print(f"  URL: {doc_url}")

inspect_cik("Lordstown (RIDE)", 1759546, ["2021-06"])
inspect_cik("Canoo (GOEV)", 1750153, ["2021-04", "2021-05"])
inspect_cik("TuSimple (TSP)", 1823593, ["2022-10", "2022-11"])

# American Apparel (historical file partition)
r = requests.get("https://data.sec.gov/submissions/CIK0001338801.json", headers=HEADERS).json()
for f in r.get("filings", {}).get("files", []):
    r_old = requests.get(f"https://data.sec.gov/submissions/{f['name']}", headers=HEADERS).json()
    forms = r_old.get("form", [])
    dates = r_old.get("filingDate", [])
    accs = r_old.get("accessionNumber", [])
    docs = r_old.get("primaryDocument", [])
    items_list = r_old.get("items", [])
    print("\n--- American Apparel (Historical Partition) ---")
    for i in range(len(forms)):
        if "8-K" in forms[i] and "2014-06" in dates[i]:
            acc = accs[i].replace("-", "")
            items = items_list[i] if i < len(items_list) else ""
            print(f"Date: {dates[i]} | Form: {forms[i]} | Items: {items}")
            print(f"  URL: https://www.sec.gov/Archives/edgar/data/1338801/{acc}/{docs[i]}")

