import { test } from "node:test";
import assert from "node:assert/strict";
import { searchStations, searchTrains, skeleton } from "./search.ts";
import type { Station, Train } from "./types.ts";

const train = (number: string, name_en: string): Train => ({
  number,
  name_en,
  name_bn: null,
  type: "intercity",
  zone: null,
  origin: "x",
  destination: "y",
  runs_on: ["sun"],
  off_days: [],
  stops: [],
  route_id: null,
  length_km: null,
});

const trains = [train("702", "Suborno Express"), train("701", "Suborno Express"), train("709", "Parabat Express")];

test("number search is exact first", () => {
  assert.equal(searchTrains(trains, "702")[0]!.item.number, "702");
  assert.equal(searchTrains(trains, "70").length, 3);
});

test("romanised spelling variants match", () => {
  assert.equal(skeleton("Subarna"), skeleton("Suborno"));
  assert.equal(searchTrains(trains, "subarna")[0]!.item.name_en, "Suborno Express");
  assert.equal(searchTrains(trains, "parabot express")[0]!.item.number, "709");
});

test("station aliases are searchable", () => {
  const stations: Station[] = [
    { code: "chattogram", name_en: "Chattogram", name_bn: null, aliases: ["Chittagong"], lat: null, lon: null, osm_id: null },
    { code: "dhaka", name_en: "Dhaka", name_bn: null, aliases: ["Kamalapur"], lat: null, lon: null, osm_id: null },
  ];
  assert.equal(searchStations(stations, "chittagong")[0]!.item.code, "chattogram");
  assert.equal(searchStations(stations, "kamala")[0]!.item.code, "dhaka");
});
