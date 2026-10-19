import { addDays, bdClock, DAY_MIN, weekdayOf } from "./time.ts";
import type { Stop, Train } from "./types.ts";

export function departureOf(stop: Stop): number {
  return stop.dep ?? stop.arr ?? 0;
}

export function arrivalOf(stop: Stop): number {
  return stop.arr ?? stop.dep ?? 0;
}

/** Scheduled minutes from origin departure to terminus arrival. */
export function scheduledDuration(train: Train): number {
  const first = train.stops[0];
  const last = train.stops[train.stops.length - 1];
  if (!first || !last) return 0;
  return arrivalOf(last) - departureOf(first);
}

export function runsOn(train: Train, serviceDate: string): boolean {
  return train.runs_on.includes(weekdayOf(serviceDate));
}

export type SchedulePosition =
  | { state: "not_started"; startsInMin: number }
  | { state: "at_station"; stopIndex: number; leavesInMin: number }
  | {
      state: "running";
      /** Index of the stop the train last left */
      fromIndex: number;
      /** 0..1 between stops[fromIndex] and stops[fromIndex + 1], by time */
      fraction: number;
      /** Estimated distance from origin, when km values are known */
      km: number | null;
      nextArrivalInMin: number;
    }
  | { state: "arrived"; arrivedMinAgo: number };

/**
 * Where the timetable says the train is at `minute` (minutes after service-date
 * midnight), optionally shifted by a known delay.
 *
 * Internal use only: deciding which journeys are scheduled to be under way,
 * checking that a passenger's GPS fits the train they picked, etc. Never show
 * the result to users as a train position (owner's rule, plan decision 4):
 * positions come only from real sources.
 */
export function positionAt(train: Train, minute: number, delayMin = 0): SchedulePosition {
  const stops = train.stops;
  const t = minute - delayMin;
  const first = stops[0];
  const last = stops[stops.length - 1];
  if (!first || !last) return { state: "not_started", startsInMin: 0 };

  const start = departureOf(first);
  if (t < start) return { state: "not_started", startsInMin: start - t };
  const end = arrivalOf(last);
  if (t >= end) return { state: "arrived", arrivedMinAgo: t - end };

  for (let i = 0; i < stops.length - 1; i++) {
    const here = stops[i]!;
    const next = stops[i + 1]!;
    const arr = arrivalOf(here);
    const dep = departureOf(here);
    if (i > 0 && t >= arr && t < dep) {
      return { state: "at_station", stopIndex: i, leavesInMin: dep - t };
    }
    const nextArr = arrivalOf(next);
    if (t >= dep && t < nextArr) {
      const span = Math.max(1, nextArr - dep);
      const fraction = Math.min(1, Math.max(0, (t - dep) / span));
      const km =
        here.km != null && next.km != null ? here.km + (next.km - here.km) * fraction : null;
      return { state: "running", fromIndex: i, fraction, km, nextArrivalInMin: nextArr - t };
    }
  }
  return { state: "arrived", arrivedMinAgo: 0 };
}

export interface ActiveJourney {
  train: Train;
  serviceDate: string;
  /** Minutes after this journey's service-date midnight, at the moment of the query */
  minute: number;
  position: SchedulePosition;
}

/**
 * Journeys the timetable says are on the move (or at a stop) at `instant`.
 * Overnight trains that left yesterday are included. Suitable for a
 * "scheduled to be on the way" list; the `position` field is internal and is
 * not a real position (see `positionAt`).
 */
export function activeJourneys(trains: Train[], instant: Date | number = Date.now()): ActiveJourney[] {
  const now = bdClock(instant);
  const out: ActiveJourney[] = [];
  for (const train of trains) {
    for (const back of [0, 1]) {
      const serviceDate = addDays(now.date, -back);
      if (!runsOn(train, serviceDate)) continue;
      const minute = now.minutes + back * DAY_MIN;
      const position = positionAt(train, minute);
      if (position.state === "running" || position.state === "at_station") {
        out.push({ train, serviceDate, minute, position });
      }
    }
  }
  return out;
}

/** Index of a station in the train's stop list, or -1. */
export function stopIndex(train: Train, station: string): number {
  return train.stops.findIndex((s) => s.station === station);
}
