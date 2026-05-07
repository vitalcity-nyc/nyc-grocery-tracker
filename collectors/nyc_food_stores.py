#!/usr/bin/env python3
"""
Pull every licensed retail food store in the five New York City counties
from the New York State Department of Agriculture and Markets dataset
hosted on data.ny.gov (resource 9a8c-vfzj).

Output:
  data/processed/nyc_food_stores.geojson   - one feature per store
  data/processed/nyc_food_stores.csv       - flat table

Classification by square footage (when reported):
  Large supermarket           10,000+ sqft
  Standard supermarket        5,000 - 9,999 sqft
  Small supermarket / grocer  2,500 - 4,999 sqft
  Corner store / specialty    under 2,500 sqft
  Size unknown                square_footage missing

Square footage is missing for roughly 23% of NYC stores. Stores with no
georeference are dropped (a small share of the file).
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "https://data.ny.gov/resource/9a8c-vfzj.json"
NYC_COUNTIES = ["NEW YORK", "BRONX", "KINGS", "QUEENS", "RICHMOND"]
COUNTY_TO_BOROUGH = {
    "NEW YORK":  "Manhattan",
    "BRONX":     "Bronx",
    "KINGS":     "Brooklyn",
    "QUEENS":    "Queens",
    "RICHMOND":  "Staten Island",
}


def classify(sqft):
    if sqft is None:
        return "Size unknown"
    if sqft >= 10000:
        return "Large supermarket"
    if sqft >= 5000:
        return "Standard supermarket"
    if sqft >= 2500:
        return "Small supermarket or grocer"
    return "Corner store or specialty"


def fetch_page(offset, limit):
    where = "county in('" + "','".join(NYC_COUNTIES) + "')"
    params = {
        "$where": where + " AND operation_type='Store'",
        "$limit": str(limit),
        "$offset": str(offset),
        "$order": "license_number",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "nyc-grocery-tracker"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def main() -> int:
    page_size = 5000
    offset = 0
    rows = []
    while True:
        page = fetch_page(offset, page_size)
        if not page:
            break
        rows.extend(page)
        print(f"Fetched {len(rows)} stores so far", file=sys.stderr)
        if len(page) < page_size:
            break
        offset += page_size

    features = []
    flat_rows = []
    skipped_no_geo = 0
    for r in rows:
        geo = r.get("georeference")
        if not geo or geo.get("type") != "Point":
            skipped_no_geo += 1
            continue
        lon, lat = geo["coordinates"]
        sqft_raw = r.get("square_footage")
        sqft = None
        if sqft_raw not in (None, ""):
            try:
                sqft = int(float(sqft_raw))
            except (ValueError, TypeError):
                sqft = None
        size_class = classify(sqft)
        county = (r.get("county") or "").upper()
        borough = COUNTY_TO_BOROUGH.get(county, "")
        addr_parts = [
            (r.get("street_number") or "").strip(),
            (r.get("street_name") or "").strip(),
        ]
        address = " ".join(p for p in addr_parts if p)
        props = {
            "license": r.get("license_number"),
            "name": r.get("dba_name") or r.get("entity_name") or "",
            "entity": r.get("entity_name") or "",
            "estab_type": r.get("estab_type") or "",
            "address": address,
            "city": r.get("city") or "",
            "zip": r.get("zip_code") or "",
            "borough": borough,
            "sqft": sqft,
            "size_class": size_class,
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })
        flat_rows.append({**props, "lon": lon, "lat": lat})

    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source": "NY State Dept of Agriculture and Markets, Retail Food Stores (data.ny.gov resource 9a8c-vfzj)",
            "filter": "operation_type=Store, NYC five counties",
            "store_count": len(features),
            "skipped_no_geo": skipped_no_geo,
        },
        "features": features,
    }
    geo_path = OUT_DIR / "nyc_food_stores.geojson"
    with geo_path.open("w") as f:
        json.dump(geojson, f)

    csv_path = OUT_DIR / "nyc_food_stores.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "license", "name", "entity", "estab_type", "address", "city",
            "zip", "borough", "sqft", "size_class", "lon", "lat",
        ])
        writer.writeheader()
        writer.writerows(flat_rows)

    print(f"Wrote {len(features)} stores to {geo_path}", file=sys.stderr)
    print(f"Wrote {csv_path}", file=sys.stderr)
    print(f"Skipped {skipped_no_geo} stores without georeference", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
