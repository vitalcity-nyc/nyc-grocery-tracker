# New York City supermarket map

Every licensed retail food store in New York City's five boroughs, sized by reported square footage. A baseline for tracking whether Mayor Mamdani's planned public supermarket sites land in neighborhoods that actually lack full-service supermarkets today.

**Live map:** https://vitalcity-nyc.github.io/nyc-grocery-tracker/

## What's here

- `index.html` — interactive map (Leaflet)
- `methodology.html` — sources, classification thresholds, limitations
- `collectors/nyc_food_stores.py` — pulls NY State Ag &amp; Markets retail food store data, classifies by square footage, writes GeoJSON + CSV
- `collectors/bls_ny_newark.py` — pulls BLS NY-Newark CBSA food-at-home CPI subgroups (kept for future context overlays)
- `collectors/bls_average_prices.py` — pulls BLS Northeast region item-level average prices (kept for future context overlays)
- `data/processed/` — generated GeoJSON, CSV, JSON outputs

## Reproducing

```
python3 collectors/nyc_food_stores.py
```

No API key required. Pulls about 11,000 stores in roughly 30 seconds.

## Source data

- NY State Department of Agriculture and Markets, Retail Food Stores (`9a8c-vfzj` on data.ny.gov)
- 2020 Census borough population totals (denominator for per-100,000 ratios)
- La Marqueta site coordinates from the NYC Mayor's Office, April 2026

## Known limitations

About 23 percent of NYC stores have no reported square footage and are off by default in the size filter. Address points are operator-filed and not independently verified. The 5,000-square-foot threshold for "full supermarket" is a convention, not a legal definition. See `methodology.html` for the full list.
