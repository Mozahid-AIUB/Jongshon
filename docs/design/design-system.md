# Jongshon design system

Status: approved 2026-10-20. Brand color: deep indigo + signal amber.
Language: the app ships in **English first**; Bangla is added later through i18n. Every string goes through i18n from day one, and every font token has a Bangla counterpart.

Live preview of the approved look: https://claude.ai/artifact/NqtZCeNhMRqRuGsUZbqVZn (option "Indigo + Amber").

## 1. Principles

1. **Status reads first.** Delay, on-time, live and estimated are the most important pixels on any screen. Brand color never competes with status color.
2. **Calm surfaces, one accent.** Mostly white and cool neutrals. Indigo marks what is interactive or "ours". Amber appears only in the logo and brand moments.
3. **Real data only** (owner's rule, 2026-10-20). A train position appears only when it comes from a real source (passenger GPS, station report, official TTMS reply) and always shows its age: `Live · 2 min ago` or `Last seen at Feni · 25 min ago`. No estimated or timetable-derived positions, ever. Published timetable times are shown and labelled `Scheduled`; `Expected` times only come from a real measured delay and say when it was measured.
4. **Motion explains, never decorates.** Animations show cause and effect (a train moving along a line, a sheet rising from the card that opened it). 60 fps or it does not ship. Respect "reduce motion".
5. **Thumb-first.** Primary actions sit in the lower half of the screen. Touch targets are at least 48 dp.

## 2. Color tokens

### Brand (indigo scale)
| Token | Hex | Use |
|---|---|---|
| `indigo.50` | `#EEF0FA` | selected row background |
| `indigo.100` | `#DDE2F5` | chip fill, pressed ghost button |
| `indigo.200` | `#BAC4EB` | dividers on indigo tint |
| `indigo.300` | `#9AA8FF` | **primary in dark mode** |
| `indigo.400` | `#6F80D6` | |
| `indigo.500` | `#4A5DB8` | focus ring |
| `indigo.600` | `#3546A0` | pressed primary (dark mode hover) |
| `indigo.700` | `#2B3A8C` | **primary** (header, buttons, active tab, train marker, route line). White text 10:1 |
| `indigo.800` | `#222E70` | pressed primary |
| `indigo.900` | `#1A2255` | status bar, deep headers, splash |
| `indigo.950` | `#10153A` | splash gradient end, shadows tint |

### Signal amber (brand moments only)
| Token | Hex | Use |
|---|---|---|
| `amber.signal` | `#F5A623` | logo, splash, store art, onboarding illustration. **Never** in status UI |

### Neutrals (cool, slightly indigo-biased)
| Token | Light | Dark |
|---|---|---|
| `bg` (screen) | `#F5F6F9` | `#0E1018` |
| `surface` (cards, sheets, tab bar) | `#FFFFFF` | `#171A24` |
| `surfaceRaised` (sheet over sheet, popovers) | `#FFFFFF` | `#20232F` |
| `line` (borders, dividers) | `#E4E6EC` | `#2A2D3A` |
| `text` | `#1A1C24` | `#ECEDF3` |
| `textMuted` | `#5A5F6E` | `#A3A7B5` |
| `textSubtle` (placeholders, disabled) | `#8A8F9E` | `#6E7383` |
| `primary` | `#2B3A8C` | `#9AA8FF` |
| `onPrimary` | `#FFFFFF` | `#0E1018` |
| `header` | `#2B3A8C` | `#171A24` (title in `primary`) |
| `onHeader` | `#FFFFFF` | `#9AA8FF` |

### Status (semantic, identical meaning everywhere)
| Token | Light | Dark | Meaning |
|---|---|---|---|
| `status.live` | `#188038` | `#5BC57A` | live data / on time (dot + text, tinted 13% background) |
| `status.lateBg` / `status.lateFg` | `#F59E0B` / `#1A1C24` | same | delayed. Always text + clock icon, never color alone |
| `status.cancelled` | `#3F4351` | `#C9CCD6` | cancelled, with strikethrough on the time |
| `status.lastSeen` | `#5A5F6E` text + clock icon | `#A3A7B5` | real data that is older than 2 min: place and age, never moved forward |
| `status.error` | `#C5221F` | `#F2877F` | form/system errors only, never train status |

Rules
- A train's **delay is never shown in red**. Late = amber badge with black text (7.9:1).
- The train marker and route line use `primary`, never green or amber.
- Never put green directly on red or amber on white text.

## 3. Typography

Font pairs are per locale so Bangla can be switched on later without touching components.

| Role | English (now) | Bangla (later) | Use |
|---|---|---|---|
| `display` | **Anek Latin** 600–700 | Anek Bangla 600–700 | screen titles, train names, times, numbers |
| `body` | **Hind** 400–600 | Hind Siliguri 400–600 | body, labels, metadata |

Google Fonts via `@expo-google-fonts/anek-latin`, `@expo-google-fonts/hind` (later `anek-bangla`, `hind-siliguri`).

| Token | Size / line | Weight | Family |
|---|---|---|---|
| `display` | 30 / 36 | 700 | display |
| `title` | 22 / 28 | 700 | display |
| `headline` | 18 / 24 | 600 | display |
| `trainName` | 17 / 22 | 600 | display |
| `time` | 20 / 24 | 600, tabular | display |
| `body` | 15 / 22 | 400 | body |
| `bodyStrong` | 15 / 22 | 600 | body |
| `label` | 13 / 18 | 500 | body |
| `caption` | 12 / 16 | 500 | body |
| `overline` | 11 / 14 | 600, +0.6 letter spacing, uppercase | body |

Times use 12-hour format with a small `AM`/`PM` (caption size) after the digits.

## 4. Space, shape, elevation

- Spacing scale (dp): 2, 4, 8, 12, 16, 20, 24, 32, 40, 48. Screen gutter 16.
- Radius: chip 999, button 14, input 14, card 18, sheet 28 (top corners), app icon 22%.
- Elevation (light): cards use a 1px `line` border plus `shadow.sm` = 0 1 2 rgba(16,21,58,0.04) and 0 4 12 rgba(16,21,58,0.05). Sheets use `shadow.lg` = 0 -8 32 rgba(16,21,58,0.12). Dark mode: no shadows, use `surfaceRaised` and borders.
- Header: indigo block under the status bar, content cards may overlap its bottom edge by 12 dp.

## 5. Motion

Library: `react-native-reanimated` (UI-thread), `react-native-gesture-handler`, `@gorhom/bottom-sheet`, `lottie-react-native` for After Effects files, `@shopify/react-native-skia` for custom drawing, `expo-haptics`.

| Token | Value | Use |
|---|---|---|
| `duration.fast` | 120 ms | press feedback, chip select |
| `duration.base` | 220 ms | fades, list item enter |
| `duration.slow` | 360 ms | screen-level, sheet snap |
| `easing.standard` | cubic-bezier(0.2, 0, 0, 1) | most transitions |
| `easing.emphasized` | cubic-bezier(0.3, 0, 0, 1) | entering elements |
| `spring.default` | damping 18, stiffness 180, mass 1 | sheets, drag release |
| `spring.snappy` | damping 22, stiffness 320 | toggles, press scale |

Patterns
- **Press:** scale to 0.97 with `spring.snappy`, light haptic on primary actions.
- **Lists:** items fade + rise 8 dp, staggered 30 ms, only on first load.
- **Live dot:** soft pulse (scale 1 → 2.2, opacity 0.5 → 0) every 1.6 s.
- **Train on progress bar (live data only):** marker glides between real positions over `duration.slow`; never jumps, never extrapolates.
- **Timeline:** the current-position marker travels down the timeline; passed stops fill with `primary`.
- **Numbers:** delay and ETA change with a vertical roll (old value up and out, new value in).
- **Skeletons:** shimmer at 1.2 s for loading states, never spinners in lists.
- **Reduce motion:** replace movement with 120 ms cross-fades; disable pulses.

## 6. Iconography and imagery

- Icons: `lucide-react-native`, stroke 1.75, 22 dp in lists, 24 dp in the tab bar.
- Illustrations and Lottie: line style in `indigo.700` with `amber.signal` highlights. Only assets we create or whose license allows commercial use in an app (LottieFiles "Lottie Simple License", Unsplash, CC0/CC BY with credit). Record every third-party asset in `apps/mobile/assets/CREDITS.md`.

## 7. Core components

| Component | Notes |
|---|---|
| `TrainCard` | name + number, status chips row, scheduled times row; the progress track and marker appear only with real live data |
| `StatusChip` | variants `live`, `lastSeen(minutes)`, `onTime`, `late(minutes)`, `scheduled`, `cancelled` |
| `ProgressTrack` | 4 dp track, filled part in `primary`, 14 dp marker with 3 dp surface border |
| `Timeline` | vertical stops, passed/current/upcoming states, scheduled vs expected times |
| `SearchField` | 14 radius, leading search icon, on the header it is white (light) / `surfaceRaised` (dark) |
| `PrimaryButton` | full width, 52 dp tall, `primary` background, press scale + haptic |
| `Sheet` | bottom sheet with 28 radius, grabber, snap points |
| `TabBar` | Home, Live, Map, Saved; active = `primary` icon + label, others `textMuted` |
| `EmptyState` | Lottie or illustration, one sentence, one action |
