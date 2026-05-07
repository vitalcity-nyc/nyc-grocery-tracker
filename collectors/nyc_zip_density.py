#!/usr/bin/env python3
"""
Build a ZIP-code (Modified ZCTA) choropleth of full-supermarket density
for New York City.

Inputs:
  - data/processed/nyc_food_stores.geojson  (must already exist; created by
    nyc_food_stores.py). Stores are matched to a Modified ZCTA via the
    operator-filed ZIP code.
  - NYC Modified ZCTAs from data.cityofnewyork.us (resource pri4-ifjk),
    which includes a population estimate and the underlying ZIP list per
    MODZCTA polygon.

Output:
  - data/processed/nyc_zip_density.geojson  - one feature per MODZCTA with:
      modzcta, label, pop_est, supermarket_count, all_store_count,
      supermarkets_per_10k

Notes:
  - "Full supermarket" here = is_supermarket=True AND sqft >= 5000.
  - MODZCTAs collapse sparse ZIPs (e.g. 10119 rolls into 10001). The script
    builds a ZIP-to-MODZCTA lookup from the polygon file's `zcta` field.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = REPO_ROOT / "data" / "processed"
_MERGED = PROCESSED / "nyc_food_stores_merged.geojson"
_BASE = PROCESSED / "nyc_food_stores.geojson"
STORES_PATH = _MERGED if _MERGED.exists() else _BASE
OUT_PATH = PROCESSED / "nyc_zip_density.geojson"

MODZCTA_URL = "https://data.cityofnewyork.us/resource/pri4-ifjk.geojson?$limit=300"


def fetch_modzcta():
    req = urllib.request.Request(MODZCTA_URL, headers={"User-Agent": "nyc-grocery-tracker"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    if not STORES_PATH.exists():
        print(f"Missing {STORES_PATH}; run nyc_food_stores.py first", file=sys.stderr)
        return 1

    stores = json.load(open(STORES_PATH))
    modzcta_geo = fetch_modzcta()

    # Build zip -> modzcta map and pop_est lookup
    zip_to_mod = {}
    pop_by_mod = {}
    label_by_mod = {}
    for f in modzcta_geo["features"]:
        p = f["properties"]
        m = p.get("modzcta")
        if not m:
            continue
        try:
            pop = int(float(p.get("pop_est") or 0))
        except (ValueError, TypeError):
            pop = 0
        pop_by_mod[m] = pop
        label_by_mod[m] = p.get("label") or m
        for z in (p.get("zcta") or "").split(","):
            z = z.strip()
            if z:
                zip_to_mod[z] = m
        # also map the modzcta code to itself
        zip_to_mod[m] = m

    # Aggregate stores per modzcta
    full_super_count = {}
    all_store_count = {}
    unmatched_stores = 0
    for f in stores["features"]:
        p = f["properties"]
        z = (p.get("zip") or "").strip()
        m = zip_to_mod.get(z)
        if not m:
            unmatched_stores += 1
            continue
        all_store_count[m] = all_store_count.get(m, 0) + 1
        is_super = bool(p.get("is_supermarket"))
        sqft = p.get("sqft")
        source = p.get("source", "")
        # Count if either: passes filter AND >=5000 sqft, OR is OSM-tagged supermarket (no sqft)
        if is_super and ((sqft and sqft >= 5000) or source == "osm"):
            full_super_count[m] = full_super_count.get(m, 0) + 1

    # Build output GeoJSON
    out_features = []
    for f in modzcta_geo["features"]:
        p = f["properties"]
        m = p.get("modzcta")
        pop = pop_by_mod.get(m, 0)
        sup = full_super_count.get(m, 0)
        all_n = all_store_count.get(m, 0)
        per10k = (sup / pop * 10000) if pop > 0 else None
        out_features.append({
            "type": "Feature",
            "geometry": f["geometry"],
            "properties": {
                "modzcta": m,
                "label": label_by_mod.get(m, m),
                "pop_est": pop,
                "supermarket_count": sup,
                "all_store_count": all_n,
                "supermarkets_per_10k": round(per10k, 2) if per10k is not None else None,
            },
        })

    out = {
        "type": "FeatureCollection",
        "metadata": {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source_zcta": "NYC Modified ZCTAs (data.cityofnewyork.us pri4-ifjk)",
            "source_stores": "nyc_food_stores.geojson (NY State Ag & Markets)",
            "definition": "Full supermarket = is_supermarket AND sqft >= 5000",
            "unmatched_stores": unmatched_stores,
            "n_modzcta": len(out_features),
        },
        "features": out_features,
    }
    with OUT_PATH.open("w") as f:
        json.dump(out, f)
    print(f"Wrote {len(out_features)} MODZCTA polygons to {OUT_PATH}", file=sys.stderr)
    print(f"Unmatched stores: {unmatched_stores}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
