# Jongshon

Live train tracking for Bangladesh Railway. Store title: **Jongshon: Live Train Track BD** (Bangla: জংশন).

Jongshon answers one question well: *where is my train right now, and when will it reach my station?* Positions come from passengers who share their phone's GPS. When nobody on a train is sharing, the app falls back to history-based estimates and the published timetable, and always labels which one you are looking at.

> Not affiliated with Bangladesh Railway.

## Repository layout

```
apps/
  mobile/        Expo (React Native) app, Expo Router, TypeScript
  api/           Fastify API (phase 2)
packages/
  shared/        Types, Bangladesh-time helpers, timetable position estimate, search
data/
  scripts/       Data pipeline (Node + Python)
  raw/           Source snapshots (e-ticket timetable, OSM rail network, Wikidata)
  build/         Generated bundle the app ships with
docs/
  plan/          Project plan (Bangla)
  competitors/   Market analysis (Bangla)
  design/        Design system
infra/           Docker Compose, Caddy (phase 2)
```

## Getting started

Requirements: Node 22.18+ (24 recommended), pnpm 10, Python 3.12+ for the OSM step.

```sh
pnpm install
pnpm mobile          # start the Expo dev server, open in Expo Go
pnpm test            # shared logic tests
```

Data pipeline (see [data/README.md](data/README.md)):

```sh
pnpm data:fetch      # timetable snapshot from the e-ticket system
pnpm data:osm        # rail network + stations from OpenStreetMap
pnpm data:build      # match stations, route trains, write data/build/bundle.json
pnpm data:validate   # sanity checks on the bundle
```

## Branches

- `main` is always releasable.
- Work happens on `feat/*`, `fix/*`, `data/*` branches and is merged into `main` when it passes typecheck and tests.

## Data and licenses

- Timetable: Bangladesh Railway e-ticket system (eticket.railway.gov.bd), public route information.
- Rail network and station positions: © OpenStreetMap contributors, ODbL 1.0.
- Station metadata: Wikidata, CC0.

Details per field are in [data/README.md](data/README.md).
