# SIREN PRD for Claude Code

Oct 11, 2026 · @Sou

## How to use this with Claude Code

Paste this whole document into Claude Code as the build spec. The hacking window ends Oct 11 at 1:00 PM, almost certainly Houston time (CDT), which is 11:30 PM IST. Confirm the exact deadline with the organizers, and plan to submit on Devpost at least one hour early.

Build in this order: the rules engine with tests and fixtures first, then the dashboard on top of storm replay, then voice, then the evidence panel, then photo depth, then live audience mode and the lead-time measurement. Every "P0" item must work end to end before any "P1" item starts. If time runs short, follow the cut list in the last section.

Opening prompt for Claude Code:

> You are building SIREN for a 24-hour hackathon. Read the whole spec first. The rules engine decides every alert; AI models only explain, translate and answer questions, and their output is always validated. The demo must run fully offline from fixtures when DEMO\_OFFLINE=true. Use only free services listed in the spec, never hardcode keys, and never commit secrets. Build in the priority order given. After each milestone, run the tests and report what works, what doesn't, and what you skipped.

## Product summary and prize strategy

SIREN turns changing environmental data into evidence-backed, accessible warnings that tell communities what is happening, who may be affected, and what action to take. Flash flooding in Houston is the only use case for this build; wildfire and air quality are named as future extensions, not built.

**The signature feature:** SIREN answers the question flood victims actually face, "how deep is it?" A resident's photo becomes a depth estimate with a confidence range, and a deterministic rule turns "12 inches or more on a road" into a do-not-drive alert. More than half of flood drownings happen in vehicles (CDC, via the National Weather Service "Turn Around Don't Drown" campaign).

**The design principle judges should notice:** rules decide, AI explains. Every alert traces back to source readings, a versioned rule, and a timestamped lifecycle.

**Languages:** English and Spanish only. Spanish is the most widely spoken language in Houston after English, so it fits a US hackathon and a Houston audience. Other languages are future work.

**Two features that make the demo hard to beat:** judges scan a QR code and receive the alert on their own phones (live audience mode), and SIREN reports a measured lead time against when the official National Weather Service warning was issued for the replayed storm.

### Judging criteria and how SIREN scores

| Criterion | What earns the points | Where judges see it |
| --- | --- | --- |
| Originality | Depth-from-photo as verified evidence; judges receive alerts on their own phones; decision traceability; separate alert lifecycle states | Scene 4 of the demo; evidence panel |
| Relevance to track | Climate adaptation protecting local communities (Environment track wording) | Opening problem statement |
| Impact | Measured lead time against official warnings; voice-first English and Spanish alerts that work for people who can't read a dashboard | Lead-time result; Spanish voice alert; accessibility features |
| Demo | A storm unfolding in real time on the judges' own phones; offline-safe backup | Live demo |
| Technical implementation | Tested rules engine, hysteresis, stale-data handling, validated AI output, fallback model | Test suite; evidence panel; fallback badge |

### Prize tracks to enter (one project, many tracks)

| Track | Why SIREN qualifies |
| --- | --- |
| Best Overall | Complete, stable system with high-impact problem |
| Best Environment Hack | Climate-driven flooding; protecting local communities |
| Best Pitch/Demo | Clear users, buyers and story |
| Most Immersive Project | Judges join from their phones and receive voice alerts as the storm unfolds |
| Best Use of Gemini API | Explanation, translation, grounded Q&A, photo depth estimation |
| Best Use of ElevenLabs | Multilingual voice alerts and spoken answers |
| Best Use of Tiger Data | All readings in hypertables; continuous aggregates drive the rules |
| Best Use of Backboard (P1) | Persistent resident preferences: language, home zone, vehicle type, accessibility needs |
| Best Use of Vultr (P1) | Backend hosting, only if free credits need no payment method |
| Best Domain Name from GoDaddy Registry (P1) | Only if MLH provides a free code |

Skip Solana: it doesn't fit, and forcing it in weakens the story.

## Scope and demo scenario

The demo replays a real past Houston rain event along one bayou, sped up 60×, through the full SIREN pipeline. Real historical readings make the story credible; a "simulate surge" button exists only as a backup.

### The scenario

- **Area:** one watershed, for example Brays Bayou in southwest Houston, with 2–3 stream gauges and 3–5 hand-drawn watch zones (GeoJSON polygons) along it.
- **Event:** pick a real heavy-rain day in the last few years where a gauge crossed its flood categories. Pull 12–24 hours of 15-minute readings around it. Record the event date and sources in `fixtures/README.md`.
- **Personas (seeded users):**
  - Maria, Spanish speaker, drives to work through an underpass in Zone B.
  - James, English speaker, lives in Zone C with an elderly parent who uses a wheelchair.
  - Rosa, Spanish speaker, older resident who prefers voice and large text.
