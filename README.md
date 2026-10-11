# SIREN

**Evidence-backed flood warnings that tell every resident what's happening, who's affected, and what to do, in their own language.**

SIREN turns changing environmental data into accessible, traceable flood warnings. It works for any US river or
bayou with USGS gauges and NOAA flood categories; the repo ships five real storms as **area packs**, switchable from the top bar:

| Area | Storm | Gauges (peak vs NOAA major stage) |
| --- | --- | --- |
| Brays Bayou, Houston TX | Hurricane Beryl, Jul 8 2024 | Gessner 57.4 ft, Main St 41.7 ft (both past minor) |
| French Broad & Swannanoa, Asheville NC | Hurricane Helene, Sep 25–27 2024 | 24.8 ft (major 18), 27.3 ft (major 16.5); gauge outage at peak |
| Winooski & Dog Rivers, Montpelier VT | Vermont flood, Jul 10–11 2023 | 21.3 ft (major 17.5), 11.6 ft (major 11) |
| North Fork Kentucky River, Whitesburg KY | Eastern Kentucky flood, Jul 28 2022 | 22.0 ft (major 14), rose 19 ft in ~10 h; gauge outage |
| San Diego River, Mission Valley CA | San Diego flash flood, Jan 22 2024 | 11.4 ft (minor 10) | A deterministic rules engine
decides every alert, and AI only explains, translates and answers questions, with every AI output validated.
Residents get voice alerts in English or Spanish, can ask follow-up questions, and can send a photo that becomes
a depth estimate. A verified estimate of 12 inches or more on a road fires a do-not-drive rule.

> Not an official warning system. Follow instructions from local officials.

## Run it (offline, no keys needed)

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DEMO_OFFLINE=true .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8765

# frontend (dev server proxies /api to :8765)
cd frontend && npm install && npm run dev        # http://localhost:5173
# or build once and let the backend serve it:  npm run build  ->  http://localhost:8765
```

Tests: `cd backend && .venv/bin/python -m pytest -q` (46 tests: rules, hysteresis, stale data, lifecycle,
validators and fallback chain, depth checks, message limits, full API demo flow).

With keys, copy `.env.example` to `.env`, set `DEMO_OFFLINE=false` once, and run
`backend/.venv/bin/python scripts/warm_cache.py` to fill `cache/` with Gemini and ElevenLabs outputs for the demo
path. Then switch back to `DEMO_OFFLINE=true`: the demo replays those cached outputs with Wi-Fi off.

## Live status anywhere in the US, right now (`/live`)

Residents can check their real location without any replay: tap **Use my location** (or search a city, address
or ZIP). For that point SIREN, in about 5–10 seconds (then cached for 5 minutes):

1. asks the NWS points API for the time zone, nearest town and weather stations
2. finds river gauges within 50 km that have official NOAA flood categories, with their last hours of stage
   (NOAA NWPS, about 30–60 min behind real time), plus any official NWS river forecast
3. gets active NWS alerts for that exact point and the last hour of rain at the nearest NWS station
4. runs the **same versioned rules engine**, warmed up over the past 3 hours so hysteresis behaves, and builds
   the same EN/ES message, voice, grounded Ask SIREN and a "How SIREN decided" panel

It never reports "Normal" from silence: no gauge nearby means "Unknown", unless an official Flash Flood Warning
applies. Live mode uses a 90-minute staleness threshold (`live_max_age_minutes` in `rules.yaml`) because real gauge
telemetry arrives late. It's per person and stateless, and it doesn't touch the replay demo. It needs internet and
is controlled by `ALLOW_LIVE_DATA` (default true), separately from `DEMO_OFFLINE`, which covers AI and voice. It
covers the US only; elsewhere it says so. API: `GET /api/live/status?lat=&lon=&lang=`,
`POST /api/live/ask`, `GET /api/geocode?q=`.

## Deploy (Vercel frontend + Render backend)

The backend keeps the replay clock, alerts and judges' phone sessions in memory, so it needs an always-on process.
Vercel serverless functions can't hold that state. Use Vercel for the frontend and Render's free tier for the API.

1. **Backend on Render.** New → Blueprint → pick this repo; `render.yaml` creates `siren-api` from the `Dockerfile`.
   Add `GEMINI_API_KEY` (and optionally `ELEVENLABS_API_KEY`, `GROQ_API_KEY`) in the Render dashboard. When it's
   live, check `https://<your-api>.onrender.com/api/health`. This URL also serves the full app, as a backup.
