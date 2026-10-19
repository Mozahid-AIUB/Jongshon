/**
 * Sanity checks on data/build/bundle.json. Exits non-zero on errors so a bad
 * timetable update never reaches the app.
 *
 * Usage: node data/scripts/validate-bundle.ts [path/to/bundle.json]
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  arrivalOf,
  departureOf,
  positionAt,
  scheduledDuration,
  type Bundle,
} from "../../packages/shared/src/index.ts";

const here = dirname(fileURLToPath(import.meta.url));
const path = process.argv[2] ?? join(here, "..", "build", "bundle.json");
const bundle = JSON.parse(readFileSync(path, "utf8")) as Bundle;

const errors: string[] = [];
const warnings: string[] = [];

// Bangladesh, with a margin for border stations
const BD = { minLat: 20.5, maxLat: 26.8, minLon: 88.0, maxLon: 92.8 };
const MAX_LEG_KMH = 130;

const stations = new Map(bundle.stations.map((s) => [s.code, s]));
if (stations.size !== bundle.stations.length) errors.push("duplicate station codes");

for (const s of bundle.stations) {
  if (!s.name_en.trim()) errors.push(`station ${s.code}: empty name`);
  if (s.lat == null || s.lon == null) {
    warnings.push(`station ${s.code}: no position`);
    continue;
  }
  if (s.lat < BD.minLat || s.lat > BD.maxLat || s.lon < BD.minLon || s.lon > BD.maxLon) {
    errors.push(`station ${s.code}: position ${s.lat},${s.lon} is outside Bangladesh`);
  }
}

const numbers = new Set<string>();
for (const t of bundle.trains) {
  const id = `train ${t.number} ${t.name_en}`;
  if (numbers.has(t.number)) errors.push(`${id}: duplicate number`);
  numbers.add(t.number);

  if (t.stops.length < 2) {
    errors.push(`${id}: fewer than two stops`);
    continue;
  }
  if (!t.runs_on.length) errors.push(`${id}: runs on no day`);
  if (t.stops[0]!.station !== t.origin) errors.push(`${id}: origin does not match first stop`);
  if (t.stops[t.stops.length - 1]!.station !== t.destination) errors.push(`${id}: destination does not match last stop`);

  let clock = -Infinity;
  let lastKm = -Infinity;
  t.stops.forEach((stop, i) => {
    if (!stations.has(stop.station)) errors.push(`${id}: unknown station ${stop.station}`);
    if (i > 0 && stop.arr == null && stop.dep == null) errors.push(`${id}: ${stop.station} has no time`);
    for (const value of [stop.arr, stop.dep]) {
      if (value == null) continue;
      if (value < clock) errors.push(`${id}: time goes backwards at ${stop.station}`);
      clock = value;
    }
    if (stop.km != null) {
      if (stop.km < lastKm) errors.push(`${id}: km goes backwards at ${stop.station}`);
      lastKm = stop.km;
    }
  });

  const duration = scheduledDuration(t);
  if (duration <= 0 || duration > 24 * 60) errors.push(`${id}: implausible duration ${duration} min`);

  for (let i = 0; i < t.stops.length - 1; i++) {
    const a = t.stops[i]!;
    const b = t.stops[i + 1]!;
    if (a.km == null || b.km == null) continue;
    const minutes = arrivalOf(b) - departureOf(a);
    const km = b.km - a.km;
    if (minutes <= 0) {
      if (km > 2) errors.push(`${id}: ${a.station} -> ${b.station} takes no time for ${km.toFixed(1)} km`);
      continue;
    }
    const kmh = km / (minutes / 60);
    if (kmh > MAX_LEG_KMH) {
      warnings.push(`${id}: ${a.station} -> ${b.station} ${km.toFixed(1)} km in ${minutes} min (${kmh.toFixed(0)} km/h)`);
    }
  }

  // The timetable estimate must say "on the move" halfway through the journey
  const mid = departureOf(t.stops[0]!) + duration / 2;
  const state = positionAt(t, mid).state;
  if (state !== "running" && state !== "at_station") errors.push(`${id}: estimate at mid-journey is "${state}"`);
}

// The update manifest must describe exactly the files next to it
const manifestPath = join(dirname(path), "manifest.json");
if (existsSync(manifestPath)) {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as {
    version: string;
    files: Record<string, { path: string; bytes: number; sha256: string }>;
  };
  if (manifest.version !== bundle.version) errors.push(`manifest version ${manifest.version} != bundle ${bundle.version}`);
  for (const [name, file] of Object.entries(manifest.files)) {
    const raw = readFileSync(join(dirname(path), file.path));
    const sha = createHash("sha256").update(raw).digest("hex");
    if (sha !== file.sha256 || raw.length !== file.bytes) errors.push(`manifest entry ${name} does not match ${file.path}`);
  }
} else {
  warnings.push("no manifest.json next to the bundle");
}

const routed = bundle.trains.filter((t) => t.route_id).length;
console.log(
  `bundle ${bundle.version}: ${bundle.trains.length} trains (${routed} routed), ${bundle.stations.length} stations`,
);
for (const w of warnings) console.log(`  warn  ${w}`);
for (const e of errors) console.log(`  ERROR ${e}`);
console.log(`${errors.length} errors, ${warnings.length} warnings`);
process.exit(errors.length ? 1 : 0);