- **Photo report:** one flood photo (openly licensed, for example from Wikimedia Commons, license recorded) submitted at the Zone B underpass during the replay.

### In scope

- Ingest rainfall, stream levels and official alerts (live mode) or fixtures (replay mode).
- Deterministic rules engine with severity levels, hysteresis and data-freshness checks.
- AI explanation, translation and grounded Q&A, all validated.
- Affected zones, nearby vulnerable facilities, a safer route suggestion.
- Voice alerts in English and Spanish; spoken follow-up questions.
- Evidence panel and alert lifecycle tracking.
- Photo depth estimation feeding the rules engine.
- Fully offline demo mode, live audience mode (judges join by QR code), and lead-time measurement against the official warning.

### Out of scope (say so in the pitch as future work)

- Wildfire and air-quality alerts.
- Real SMS or phone-call delivery (delivery is simulated in-app, and the lifecycle shows it honestly).
- Hydrological modeling or official inundation forecasts. SIREN never claims to replace official warnings; it links to them.
- User accounts beyond seeded personas and anonymous audience sessions; languages beyond English and Spanish.

## Free stack, keys and hard constraints

Everything runs on free tiers with no payment method. Free-tier limits change often, so the code must handle rate limits gracefully and the demo must not depend on any live API.

| Layer | Choice | Notes |
| --- | --- | --- |
| Frontend | React + Vite + TypeScript, MapLibre GL (or Leaflet), Recharts | Host on Vercel or Netlify free |
| Backend | Python FastAPI | Host on Render free (sleeps when idle; wake it before judging) |
| Database | Tiger Data free option, or TimescaleDB in Docker locally | Confirm with MLH that self-hosted TimescaleDB counts for the Tiger Data track |
| Primary AI | Gemini Flash via Google AI Studio key | Pro models are not free; use Flash |
| Fallback AI | Groq free tier (a Llama or GPT-OSS text model) | Text tasks only; used on Gemini rate-limit errors |
| Voice | ElevenLabs free plan (about 10 minutes of speech per month) | Cache every clip; show "Voice generated by ElevenLabs" |
| Speech-to-text | Browser Web Speech API (Chrome); Groq Whisper as fallback | Both free |
| Stream gauges | USGS Water Data API (instantaneous values) | Verify which endpoint is current; legacy endpoints are being retired |
| Flood categories | NOAA National Water Prediction Service gauge data (action, minor, moderate, major stages) | Official thresholds make the rules credible |
| Rainfall | Harris County Flood Warning System, or NWS observations | Precompute into fixtures for replay |
| Official alerts | NWS API `api.weather.gov/alerts/active` | No key; send a descriptive User-Agent header as NWS requires |
| Facilities | OpenStreetMap via Overpass API | Cache results into a fixture |
| Routing | OpenRouteService free key, `avoid_polygons` | Precompute the demo route |

### Hard constraints

- All keys in `.env`, read through settings; `.env.example` committed with blanks. Never expose AI keys to the browser; all AI calls go through the backend.
- `DEMO_OFFLINE=true` makes every external call read from `fixtures/` and `cache/`, including AI outputs and audio. The full demo must run with Wi-Fi off.
- Cache AI and voice outputs by a hash of (task, model, language, input text). Regenerate only when the input changes.
- On HTTP 429 or timeout from Gemini: retry once with backoff, then fall back to Groq for text tasks, then fall back to a deterministic template. Record which path produced each output.
- Respect free API usage policies: rate-limit outbound calls, add User-Agent headers, and cache map and Overpass results. Past NWS warnings for the lead-time measurement come from the Iowa Environmental Mesonet warning archive (free); cache the relevant warnings into fixtures.
- Attribution in the app footer: OpenStreetMap contributors, ElevenLabs, data sources (USGS, NOAA/NWS, Harris County), and "Not an official warning system. Follow instructions from local officials."

## Architecture, data model and API

One backend service runs the pipeline as five stages, each a separate module with its own tests: ingest → evaluate → prioritize → communicate → record. A replay clock drives ingestion in demo mode; a scheduler drives it in live mode. The frontend polls (or uses server-sent events) for incident updates.

### Repository layout

