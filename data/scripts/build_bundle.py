"""
Build the app's static data bundle from the raw sources.

  raw/eticket/   timetable (trains, stops, running days)
  raw/osm/       rail network + station positions/names
  raw/wikidata/  station positions/names (second source)
  curation/      reviewed manual decisions (station overrides, aliases)

Steps
  1. Normalise trains and stops (times -> minutes after service-date midnight)
  2. Match every timetable station to a position (OSM first, Wikidata second),
     using name similarity and route geometry (neighbouring stops must be
     reachable at a plausible train speed)
  3. Route each train over the OSM rail graph, compute km of every stop
  4. Write build/bundle.json, build/segments.geojson and build/report.json,
     and copy the bundle into the mobile app's assets

Usage: data/.venv/Scripts/python data/scripts/build_bundle.py
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

DATA = Path(__file__).resolve().parent.parent
REPO = DATA.parent
RAW = DATA / "raw"
CURATION = DATA / "curation"
BUILD = DATA / "build"
APP_BUNDLE = REPO / "apps" / "mobile" / "assets" / "data" / "bundle.json"

WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
BENGALI = re.compile(r"[ঀ-৿]")
# Bump when the bundle's shape changes in a way older apps cannot read
BUNDLE_SCHEMA = 1

# A scheduled train never averages more than this between two stops; used to
# reject station matches that would make the timetable physically impossible.
MAX_KMH = 110.0
MATCH_ACCEPT = 88  # name score that is trusted without geometry support
MATCH_MIN = 70  # below this a name is not considered at all


# --------------------------------------------------------------------------
# helpers


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_12h(value: str) -> int:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*([ap])m", value, re.I)
    if not m:
        raise ValueError(f"bad time {value!r}")
    h, mi = int(m.group(1)) % 12, int(m.group(2))
    if m.group(3).lower() == "p":
        h += 12
    return h * 60 + mi


SMALL_WORDS = {"of", "and"}


def title_case(text: str) -> str:
    words = []
    for w in text.lower().split():
        if w in SMALL_WORDS and words:
            words.append(w)
            continue
        parts = w.split("-")
        words.append("-".join(p[:1].upper() + p[1:] for p in parts))
    return " ".join(words)


def station_code(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def display_name(key: str) -> str:
    text = key.replace("_", " ").strip()
    if text.isupper() or text.islower():
        text = title_case(text)
    return re.sub(r"\s+", " ", text)


GENERIC = re.compile(
    r"\b(railway|rail|train|station|stn|junction|jn|jct|halt|rly|terminal)\b", re.I
)
BN_GENERIC = re.compile(r"(রেলওয়ে|রেলস্টেশন|রেল|ট্রেন|স্টেশন|ষ্টেশন|জংশন|হল্ট)")


def norm(text: str) -> str:
    text = text.split(",")[0]
    text = text.lower().replace("_", " ").replace("-", " ").replace("'", "").replace("’", "")
    text = GENERIC.sub(" ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def skeleton(text: str) -> str:
    s = norm(text).replace(" ", "")
    for a, b in (("kh", "k"), ("gh", "g"), ("ch", "c"), ("jh", "j"), ("th", "t"), ("dh", "d"),
                 ("ph", "f"), ("bh", "b"), ("sh", "s"), ("q", "k"), ("z", "j")):
        s = s.replace(a, b)
    s = re.sub(r"[aeiouyw]", "", s)
    return re.sub(r"(.)\1+", r"\1", s)


def clean_bn(text: str | None) -> str | None:
    if not text or not BENGALI.search(text):
        return None
    text = BN_GENERIC.sub(" ", text.split(",")[0])
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1. timetable


@dataclass
class RawStop:
    key: str
    arr: int | None
    dep: int | None
    halt: int | None


@dataclass
class RawTrain:
    number: str
    name_en: str
    zone: str | None
    runs_on: list[str]
    stops: list[RawStop]
    issues: list[str] = field(default_factory=list)


def classify(number: str, name: str) -> str:
    upper = name.upper()
    if "SHUTTLE" in upper:
        return "shuttle"
    if "COMMUTER" in upper or "DEMU" in upper:
        return "commuter"
    if "SPECIAL" in upper:
        return "special"
    n = int(number) if number.isdigit() else 0
    if 700 <= n <= 899:
        return "intercity"
    if "MAIL" in upper or "LOCAL" in upper:
        return "mail_express" if "MAIL" in upper else "local"
    return "intercity" if "EXPRESS" in upper else "mail_express"


def clock_of(value: str | None) -> int | None:
    return parse_12h(value) if value else None


# Moving forward by more than this between consecutive stops really means the
# time went *backwards* (a data error), not a long overnight leg.
MAX_FORWARD_GAP = 12 * 60


def consistent_chain(rows: list[dict], weight) -> list[dict]:
    """
    Longest (by weight) subsequence of stops whose times only move forward,
    keeping the first and last row. Drops as few stops as possible when the
    source has a mistyped time.
    """
    n = len(rows)
    t_in = [r["arr"] if r["arr"] is not None else r["dep"] for r in rows]
    t_out = [r["dep"] if r["dep"] is not None else r["arr"] for r in rows]
    best: list[float | None] = [None] * n
    prev: list[int | None] = [None] * n
    best[0] = weight(rows[0])
    for j in range(1, n):
        for i in range(j):
            if best[i] is None or (t_in[j] - t_out[i]) % 1440 > MAX_FORWARD_GAP:
                continue
            score = best[i] + weight(rows[j])
            if best[j] is None or score > best[j]:
                best[j], prev[j] = score, i
    if best[n - 1] is None:
        return rows
    chain, k = [], n - 1
    while k is not None:
        chain.append(rows[k])
        k = prev[k]
    return chain[::-1]


def load_timetable() -> tuple[list[RawTrain], list[dict], dict]:
    info = load_json(RAW / "eticket" / "all-trains-info.json")
    zones = {t["train_number"]: t.get("zone") for t in info["data"]["trains"]}
    listed_origin = {t["train_number"]: t.get("origin_city") for t in info["data"]["trains"]}
    docs = []
    for path in sorted((RAW / "eticket" / "routes").glob("*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        docs.append((path.stem, load_json(path)))

    # Typical dwell per station across all trains: used to repair a departure
    # the source lists before the arrival.
    dwell: dict[str, list[int]] = defaultdict(list)
    for _, doc in docs:
        for r in (doc.get("data") or {}).get("routes") or []:
            a, d = clock_of(r.get("arrival_time")), clock_of(r.get("departure_time"))
            if a is not None and d is not None and 0 <= d - a <= 60:
                dwell[r["city"]].append(d - a)

    def typical_dwell(city: str) -> int:
        values = sorted(dwell.get(city, []))
        return values[len(values) // 2] if values else 2

    # How many trains call at each station: when one of two stops must go,
    # keep the busier station.
    calls: dict[str, int] = defaultdict(int)
    for _, doc in docs:
        for r in (doc.get("data") or {}).get("routes") or []:
            calls[r["city"]] += 1

    def weight(row: dict) -> float:
        complete = row["arr"] is not None and row["dep"] is not None
        return 1 + (0.1 if complete else 0) + 0.001 * calls[row["city"]]

    trains: list[RawTrain] = []
    skipped: list[dict] = []
    fetched_at = None
    for number, doc in docs:
        fetched_at = max(fetched_at or "", doc.get("fetched_at", ""))
        data = doc.get("data") or {}
        routes = data.get("routes") or []
        if len(routes) < 2:
            skipped.append({"number": number, "reason": "no route published on e-ticket"})
            continue
        name = re.sub(r"\s*\(\s*\d+\s*\)\s*$", "", data.get("train_name") or "").strip()
        days = [d.strip().lower()[:3] for d in data.get("days") or []]
        runs_on = [d for d in WEEKDAYS if d in days]
        issues: list[str] = []
        last = len(routes) - 1

        # 1. clock times per stop, repairing a departure listed before the arrival
        rows = []
        for i, r in enumerate(routes):
            arr = clock_of(r.get("arrival_time")) if i > 0 else None
            dep = clock_of(r.get("departure_time")) if i < last else None
            halt = int(r["halt"]) if (r.get("halt") or "").strip().isdigit() else None
            if arr is not None and dep is not None and 0 < arr - dep < 360:
                fixed = (arr + typical_dwell(r["city"])) % 1440
                issues.append(f"{r['city']}: source departure {dep // 60:02d}:{dep % 60:02d} is before arrival "
                              f"{arr // 60:02d}:{arr % 60:02d}; used typical {typical_dwell(r['city'])} min halt")
                dep = fixed
            rows.append({"city": r["city"], "arr": arr, "dep": dep, "halt": halt, "first": i == 0, "last": i == last})

        # 2a. the source sometimes lists a major intermediate station first
        #     (810 starts at Burimari but Lalmonirhat comes first). Only when
        #     the first row does not fit before the second one in time: find
        #     the real origin (a row with a departure but no arrival) and move
        #     the misplaced row to where its departure time belongs.
        origin = None
        if len(rows) > 2 and rows[0]["dep"] is not None:
            t1 = rows[1]["arr"] if rows[1]["arr"] is not None else rows[1]["dep"]
            if t1 is not None and (t1 - rows[0]["dep"]) % 1440 > MAX_FORWARD_GAP:
                starts = [r["city"] for r in rows[1:-1] if r["arr"] is None and r["dep"] is not None]
                origin = starts[0] if starts else listed_origin.get(number)
        if origin and rows[0]["city"] != origin and any(r["city"] == origin for r in rows[1:]):
            misplaced = rows.pop(0)
            start = next(i for i, r in enumerate(rows) if r["city"] == origin)
            rows = rows[start:] if start else rows
            for r in rows:
                r["first"] = False
            rows[0]["first"] = True
            rows[0]["arr"] = None
            t = misplaced["dep"]
            t0 = rows[0]["dep"]
            pos = len(rows) - 1
            for i in range(1, len(rows)):
                t_i = rows[i]["arr"] if rows[i]["arr"] is not None else rows[i]["dep"]
                if (t_i - t0) % 1440 > (t - t0) % 1440:
                    pos = i
                    break
            misplaced["first"] = False
            rows.insert(pos, misplaced)
            issues.append(f"{misplaced['city']}: listed first in source but the train starts at {origin}; "
                          f"placed between {rows[pos - 1]['city']} and {rows[pos + 1]['city']} by time")

        # 2b. drop stops whose times break the running order (mistyped times,
        #     a branch service listed inside the main train)
        kept = consistent_chain(rows, weight)
        dropped = [r["city"] for r in rows if r not in kept]
        for city in dropped:
            issues.append(f"{city}: time out of running order in source, stop left out")

        # 3. absolute minutes after service-date midnight
        stops: list[RawStop] = []
        clock = -1
        for row in kept:
            vals = []
            for key in ("arr", "dep"):
                t = row[key]
                if t is None:
                    vals.append(None)
                    continue
                t += (clock // 1440) * 1440 if clock >= 0 else 0
                while t < clock:
                    t += 1440
                clock = t
                vals.append(t)
            stops.append(RawStop(row["city"], vals[0], vals[1], row["halt"]))

        if not runs_on:
            issues.append("no running days published")
        trains.append(RawTrain(number, title_case(name) if name else f"Train {number}", zones.get(number), runs_on, stops, issues))
    meta = {"eticket_fetched_at": fetched_at}
    return trains, skipped, meta


# --------------------------------------------------------------------------
# 2. station positions


@dataclass
class Candidate:
    source: str  # osm | wikidata
    ref: str
    names: list[str]
    name_bn: str | None
    lon: float
    lat: float
    kind: str | None = None


def load_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    osm = load_json(RAW / "osm" / "rail.json")
    for s in osm["stations"]:
        names = [n for n in [s.get("name_en"), s.get("name"), *s.get("alt_names", [])] if n and not BENGALI.search(n)]
        bn = clean_bn(s.get("name_bn")) or clean_bn(s.get("name"))
        if not names and not bn:
            continue
        out.append(Candidate("osm", f"{s['osm_type']}/{s['osm_id']}", names, bn, s["lon"], s["lat"], s.get("railway")))
    wd = load_json(RAW / "wikidata" / "bd_railway_stations.json")
    for b in wd["results"]["bindings"]:
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
        if not m:
            continue
        names = [b["en"]["value"]] if "en" in b else []
        aliases = (b.get("aliases", {}).get("value") or "").split("|")
        names += [a for a in aliases if a and not BENGALI.search(a)]
        bn = clean_bn(b.get("bn", {}).get("value"))
        out.append(Candidate("wikidata", b["item"]["value"].rsplit("/", 1)[-1], names, bn, float(m.group(1)), float(m.group(2))))
    return out


@dataclass
class Match:
    key: str
    lon: float | None = None
    lat: float | None = None
    method: str = "unmatched"
    score: float = 0
    source: str | None = None
    ref: str | None = None
    matched_name: str | None = None
    name_bn: str | None = None
    aliases: list[str] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)


PLACE_SUFFIX = re.compile(r"\b(bazar|bazaar|ghat|school|college)\b")


def name_score(queries: list[str], cand: Candidate) -> tuple[float, str]:
    """Best fuzzy score between any query name and any candidate name (0-100)."""
    best, best_name = 0.0, ""
    for q in queries:
        nq, sq = norm(q), skeleton(q)
        if not nq:
            continue
        bare_q = re.sub(r"\s+", " ", PLACE_SUFFIX.sub(" ", nq)).strip()
        for n in cand.names:
            nc = norm(n)
            if not nc:
                continue
            s = fuzz.ratio(nq, nc)
            if sq and sq == skeleton(n):
                s = max(s, 92)
            # "Dewanganj Bazar" vs "Dewanganj", "Sultanpur" vs "Sultanpur School"
            bare_c = re.sub(r"\s+", " ", PLACE_SUFFIX.sub(" ", nc)).strip()
            if bare_q and bare_c and (bare_q != nq or bare_c != nc):
                s = max(s, fuzz.ratio(bare_q, bare_c) - 3)
            if s > best:
                best, best_name = s, n
    return best, best_name


def match_stations(trains: list[RawTrain], candidates: list[Candidate], overrides: dict, aliases: dict,
                   places: list[dict], graph: "RailGraph") -> dict[str, Match]:
    keys = sorted({s.key for t in trains for s in t.stops})

    # Minutes between neighbouring stops, per station pair (shortest seen)
    neighbours: dict[str, dict[str, int]] = defaultdict(dict)
    for t in trains:
        for a, b in zip(t.stops, t.stops[1:]):
            minutes = (b.arr if b.arr is not None else b.dep) - (a.dep if a.dep is not None else a.arr)
            # the most generous time any train takes, so one mistyped timetable
            # entry cannot reject a correct station
            for x, y in ((a.key, b.key), (b.key, a.key)):
                prev = neighbours[x].get(y)
                neighbours[x][y] = minutes if prev is None else max(prev, minutes)

    matches: dict[str, Match] = {}
    scored: dict[str, list[tuple[float, str, Candidate]]] = {}
    for key in keys:
        queries = [display_name(key), *aliases.get(key, [])]
        ranked = []
        for c in candidates:
            s, n = name_score(queries, c)
            if s >= MATCH_MIN:
                ranked.append((s, n, c))
        ranked.sort(key=lambda x: (-x[0], x[2].source != "osm", x[2].kind == "platform"))
        scored[key] = ranked
        matches[key] = Match(key, aliases=list(aliases.get(key, [])))

    def worst_ratio(key: str, c: Candidate) -> float:
        """Largest (straight-line distance / reachable distance) to any positioned neighbour."""
        worst = 0.0
        for other, minutes in neighbours[key].items():
            m = matches[other]
            if m.lat is None or other == key:
                continue
            limit = max(3.0, minutes / 60 * MAX_KMH + 3)
            worst = max(worst, haversine_km(c.lon, c.lat, m.lon, m.lat) / limit)
        return worst

    def plausible(key: str, c: Candidate) -> bool:
        return worst_ratio(key, c) <= 1.0

    def checked_by_neighbour(key: str) -> bool:
        return any(matches[o].lat is not None for o in neighbours[key] if o != key)

    def off_track(c: Candidate) -> bool:
        """True when track exists nearby but the point is clearly not on it (old/abandoned site)."""
        _, d = graph.nearest(c.lon, c.lat, 2.0)
        return d is not None and 1.0 < d < 2.0

    def accept(key: str, c: Candidate, score: float, name: str, method: str) -> None:
        m = matches[key]
        m.lon, m.lat, m.method, m.score = c.lon, c.lat, method, round(score, 1)
        m.source, m.ref, m.matched_name, m.name_bn = c.source, c.ref, name, c.name_bn

    # Manual overrides first: they are reviewed decisions
    for key, ov in overrides.items():
        if key not in matches:
            continue
        m = matches[key]
        if "ref" in ov:
            hit = next((c for c in candidates if c.ref == ov["ref"]), None)
            if hit is None:
                print(f"  override for {key}: ref {ov['ref']} not found", file=sys.stderr)
                continue
            accept(key, hit, 100, hit.names[0] if hit.names else key, "override")
        else:
            m.lon, m.lat, m.method, m.score = ov["lon"], ov["lat"], "override", 100
            m.source, m.ref, m.matched_name = ov.get("source", "manual"), None, ov.get("note")
        if ov.get("name_bn"):
            m.name_bn = ov["name_bn"]

    # Pass 1: clear name matches. Where OSM and Wikidata both name the station,
    # prefer OSM (positions are surveyed on the track).
    for key in keys:
        m = matches[key]
        if m.method != "unmatched":
            continue
        ranked = scored[key]
        if not ranked or ranked[0][0] < MATCH_ACCEPT:
            continue
        top = ranked[0][0]
        same = [r for r in ranked if r[0] >= top - 2]
        spread = max(haversine_km(a[2].lon, a[2].lat, b[2].lon, b[2].lat) for a in same for b in same)
        if spread <= 3:  # all top candidates describe the same place
            s, n, c = same[0]
            if not off_track(c):
                accept(key, c, s, n, "name")

    # Pass 2: resolve the rest using geometry, repeat until stable. A weaker
    # name match is only taken when a positioned neighbour confirms it.
    for _ in range(6):
        changed = False
        for key in keys:
            m = matches[key]
            if m.method != "unmatched" or not checked_by_neighbour(key):
                continue
            ok = [
                r for r in scored[key]
                if not off_track(r[2]) and (
                    (r[0] >= 78 and plausible(key, r[2]))
                    # weaker spelling match, but it sits on the track right where the timetable puts it
                    or (r[0] >= 72 and worst_ratio(key, r[2]) <= 0.6 and graph.nearest(r[2].lon, r[2].lat, 0.6)[0] is not None)
                )
            ]
            if ok:
                s, n, c = ok[0]
                accept(key, c, s, n, "name+geometry")
                changed = True
        if not changed:
            break

    # Pass 2b: stations nobody has mapped as a station yet. Use the town or
    # village of the same name and put the point on the nearest track.
    place_cands = []
    for p in places:
        names = [n for n in (p.get("name_en"), p.get("name")) if n and not BENGALI.search(n)]
        if names:
            bn = clean_bn(p.get("name_bn")) or clean_bn(p.get("name"))
            place_cands.append(Candidate("osm-place", p["place"], names, bn, p["lon"], p["lat"], p["place"]))
    for _ in range(3):
        for key in keys:
            m = matches[key]
            if m.method != "unmatched":
                continue
            queries = [display_name(key), *aliases.get(key, [])]
            ranked = []
            for c in place_cands:
                s, n = name_score(queries, c)
                if s >= 90:
                    ranked.append((s, n, c))
            ranked.sort(key=lambda x: -x[0])
            for s, n, c in ranked:
                node, _ = graph.nearest(c.lon, c.lat, max_km=4.0)
                if node is None:
                    continue
                lon, lat = graph.coord[node]
                on_track = Candidate(c.source, c.ref, c.names, c.name_bn, lon, lat)
                if plausible(key, on_track):
                    accept(key, on_track, s, n, "place+track (approximate)")
                    break

    # Pass 3: re-check name-only matches against geometry. A match that is
    # wildly out of reach (e.g. the Narail "Lohagara" for the station on the
    # Cox's Bazar line) is dropped; a marginal one is kept and flagged.
    for key in keys:
        m = matches[key]
        if m.method != "name":
            continue
        ratio = worst_ratio(key, Candidate(m.source or "", m.ref or "", [], None, m.lon, m.lat))
        if ratio > 3:
            matches[key] = Match(key, aliases=m.aliases, method="unmatched")
            matches[key].matched_name = f"rejected {m.matched_name} ({m.source} {m.ref}): {ratio:.1f}x too far"
        elif ratio > 1:
            m.method = "name (geometry conflict)"

    for key in keys:
        m = matches[key]
        seen = set()
        for s, n, c in scored[key][:5]:
            sig = (round(c.lon, 3), round(c.lat, 3))
            if sig in seen:
                continue
            seen.add(sig)
            m.alternatives.append({"score": round(s, 1), "name": n, "source": c.source, "ref": c.ref,
                                   "lon": c.lon, "lat": c.lat})
    return matches


# --------------------------------------------------------------------------
# 3. routing over the rail graph


SERVICE_COST = {"yard": 4.0, "spur": 4.0, "crossover": 2.0, "siding": 3.0}
GAP_KM = 0.15  # mapping gaps up to this size between separate pieces of track are bridged


class RailGraph:
    def __init__(self, osm: dict):
        self.coord: dict[int, tuple[float, float]] = {int(k): (v[0], v[1]) for k, v in osm["nodes"].items()}
        # adjacency: neighbour -> (cost used for routing, real length in km)
        self.adj: dict[int, dict[int, tuple[float, float]]] = defaultdict(dict)
        for w in osm["ways"]:
            factor = SERVICE_COST.get(w.get("service") or "", 1.0)
            ids = w["nodes"]
            for a, b in zip(ids, ids[1:]):
                if a in self.coord and b in self.coord:
                    self._link(a, b, factor)
        self.grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for n, (lon, lat) in self.coord.items():
            if n in self.adj:
                self.grid[(int(lon * 50), int(lat * 50))].append(n)
        self.bridged = self._heal_gaps()
        self._cache: dict[tuple[int, int], tuple[float, list[int]] | None] = {}
        self._route_cache: dict[tuple, tuple[float, list[int]] | None] = {}

    def _link(self, a: int, b: int, factor: float = 1.0) -> None:
        d = haversine_km(*self.coord[a], *self.coord[b])
        cost = d * factor
        if b not in self.adj[a] or self.adj[a][b][0] > cost:
            self.adj[a][b] = (cost, d)
            self.adj[b][a] = (cost, d)

    def _components(self) -> dict[int, int]:
        comp: dict[int, int] = {}
        for start in self.adj:
            if start in comp:
                continue
            stack = [start]
            comp[start] = start
            while stack:
                n = stack.pop()
                for m in self.adj[n]:
                    if m not in comp:
                        comp[m] = start
                        stack.append(m)
        return comp

    def _heal_gaps(self) -> int:
        """Join dead-ends to a different piece of track a few metres away."""
        comp = self._components()
        joins = 0
        for n in [n for n, nb in self.adj.items() if len(nb) == 1]:
            lon, lat = self.coord[n]
            best, best_d = None, GAP_KM
            gx, gy = int(lon * 50), int(lat * 50)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for m in self.grid.get((gx + dx, gy + dy), ()):
                        if comp.get(m) == comp.get(n):
                            continue
                        d = haversine_km(lon, lat, *self.coord[m])
                        if d < best_d:
                            best, best_d = m, d
            if best is not None:
                self._link(n, best, 1.5)
                joins += 1
                old, new = comp[best], comp[n]
                for k, v in comp.items():
                    if v == old:
                        comp[k] = new
        return joins

    def near(self, lon: float, lat: float, radius_km: float = 0.5) -> list[tuple[int, float]]:
        """Track nodes within radius, closest first (every parallel track at a station)."""
        gx, gy = int(lon * 50), int(lat * 50)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for n in self.grid.get((gx + dx, gy + dy), ()):
                    d = haversine_km(lon, lat, *self.coord[n])
                    if d <= radius_km:
                        out.append((n, d))
        out.sort(key=lambda x: x[1])
        return out

    def station_nodes(self, lon: float, lat: float) -> list[tuple[int, float]]:
        hits = self.near(lon, lat, 0.5)
        if hits:
            return hits
        n, d = self.nearest(lon, lat, 2.0)
        return [(n, d)] if n is not None else []

    def route(self, a: tuple[float, float], b: tuple[float, float]) -> tuple[float, list[int]] | None:
        """Shortest track path between two station points, trying every nearby track at both ends."""
        key = (round(a[0], 6), round(a[1], 6), round(b[0], 6), round(b[1], 6))
        if key in self._route_cache:
            return self._route_cache[key]
        sources = self.station_nodes(*a)
        targets = {n: d for n, d in self.station_nodes(*b)}
        result = None
        if sources and targets:
            cost: dict[int, float] = {}
            prev: dict[int, int] = {}
            heap = []
            for n, d in sources:
                c = d * 2  # small preference for the track closest to the station point
                if c < cost.get(n, math.inf):
                    cost[n] = c
                    heapq.heappush(heap, (c + max(0.0, haversine_km(*self.coord[n], *b) - 0.5), c, n))
            while heap:
                _, c, n = heapq.heappop(heap)
                if c > cost.get(n, math.inf):
                    continue
                if n in targets:
                    path = [n]
                    while path[-1] in prev:
                        path.append(prev[path[-1]])
                    path.reverse()
                    length = sum(self.adj[p][q][1] for p, q in zip(path, path[1:]))
                    result = (length, path)
                    break
                for m, (w, _) in self.adj[n].items():
                    nc = c + w
                    if nc < cost.get(m, math.inf):
                        cost[m] = nc
                        prev[m] = n
                        heapq.heappush(heap, (nc + max(0.0, haversine_km(*self.coord[m], *b) - 0.5), nc, m))
        self._route_cache[key] = result
        return result

    def nearest(self, lon: float, lat: float, max_km: float = 2.0) -> tuple[int | None, float]:
        gx, gy = int(lon * 50), int(lat * 50)
        best, best_d = None, max_km
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for n in self.grid.get((gx + dx, gy + dy), ()):
                    d = haversine_km(lon, lat, *self.coord[n])
                    if d < best_d:
                        best, best_d = n, d
        return best, best_d

    def point_along(self, path: list[int], km: float) -> tuple[float, float]:
        acc = 0.0
        for p, q in zip(path, path[1:]):
            seg = self.adj[p][q][1]
            if acc + seg >= km and seg > 0:
                r = (km - acc) / seg
                (x1, y1), (x2, y2) = self.coord[p], self.coord[q]
                return x1 + (x2 - x1) * r, y1 + (y2 - y1) * r
            acc += seg
        return self.coord[path[-1]]


def interpolate_missing(trains: list[RawTrain], matches: dict[str, Match], graph: RailGraph) -> list[str]:
    """
    Stations that no source has mapped get a point on the track between the
    nearest positioned stops, placed by scheduled time. Marked approximate.
    """
    estimates: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for t in trains:
        stops = t.stops
        for i, s in enumerate(stops):
            if matches[s.key].lat is not None:
                continue
            j = next((k for k in range(i - 1, -1, -1) if matches[stops[k].key].lat is not None), None)
            k = next((k for k in range(i + 1, len(stops)) if matches[stops[k].key].lat is not None), None)
            if j is None or k is None:
                continue
            a, b = matches[stops[j].key], matches[stops[k].key]
            res = graph.route((a.lon, a.lat), (b.lon, b.lat))
            if res is None:
                continue
            length, path = res
            ta = stops[j].dep if stops[j].dep is not None else stops[j].arr
            tb = stops[k].arr if stops[k].arr is not None else stops[k].dep
            arr = s.arr if s.arr is not None else s.dep
            dep = s.dep if s.dep is not None else s.arr
            if ta is None or tb is None or tb <= ta:
                continue
            f = min(max(((arr + dep) / 2 - ta) / (tb - ta), 0.02), 0.98)
            estimates[s.key].append(graph.point_along(path, f * length))
    for key, pts in estimates.items():
        lons = sorted(p[0] for p in pts)
        lats = sorted(p[1] for p in pts)
        m = matches[key]
        m.lon, m.lat = lons[len(lons) // 2], lats[len(lats) // 2]
        m.method, m.source, m.score = "interpolated (approximate)", "timetable+track", 0
    return sorted(estimates)


# --------------------------------------------------------------------------
# 4. assemble


def main() -> None:
    t0 = time.time()
    BUILD.mkdir(parents=True, exist_ok=True)
    overrides = load_json(CURATION / "station_overrides.json", {})
    aliases = load_json(CURATION / "station_aliases.json", {})
    train_overrides = load_json(CURATION / "train_overrides.json", {})

    trains, skipped, meta = load_timetable()
    candidates = load_candidates()
    osm = load_json(RAW / "osm" / "rail.json")
    graph = RailGraph(osm)
    places = load_json(RAW / "osm" / "places.json", [])
    matches = match_stations(trains, candidates, overrides, aliases, places, graph)
    print(f"rail graph: {len(graph.adj)} nodes, {graph.bridged} mapping gaps bridged")

    report: dict = {"skipped_trains": skipped, "train_issues": {}, "stations": {}, "routing": {}, "speed": []}

    # Owner's rule: only real, citable positions are published. Positions
    # inferred from the timetable or a village name stay in the report as
    # hints for whoever surveys the station, never in the bundle.
    interpolate_missing(trains, matches, graph)
    unverified: dict[str, dict] = {}
    for key, m in matches.items():
        if m.lat is not None and "approximate" in m.method:
            unverified[key] = {"hint_lon": round(m.lon, 6), "hint_lat": round(m.lat, 6),
                               "method": m.method, "matched_name": m.matched_name}
            m.lon = m.lat = None
            m.method = "unverified"
    report["unverified_positions"] = unverified
    print(f"positions withheld until verified: {', '.join(sorted(unverified)) or 'none'}")

    for key, m in matches.items():
        node, d = graph.nearest(m.lon, m.lat) if m.lat is not None else (None, None)
        report["stations"][key] = {
            "method": m.method, "score": m.score, "source": m.source, "ref": m.ref,
            "matched_name": m.matched_name, "lon": m.lon, "lat": m.lat,
            "km_to_track": round(d, 3) if node is not None else None,
        }

    segments: dict[tuple[str, str], dict] = {}
    out_trains = []
    for t in trains:
        if t.issues:
            report["train_issues"][t.number] = t.issues
        ov = train_overrides.get(t.number, {})
        # Route between the stops whose position is known; a stop without a
        # verified position keeps km = null and is simply passed through.
        positioned = [i for i, s in enumerate(t.stops) if matches[s.key].lat is not None]
        kms: list[float | None] = [None] * len(t.stops)
        km = 0.0
        routed = bool(positioned) and positioned[0] == 0 and positioned[-1] == len(t.stops) - 1
        if not routed:
            report["routing"].setdefault(t.number, []).append("origin or terminus has no verified position")
        else:
            kms[0] = 0.0
        for i, j in zip(positioned, positioned[1:]):
            if not routed:
                break
            a, b = t.stops[i], t.stops[j]
            ma, mb = matches[a.key], matches[b.key]
            res = graph.route((ma.lon, ma.lat), (mb.lon, mb.lat))
            if res is None:
                routed = False
                report["routing"].setdefault(t.number, []).append(f"no path {a.key} -> {b.key}")
                break
            dist, path = res
            straight = haversine_km(ma.lon, ma.lat, mb.lon, mb.lat)
            if straight > 1 and dist / straight > 2.2:
                report["routing"].setdefault(t.number, []).append(
                    f"detour {a.key} -> {b.key}: {dist:.1f} km by rail vs {straight:.1f} km straight")
            minutes = (b.arr if b.arr is not None else b.dep) - (a.dep if a.dep is not None else a.arr)
            if minutes > 0 and dist / (minutes / 60) > MAX_KMH:
                report["speed"].append({"train": t.number, "from": a.key, "to": b.key,
                                        "km": round(dist, 1), "min": minutes, "kmh": round(dist / (minutes / 60))})
            km += dist
            kms[j] = round(km, 2)
            seg_key = tuple(sorted((station_code(a.key), station_code(b.key))))
            if seg_key not in segments:
                coords = [list(graph.coord[n]) for n in path]
                if seg_key[0] != station_code(a.key):
                    coords.reverse()
                segments[seg_key] = {"km": round(dist, 2), "coords": coords}

        runs_on = ov.get("runs_on", t.runs_on)
        out_trains.append({
            "number": t.number,
            "name_en": ov.get("name_en", t.name_en),
            "name_bn": ov.get("name_bn"),
            "type": ov.get("type", classify(t.number, t.name_en)),
            "zone": t.zone,
            "origin": station_code(t.stops[0].key),
            "destination": station_code(t.stops[-1].key),
            "runs_on": runs_on,
            "off_days": [d for d in WEEKDAYS if d not in runs_on],
            "stops": [{"station": station_code(s.key), "arr": s.arr, "dep": s.dep,
                       "km": kms[i] if routed else None}
                      for i, s in enumerate(t.stops)],
            "route_id": t.number if routed else None,
            "length_km": round(km, 1) if routed else None,
        })

    out_stations = []
    for key, m in sorted(matches.items(), key=lambda kv: station_code(kv[0])):
        alias_set = {display_name(key)} | set(m.aliases)
        if m.matched_name:
            cleaned = m.matched_name.split(",")[0].strip()
            alias_set.add(re.sub(GENERIC, "", cleaned).strip() or cleaned)
        alias_set.discard(display_name(key))
        out_stations.append({
            "code": station_code(key),
            "name_en": display_name(key),
            "name_bn": m.name_bn,
            "aliases": sorted(a for a in alias_set if a),
            "lat": round(m.lat, 6) if m.lat is not None else None,
            "lon": round(m.lon, 6) if m.lon is not None else None,
            "osm_id": int(m.ref.split("/")[1]) if m.source == "osm" and m.ref and "/" in m.ref else None,
        })

    body = {"stations": out_stations, "trains": out_trains}
    digest = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:8]
    now = time.gmtime()
    bundle = {
        "version": f"{time.strftime('%Y.%m.%d', now)}-{digest}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", now),
        "sources": [
            {"id": "eticket", "name": "Bangladesh Railway e-ticket timetable", "url": "https://eticket.railway.gov.bd",
             "fetched_at": meta["eticket_fetched_at"], "license": "Public route information"},
            {"id": "osm", "name": "OpenStreetMap", "url": "https://www.openstreetmap.org/copyright",
             "fetched_at": osm["source"]["extracted_at"], "license": "ODbL 1.0, © OpenStreetMap contributors"},
            {"id": "wikidata", "name": "Wikidata", "url": "https://www.wikidata.org",
             "fetched_at": time.strftime("%Y-%m-%d", now), "license": "CC0"},
        ],
        **body,
    }

    (BUILD / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    seg_fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"from": k[0], "to": k[1], "km": v["km"]},
         "geometry": {"type": "LineString", "coordinates": v["coords"]}} for k, v in sorted(segments.items())]}
    (BUILD / "segments.geojson").write_text(json.dumps(seg_fc, separators=(",", ":")), encoding="utf-8")

    # Light copy for the app's network map: ~30 m simplification, 5 decimals
    from shapely.geometry import LineString
    network = []
    for (a, b), v in sorted(segments.items()):
        coords = v["coords"]
        if len(coords) > 2:
            coords = list(LineString(coords).simplify(0.0003, preserve_topology=False).coords)
        network.append({"a": a, "b": b, "km": v["km"], "line": [[round(x, 5), round(y, 5)] for x, y in coords]})
    (BUILD / "network.json").write_text(json.dumps({"version": None, "segments": network}, separators=(",", ":")),
                                        encoding="utf-8")

    unmatched = [k for k, m in matches.items() if m.lat is None]
    conflicts = [k for k, m in matches.items() if "conflict" in m.method]
    report["summary"] = {
        "trains": len(out_trains), "skipped_trains": len(skipped), "stations": len(out_stations),
        "matched": len(matches) - len(unmatched), "unmatched": unmatched, "unverified": len(unverified),
        "geometry_conflicts": conflicts,
        "routed_trains": sum(1 for t in out_trains if t["route_id"]), "segments": len(segments),
        "speed_flags": len(report["speed"]), "seconds": round(time.time() - t0, 1),
    }
    report["review"] = {k: {"method": m.method, "score": m.score, "matched_name": m.matched_name,
                            "alternatives": m.alternatives}
                        for k, m in sorted(matches.items()) if m.method != "name" or m.score < 95}
    (BUILD / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    net = json.loads((BUILD / "network.json").read_text(encoding="utf-8"))
    net["version"] = bundle["version"]
    (BUILD / "network.json").write_text(json.dumps(net, separators=(",", ":")), encoding="utf-8")

    # Manifest for over-the-air data updates: the app compares `version`,
    # checks `schema` is one it understands, downloads the files and verifies
    # each sha256 before swapping them in.
    def file_entry(name: str) -> dict:
        raw = (BUILD / name).read_bytes()
        return {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    manifest = {
        "schema": BUNDLE_SCHEMA,
        "version": bundle["version"],
        "generated_at": bundle["generated_at"],
        "files": {"bundle": file_entry("bundle.json"), "network": file_entry("network.json")},
    }
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    if APP_BUNDLE.parent.parent.exists():
        APP_BUNDLE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BUILD / "bundle.json", APP_BUNDLE)
        shutil.copyfile(BUILD / "network.json", APP_BUNDLE.parent / "network.json")

    s = report["summary"]
    print(f"bundle {bundle['version']}: {s['trains']} trains ({s['routed_trains']} routed), "
          f"{s['stations']} stations ({s['matched']} positioned), {s['segments']} track segments, "
          f"{s['speed_flags']} speed flags, {len(conflicts)} conflicts, {s['seconds']}s")
    if unmatched:
        print("unmatched:", ", ".join(unmatched))


if __name__ == "__main__":
    main()
