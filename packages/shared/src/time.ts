import { WEEKDAYS, type Weekday } from "./types.ts";

/** Bangladesh Standard Time is UTC+6 all year (no daylight saving). */
export const BD_OFFSET_MIN = 6 * 60;
export const DAY_MIN = 24 * 60;

/** Wall-clock view of an instant in Bangladesh time. */
export interface BdClock {
  /** Service-date style key, YYYY-MM-DD */
  date: string;
  /** Minutes after local midnight */
  minutes: number;
  weekday: Weekday;
}

export function bdClock(instant: Date | number = Date.now()): BdClock {
  const ms = typeof instant === "number" ? instant : instant.getTime();
  const local = new Date(ms + BD_OFFSET_MIN * 60_000);
  return {
    date: local.toISOString().slice(0, 10),
    minutes: local.getUTCHours() * 60 + local.getUTCMinutes() + local.getUTCSeconds() / 60,
    weekday: WEEKDAYS[local.getUTCDay()]!,
  };
}

/** Shift a YYYY-MM-DD date by whole days. */
export function addDays(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function weekdayOf(date: string): Weekday {
  return WEEKDAYS[new Date(`${date}T00:00:00Z`).getUTCDay()]!;
}

/** "16:30" → 990 */
export function parseHHMM(value: string): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!m) throw new Error(`bad time "${value}"`);
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) throw new Error(`bad time "${value}"`);
  return h * 60 + min;
}

/** "04:30 pm BST" / "4:30 PM" → 990 */
export function parse12h(value: string): number {
  const m = /^(\d{1,2}):(\d{2})\s*([ap])\.?m\.?/i.exec(value.trim());
  if (!m) throw new Error(`bad 12h time "${value}"`);
  let h = Number(m[1]);
  const min = Number(m[2]);
  if (h < 1 || h > 12 || min > 59) throw new Error(`bad 12h time "${value}"`);
  const pm = m[3]!.toLowerCase() === "p";
  if (h === 12) h = 0;
  return (pm ? h + 12 : h) * 60 + min;
}

/** 990 → "16:30"; values past midnight wrap (1530 → "01:30") */
export function formatHHMM(minutes: number): string {
  const m = ((Math.round(minutes) % DAY_MIN) + DAY_MIN) % DAY_MIN;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

/** 990 → { time: "4:30", period: "PM" } */
export function format12h(minutes: number): { time: string; period: "AM" | "PM" } {
  const m = ((Math.round(minutes) % DAY_MIN) + DAY_MIN) % DAY_MIN;
  const h24 = Math.floor(m / 60);
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return { time: `${h12}:${String(m % 60).padStart(2, "0")}`, period: h24 < 12 ? "AM" : "PM" };
}

/** 295 → "4h 55m", 45 → "45m" */
export function formatDuration(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m}m`;
  return m ? `${h}h ${m}m` : `${h}h`;
}