```
siren/
  backend/
    app/
      main.py                 # FastAPI app, routes
      settings.py             # env, DEMO_OFFLINE, keys
      clock.py                # replay clock (speed, pause, jump)
      ingest/                 # usgs.py nwps.py rainfall.py nws_alerts.py fixtures.py
      rules/
        engine.py             # evaluates rules -> severity per zone
        rules.yaml            # versioned rule definitions
        hysteresis.py
      prioritize/             # zones.py facilities.py routing.py
      ai/
        client.py             # Gemini -> Groq -> template fallback chain
        prompts.py  schemas.py  validators.py  guidance.md
      voice/                  # elevenlabs.py, cache by hash
      depth/                  # photo depth estimation + checks
      lifecycle.py            # alert state machine
      db.py  models.sql
    tests/
  frontend/
    src/ components/ pages/ hooks/ i18n/
  fixtures/                   # replay readings, zones.geojson, facilities.json, route.json, photos/, README.md
  cache/                      # ai/ and audio/ outputs for offline demo
  docker-compose.yml          # timescaledb + backend for local dev
  README.md  LICENSE
```

### Database (TimescaleDB / Tiger Data)

```sql
CREATE TABLE readings (
  time        TIMESTAMPTZ NOT NULL,
  source      TEXT NOT NULL,         -- usgs, hcfws, nws, photo
  station_id  TEXT NOT NULL,
  metric      TEXT NOT NULL,         -- stage_ft, rain_in, depth_in
  value       DOUBLE PRECISION NOT NULL,
  quality     TEXT,                  -- provisional, estimated, verified
  source_url  TEXT
);
SELECT create_hypertable('readings', 'time');

-- 15-minute rollups the rules engine reads (continuous aggregate)
CREATE MATERIALIZED VIEW readings_15m WITH (timescaledb.continuous) AS
SELECT time_bucket('15 minutes', time) AS bucket, station_id, metric,
       max(value) AS max_v, last(value, time) AS last_v, count(*) AS n
FROM readings GROUP BY bucket, station_id, metric;

CREATE TABLE rule_evaluations (
  id BIGSERIAL, time TIMESTAMPTZ NOT NULL, zone_id TEXT, rule_id TEXT,
  rule_version TEXT, fired BOOLEAN, severity TEXT,
  inputs JSONB,            -- exact readings used, with timestamps
  inputs_hash TEXT, missing_data JSONB
);
SELECT create_hypertable('rule_evaluations', 'time');

CREATE TABLE incidents (id TEXT PRIMARY KEY, zone_id TEXT, opened_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ, peak_severity TEXT, status TEXT);

CREATE TABLE alerts (id TEXT PRIMARY KEY, incident_id TEXT, severity TEXT,
  rule_ids TEXT[], text_en TEXT, explanation JSONB, ai_path TEXT, created_at TIMESTAMPTZ);

CREATE TABLE alert_deliveries (id TEXT PRIMARY KEY, alert_id TEXT, user_id TEXT,
  language TEXT, text TEXT, audio_path TEXT, state TEXT, updated_at TIMESTAMPTZ);

CREATE TABLE alert_events (time TIMESTAMPTZ NOT NULL, alert_id TEXT, delivery_id TEXT,
  from_state TEXT, to_state TEXT, actor TEXT, note TEXT);   -- full audit trail

CREATE TABLE photo_reports (id TEXT PRIMARY KEY, time TIMESTAMPTZ, lat DOUBLE PRECISION,
  lon DOUBLE PRECISION, image_path TEXT, analysis JSONB, status TEXT);

CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT, language TEXT, zone_id TEXT,
  vehicle TEXT, needs JSONB);
```

Show Tiger Data features on purpose: hypertables, a continuous aggregate feeding the rules, and a compression policy on `readings` (mention the storage saved in the pitch).

### API endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /api/state` | Current clock time, per-zone severity, latest readings, open incidents |
| `GET /api/readings?station=&metric=&from=&to=` | Time series for charts |
| `POST /api/replay` | Control the replay: start, pause, speed, jump to scene |
| `POST /api/simulate` | Backup: inject a synthetic surge |
| `GET /api/incidents/{id}` | Incident with timeline |
| `GET /api/alerts/{id}/evidence` | Everything for the evidence panel |
| `POST /api/alerts/{id}/deliver` | Generate and deliver to a user in their language |
| `POST /api/deliveries/{id}/ack` | Resident acknowledges |
| `POST /api/ask` | Grounded Q&A: question, user, language → answer, citations, audio |
| `POST /api/photos` | Upload photo with location → depth analysis, new reading |
| `GET /api/users` / `PATCH /api/users/{id}` | Personas and preferences |
| `GET /api/health` | Status of each external dependency and offline mode |

### Additions for live audience mode and lead time

```sql
CREATE TABLE audience_sessions (
  id TEXT PRIMARY KEY,          -- random id stored in the phone's page URL
  demo_run_id TEXT,             -- groups one demo session
  language TEXT,                -- en or es
  zone_id TEXT,
  joined_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ
);
-- audience deliveries reuse alert_deliveries with user_id = audience session id

CREATE TABLE official_warnings (
  id TEXT PRIMARY KEY,          -- NWS warning identifier from the archive
  issued_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
  event TEXT,                   -- e.g. Flash Flood Warning
  polygon JSONB, source_url TEXT
);

CREATE TABLE lead_time_results (
  zone_id TEXT, siren_first_alert_at TIMESTAMPTZ, siren_severity TEXT,
  official_warning_id TEXT, official_issued_at TIMESTAMPTZ,
  lead_minutes DOUBLE PRECISION, computed_at TIMESTAMPTZ, notes TEXT
);
```

