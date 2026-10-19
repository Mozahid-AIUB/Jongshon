import { arrivalOf, departureOf, runsOn } from "./schedule.ts";
import { addDays, bdClock, DAY_MIN } from "./time.ts";
import type { Train } from "./types.ts";

export interface DirectTrip {
  train: Train;
  fromIndex: number;
  toIndex: number;
  /** Minutes after the train's service-date midnight */
  departs: number;
  arrives: number;
  durationMin: number;
  /** Distance travelled between the two stops, when km values are known */
  km: number | null;
}

/**
 * Trains that call at `from` and later at `to`, without changing trains.
 * Sorted by departure time of day.
 */
export function directTrips(trains: Train[], from: string, to: string): DirectTrip[] {
  const out: DirectTrip[] = [];
  for (const train of trains) {
    const fromIndex = train.stops.findIndex((s) => s.station === from);
    if (fromIndex < 0) continue;
    const toIndex = train.stops.findIndex((s, i) => i > fromIndex && s.station === to);
    if (toIndex < 0) continue;
    const a = train.stops[fromIndex]!;
    const b = train.stops[toIndex]!;
    const departs = departureOf(a);
    const arrives = arrivalOf(b);
    out.push({
      train,
      fromIndex,
      toIndex,
      departs,
      arrives,
      durationMin: arrives - departs,
      km: a.km != null && b.km != null ? Math.round((b.km - a.km) * 10) / 10 : null,
    });
  }
  return out.sort((x, y) => (x.departs % DAY_MIN) - (y.departs % DAY_MIN) || x.durationMin - y.durationMin);
}

export type BoardKind = "starts" | "calls" | "terminates";

export interface BoardEntry {
  train: Train;
  serviceDate: string;
  stopIndex: number;
  kind: BoardKind;
  /** Scheduled times, minutes after the service-date midnight (null at origin/terminus) */
  arr: number | null;
  dep: number | null;
  /**
   * Minutes from the query instant to the event that matters on a board:
   * the departure, or the arrival for a train that ends here. Negative = already happened.
   */
  inMin: number;
}

export interface BoardOptions {
  /** Include events up to this many minutes ago (default 60) */
  pastMin?: number;
  /** Include events up to this many minutes ahead (default 180) */
  futureMin?: number;
}

/**
 * Timetable board for one station: every train calling there inside the
 * window, respecting running days and trains that crossed midnight.
 */
export function stationBoard(
  trains: Train[],
  station: string,
  instant: Date | number = Date.now(),
  { pastMin = 60, futureMin = 180 }: BoardOptions = {},
): BoardEntry[] {
  const now = bdClock(instant);
  const out: BoardEntry[] = [];
  for (const train of trains) {
    const stopIndex = train.stops.findIndex((s) => s.station === station);
    if (stopIndex < 0) continue;
    const stop = train.stops[stopIndex]!;
    const last = stopIndex === train.stops.length - 1;
    const kind: BoardKind = stopIndex === 0 ? "starts" : last ? "terminates" : "calls";
    const event = last ? arrivalOf(stop) : departureOf(stop);
    // A journey that started yesterday can still reach this station today, and
    // one that starts tomorrow can fall inside a window that crosses midnight.
    for (const offset of [-1, 0, 1]) {
      const serviceDate = addDays(now.date, offset);
      if (!runsOn(train, serviceDate)) continue;
      const inMin = Math.round(event + offset * DAY_MIN - now.minutes);
      if (inMin < -pastMin || inMin > futureMin) continue;
      out.push({ train, serviceDate, stopIndex, kind, arr: stop.arr, dep: stop.dep, inMin });
    }
  }
  return out.sort((a, b) => a.inMin - b.inMin || a.train.number.localeCompare(b.train.number, "en", { numeric: true }));
}
