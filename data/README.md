# Data pipeline

The app ships a static bundle (`data/build/bundle.json`, shape `Bundle` in `packages/shared/src/types.ts`). Everything in it comes from the sources below; nothing is typed in by hand except the reviewed station overrides in `data/curation/`.

## Sources

| Source | What we take | Where it lands | License / terms |
|---|---|---|---|
| Bangladesh Railway e-ticket system (`railspaapi.shohoz.com/v1.0/web`, the API behind eticket.railway.gov.bd) | Train list (`GET /all-trains/info`), per-train stops, arrival/departure, halt, running days (`POST /train-routes`) | `raw/eticket/` | Public route information shown on the official site. Fetched slowly (1.5 s between requests) |
| OpenStreetMap via Geofabrik (`asia/bangladesh-latest.osm.pbf`) | `railway=rail` lines, `railway=station/halt` positions and names (English and Bangla) | `raw/osm/rail.json` (the .pbf itself is not committed) | © OpenStreetMap contributors, ODbL 1.0. Attribution required in the app |
| Wikidata SPARQL | Railway stations in Bangladesh with coordinates, English/Bangla labels and aliases | `raw/wikidata/` | CC0 |

`raw/SOURCES.md` (written by the research pass) lists further sources checked, coverage gaps (mail, commuter and local trains not sold on e-ticket) and cross-check results.

## Steps

1. `node data/scripts/fetch-eticket.ts` — snapshot the timetable. Re-run with `--refresh` when Bangladesh Railway changes schedules.
2. Download `bangladesh-latest.osm.pbf` from Geofabrik into `raw/osm/` (check the `.md5`), then `data/.venv/Scripts/python data/scripts/extract_osm.py`.
3. `data/scripts/build_bundle.py` — normalise trains and stops, match e-ticket station names to OSM/Wikidata positions, route each train over the rail graph, compute km along the route, write `build/bundle.json` and `build/routes.geojson`.
4. `node data/scripts/validate-bundle.ts` — fails on stops out of time order, impossible speeds, stations far from the rail line, trains with no running days.

## Python environment

```sh
py -m venv data/.venv
data/.venv/Scripts/python -m pip install osmium shapely pyproj rapidfuzz
```