| Method and path | Purpose |
| --- | --- |
| `POST /api/audience/join` | Phone joins: picks language and zone, gets a session id |
| `GET /api/audience/{id}/feed` | Phone polls every 2 s (or SSE) for new alerts in its language |
| `POST /api/audience/{id}/ack` | Phone acknowledges an alert |
| `GET /api/audience/summary` | Operations view: joined, delivered, acknowledged counts, live |
| `POST /api/audience/reset` | Clear sessions between demo runs |
| `GET /api/lead-time` | Lead-time result per zone for the replayed storm |

## Feature specs

Each feature is tagged P0 (must ship) or P1 (ship if time allows).

### 01 Detect (P0)

- Ingest stream stage (ft) and rainfall (in) per station every 15 minutes, plus active NWS flood alerts for the area. In replay mode, the replay clock releases fixture readings at the chosen speed (default 60×, so 12 hours plays in 12 minutes; the demo jumps between scenes).
- Every reading stores source, station, timestamp, quality flag and source URL.
- Dashboard charts: stage vs time per gauge with horizontal lines for action, minor and moderate flood stages; rainfall bars per 15 minutes; a "now" marker that moves with the clock.

### 02 Reason: the rules engine (P0)

Rules live in `rules.yaml`, each with an id, version, plain-English description, inputs and thresholds. The engine runs every clock tick per zone and writes one `rule_evaluations` row per rule, fired or not.

| Rule id | Condition | Severity if fired |
| --- | --- | --- |
| `STAGE_ACTION` | Latest stage ≥ action stage at the zone's gauge | Watch |
| `STAGE_MINOR` | Latest stage ≥ minor flood stage | Warning |
| `STAGE_MODERATE` | Latest stage ≥ moderate flood stage | Emergency |
| `RISE_RATE` | Stage rose ≥ 1.0 ft in the last 30 min (configurable) | Raise one level, max Warning |
| `RAIN_1H` | Rainfall ≥ 2.0 in in the last hour at nearest rain gauge | Watch |
| `NWS_FFW` | An active NWS Flash Flood Warning polygon contains the zone | Warning (official) |
| `PHOTO_DEPTH_ROAD` | A verified photo report on a road shows depth range high ≥ 12 in | Emergency for that road segment: do not drive |
| `STALE_DATA` | No reading from the zone's gauge for > 30 min | No severity change; flag "missing data" |

Thresholds above are starting values; replace stage thresholds with the official NOAA flood categories for each gauge and cite them.

Severity combines as the maximum of fired rules. Hysteresis: a zone escalates immediately but de-escalates only after its triggering condition has been false for 2 consecutive evaluations, and the stage has dropped at least 0.3 ft below the threshold. Stale data never produces "Normal"; it produces "Unknown, data missing" so silence is never mistaken for safety.

When severity rises, the engine opens or updates an incident and creates an alert draft. Gemini then writes the explanation (see AI section); the decision is already made before AI is called.

### 03 Prioritize (P0 core, P1 routing)

- Affected zones: zones whose severity is Watch or higher, shaded on the map.
- Exposure: facilities from the OpenStreetMap fixture (hospitals, schools, nursing homes, clinics, fire stations, shelters) inside affected zones, listed with distance.
- Clearly label every item as either **Estimated exposure** (inside a zone at risk) or **Verified danger** (official warning, gauge over flood stage at that location, or verified photo depth). Use different icons and words, not just colors.
- Safer route (P1): for a persona's commute, an OpenRouteService route that avoids zones at Warning or above and any road segment with a do-not-drive photo report. Precompute for the demo.

### 04 Communicate (P0)

- Alerts are generated per persona or audience member in their language: English or Spanish.
- Message structure is fixed: what is happening, where, what to do now, when it was last updated, source. Maximum 60 words spoken.
- Audio: ElevenLabs text-to-speech, cached. Always show the text transcript with the audio (accessibility, and a fallback if audio fails).
- "Ask SIREN": the resident taps the microphone, speaks a question, and hears a short answer grounded only in approved guidance plus current incident facts. Unanswerable questions get a safe refusal that points to 911 and official sources.
- Acknowledge button: "I understand" moves the delivery to Acknowledged.
- Backboard (P1): store and recall persona preferences (language, zone, vehicle, needs) across sessions; show "remembered" chips in the UI.

