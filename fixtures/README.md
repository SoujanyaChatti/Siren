# SIREN replay fixtures

Each area is a folder in `areas/<id>/` built by `scripts/build_fixtures.py <id>` from `scripts/areas/<id>.json`,
plus hand-made `area.json`, `zones.geojson`, `users.json` and `scenes.json`. Shared: `photos/`,
`depth_validation/`, `translation_review.json`.

- `areas/houston-brays/`: Hurricane Beryl, Brays Bayou (documented below)
- `areas/asheville-helene/`: Hurricane Helene, Sept 25–27 2024. French Broad River at Asheville (AVLN7 / USGS
  03451500; action 6.5, minor 9.5, moderate 13, major 18 ft; peaked 24.8 ft) and Swannanoa River at Biltmore
  (BLTN7 / USGS 03451000; action 9, minor 10, moderate 14.5, major 16.5 ft; peaked 27.3 ft, with gaps of
  1.75 h and 2.5 h in the record during the peak). Rain: Asheville Regional Airport ASOS (AVL), 14.2 in over the
  window. 9 NWS GSP warnings/advisories. 18 OSM facilities. The demo photo is the same FEMA Houston photo,
  submitted at a demo location in Biltmore Village; it was not taken there.

- `areas/montpelier-2023/`: Vermont flood, Jul 10–11 2023. Winooski River at Montpelier (MONV1 / USGS 04286000;
  11 / 15 / 16 / 17.5 ft; peak 21.29 ft) and Dog River at Northfield Falls (NFFV1 / USGS 04287000; 7 / 8 / 10 / 11 ft;
  peak 11.63 ft; hourly record ends early on Jul 11, shown as missing data). Rain: Barre-Montpelier ASOS (MPV), 6.4 in.
  5 NWS BTV warnings. 19 OSM facilities.
- `areas/whitesburg-2022/`: Eastern Kentucky flood, Jul 28 2022. North Fork Kentucky River at Whitesburg (WHTK2 /
  USGS 03277300; 8 / 10 / 12 / 14 ft; 3 ft → 22.04 ft record crest; repeated gaps of 1–3 h after the crest).
  Rain: Jackson KY ASOS (JKL, ~60 km away), 4.7 in. 3 NWS JKL warnings. 5 OSM facilities.
- `areas/san-diego-2024/`: Jan 22 2024. San Diego River at Fashion Valley (FSNC1 / USGS 11023000; 7.5 / 10 / 13.5 /
  16.5 ft; peak 11.4 ft). Rain: San Diego Lindbergh Field ASOS (SAN), 2.7 in. 4 NWS SGX warnings. 36 OSM facilities.

All new packs use the same FEMA Houston demo photo at a labelled demo location. Zones are hand-drawn for the demo.

The rest of this file documents the Houston pack.

All replay data is real, public, historical data, pulled once by `scripts/build_fixtures.py` and committed so the
demo runs with Wi-Fi off. Nothing here is synthetic except where marked.

## Event

**Hurricane Beryl, Monday July 8, 2024**, Brays Bayou, southwest Houston. Replay window 03:00–21:00 UTC
(10:00 PM Jul 7 – 4:00 PM Jul 8 CDT), 15-minute data, played at 60× by default.

## Files

| File | Contents | Source |
| --- | --- | --- |
| `stations.json` | Gauges with official NOAA flood categories; rain stations | NOAA NWPS API `api.water.noaa.gov/nwps/v1/gauges/{lid}` |
| `readings.json` | 151 stage readings (2 gauges) + 154 15-min rain totals (2 stations) | USGS Water Data OGC API; NWS ASOS via IEM |
| `official_warnings.json` | 7 NWS HGX warnings/advisories touching the area during the event | Iowa Environmental Mesonet storm-based warning archive |
| `zones.geojson` | 3 hand-drawn watch zones along Brays Bayou, each linked to a gauge, rain station and road points | Drawn for this demo |
| `facilities.json` | 153 hospitals, clinics, schools, nursing homes, fire stations | OpenStreetMap via Overpass API (© OpenStreetMap contributors, ODbL) |
| `route.json` | Maria's commute: usual route through the S Rice Ave low point, and a safer route | OSRM public demo server on OpenStreetMap data, precomputed |
| `users.json` | Seeded personas Maria, James, Rosa | Fictional |
| `scenes.json` | Demo "jump to scene" times | — |
| `photos/demo_underpass.jpg` | Demo photo report | FEMA photo, public domain (below) |
| `photos/demo_underpass.analysis.json` | Human reference annotation for offline use (labelled `fixture`, **not** a model output) | SIREN team |
| `depth_validation/` | Seed validation photos with judged depths | Wikimedia Commons (licenses in manifest) |
| `translation_review.json` | Whether the Spanish template phrases were reviewed by a fluent speaker | — |

## Gauges and official flood categories (NOAA NWPS)

| NWPS id | USGS site | Name | Action | Minor | Moderate | Major |
| --- | --- | --- | --- | --- | --- | --- |
| GSST2 | 08074810 | Brays Bayou at Gessner Dr | 54 ft | 57 ft | 58 ft | 59 ft |
| HBMT2 | 08075000 | Brays Bayou at Main St, Houston | 38 ft | 41 ft | 42 ft | 43 ft |

Observed in this window: Gessner peaked at 57.43 ft (14:45 UTC); Main St peaked at 41.73 ft (≈15:15 UTC). Both
crossed action and minor flood stage, neither reached moderate.

## Rain

NWS ASOS hourly-cumulative precipitation (`p01i`) at Sugar Land (SGR) and Houston Hobby (HOU), converted to
increments and bucketed into 15-minute totals ending at the bucket time. Totals over the window: SGR 5.70 in,
HOU 5.28 in. Harris County Flood Warning System gauges are denser and closer to the bayou; they would be the
preferred live source (not used in this build). No 1-hour total reached the 2.0 in `RAIN_1H` threshold.

## Official warnings in the archive (HGX, touching the area)

| Issued (UTC) | Event | IEM id |
| --- | --- | --- |
| 09:12 | Flood Advisory | HGX.FA.Y.0091 |
| 09:54 | Flash Flood Warning | HGX.FF.W.0051 (covers all three zones) |
| 11:09 | Flood Warning (river) | HGX.FL.W.0113 |
| 13:32 | Flood Warning (river) | HGX.FL.W.0127 |
| 15:36 | Flood Warning (river) | HGX.FL.W.0134 |
| 16:00 | Flash Flood Warning | HGX.FF.W.0055 |
| 18:29 | Flood Warning (areal) | HGX.FA.W.0036 |

## Demo photo

`photos/demo_underpass.jpg`: "Cars Floating in Houston Street", Houston TX, 2017-08-31, Dominick Del Vecchio / FEMA.
Public domain. https://commons.wikimedia.org/wiki/File:FEMA_-_IMG_0401MEB_-_Cars_Floating_in_Houston_Street.jpg
In the demo it is submitted at the S Rice Ave / Braeswood Blvd low point in Zone B (a demo location; the photo
was not taken there).

## Synthetic data

Only `POST /api/simulate` (director backup) injects synthetic readings; they are tagged `quality: synthetic`
and `source: simulate` everywhere they appear.

## Rebuild

    backend/.venv/bin/python scripts/build_fixtures.py

Thresholds in `backend/app/rules/rules.yaml` are independent of this script and were fixed before computing the
lead-time comparison.
