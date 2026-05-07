#!/usr/bin/env python3
"""
Pull BLS Average Price Data series for the curated core staples basket.

Two area codes are pulled in parallel for each item:
  0000 = U.S. city average
  0100 = Northeast urban (closest available proxy for NYC; BLS does not
         publish item-level Average Price series at the New York-Newark CBSA
         level -- only CPI indexes are published there).

Output: data/processed/bls_average_prices.csv
        data/processed/bls_average_prices.json

Notes on coverage:
  Some Northeast item series are sparser than the U.S.-average equivalent
  because BLS suppresses values when the regional sample size is too small.
  The script preserves whatever the API returns and the dashboard handles
  missing months gracefully.
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

# Curated core staples basket. Each tuple = (BLS item code, human label, basket category).
ITEMS = [
    ("701111", "Flour, white, all-purpose, lb",          "Cereals/bakery"),
    ("701312", "Rice, white, long grain, uncooked, lb",  "Cereals/bakery"),
    ("701322", "Spaghetti and macaroni, lb",             "Cereals/bakery"),
    ("702111", "Bread, white, pan, lb",                  "Cereals/bakery"),
    ("702212", "Bread, whole wheat, pan, lb",            "Cereals/bakery"),
    ("703112", "Ground beef, 100% beef, lb",             "Meats/poultry/fish/eggs"),
    ("704111", "Bacon, sliced, lb",                      "Meats/poultry/fish/eggs"),
    ("706111", "Chicken, fresh, whole, lb",              "Meats/poultry/fish/eggs"),
    ("706211", "Chicken breast, bone-in, lb",            "Meats/poultry/fish/eggs"),
    ("FF1101", "Chicken breast, boneless, lb",           "Meats/poultry/fish/eggs"),
    ("707111", "Tuna, light, chunk, lb",                 "Meats/poultry/fish/eggs"),
    ("708111", "Eggs, grade A, large, dozen",            "Meats/poultry/fish/eggs"),
    ("709112", "Milk, fresh, whole, fortified, gallon",  "Dairy"),
    ("709213", "Milk, fresh, low-fat, gallon",           "Dairy"),
    ("710111", "Butter, salted, grade AA, stick, lb",    "Dairy"),
    ("710212", "Cheddar cheese, natural, lb",            "Dairy"),
    ("710411", "Ice cream, prepackaged, half gallon",    "Dairy"),
    ("711111", "Apples, Red Delicious, lb",              "Fruits/vegetables"),
    ("711211", "Bananas, lb",                            "Fruits/vegetables"),
    ("711311", "Oranges, Navel, lb",                     "Fruits/vegetables"),
    ("712112", "Potatoes, white, lb",                    "Fruits/vegetables"),
    ("712311", "Tomatoes, field grown, lb",              "Fruits/vegetables"),
    ("712404", "Onions, dry yellow, lb",                 "Fruits/vegetables"),
    ("714233", "Beans, dried, lb",                       "Other food at home"),
    ("716141", "Peanut butter, creamy, lb",              "Other food at home"),
    ("717311", "Coffee, 100%, ground roast, lb",         "Other food at home"),
    ("717114", "Cola, nondiet, 2 liters",                "Nonalcoholic beverages"),
]

AREAS = {
    "0000": "U.S. city average",
    "0100": "Northeast urban",
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def main() -> int:
    end_year = datetime.now().year
    start_year = end_year - 9  # 10-year window inclusive (BLS free-tier cap)

    series_ids = []
    series_meta = {}
    for code, label, category in ITEMS:
        for area_code, area_label in AREAS.items():
            sid = f"APU{area_code}{code}"
            series_ids.append(sid)
            series_meta[sid] = {
                "item_code": code,
                "label": label,
                "category": category,
                "area_code": area_code,
                "area_label": area_label,
            }

    # BLS unregistered limit is 25 series per request. Chunk.
    chunk_size = 25
    chunks = [series_ids[i:i + chunk_size] for i in range(0, len(series_ids), chunk_size)]

    rows = []
    for i, chunk in enumerate(chunks, 1):
        print(f"[{i}/{len(chunks)}] Fetching {len(chunk)} series for {start_year}-{end_year}", file=sys.stderr)
        result = fetch(chunk, start_year, end_year)
        if result.get("status") != "REQUEST_SUCCEEDED":
            print(f"BLS API error: {result.get('status')}", file=sys.stderr)
            for m in result.get("message", []):
                print(f"  {m}", file=sys.stderr)
            return 1
        for series in result["Results"]["series"]:
            sid = series["seriesID"]
            meta = series_meta[sid]
            for obs in series["data"]:
                if obs["period"] == "M13":
                    continue
                try:
                    value = float(obs["value"])
                except (ValueError, TypeError):
                    continue
                if value <= 0:
                    continue
                month = int(obs["period"][1:])
                year = int(obs["year"])
                rows.append({
                    "series_id": sid,
                    "item_code": meta["item_code"],
                    "label": meta["label"],
                    "category": meta["category"],
                    "area_code": meta["area_code"],
                    "area_label": meta["area_label"],
                    "year": year,
                    "month": month,
                    "date": f"{year:04d}-{month:02d}-01",
                    "value": value,
                })

    rows.sort(key=lambda r: (r["item_code"], r["area_code"], r["date"]))

    csv_path = OUT_DIR / "bls_average_prices.csv"
    with csv_path.open("w") as f:
        f.write("series_id,item_code,label,category,area_code,area_label,year,month,date,value\n")
        for r in rows:
            label_q = '"' + r["label"].replace('"', '""') + '"'
            cat_q = '"' + r["category"] + '"'
            area_q = '"' + r["area_label"] + '"'
            f.write(f'{r["series_id"]},{r["item_code"]},{label_q},{cat_q},{r["area_code"]},{area_q},{r["year"]},{r["month"]},{r["date"]},{r["value"]}\n')

    items_meta = [{"item_code": code, "label": label, "category": category} for code, label, category in ITEMS]
    json_path = OUT_DIR / "bls_average_prices.json"
    with json_path.open("w") as f:
        json.dump({
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source": "BLS Public API v2 Average Price Data, areas 0000 (U.S. city avg) and 0100 (Northeast urban)",
            "items": items_meta,
            "areas": AREAS,
            "data": rows,
        }, f, indent=2)

    print(f"Wrote {len(rows)} observations to {csv_path}", file=sys.stderr)
    print(f"Wrote {json_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