### 05 Verify: evidence and lifecycle (P0)

Alert lifecycle states are tracked separately and never merged:

1. Drafted: rule fired, alert created.
2. Generated: text and audio produced (records which AI path: Gemini, Groq or template).
3. Delivered: shown or played to the resident in the app.
4. Acknowledged: resident tapped "I understand".
5. Superseded, Expired or Cancelled: replaced by a newer alert, timed out, or conditions cleared.

Every transition writes an `alert_events` row with time and actor. Invalid transitions (for example Acknowledged before Delivered) raise errors and are covered by tests.

The evidence panel for an alert shows: the rule(s) that fired with version and plain-English condition; the exact readings used, each with timestamp, station, value and source link; data freshness and any missing data; the photo, its depth analysis and confidence if relevant; the AI explanation with model name and fallback badge; the language and transcript; the lifecycle timeline; and an `inputs_hash` so anyone can re-run the evaluation and get the same result (P1: a "Re-run rule" button that proves it).

### 06 Photo depth estimation (P0)

- Resident uploads a photo and confirms location on the map (in the demo, the Zone B underpass).
- Gemini Flash vision returns structured JSON: detected reference objects with their typical heights, where the waterline sits on each, depth estimate and range in inches, and confidence.
- Deterministic checks: reject if no reference object found; if confidence < 0.5, store as "Unverified report" (shown, but cannot fire `PHOTO_DEPTH_ROAD`); if the range is wider than 18 inches, mark "Low precision".
- A verified analysis becomes a `readings` row with metric `depth_in`, so it flows through the same rules engine as gauges.
- Validation (P0 for credibility): run the analyzer on 15–30 openly licensed flood photos where depth can be judged from objects (for example water at mid-wheel). Report mean absolute error and how often the true depth fell inside the range, in the README and on the pitch slide. Be honest about the small sample.
- In the UI, the photo shows the detected reference object and a drawn waterline (from returned coordinates, if available) next to "≈ 18 in (14–22 in). Most cars can float at 12 in."

### 07 Storm replay and director controls (P0)

- Replay controls: play, pause, speed (1×, 60×, 300×), and "jump to scene" buttons matching the demo script.
- A hidden director panel (keyboard shortcut) to trigger the photo report, switch persona, force a Gemini fallback (to show resilience), and reset.
- `POST /api/simulate` injects a synthetic surge if real fixtures fail to load.

### 08 Live audience mode: judges' phones (P0)

Judges become residents. At the start of the demo, the operations view shows a large QR code linking to the hosted resident view (`/join?run=<demo_run_id>`).

- Joining takes two taps: pick English or Español, then tap a zone on a small map (default: Zone B). No sign-up, no personal data; the session id lives only in the page URL.
- The phone shows "Monitoring Zone B" with a calm status card until the rules engine escalates that zone.
- When an alert fires, every joined phone in that zone shows the alert card within 3 seconds, vibrates (where the browser allows), and offers a large play button for the voice alert. Browsers block autoplay, so audio plays on tap; the transcript is always visible.
- "I understand" acknowledges the alert. The operations view's audience panel shows counts updating live: joined, delivered, acknowledged, and median time to acknowledge.
- Each audience delivery appears in the evidence panel with its own lifecycle (Drafted → Generated → Delivered → Acknowledged). Delivered means the phone actually fetched and rendered the alert, confirmed by the phone, not just sent by the server.
- Phones can use "Ask SIREN" and "Report flooding" too, but rate-limit them (for example, 3 questions per phone) to protect free API quotas; answers to common questions come from cache.
- Works for remote judging: judges open the same link on any device.
- Backup: if venue Wi-Fi blocks phones, the seeded personas run the same flow on screen.

### 09 Lead time against official warnings (P0)

SIREN measures, for the replayed storm, how its alerts compare in time with the official warning.

- Load the NWS warnings issued for the area during the storm from the Iowa Environmental Mesonet archive into `official_warnings` (fixture).
- For each zone, find SIREN's first alert at Warning or above and the first official flood-related warning whose polygon contains the zone.
- Lead time = official issue time − SIREN first alert time, in minutes. Positive means SIREN was earlier.
- Show the result on the incident timeline as two markers (SIREN alert, official warning) and as one sentence on the closing slide, for example "SIREN flagged Zone B 35 minutes before the official warning."
- Report honestly. If SIREN was later or there was no official warning, say so and present SIREN's value as street-level depth evidence, language access and delivery tracking on top of official warnings. Never tune thresholds after seeing the result just to win the comparison; document thresholds before computing it, and note in the README that this is one storm, not a statistical study.
- Caveat to state: SIREN's rules use gauge thresholds for specific zones, while official warnings cover larger areas and include forecaster judgment, so the comparison shows timing, not which is better overall.

