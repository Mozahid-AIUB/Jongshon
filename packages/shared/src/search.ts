import type { Station, Train } from "./types.ts";

/** Lowercase, drop punctuation and the words every train name shares. */
export function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[_\-()/.,'’]/g, " ")
    .replace(/\b(express|exp|intercity|commuter|mail|train|station|rly|railway)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Romanised Bangla is spelled many ways (Suborno / Subarna, Chottogram /
 * Chattogram, Sylhet / Silet). Comparing consonant skeletons with common
 * digraphs folded catches most of them.
 */
export function skeleton(text: string): string {
  return normalize(text)
    .replace(/\s+/g, "")
    .replace(/kh/g, "k")
    .replace(/gh/g, "g")
    .replace(/ch/g, "c")
    .replace(/jh/g, "j")
    .replace(/th/g, "t")
    .replace(/dh/g, "d")
    .replace(/ph/g, "f")
    .replace(/bh/g, "b")
    .replace(/sh/g, "s")
    .replace(/[aeiouyw]/g, "")
    .replace(/(.)\1+/g, "$1");
}

export interface Hit<T> {
  item: T;
  score: number;
}

function scoreText(query: string, qSkel: string, candidate: string): number {
  const c = normalize(candidate);
  if (!c) return 0;
  if (c === query) return 100;
  if (c.startsWith(query)) return 80;
  if (c.split(" ").some((w) => w.startsWith(query))) return 70;
  if (c.includes(query)) return 55;
  if (qSkel.length >= 2) {
    const cs = skeleton(candidate);
    if (cs === qSkel) return 50;
    if (cs.startsWith(qSkel)) return 40;
  }
  return 0;
}

export function searchTrains(trains: Train[], rawQuery: string, limit = 20): Hit<Train>[] {
  const q = normalize(rawQuery);
  const digits = rawQuery.replace(/\D/g, "");
  if (!q && !digits) return [];
  const qSkel = skeleton(rawQuery);
  const hits: Hit<Train>[] = [];
  for (const train of trains) {
    let score = 0;
    if (digits && digits.length === rawQuery.replace(/\s/g, "").length) {
      if (train.number === digits || train.number.replace(/^0+/, "") === digits) score = 120;
      else if (train.number.startsWith(digits)) score = 90;
    }
    for (const name of [train.name_en, train.name_bn ?? ""]) {
      score = Math.max(score, scoreText(q, qSkel, name));
    }
    if (score) hits.push({ item: train, score });
  }
  return hits
    .sort((a, b) => b.score - a.score || a.item.number.localeCompare(b.item.number, "en", { numeric: true }))
    .slice(0, limit);
}

export function searchStations(stations: Station[], rawQuery: string, limit = 20): Hit<Station>[] {
  const q = normalize(rawQuery);
  if (!q) return [];
  const qSkel = skeleton(rawQuery);
  const hits: Hit<Station>[] = [];
  for (const station of stations) {
    let score = 0;
    for (const name of [station.name_en, station.name_bn ?? "", ...station.aliases]) {
      score = Math.max(score, scoreText(q, qSkel, name));
    }
    if (score) hits.push({ item: station, score });
  }
  return hits.sort((a, b) => b.score - a.score || a.item.name_en.localeCompare(b.item.name_en)).slice(0, limit);
}