2. **Frontend on Vercel.** New Project → import this repo → **Root Directory: `frontend`** (Vite is detected).
   Add the environment variable `VITE_API_BASE=https://<your-api>.onrender.com` and deploy. `frontend/vercel.json`
   handles client-side routes (`/replay`, `/how`, `/join`, `/r/…`).
3. Optionally set `CORS_ORIGINS=https://<your-app>.vercel.app` on Render to lock the API to your site.
4. Before judging: open `/api/health` on Render to wake it (free instances sleep after ~15 min idle), then test
   the QR join on a phone over mobile data. The QR code uses the page origin, so it points at the Vercel URL.

Voice: the demo path's ElevenLabs clips are committed in `cache/audio/` (made with `scripts/warm_voice.py`,
about 3.7k characters). New clips are generated only on demand, capped by `ELEVENLABS_CHAR_BUDGET`. Free
ElevenLabs plans can only use default voices via the API (the default here is "Sarah").

## Add a new area (no code changes)

SIREN's data sources (USGS Water Data, NOAA NWPS flood categories, NWS ASOS rain, the NWS warning archive,
OpenStreetMap) cover the whole US, so a new area is configuration, not code:

1. Find gauges: `https://api.water.noaa.gov/nwps/v1/gauges?bbox.xmin=…&bbox.ymin=…&bbox.xmax=…&bbox.ymax=…&srid=EPSG_4326`
   (pick ones with a `usgsId` and flood categories) and a storm where they crossed flood stage.
2. Write `scripts/areas/<id>.json` (gauges with short EN/ES names, ASOS rain stations, bounding box, NWS office,
   fetch window, optional commute route), then run `backend/.venv/bin/python scripts/build_fixtures.py <id>`.
3. In `fixtures/areas/<id>/` add the hand-made files: `area.json` (name, storm, time zone, replay window, demo
   photo location), `zones.geojson` (each zone links a gauge, a rain station and road low points),
   `users.json` (personas), `scenes.json`.
4. Restart: the area appears in the switcher, and the rules, lead-time comparison, join page and phones all work.
   Set `SIREN_AREA=<id>` to make it the default.

Outside the US, swap the ingest sources (gauge, flood-category and warning feeds); the rules engine, lifecycle,
AI layer and UI are source-agnostic.

## Pages

- **`/` Live now (home).** On first visit SIREN asks for the browser location (or search a city/ZIP), then shows
  the rule-decided status where you are, the official NWS river forecast, a map, nearby gauges, NWS alerts,
  Ask SIREN, and "How deep is it?" photo depth. See "Live status" below.
- **`/replay` Storm replays.** Five real past floods through the full pipeline: zones, map and a resident's phone
  up front; gauges, timeline, live audience (QR join) and timing vs NWS in tabs.
- **`/how` How it works.** Rules, photo depth validation results, timing across all storms, limits.
- **`/join`, `/r/<session>`.** The audience phone flow for the replay demo.

## Views (replay)

- **Operations** (`/`): map of watch zones shaded by severity, gauges, facilities, photo pins, and Maria's route;
  stage charts with official NOAA flood-stage lines and a moving "now" marker; rainfall bars; incident timeline;
  evidence drawer; live-audience QR panel; lead-time card; replay clock (play, pause, 1×/60×/300×, jump to scene).
  **Shift+D** opens the director panel (trigger photo report, force Gemini failure, simulate surge, switch persona, reset).
- **Resident phone** (right column): personas Maria (ES, Zone B, drives through the S Rice Ave low point),
  James (EN, Zone C, parent uses a wheelchair), Rosa (ES, Zone A, prefers voice and large text).
- **Join** (`/join?run=…`): judges scan the QR code, pick English or Español, tap a zone, and get the same
  resident view on their own phone (`/r/<session>`). No sign-up; the session id lives only in the URL.

## How it works

```
fixtures (USGS, NOAA NWPS, NWS ASOS, IEM warnings, OSM)
   │ replay clock (60×)
   ▼
ingest ──► evaluate (rules.yaml, hysteresis, stale data) ──► prioritize (zones, facilities, route)
                                         │ severity decided here, before any AI call
                                         ▼
                   communicate: deterministic EN template ─► Gemini translation (validated) ─► ElevenLabs voice
                                Gemini explanation (validated)   Ask SIREN (grounded, cited)
                                         │ fallback: Gemini → Groq → deterministic template
                                         ▼
                   record: rule_evaluations, alerts, deliveries, alert_events (TimescaleDB hypertables)
```

