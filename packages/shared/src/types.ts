/**
 * Static data bundle (data/build/bundle.json). The app ships one copy and can
 * download newer versions without an app update.
 *
 * All schedule times are integer minutes after midnight (Bangladesh time) of
 * the train's service date, i.e. the date it leaves its origin. Values above
 * 1440 mean the next calendar day, so an overnight train needs no extra
 * day-offset bookkeeping.
 */

export type Weekday = "sun" | "mon" | "tue" | "wed" | "thu" | "fri" | "sat";

export const WEEKDAYS: readonly Weekday[] = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

export type TrainType = "intercity" | "commuter" | "mail_express" | "local" | "shuttle" | "special";

export type Zone = "EAST" | "WEST";

export interface Station {
  /** Stable key, e.g. "biman_bandar" */
  code: string;
  name_en: string;
  name_bn: string | null;
  /** Other spellings people search with: Chittagong, CTG, Kamalapur … */
  aliases: string[];
  lat: number | null;
  lon: number | null;
  osm_id: number | null;
}

export interface Stop {
  station: string;
  /** Minutes after service-date midnight; null at the origin */
  arr: number | null;
  /** Minutes after service-date midnight; null at the terminus */
  dep: number | null;
  /** Distance along the train's route from the origin, when the route geometry is known */
  km: number | null;
}

export interface Train {
  /** Kept as a string: "01", "702" */
  number: string;
  name_en: string;
  name_bn: string | null;
  type: TrainType;
  zone: Zone | null;
  origin: string;
  destination: string;
  runs_on: Weekday[];
  off_days: Weekday[];
  stops: Stop[];
  /** Key into routes.geojson; null until the route is matched to the rail network */
  route_id: string | null;
  /** Total route length in km, from the matched geometry */
  length_km: number | null;
}

export interface DataSource {
  id: string;
  name: string;
  url: string;
  fetched_at: string;
  license: string;
}

export interface Bundle {
  version: string;
  generated_at: string;
  sources: DataSource[];
  stations: Station[];
  trains: Train[];
}
