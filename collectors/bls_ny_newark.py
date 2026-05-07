#!/usr/bin/env python3
"""
Pull BLS Consumer Price Index series for the New York-Newark-Jersey City
CBSA (BLS area code S12A), focused on food-at-home and its 6 subgroups.

Output: data/processed/bls_ny_newark.csv
        data/processed/bls_ny_newark.json (long-form, ready for the dashboard)

Series IDs follow the BLS CU schema:
  CUUR  = Consumer Price Index, Urban, not seasonally adjusted
  S12A  = New York-Newark-Jersey City, NY-NJ-PA CBSA (BLS area code)
  SAF*  = food categories

If a subgroup is not published for NY-Newark in a given month
(BLS suppresses when sample is too small), the API returns no data
for that month and the script skips it cleanly.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SERIES = {
    "CUURS12ASA0":    "All items",
    "CUURS12ASAF1":   "Food",
    "CUURS12ASAF11":  "Food at home",
    "CUURS12ASEFV":   "Food away from home",
    "CUURS12ASAF111": "Cereals and bakery products",
    "CUURS12ASAF112": "Meats, poultry, fish, and eggs",
    "CUURS12ASAF113": "Dairy and related products",
    "CUURS12ASAF114": "Fruits and vegetables",
    "CUURS12ASAF115": "Nonalcoholic beverages",
    "CUURS12ASAF116": "Other food at home",
}

API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def fetch(series_ids, start_year, end_year):
    payload = json.dumps({
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    end_year = datetime.now().year
    start_year = end_year - 9  # rolling 10-year window (BLS free-tier cap)

    print(f"Fetching BLS series for {start_year}-{end_year}...", file=sys.stderr)
    result = fetch(list(SERIES.keys()), start_year, end_year)

    if result.get("status") != "REQUEST_SUCCEEDED":
        print(f"BLS API error: {result.get('status')}", file=sys.stderr)
        for m in result.get("message", []):
            print(f"  {m}", file=sys.stderr)
        return 1

    rows = []
    for series in result["Results"]["series"]:
        sid = series["seriesID"]
        label = SERIES.get(sid, sid)
        for obs in series["data"]:
            if obs["period"] == "M13":
                continue  # annual average, skip
            month = int(obs["period"][1:])
            year = int(obs["year"])
            try:
                value = float(obs["value"])
            except (ValueError, TypeError):
                continue
            rows.append({
                "series_id": sid,
                "label": label,
                "year": year,
                "month": month,
                "date": f"{year:04d}-{month:02d}-01",
                "value": value,
            })

    rows.sort(key=lambda r: (r["series_id"], r["date"]))

    csv_path = OUT_DIR / "bls_ny_newark.csv"
    with csv_path.open("w") as f:
        f.write("series_id,label,year,month,date,value\n")
        for r in rows:
            label_escaped = '"' + r["label"].replace('"', '""') + '"'
            f.write(f'{r["series_id"]},{label_escaped},{r["year"]},{r["month"]},{r["date"]},{r["value"]}\n')

    json_path = OUT_DIR / "bls_ny_newark.json"
    with json_path.open("w") as f:
        json.dump({
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source": "BLS Public API v2, area A101 (New York-Newark-Jersey City, NY-NJ-PA)",
            "series": SERIES,
            "data": rows,
        }, f, indent=2)

    print(f"Wrote {len(rows)} observations to {csv_path}", file=sys.stderr)
    print(f"Wrote {json_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