| Module | What it does |
| --- | --- |
| `backend/app/rules/` | `rules.yaml` (versioned rules with plain-English conditions), `engine.py` (gather exact inputs → pure condition → `inputs_hash`), `hysteresis.py` |
| `backend/app/lifecycle.py` | Drafted → Generated → Delivered → Acknowledged, plus Superseded / Expired / Cancelled. Invalid transitions raise errors; every transition writes an event. |
| `backend/app/pipeline.py` | Replay orchestration, incidents, alerts, per-recipient deliveries, audience sessions, lead time |
| `backend/app/ai/` | Fallback chain with cache and logging (`client.py`), prompts, response schemas, validators, `guidance.md` (20 cited NWS / Ready.gov snippets in EN/ES) |
| `backend/app/messages.py` | Fixed alert structure (what / where / what to do / updated / source), ≤ 60 spoken words, pre-translated Spanish phrases |
| `backend/app/depth/` | Gemini vision depth estimate + deterministic checks (no reference object → rejected; confidence < 0.5 → unverified; range > 18 in → low precision) |
| `backend/app/voice/` | ElevenLabs TTS cached by content hash; the browser voice is the fallback, and a transcript is always shown |
| `backend/app/db.py`, `models.sql` | TimescaleDB / Tiger Data: hypertables, `readings_15m` continuous aggregate, compression policy |

### Rules (thresholds fixed before computing lead time)

| Rule | Condition | Severity |
| --- | --- | --- |
| STAGE_ACTION / MINOR / MODERATE | Latest stage ≥ official NOAA category at the zone's gauge | Watch / Warning / Emergency |
| RISE_RATE | ≥ 1.0 ft rise in 30 min | Raise one level, max Warning |
| RAIN_1H | ≥ 2.0 in in the last hour | Watch |
| NWS_FFW | Active NWS Flash Flood Warning polygon contains the zone | Warning (official) |
| PHOTO_DEPTH_ROAD | Verified photo on a road, range high ≥ 12 in | Emergency (do not drive) |
| STALE_DATA | No gauge reading > 30 min | No change; never reports Normal (shows "Unknown, data missing") |

Hysteresis: escalate immediately. De-escalate only after the condition has been false for 2 evaluations in a row
and the stage is ≥ 0.3 ft below the threshold.

## Lead time vs the official warning (reported honestly)

**Why SIREN's own Warning comes after the official one:** NWS Flash Flood Warnings are issued from radar rainfall
estimates and forecaster judgment, so they see the rain before rivers respond. SIREN's replay rules use river
gauges, which react later. The thresholds were fixed before the comparison, and we didn't add or tune rules
afterwards to win it. What SIREN adds:

| Storm | SIREN's first signal (Watch) vs official | SIREN's own Warning vs official | Relays the official warning in |
| --- | --- | --- | --- |
| Beryl, Houston | **+39 min** | −111 min | ≤ 6 min |
| Helene, Asheville | **+12 min** | −48 min | ≤ 3 min |
| E. Kentucky, Whitesburg | **+101 min** | −244 min | ≤ 4 min |
| San Diego | −41 min | −56 min | ≤ 11 min |
| Vermont, Montpelier | −411 min | −456 min | ≤ 6 min |

(+ = before the official warning, best zone.) Relay is the time for SIREN to deliver the official warning to each
resident in their own language and voice, with tracked delivery. In live mode SIREN also shows the official NWS
river forecast, so residents see what's coming, not only what's happening.


**Helene, Asheville:** NWS issued a Flash Flood Warning at 6:12 PM EDT Sept 25. SIREN's own rules reached Warning
48 minutes later in Zone A (2.8 in of rain in an hour plus a fast rise) and about 14 hours later on the French
Broad zones (minor stage). The Swannanoa gauge stopped reporting for about 4 hours at the peak, and SIREN flagged
that as missing data instead of reporting the zone as safe.

**Montpelier / Whitesburg / San Diego:** the first NWS Flash Flood Warning also came before SIREN's own
gauge-based Warning (by 7.6–14 h, 4 h and 56 min respectively); `GET /api/lead-time` gives per-zone numbers.

