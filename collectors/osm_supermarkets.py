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

# NYC borough polygon (multipolygon) -- used to drop OSM features that fall
# inside the bounding box but are actually in New Jersey or Long Island.
NYC_BOUNDARY_URL = "https://data.cityofnewyork.us/resource/gthc-hcne.geojson?$limit=10"

NJ_CITIES = {
    "JERSEY CITY", "NEWARK", "HOBOKEN", "BAYONNE", "UNION CITY", "WEEHAWKEN",
    "WEST NEW YORK", "NORTH BERGEN", "SECAUCUS", "ELIZABETH", "KEARNY",
    "HARRISON", "GUTTENBERG", "FAIRVIEW", "EDGEWATER", "FORT LEE", "PALISADES PARK",
    "CLIFFSIDE PARK", "RIDGEFIELD", "BERGEN", "LEONIA", "ENGLEWOOD CLIFFS",
    "ENGLEWOOD", "HACKENSACK", "TEANECK", "PATERSON", "PASSAIC",
}

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


def fetch_nyc_polygon():
    """Fetch NYC borough boundaries and return a list of (rings, bbox) for
    fast point-in-polygon testing using ray casting."""
    req = urllib.request.Request(NYC_BOUNDARY_URL, headers={"User-Agent": "nyc-grocery-tracker"})
    with urllib.request.urlopen(req, timeout=60) as r:
        geo = json.loads(r.read())
    polygons = []  # list of (outer_rings, bbox) tuples
    for feat in geo["features"]:
        geom = feat["geometry"]
        coord_sets = geom["coordinates"]
        if geom["type"] == "Polygon":
            coord_sets = [coord_sets]
        for poly in coord_sets:  # MultiPolygon: list of polygons
            outer = poly[0]
            xs = [c[0] for c in outer]
            ys = [c[1] for c in outer]
            polygons.append((outer, (min(xs), min(ys), max(xs), max(ys))))
    return polygons


def point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def point_in_nyc(lon, lat, polygons):
    for ring, bbox in polygons:
        if bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]:
            if point_in_ring(lon, lat, ring):
                return True
    return False


def main() -> int:
    print("Fetching NYC borough polygons for inside-NYC filter...", file=sys.stderr)
    polygons = fetch_nyc_polygon()
    print(f"  {len(polygons)} polygon rings", file=sys.stderr)

    print("Querying Overpass API for NYC food stores...", file=sys.stderr)
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(URL, data=data, headers={
        "User-Agent": "nyc-grocery-tracker (josh.greenman@gmail.com)",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        result = json.loads(r.read())

    features = []
    skipped_outside = 0
    skipped_nj = 0
    for el in result.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:  # way
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        # Drop NJ / Long Island stores by state field
        if (tags.get("addr:state") or "").upper() in ("NJ", "NEW JERSEY"):
            skipped_nj += 1
            continue
        if (tags.get("addr:city") or "").upper() in NJ_CITIES:
            skipped_nj += 1
            continue
        # Final geometric check against NYC borough polygons
        if not point_in_nyc(lon, lat, polygons):
            skipped_outside += 1
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
    print(f"  skipped (NJ): {skipped_nj}", file=sys.stderr)
    print(f"  skipped (outside NYC polygon): {skipped_outside}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