## AI prompts, output schemas and guardrails

AI performs four tasks, each with a JSON output schema enforced through Gemini's structured output (response schema) and re-checked by a validator. Any output that fails validation is discarded and replaced by the next fallback (Groq, then a deterministic template). The AI never decides severity.

### Task 1: Situation explanation

Input: zone, severity, fired rules with plain-English conditions, the readings used (values, units, timestamps), missing-data flags, affected facilities.

System prompt core: "You explain a flood alert that has already been decided by rules. Use only the facts provided. Do not add numbers, places or instructions that are not in the input. If data is missing, say so plainly. Write for a general audience at about a 6th-grade reading level."

```json
{
  "headline": "string, max 12 words",
  "what_is_happening": "string, max 40 words",
  "why": [{"rule_id": "string", "evidence": "string"}],
  "who_may_be_affected": "string, max 30 words",
  "missing_data": ["string"],
  "confidence_note": "string"
}
```

Validator: every `rule_id` must be one that fired; every number in the text must appear in the input facts (regex-extract numbers and compare); max lengths enforced.

### Task 2: Alert text and translation

The English alert text is built from a fixed template filled with rule outputs (deterministic), not written by AI. AI only translates it.

Translation prompt core: "Translate this emergency message into {language}. Keep all numbers, street names, times and the phrase meaning 'Turn around, don't drown' accurate. Use plain, calm language. Return JSON."

```json
{"language": "es", "text": "string", "kept_terms": ["string"]}
```

Validator: all numbers and protected terms (street names, zone names) from the English text appear unchanged in the translation. A fluent Spanish speaker reviews the cached demo translations before judging; mark them "reviewed" in the evidence panel. Pre-translate the template's fixed phrases for each language and store them, so only the variable parts depend on live AI.

### Task 3: Grounded Q&A ("Ask SIREN")

Input: the question (transcribed), the persona's language, current incident facts, and `guidance.md`, a small file of 15–25 short safety guidance snippets with ids, paraphrased from National Weather Service and Ready.gov flood safety pages and cited.

System prompt core: "Answer only using the guidance snippets and incident facts provided. Cite the snippet ids you used. If the question cannot be answered from them, set answerable to false. Never tell anyone it is safe to drive or walk through water. Keep answers under 50 words."

```json
{"answerable": true, "answer": "string", "citations": ["G07", "F2"], "language": "es"}
```

Validator: `answerable=false` or empty citations → replace with the fixed refusal in that language: "I can only answer from official safety guidance. If you are in danger, call 911. Follow instructions from local officials." Block any answer containing phrases that suggest water is safe to cross (keyword list in each language).

### Task 4: Photo depth estimation (vision)

Prompt core: "Estimate floodwater depth at the deepest visible point on the road. Identify reference objects with known typical heights (car tire about 26–30 in tall, sedan wheel hub about 13–15 in above ground, standard curb about 6 in, adult knee about 18–20 in, depth-marker post readings). For each, say where the waterline sits. Return a depth range, not just a number. If you cannot see a reference object, say so."

```json
{
  "reference_objects": [{"type": "car_tire", "typical_height_in": 28, "waterline_fraction": 0.6, "box": [0,0,0,0]}],
  "depth_in": 17,
  "depth_low_in": 14,
  "depth_high_in": 22,
  "confidence": 0.7,
  "is_road": true,
  "notes": "string"
}
```

Validator and checks: as listed in the photo depth feature spec. The reference heights in the prompt are approximate; keep them in a config file with a comment noting they are typical values.

### Fallback chain and logging

1. Gemini Flash with structured output.
2. On 429, timeout or validation failure: Groq text model (tasks 1–3 only) with the same prompt and validator.
3. Final fallback: deterministic template (task 1: list fired rules and readings; task 2: stored pre-translated phrases; task 3: refusal; task 4: "Could not analyze photo; report saved as unverified").

Log task, model, latency, cache hit, validation result and fallback reason for every call; the evidence panel reads these logs.

## Interface, visual design and accessibility