**Beryl, Houston:**

The NWS Flash Flood Warning (HGX FF.W 0051, 4:54 AM CDT) came **before** SIREN's own gauge-based
Warning in every zone:

| Zone | SIREN first Watch | SIREN first Warning (own rules) | Official warning | Lead |
| --- | --- | --- | --- | --- |
| A | 4:15 AM (RISE_RATE) | 6:45 AM | 4:54 AM | −111 min |
| B | 4:15 AM (RISE_RATE) | 7:00 AM | 4:54 AM | −126 min |
| C | 4:15 AM (RISE_RATE) | 7:00 AM | 4:54 AM | −126 min |

SIREN's rise-rate Watch came 39 minutes before the official warning, but a Watch isn't a Warning, so the headline
number is negative. In this storm SIREN adds value on top of official warnings: it relays them in the resident's
own language and voice, adds street-level depth evidence from photos, answers questions, and tracks delivery and
acknowledgment. It doesn't beat them on timing. The thresholds were fixed before this comparison and were not
tuned afterwards. The caveat: SIREN uses gauge thresholds for specific zones, while official warnings cover larger
areas and include forecaster judgment, so this compares timing, not overall quality. `GET /api/lead-time`
recomputes the table.

## Status (be honest in the pitch)

Working and tested offline:
- Real-data replay, rules engine, hysteresis, stale-data handling, lifecycle, evidence panel with "Re-run rule"
- Every alert traced to readings (with timestamps and source links), the rule and its version, and its `inputs_hash`
- English and Spanish alerts. Spanish uses AI translation when available (validated against numbers and protected
  terms), otherwise pre-translated template phrases.
- Live audience mode: join by QR, per-phone deliveries confirmed by the phone, acknowledgments, live counts,
  median time to acknowledge, a 3-question limit per phone
- Grounded Ask SIREN with citations and a safe refusal; blocks unsafe "water is safe" phrasing in EN and ES
- Photo report → depth → `PHOTO_DEPTH_ROAD` → Emergency → safer route
- Lead time; offline mode; attribution footer; keyboard navigation, live regions, large-text and high-contrast
  modes, `prefers-reduced-motion`

Needs you before judging:
- **API keys + `scripts/warm_cache.py`.** Without them, explanations come from the deterministic template, voice
  uses the browser's speech synthesis, and the demo photo uses a committed human reference annotation, labelled
  `fixture` in the evidence panel. None of these are shown as Gemini or ElevenLabs output.
- **Spanish review.** A fluent speaker should review `messages.py` phrases and `guidance.md`, then set
  `fixtures/translation_review.json` → `reviewed: true`.
- **Depth validation.** The seed set has 3 photos. Grow it to 15–30, run `scripts/validate_depth.py`, and put the
  MAE and range coverage here and on the slide.
- **Deploy.** `render.yaml` + `Dockerfile` give a single service that serves the frontend and API from one URL for
  the QR code. Test it on phones over mobile data. Render sleeps when idle, so hit `/api/health` before judging.
- **Tiger Data.** `docker compose up` runs TimescaleDB locally; set `DATABASE_URL` for Tiger Cloud. Measure
  compression savings with `GET /api/health` → `deps.database.compression` after the compression policy runs.

Future work: wildfire and air-quality alerts, real SMS and phone-call delivery, Harris County FWS rain gauges,
live scheduler mode, Backboard persona memory, more languages.

## Prize tracks

Environment (climate adaptation for local communities); Gemini (explanation, translation, grounded Q&A, photo
depth); ElevenLabs (bilingual voice alerts and spoken answers); Tiger Data (hypertables for readings, evaluations
and alert events, plus a continuous aggregate and compression); Most Immersive (judges get alerts on their own
phones); Best Pitch/Demo.

## Data and credits

USGS Water Data (gauge heights); NOAA/NWS National Water Prediction Service (flood categories); NWS ASOS
precipitation and the storm-based warning archive via the Iowa Environmental Mesonet; © OpenStreetMap contributors
(facilities, routing, map tiles); OSRM demo server (precomputed routes); FEMA (public-domain demo photo); Wikimedia
Commons contributors (validation photos; licenses in `fixtures/depth_validation/manifest.json`); voice generated
by ElevenLabs; AI by Google Gemini with Groq fallback. Built with AI assistance (Claude Code). See
`fixtures/README.md` for details.

MIT License.
