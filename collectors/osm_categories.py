#!/usr/bin/env python3
"""
Pull OSM features in NYC that carry a category tag the state license file
cannot give us: amenity, shop, craft, tourism. Used downstream to
override `is_supermarket` for state-file stores whose nearest OSM neighbor
identifies them as a brewery, pharmacy, bar, restaurant, etc.

Output: data/processed/osm_categories.geojson
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "data" / "processed" / "osm_categories.geojson"
OUT.parent.mkdir(parents=True, exist_ok=True)

BBOX = "40.49,-74.27,40.92,-73.68"

# We pull anything that could plausibly disqualify a state-file row from
# being a "supermarket". Pulling all amenity/shop/craft would be huge; this
# narrows to the disqualifying categories.
QUERY = f"""
[out:json][timeout:90];
(
  node["craft"~"^(brewery|distillery|winery|cidery)$"]({BBOX});
  way["craft"~"^(brewery|distillery|winery|cidery)$"]({BBOX});
  node["amenity"~"^(bar|pub|nightclub|biergarten|restaurant|fast_food|cafe|food_court|ice_cream|pharmacy|fuel|tobacco_shop)$"]({BBOX});
  way["amenity"~"^(bar|pub|nightclub|biergarten|restaurant|fast_food|cafe|food_court|ice_cream|pharmacy|fuel|tobacco_shop)$"]({BBOX});
  node["shop"~"^(alcohol|wine|tobacco|bakery|pastry|chocolate|confectionery|coffee|tea|deli|butcher|seafood|cheese|chemist|cosmetics|department_store|variety_store|kiosk|gas)$"]({BBOX});
  way["shop"~"^(alcohol|wine|tobacco|bakery|pastry|chocolate|confectionery|coffee|tea|deli|butcher|seafood|cheese|chemist|cosmetics|department_store|variety_store|kiosk|gas)$"]({BBOX});
);
out tags center;
"""

URL = "https://overpass-api.de/api/interpreter"


def main() -> int:
    print("Querying Overpass for non-supermarket categories...", file=sys.stderr)
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(URL, data=data, headers={
        "User-Agent": "nyc-grocery-tracker (josh.greenman@gmail.com)",
    })
    with urllib.request.urlopen(req, timeout=180) as r:
        result = json.loads(r.read())

    features = []
    for el in result.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center", {})
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        # Identify the disqualifying category
        cat = None
        if tags.get("craft") in ("brewery", "distillery", "winery", "cidery"):
            cat = f"craft={tags['craft']}"
        elif tags.get("amenity"):
            cat = f"amenity={tags['amenity']}"
        elif tags.get("shop"):
            cat = f"shop={tags['shop']}"
        if not cat:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "osm_id": f"{el['type']}/{el['id']}",
                "name": tags.get("name", ""),
                "category": cat,
                "addr": " ".join([
                    tags.get("addr:housenumber", ""),
                    tags.get("addr:street", ""),
                ]).strip(),
                "state": tags.get("addr:state", ""),
                "city": tags.get("addr:city", ""),
            },
        })

    out = {
        "type": "FeatureCollection",
        "metadata": {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source": "OpenStreetMap via Overpass API; (c) OSM contributors, ODbL",
            "filter": "disqualifying categories only (brewery, bar, restaurant, pharmacy, etc.)",
            "count": len(features),
        },
        "features": features,
    }
    with OUT.open("w") as f:
        json.dump(out, f)
    print(f"Wrote {len(features)} OSM category points to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
