/**
 * Pulls the published timetable from Bangladesh Railway's e-ticket system
 * (eticket.railway.gov.bd, API host railspaapi.shohoz.com).
 *
 * - GET  /all-trains/info  -> every ticketed train number with origin/destination
 * - POST /train-routes     -> ordered stops, arrival/departure, halt, running days
 *
 * Raw responses are stored untouched under data/raw/eticket so the build step
 * can be re-run without hitting the API again. Requests are sequential and
 * spaced out; existing files are skipped unless --refresh is passed.
 *
 * Usage: node data/scripts/fetch-eticket.ts [--refresh] [--only 701,702]
 */
import { mkdir, readFile, writeFile, access } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const API = "https://railspaapi.shohoz.com/v1.0/web";
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "raw", "eticket");
const ROUTES_DIR = join(ROOT, "routes");
const DELAY_MS = 1500;
const HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json",
  "User-Agent": "Jongshon-timetable-sync/0.1",
};

const args = process.argv.slice(2);
const refresh = args.includes("--refresh");
const onlyIdx = args.indexOf("--only");
const only = onlyIdx >= 0 ? new Set(args[onlyIdx + 1].split(",")) : null;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function exists(path: string) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function request(url: string, init: RequestInit, attempt = 1): Promise<unknown> {
  try {
    const res = await fetch(url, { ...init, headers: HEADERS, signal: AbortSignal.timeout(30_000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    if (attempt >= 4) throw err;
    const wait = 2000 * 2 ** attempt;
    console.warn(`  retry ${attempt} in ${wait / 1000}s: ${(err as Error).message}`);
    await sleep(wait);
    return request(url, init, attempt + 1);
  }
}

/** A date a few days ahead; the route endpoint returns the same stops for any date. */
function journeyDate() {
  const d = new Date(Date.now() + 3 * 86_400_000);
  return d.toISOString().slice(0, 10);
}

async function main() {
  await mkdir(ROUTES_DIR, { recursive: true });

  const listPath = join(ROOT, "all-trains-info.json");
  let list: any;
  if (refresh || !(await exists(listPath))) {
    console.log("Fetching train list…");
    list = await request(`${API}/all-trains/info`, { method: "GET" });
    await writeFile(listPath, JSON.stringify(list, null, 2));
  } else {
    list = JSON.parse(await readFile(listPath, "utf8"));
  }

  const trains: { train_number: string }[] = list.data.trains;
  const date = journeyDate();
  console.log(`${trains.length} trains in list, journey date ${date}`);

  let fetched = 0;
  let empty: string[] = [];
  for (const t of trains) {
    const no = t.train_number;
    if (only && !only.has(no)) continue;
    const out = join(ROUTES_DIR, `${no}.json`);
    if (!refresh && (await exists(out))) continue;

    const body = JSON.stringify({ model: no, departure_date_time: date });
    const json: any = await request(`${API}/train-routes`, { method: "POST", body });
    const stops = json?.data?.routes?.length ?? 0;
    if (!stops) empty.push(no);
    await writeFile(out, JSON.stringify({ fetched_at: new Date().toISOString(), journey_date: date, ...json }, null, 2));
    fetched++;
    console.log(`  ${no.padStart(4)}  ${String(stops).padStart(2)} stops  ${json?.data?.train_name ?? ""}`);
    await sleep(DELAY_MS);
  }

  console.log(`Done. fetched=${fetched}${empty.length ? `, empty routes: ${empty.join(", ")}` : ""}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
