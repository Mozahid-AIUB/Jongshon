"""
Extract the Bangladesh rail network from the Geofabrik OSM extract.

Two passes keep memory low (the country file has tens of millions of nodes):
  1. ways + tagged nodes: rail lines (railway=rail) and stations/halts
  2. untagged nodes: coordinates only for the node ids the rail ways use

Output: data/raw/osm/rail.json
  {
    "source": {...},
    "stations": [{osm_type, osm_id, railway, name, name_en, name_bn, alt_names, lon, lat}],
    "ways":     [{id, nodes: [ids], gauge, usage, service, name}],
    "nodes":    {id: [lon, lat]}
  }

Usage: data/.venv/Scripts/python data/scripts/extract_osm.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import osmium

ROOT = Path(__file__).resolve().parent.parent
PBF = ROOT / "raw" / "osm" / "bangladesh-latest.osm.pbf"
OUT = ROOT / "raw" / "osm" / "rail.json"

STATION_VALUES = {"station", "halt"}
# Tracks that never carry through-trains; leaving them out keeps routing on main lines.
SKIP_SERVICE = {"yard", "spur", "crossover"}
NAME_KEYS = ("name", "name:en", "name:bn", "alt_name", "alt_name:en", "old_name", "official_name", "short_name")


def station_record(osm_type: str, osm_id: int, tags: dict[str, str], lon: float, lat: float) -> dict:
    alt = set()
    for key in ("alt_name", "alt_name:en", "old_name", "official_name", "short_name"):
        for part in tags.get(key, "").split(";"):
            if part.strip():
                alt.add(part.strip())
    return {
        "osm_type": osm_type,
        "osm_id": osm_id,
        "railway": tags.get("railway") or tags.get("public_transport"),
        "name": tags.get("name"),
        "name_en": tags.get("name:en"),
        "name_bn": tags.get("name:bn"),
        "alt_names": sorted(alt),
        "ref": tags.get("ref") or tags.get("railway:ref"),
        "lon": round(lon, 7),
        "lat": round(lat, 7),
    }


def is_train_station(tags: dict[str, str]) -> bool:
    if tags.get("railway") in STATION_VALUES:
        # Dhaka metro stations are tagged station + station=subway/light_rail
        return tags.get("station") not in {"subway", "light_rail", "monorail"}
    return tags.get("public_transport") == "station" and tags.get("train") == "yes"


def main() -> None:
    if not PBF.exists():
        sys.exit(f"missing {PBF}; download it first (see data/README.md)")

    t0 = time.time()
    ways: list[dict] = []
    station_ways: list[tuple[int, dict, list[int]]] = []
    stations: list[dict] = []
    needed: set[int] = set()

    # Pass 1: tagged objects only
    fp = osmium.FileProcessor(str(PBF), osmium.osm.NODE | osmium.osm.WAY).with_filter(
        osmium.filter.KeyFilter("railway", "public_transport")
    )
    for obj in fp:
        tags = {t.k: t.v for t in obj.tags}
        if obj.is_node():
            if is_train_station(tags):
                stations.append(station_record("node", obj.id, tags, obj.location.lon, obj.location.lat))
            continue
        refs = [n.ref for n in obj.nodes]
        if tags.get("railway") == "rail" and tags.get("service") not in SKIP_SERVICE:
            ways.append(
                {
                    "id": obj.id,
                    "nodes": refs,
                    "gauge": tags.get("gauge"),
                    "usage": tags.get("usage"),
                    "service": tags.get("service"),
                    "name": tags.get("name"),
                }
            )
            needed.update(refs)
        elif is_train_station(tags):
            station_ways.append((obj.id, tags, refs))
            needed.update(refs)
    print(f"pass 1: {len(ways)} rail ways, {len(stations)} station nodes, {len(station_ways)} station areas "
          f"({time.time() - t0:.0f}s)")

    # Pass 2: coordinates for the nodes we need
    nodes: dict[int, list[float]] = {}
    fp = osmium.FileProcessor(str(PBF), osmium.osm.NODE).with_filter(osmium.filter.IdFilter(needed))
    for n in fp:
        nodes[n.id] = [round(n.location.lon, 7), round(n.location.lat, 7)]
    print(f"pass 2: {len(nodes)} / {len(needed)} node coordinates ({time.time() - t0:.0f}s)")

    for way_id, tags, refs in station_ways:
        pts = [nodes[r] for r in refs if r in nodes]
        if not pts:
            continue
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        stations.append(station_record("way", way_id, tags, lon, lat))

    # Ways with missing node coordinates (clipped at the extract border) are trimmed
    for w in ways:
        w["nodes"] = [r for r in w["nodes"] if r in nodes]
    ways = [w for w in ways if len(w["nodes"]) >= 2]
    used = {r for w in ways for r in w["nodes"]}

    out = {
        "source": {
            "file": PBF.name,
            "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "license": "ODbL 1.0, (c) OpenStreetMap contributors",
        },
        "stations": sorted(stations, key=lambda s: (s["name"] or "", s["osm_id"])),
        "ways": ways,
        "nodes": {str(k): v for k, v in nodes.items() if k in used},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT.parent)}: {len(stations)} stations, {len(ways)} ways, "
          f"{len(out['nodes'])} nodes ({OUT.stat().st_size / 1e6:.1f} MB, {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
