import { test } from "node:test";
import assert from "node:assert/strict";
import { addDays, bdClock, format12h, formatDuration, formatHHMM, parse12h, parseHHMM, weekdayOf } from "./time.ts";

test("parses 12-hour times from the e-ticket feed", () => {
  assert.equal(parse12h("04:30 pm BST"), 990);
  assert.equal(parse12h("12:05 am BST"), 5);
  assert.equal(parse12h("12:40 pm"), 760);
  assert.throws(() => parse12h("13:00 pm"));
});

test("parses and formats 24-hour times, wrapping past midnight", () => {
  assert.equal(parseHHMM("16:30"), 990);
  assert.equal(formatHHMM(990), "16:30");
  assert.equal(formatHHMM(1530), "01:30");
});

test("formats for display", () => {
  assert.deepEqual(format12h(990), { time: "4:30", period: "PM" });
  assert.deepEqual(format12h(0), { time: "12:00", period: "AM" });
  assert.equal(formatDuration(295), "4h 55m");
  assert.equal(formatDuration(45), "45m");
  assert.equal(formatDuration(120), "2h");
});

test("Bangladesh clock is UTC+6", () => {
  // 2026-10-19 20:30 UTC is 2026-10-20 02:30 in Dhaka (a Tuesday)
  const c = bdClock(Date.UTC(2026, 9, 19, 20, 30));
  assert.equal(c.date, "2026-10-20");
  assert.equal(c.minutes, 150);
  assert.equal(c.weekday, "tue");
});

test("date helpers", () => {
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(addDays("2026-03-01", -1), "2026-02-28");
  assert.equal(weekdayOf("2026-10-23"), "fri");
});