SIREN has two views that share one backend: an **Operations view** (what judges see first, the system's brain) and a **Resident view** (a phone-sized panel showing what one person hears and sees). In the demo they sit side by side: operations on the left two-thirds, the resident phone on the right third.

### Operations view

- Top bar: SIREN wordmark, area name, replay clock with speed control, data-freshness indicator (green "live", amber "delayed", grey "missing"), and offline-mode badge when on.
- Map (center): watch zones shaded by severity, gauges as markers with current stage, facilities as icons, photo reports as camera pins, safer route as a line.
- Charts (below map): stage per gauge with flood-stage lines; rainfall bars.
- Incident timeline (right rail): every rule evaluation that changed severity, every alert state change, newest first, each clickable to open evidence.
- Evidence drawer: slides over the right rail; sections as listed in the Verify spec. Audience panel: the join QR code, then live counts of joined, delivered and acknowledged phones. Lead-time card: SIREN's first alert time vs the official warning time for each zone.

### Resident view (phone frame)

- Persona switcher (Maria, James, Rosa) with language and preferences shown as chips. Audience members who joined by QR code get the same resident view on their own phones.
- Alert card: severity word and icon, headline, three lines (what, where, what to do), "updated 2 min ago", source.
- Large play button for the voice alert; transcript always visible.
- "Ask SIREN" microphone button; answer appears as text and plays as audio; citations shown as small chips.
- "I understand" acknowledge button; "Report flooding" photo upload button.

### Visual style

- Calm, serious emergency-operations look: dark slate background for operations, light high-contrast resident view (like a real phone alert).
- Severity scale: Normal, Watch, Warning, Emergency, Unknown. Each has a color, an icon shape and the word printed; never color alone. Use a color-blind-safe palette (for example blue, amber, orange-red, magenta, grey) and verify contrast.
- Typography: Inter for UI, tabular numbers for readings; minimum 16 px body text in the resident view.
- Motion is minimal and purposeful: the clock ticking, chart lines growing, a single pulse when severity changes. No decorative animation.

### Accessibility (required, and part of the pitch)

- WCAG 2.1 AA contrast; full keyboard navigation with visible focus; ARIA labels on all controls.
- Every audio alert has a text transcript; every chart has a short text summary for screen readers.
- A live region announces severity changes.
- Resident view supports large text and high-contrast modes and works at 200% zoom.
- Respect `prefers-reduced-motion`.
- Languages: interface strings in English and Spanish via an i18n file, switchable at any time; alerts in the persona's language.

## Demo script and Devpost submission

The demo runs about 4 minutes. Live audience mode needs the hosted site online; every other part can fall back to offline mode, and a recorded backup video is ready. Practice it at least three times end to end.

| Time | Scene | On screen | What you say |
| --- | --- | --- | --- |
| 0:00–0:20 | Hook | Title, one photo of a flooded underpass | "More than half of flood drownings happen in cars. In a flood, people need three answers fast: what's happening, does it affect me, and how deep is it?" |
| 0:20–0:50 | Join | Large QR code; judges scan, pick English or Español and Zone B; audience panel counts them in | "Take out your phones. For the next four minutes, you live in Zone B, next to Brays Bayou." |
| 0:50–1:20 | 1. Normal | Map all blue, gauges steady, clock at 60×; judges' phones show "Monitoring Zone B" | "This is a real storm, replayed from official gauge data. Right now everything is normal." |
| 1:20–2:00 | 2. Conditions change | Rain bars climb; stage crosses action, then minor flood stage; Zone B turns Watch, then Warning | "Rules decide, not AI. The minor flood stage was crossed and the river is rising fast, so Zone B moves to Warning." |
| 2:00–2:30 | 3. SIREN speaks | Judges' phones light up with the alert; one judge taps play in Spanish; the room hears it; acknowledgments tick up on screen | "That alert just reached you, in the language you chose. Tap 'I understand,' and watch it arrive here." |
| 2:30–3:00 | 4. Photo | Maria's photo of the underpass: tire, waterline, ≈ 18 in (14–22 in); do-not-drive rule fires; her route changes | "A resident's photo becomes evidence. Eighteen inches can float most cars, so SIREN closes that road for her route." |
| 3:00–3:20 | 5. Ask SIREN | A judge asks "What should I do now?" by voice; grounded answer plays with citations | "Answers come only from official safety guidance. If SIREN can't answer from it, it says so and points to 911." |
| 3:20–3:50 | 6. Prove it | Evidence panel: readings, rule and version, AI path, transcript, and the judges' own deliveries moving Drafted → Generated → Delivered → Acknowledged | "Every warning is traceable, including the ones you just received." |
| 3:50–4:15 | Close | Lead-time card: SIREN alert vs official warning; validation numbers; stack | "On this storm, SIREN flagged Zone B \[X\] minutes before the official warning. Built on Tiger Data, Gemini and ElevenLabs, entirely on free tiers." |

Optional resilience moment (if a judge asks about reliability): use the director panel to force a Gemini failure and show the Groq fallback badge in the evidence panel.

### Likely judge questions and answers

- **"What if the AI is wrong?"** AI never decides severity. Rules decide; AI output is validated, and numbers it writes must match the input.
- **"How accurate is the depth estimate?"** Give the measured error from your validation set, and explain that low-confidence photos are stored as unverified and can't trigger alerts.
- **"Who would pay for this?"** County and city emergency management offices, school districts and fleet operators (delivery, utilities, energy field crews) who need to keep people off flooded roads; insurers for claims triage.
- **"How is this different from official alerts?"** Official alerts cover broad areas in one or two languages. SIREN adds street-level depth evidence, the resident's own language and voice, follow-up questions, and delivery tracking. It links to official alerts and never replaces them.

### Devpost submission checklist

- Hosted website URL (frontend) and public repository URL, both required by the rules.
- Tagline: "Evidence-backed flood warnings that tell every resident what's happening, who's affected, and what to do, in their own language."
- Sections: Inspiration, What it does, How we built it (architecture image), Challenges, Accomplishments (validation numbers, tests passing), What we learned, What's next (wildfire, air quality, SMS and phone delivery).
- Select every track from the prize strategy table that the project truly uses.
- Demo video (2–3 minutes) uploaded and public, in case judging is remote.
- Screenshots: operations view mid-storm, resident view in Spanish on a phone, audience panel with acknowledgments, evidence panel, photo analysis.
- Credits: data sources, OpenStreetMap, ElevenLabs attribution, AI assistance disclosure, and image licenses.

## Build plan, acceptance checklist and risks

The plan assumes roughly 12 working hours remain; compress proportionally. Run tracks in parallel if you have teammates (backend, frontend, AI and voice, data and fixtures).

1. **H0–H1: Fixtures first.** Pick the storm, pull gauge and rainfall readings, look up official flood stages, pull the official warnings for that storm from the Iowa Environmental Mesonet archive, draw zones, cache facilities, pick the photo.
2. **H1–H3: Rules engine and database.** Schema, replay clock, rules with hysteresis and stale-data handling, lifecycle state machine, all with tests.
3. **H2–H5: Operations view.** Map, charts, timeline, replay controls, wired to `/api/state`.
4. **H4–H6: AI and voice.** Explanation, English template plus Spanish translation, grounded Q&A, fallback chain, ElevenLabs with caching. Fill `cache/` for the demo path.
5. **H6–H8: Resident view, live audience mode and evidence panel.** Resident view doubles as the audience phone page.
6. **H7–H8: Lead-time measurement.** Compute and display it; fix thresholds before computing.
7. **H8–H9: Photo depth** plus a small validation run.
8. **H9: Feature freeze.** Deploy frontend and backend, test the hosted URLs on phones over mobile data, test offline mode with Wi-Fi off.
9. **H9–H11: Polish, accessibility pass, README, Devpost write-up, record the backup video.**
10. **H11–H12: Rehearse the demo three times with friends' phones; submit with at least an hour to spare.**

**Cut list, in this order:** Backboard; safer routing (show affected roads instead); "Re-run rule" button; Ask SIREN on audience phones (keep it on the presenter's screen); Groq fallback (keep the template fallback); validation set size (keep at least 10 photos). Never cut: real-data replay, rules engine with tests, English and Spanish voice alerts, live audience mode, the lead-time result, the evidence panel, the lifecycle states, offline fallback.

### Acceptance checklist

- [ ] Full demo runs start to finish in offline mode with Wi-Fi off.
- [ ] Rules engine tests pass: threshold crossing, rise rate, hysteresis (no flapping), stale data gives Unknown, photo depth only fires when verified.
- [ ] Lifecycle tests pass: valid transitions recorded, invalid transitions rejected.
- [ ] AI validators reject an injected bad output (wrong number, missing citation) and the fallback is used.
- [ ] Evidence panel shows source readings, rule and version, AI path, transcript and lifecycle for every alert.
- [ ] English and Spanish alerts play from cache; Spanish reviewed by a fluent speaker. Lead-time result computed with thresholds fixed in advance and shown on the timeline.
- [ ] Hosted site and repo URLs work from another device; live audience mode works with at least 5 phones at once, on Wi-Fi and mobile data; no secrets in the repo.
- [ ] Keyboard-only walkthrough works; contrast checked; transcripts present.
- [ ] Attribution and "not an official warning system" notice visible.

### Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Free-tier rate limits hit during judging | Offline mode with cached AI and audio; fallback chain |
| ElevenLabs credits run out | Cache every clip; develop with the cheaper Flash model; generate final demo clips once |
| Judges' phones can't connect at the venue (Wi-Fi blocks, captive portals) | Public HTTPS URL tested on mobile data; short link next to the QR code; seeded personas run the same flow on screen as backup |
| USGS or other data endpoints change | Fixtures are committed; live mode is optional |
| Depth estimates look wrong on stage | Use the validated demo photo; show the range and confidence, not a single number |
| Render backend asleep at judging time | Hit `/api/health` 5 minutes before; run locally as backup |
| Judges question safety claims | The "never says water is safe" guardrail, the not-an-official-system notice, and links to official alerts |
