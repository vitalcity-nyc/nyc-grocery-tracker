#!/usr/bin/env python3
"""
Merge the NY State retail food store file (filtered) with OpenStreetMap
shop=supermarket entries to catch new openings the state file misses.

Strategy
--------
1. Start with the state file as the base — it has square footage, which OSM
   lacks. Tag each store with `source = "ny_state"`.
2. For every OSM store tagged shop=supermarket, look for a state-file store
   within 80 meters that has a similar name. If found, mark the state record
   as `source = "both"` and copy the OSM `shop` tag onto it (useful as a
   secondary signal that the state record really is a supermarket).
3. OSM stores with no nearby match are emitted as new features tagged
   `source = "osm"`. They have no square footage; they are still rendered
   on the map (in a distinct style) so readers can see new openings.
4. OSM `shop=grocery` and `shop=convenience` are NOT injected as new
   stores -- only `shop=supermarket`. The state file already covers smaller
   stores comprehensively, and we want to avoid double-counting bodegas.

Output
------
data/processed/nyc_food_stores_merged.geojson  — superset for the map.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = REPO_ROOT / "data" / "processed"
STATE_PATH = PROCESSED / "nyc_food_stores.geojson"
OSM_PATH = PROCESSED / "osm_nyc_food_stores.geojson"
OUT_PATH = PROCESSED / "nyc_food_stores_merged.geojson"

MATCH_RADIUS_M = 80


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    rad = math.pi / 180
    dlat = (lat2 - lat1) * rad
    dlon = (lon2 - lon1) * rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def normalize_name(name):
    if not name:
        return ""
    s = name.upper()
    s = re.sub(r"#\d+", "", s)
    s = re.sub(r"\b(SUPERMARKET|MARKET|GROCERY|FOODS?|MART|STORE|CORP|INC|LLC|CO)\b", "", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main() -> int:
    state = json.load(open(STATE_PATH))
    osm = json.load(open(OSM_PATH))

    state_features = list(state["features"])
    # Tag base features
    for f in state_features:
        f["properties"]["source"] = "ny_state"
        f["properties"]["osm_shop"] = ""

    # Index state features by approximate grid for fast spatial lookup
    cell = 0.005  # ~500m
    grid = {}
    for i, f in enumerate(state_features):
        lon, lat = f["geometry"]["coordinates"]
        key = (round(lat / cell), round(lon / cell))
        grid.setdefault(key, []).append(i)

    def neighbors(lat, lon):
        center_key = (round(lat / cell), round(lon / cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                key = (center_key[0] + dx, center_key[1] + dy)
                if key in grid:
                    yield from grid[key]

    matched_state = set()
    new_features = []
    matched_count = 0
    new_count = 0
    for of in osm["features"]:
        otag = of["properties"].get("shop", "")
        if otag != "supermarket":
            continue
        oname = normalize_name(of["properties"].get("name", ""))
        olon, olat = of["geometry"]["coordinates"]
        # Find any state-file store within radius
        best_idx = None
        best_dist = MATCH_RADIUS_M + 1
        for i in neighbors(olat, olon):
            sf = state_features[i]
            slon, slat = sf["geometry"]["coordinates"]
            d = haversine_m(olat, olon, slat, slon)
            if d <= MATCH_RADIUS_M and d < best_dist:
                # Optional name check: prefer matches with name overlap
                sname = normalize_name(sf["properties"].get("name", ""))
                if oname and sname:
                    if oname in sname or sname in oname or any(
                        w in sname.split() for w in oname.split() if len(w) >= 4
                    ):
                        best_idx = i
                        best_dist = d
                        continue
                # Even without name match, accept very close matches
                if d <= 30:
                    best_idx = i
                    best_dist = d
        if best_idx is not None:
            matched_state.add(best_idx)
            sf = state_features[best_idx]
            sf["properties"]["source"] = "both"
            sf["properties"]["osm_shop"] = otag
            matched_count += 1
        else:
            # OSM-only feature; promote to a synthesized store entry
            p = of["properties"]
            new_features.append({
                "type": "Feature",
                "geometry": of["geometry"],
                "properties": {
                    "license": "",
                    "name": p.get("name") or p.get("brand") or "(unnamed OSM supermarket)",
                    "entity": p.get("brand", ""),
                    "estab_type": "",
                    "address": p.get("address", ""),
                    "city": p.get("city", ""),
                    "zip": p.get("zip", ""),
                    "borough": "",
                    "sqft": None,
                    "size_class": "OSM-only supermarket",
                    "is_supermarket": True,
                    "source": "osm",
                    "osm_id": p.get("osm_id", ""),
                    "osm_shop": "supermarket",
                    "website": p.get("website", ""),
                },
            })
            new_count += 1

    merged = {
        "type": "FeatureCollection",
        "metadata": {
            "state_features": len(state_features),
            "osm_supermarkets_matched": matched_count,
            "osm_only_supermarkets_added": new_count,
            "match_radius_m": MATCH_RADIUS_M,
        },
        "features": state_features + new_features,
    }
    with OUT_PATH.open("w") as f:
        json.dump(merged, f)
    print(f"Wrote {OUT_PATH}", file=sys.stderr)
    print(f"  state features: {len(state_features)}", file=sys.stderr)
    print(f"  OSM supermarkets matched to state: {matched_count}", file=sys.stderr)
    print(f"  OSM-only supermarkets added: {new_count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
