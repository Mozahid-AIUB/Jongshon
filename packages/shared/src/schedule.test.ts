import { test } from "node:test";
import assert from "node:assert/strict";
import { activeJourneys, positionAt, runsOn, scheduledDuration } from "./schedule.ts";
import type { Train } from "./types.ts";

// Overnight train: leaves 22:00, stops 23:50-00:05, arrives 02:00 next day
const night: Train = {
  number: "999",
  name_en: "Test Night Express",
  name_bn: null,
  type: "intercity",
  zone: "EAST",
  origin: "a",
  destination: "c",
  runs_on: ["mon", "wed"],
  off_days: ["sun", "tue", "thu", "fri", "sat"],
  route_id: "999",
  length_km: 200,
  stops: [
    { station: "a", arr: null, dep: 1320, km: 0 },
    { station: "b", arr: 1430, dep: 1445, km: 100 },
    { station: "c", arr: 1560, dep: null, km: 200 },
  ],
};

test("duration spans midnight", () => {
  assert.equal(scheduledDuration(night), 240);
});

test("position before, during, at a stop and after the journey", () => {
  assert.deepEqual(positionAt(night, 1300), { state: "not_started", startsInMin: 20 });

  const halfway = positionAt(night, 1375);
  assert.equal(halfway.state, "running");
  if (halfway.state === "running") {
    assert.equal(halfway.fromIndex, 0);
    assert.equal(halfway.fraction, 0.5);
    assert.equal(halfway.km, 50);
    assert.equal(halfway.nextArrivalInMin, 55);
  }

  assert.deepEqual(positionAt(night, 1440), { state: "at_station", stopIndex: 1, leavesInMin: 5 });
  assert.deepEqual(positionAt(night, 1600), { state: "arrived", arrivedMinAgo: 40 });
});

test("a known delay shifts the estimate", () => {
  const late = positionAt(night, 1340, 30);
  assert.equal(late.state, "not_started");
});

test("running days use the service date (origin departure date)", () => {
  assert.equal(runsOn(night, "2026-10-19"), true); // Monday
  assert.equal(runsOn(night, "2026-10-20"), false); // Tuesday
});

test("overnight journey that left yesterday is active after midnight", () => {
  // Tuesday 2026-10-20 00:30 in Dhaka = Monday 18:30 UTC
  const active = activeJourneys([night], Date.UTC(2026, 9, 19, 18, 30));
  assert.equal(active.length, 1);
  assert.equal(active[0]!.serviceDate, "2026-10-19");
  assert.equal(active[0]!.position.state, "running");
});
