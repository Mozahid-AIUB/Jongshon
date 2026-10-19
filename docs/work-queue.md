# Work queue (team lead)

The single source of truth for "what next". Every work session, including the
hourly auto-resume, starts here: finish what is in progress, then take the
first unchecked task. Tick boxes and commit this file as tasks finish.

Owner preferences: reply in Bangla script; app is English first; best-in-class
quality and smooth animation; full freedom, subagents allowed (max 3 at once).

## Ground rules
- Never deploy, sign in to accounts, or push secrets. Accounts and payments are the owner's job (see "Waiting on the owner").
- Never take other tracking apps' data, directly or indirectly. Sources: e-ticket timetable, OSM, Wikidata, official Bangladesh Railway documents, our own users.
- Work on `feat/*`, `data/*`, `fix/*` branches; merge into `main` with `--no-ff` only when typecheck, tests and `pnpm data:validate` pass; then push.
- Do not run two `pnpm install`s at once in the main working tree.

## In progress (background agents started 2026-10-20, all three hit the usage limit at ~02:30 and were resumed 05:22)
- [ ] **Mobile foundation** (agent, main working tree, `apps/mobile`): Expo SDK 58 app, theme, motion, screens, Skia network map, uses `assets/data/bundle.json` + `network.json`.
  On finish: run `pnpm --filter @jongshon/mobile exec tsc --noEmit` and `npx expo export --platform android` in `apps/mobile`; check screens against `docs/design/design-system.md`; branch `feat/mobile-foundation`, commit, merge, push. Then tell the owner how to open it in Expo Go.
- [ ] **Data research** (agent, `data/raw/*`, `data/scripts/parse_*`, `fetch_eticket_extra.py`): sources for mail/commuter/local trains, Bangla train and station names, fares, cross-check. Report in `data/raw/SOURCES.md`.
  On finish: read the report; feed Bangla names and aliases into `build_bundle.py` (train `name_bn`, station `name_bn`, aliases); add non-e-ticket trains as a second timetable source if a parser exists; rebuild, validate, commit on `data/names-and-coverage`, merge, push.
- [ ] **Backend foundation** (agent, separate git worktree, branch `feat/api-foundation`): Fastify API, Postgres/PostGIS migrations, tracking engine, chat, push, Docker Compose, VPS guide.
  On finish: review the diff, run its tests, merge the branch into `main`, push. Summarise for the owner what the VPS needs.

## Next (in order)
- [ ] ESLint (flat config) for TypeScript + React Native at the root; fix findings.
- [ ] GitHub Actions CI: install, typecheck, `pnpm test`, `pnpm data:validate` on every push and PR. **Written** at `.github/workflows/ci.yml` (uncommitted): commit it on `feat/ci` right after the mobile merge, because it needs the committed `pnpm-lock.yaml`.
- [ ] Mobile: development-build setup for MapLibre (`expo-dev-client`, `@maplibre/maplibre-react-native` config plugin, `eas.json` profiles) so the map can switch from the Skia drawing to real vector tiles once the owner has an Expo account. Style: OpenFreeMap tiles for development, indigo light/dark styles from the design system.
- [ ] Mobile: GPS sharing spike screen (expo-location + task manager, Android foreground service, batching, offline queue) for the owner's real-train test (plan section 9, phase 0).
- [ ] Mobile: i18n check (every string in `en.json`), accessibility pass (labels, 48 dp targets, contrast), reduce-motion pass.
- [ ] Data: over-the-air bundle updates (manifest with version + hash, app downloads newer bundle).
- [x] Docs: privacy policy draft (`docs/legal/privacy-policy.md`) and Play listing (`docs/store/play-listing.md`); [TBD] items need the domain, contact and hosting details.

## Waiting on the owner
- Expo Go on an Android phone (to preview), expo.dev account (dev builds), phone brand.
- VPS details (OS version, RAM/CPU), domain (jongshon.app or .com).
- Later: Firebase project (FCM), Google Play developer account, 12 closed-testing testers, a real train trip for the GPS test.

## Done
- [x] Monorepo, shared logic with tests, design system, plan updates (2026-10-20)
- [x] Timetable bundle pipeline: 127 trains routed, 236 stations positioned, validator 0 errors (2026-10-20)
- [x] Simplified track network for the app map (2026-10-20)
