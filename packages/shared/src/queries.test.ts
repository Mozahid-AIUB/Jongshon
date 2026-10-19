import { test } from "node:test";
import assert from "node:assert/strict";
import { directTrips, stationBoard } from "./queries.ts";
import type { Train, Weekday } from "./types.ts";

const ALL: Weekday[] = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

function train(number: string, runs_on: Weekday[], stops: [string, number | null, number | null, number][]): Train {
  return {
    number,
    name_en: `Train ${number}`,
    name_bn: null,
    type: "intercity",
    zone: null,
    origin: stops[0]![0],
    destination: stops[stops.length - 1]![0],
    runs_on,
    off_days: ALL.filter((d) => !runs_on.includes(d)),
    route_id: number,
    length_km: stops[stops.length - 1]![3],
    stops: stops.map(([station, arr, dep, km]) => ({ station, arr, dep, km })),
  };
}

// Day train dhaka 07:00 -> airport 07:25/07:30 -> ctg 12:15
const day = train("701", ALL, [
  ["dhaka", null, 420, 0],
  ["airport", 445, 450, 17],
  ["ctg", 735, null, 320],
]);
// Night train dhaka 23:00 -> airport 23:25/23:30 -> ctg 05:00 (+1 day), not on Fridays
const night = train("703", ["sat", "sun", "mon", "tue", "wed", "thu"], [
  ["dhaka", null, 1380, 0],
  ["airport", 1405, 1410, 17],
  ["ctg", 1740, null, 320],
]);
// Other direction
const up = train("702", ALL, [
  ["ctg", null, 600, 0],
  ["dhaka", 900, null, 320],
]);

test("direct trips only in the travel direction, sorted by time of day", () => {
  const trips = directTrips([night, day, up], "dhaka", "ctg");
  assert.deepEqual(trips.map((t) => t.train.number), ["701", "703"]);
  assert.equal(trips[0]!.durationMin, 315);
  assert.equal(trips[1]!.durationMin, 360);
  assert.equal(trips[0]!.km, 320);
  assert.equal(directTrips([day], "ctg", "dhaka").length, 0);
});

test("station board includes trains that crossed midnight", () => {
  // Wednesday 2026-10-21 04:30 Dhaka time = Tuesday 22:30 UTC
  const board = stationBoard([day, night, up], "ctg", Date.UTC(2026, 9, 20, 22, 30));
  // Night train from Tuesday arrives at 05:00 Wednesday: 30 minutes from now
  assert.equal(board.length, 1);
  assert.equal(board[0]!.train.number, "703");
  assert.equal(board[0]!.serviceDate, "2026-10-20");
  assert.equal(board[0]!.kind, "terminates");
  assert.equal(board[0]!.inMin, 30);
});

test("station board respects running days", () => {
  // Saturday 2026-10-24 04:30 Dhaka: the night train did not run on Friday
  const board = stationBoard([night], "ctg", Date.UTC(2026, 9, 23, 22, 30));
  assert.equal(board.length, 0);
});

test("station board window covers a train starting after midnight", () => {
  // Tuesday 2026-10-20 22:00 Dhaka (16:00 UTC), window 3 h: the 23:00 departure is 60 min away
  const board = stationBoard([night, day], "dhaka", Date.UTC(2026, 9, 20, 16, 0));
  assert.deepEqual(board.map((e) => [e.train.number, e.kind, e.inMin]), [["703", "starts", 60]]);
});
