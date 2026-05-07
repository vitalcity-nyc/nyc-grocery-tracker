#!/usr/bin/env python3
"""
Pull every node and way tagged `shop=supermarket`, `shop=grocery`, or
`shop=convenience` inside the NYC bounding box from OpenStreetMap via the
Overpass API.

Output:
  data/processed/osm_nyc_food_stores.geojson

OSM data is licensed ODbL. Attribution required: "(c) OpenStreetMap
contributors". The methodology page handles attribution.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "data" / "processed" / "osm_nyc_food_stores.geojson"
OUT.parent.mkdir(parents=True, exist_ok=True)

# NYC bbox: south, west, north, east
BBOX = "40.49,-74.27,40.92,-73.68"

QUERY = f"""
[out:json][timeout:60];
(
  node["shop"~"^(supermarket|grocery|convenience)$"]({BBOX});
  way["shop"~"^(supermarket|grocery|convenience)$"]({BBOX});
);
out tags center;
"""

URL = "https://overpass-api.de/api/interpreter"


def main() -> int:
    print("Querying Overpass API for NYC food stores...", file=sys.stderr)
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(URL, data=data, headers={
        "User-Agent": "nyc-grocery-tracker (josh.greenman@gmail.com)",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        result = json.loads(r.read())

    features = []
    for el in result.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:  # way
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        addr_parts = [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
        ]
        address = " ".join(p for p in addr_parts if p).strip()
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "osm_id": f"{el['type']}/{el['id']}",
                "name": tags.get("name") or tags.get("brand") or "",
                "brand": tags.get("brand", ""),
                "shop": tags.get("shop", ""),
                "address": address,
                "city": tags.get("addr:city", ""),
                "zip": tags.get("addr:postcode", ""),
                "website": tags.get("website", ""),
                "opening_hours": tags.get("opening_hours", ""),
            },
        })

    out = {
        "type": "FeatureCollection",
        "metadata": {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source": "OpenStreetMap via Overpass API; (c) OpenStreetMap contributors, ODbL",
            "filter": "shop=supermarket|grocery|convenience inside NYC bbox",
            "count": len(features),
        },
        "features": features,
    }
    with OUT.open("w") as f:
        json.dump(out, f)
    print(f"Wrote {len(features)} OSM stores to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
