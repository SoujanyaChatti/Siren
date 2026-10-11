"""SIREN FastAPI app: routes over the pipeline."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import live
from . import pipeline as pl
from .ai import client as ai_client
from .ai import tasks
from .db import make_sink
from .depth import analyzer
from .ingest.fixtures import list_areas, parse_t
from .lifecycle import InvalidTransition
from .rules.engine import condition, inputs_hash
from .settings import ROOT, settings
from .voice import elevenlabs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("siren")

siren: pl.Siren


async def _ticker() -> None:
    while True:
        try:
            siren.tick()
        except Exception:  # never let the clock loop die
            log.exception("tick failed")
        await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global siren
    siren = pl.Siren(sink=make_sink(settings.database_url))
    siren.jump(siren.start)
    task = asyncio.create_task(_ticker())
    log.info("SIREN ready (DEMO_OFFLINE=%s)", settings.demo_offline)
    yield
    task.cancel()


app = FastAPI(title="SIREN", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])


def _err(e: Exception, code: int = 400):
    raise HTTPException(code, str(e))


# ------------------------------------------------------------------ state and readings

@app.get("/api/state")
def get_state():
    return siren.state()


@app.get("/api/series")
def get_series():
    siren.tick()
    return siren.series()


@app.get("/api/readings")
def get_readings(station: str, metric: str = "stage_ft", start: str | None = None, end: str | None = None,
                 bucket: str | None = None):
    s = parse_t(start) if start else None
    e = min(parse_t(end), siren.clock.now()) if end else siren.clock.now()
    if bucket == "15m":
        if siren.sink:
            rows = siren.sink.rollup_15m(station, metric, s or siren.start - timedelta(hours=1), e)
            if rows is not None:
                return {"source": "timescale:readings_15m", "rows": rows}
        return {"source": "memory:rollup_15m", "rows": siren.store.rollup_15m(station, metric, e)}
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in siren.store.series(station, metric, s, e)]
    return {"source": "memory", "rows": rows}


# ------------------------------------------------------------------ replay and director

class ReplayCmd(BaseModel):
    action: str                       # play | pause | speed | jump | scene | reset
    speed: float | None = None
    time: str | None = None
    scene: str | None = None


@app.post("/api/replay")
def replay(cmd: ReplayCmd):
    c = siren.clock
    if cmd.action == "play":
        c.play()
    elif cmd.action == "pause":
        c.pause()
    elif cmd.action == "speed" and cmd.speed:
        c.set_speed(cmd.speed)
    elif cmd.action == "jump" and cmd.time:
        siren.jump(parse_t(cmd.time))
    elif cmd.action == "scene" and cmd.scene:
        sc = next((s for s in siren.fx.scenes if s["id"] == cmd.scene), None)
        if not sc:
            raise HTTPException(404, "unknown scene")
        siren.jump(parse_t(sc["time"]))
    elif cmd.action == "reset":
        c.pause()
        siren.reset_state()
        siren.clock.jump(siren.start)
        siren.tick()
    else:
        raise HTTPException(400, "bad replay command")
    return siren.clock.state()


class SimulateCmd(BaseModel):
    zone_id: str | None = None
    rise_to: str = "moderate"


@app.post("/api/simulate")
def simulate(cmd: SimulateCmd):
    return siren.simulate_surge(cmd.zone_id, cmd.rise_to)


class DirectorCmd(BaseModel):
    action: str            # force_fallback | photo | reset_all
    value: bool | None = None


@app.post("/api/director")
async def director(cmd: DirectorCmd):
    if cmd.action == "force_fallback":
        settings.force_gemini_failure = bool(cmd.value)
        return {"force_gemini_failure": settings.force_gemini_failure}
    if cmd.action == "photo":
        dp = siren.area.get("demo_photo")
        p = settings.fixtures_dir / dp["file"] if dp else None
        if not p or not p.exists():
            raise HTTPException(404, "demo photo missing for this area")
        loc = siren.demo_location()
        persona = next((u["id"] for u in siren.users.values() if u["zone_id"] == loc["zone_id"]), "resident")
        return await _photo(p.read_bytes(), "image/jpeg", loc["lat"], loc["lon"], f"director:{persona}")
    if cmd.action == "reset_all":
        siren.clock.pause()
        siren.audience_reset()
        siren.reset_state()
        siren.clock.jump(siren.start)
        siren.tick()
        settings.force_gemini_failure = False
        return {"ok": True}
    raise HTTPException(400, "bad director command")


# ------------------------------------------------------------------ incidents, alerts, evidence

@app.get("/api/incidents/{iid}")
def incident(iid: str):
    inc = siren.incidents.get(iid) or _err(KeyError(iid), 404)
    alerts = [pl._alert_summary(siren.alerts[a]) for a in inc["alert_ids"]]
    events = [e for e in siren.lifecycle.events if e["alert_id"] in inc["alert_ids"]]
    sev = [h for h in siren.severity_history if h["zone_id"] == inc["zone_id"] and h["time"] >= inc["opened_at"]
           and (inc["closed_at"] is None or h["time"] <= inc["closed_at"])]
    return {**inc, "alerts": alerts, "events": events, "severity_history": sev}


@app.get("/api/timeline")
def timeline(limit: int = 120):
    return siren.timeline(limit)


@app.get("/api/alerts/{aid}/evidence")
def evidence(aid: str):
    a = siren.alerts.get(aid) or _err(KeyError(aid), 404)
    fired = [r for r in a["results"] if r["fired"]]
    rule_rows = []
    for r in a["results"]:
        inp = r["inputs"]
        readings = []
        for k in ("latest", "prior"):
            if isinstance(inp.get(k), dict):
                readings.append({**inp[k], "role": k})
        for x in inp.get("readings", []) or []:
            readings.append({**x, "role": "window"})
        for x in inp.get("verified_reports", []) or []:
            readings.append({**x, "role": "photo"})
        rule_rows.append({"rule_id": r["rule_id"], "version": r["version"], "description": r["description"],
                          "fired": r["fired"], "raw": r["raw"], "held_by_hysteresis": r["held"],
                          "severity": r["severity"], "official": r["official"], "inputs_hash": r["inputs_hash"],
                          "missing_data": r["missing_data"], "readings": readings,
                          "threshold_ft": inp.get("threshold_ft"), "threshold_source": inp.get("threshold_source"),
                          "age_minutes": inp.get("age_minutes"), "active_warnings": inp.get("active_warnings"),
                          "sum_in": inp.get("sum_in")})
    deliveries = []
    for did in a["delivery_ids"]:
        d = siren.deliveries[did]
        deliveries.append({**pl._public_delivery(d), "source_text_en": d.get("source_text_en"),
                           "events": [e for e in siren.lifecycle.events if e["delivery_id"] == did],
                           "label": (siren.users.get(d["user_id"]) or {}).get("name") or f"Audience {d['user_id'][:4]}"})
    photos = [pl._public_photo(siren.photos[p]) for p in a.get("photo_ids", []) if p in siren.photos]
    return {
        "alert": pl._alert_summary(a), "ruleset_version": siren.rules["ruleset_version"],
        "message_en": a["message_en"], "rules": rule_rows, "fired_rule_ids": [r["rule_id"] for r in fired],
        "missing_data": siren.zone_state[a["zone_id"]]["missing"], "exposure": a["exposure"],
        "explanation": a.get("explanation"), "explanation_facts": a.get("explanation_facts"), "ai": a.get("ai"),
        "photos": photos, "deliveries": deliveries,
        "lifecycle": [e for e in siren.lifecycle.events if e["alert_id"] == aid and e["delivery_id"] is None],
    }


@app.post("/api/alerts/{aid}/rerun")
def rerun(aid: str):
    """Re-run every rule from its stored inputs and prove the result and hash match."""
    a = siren.alerts.get(aid) or _err(KeyError(aid), 404)
    out = []
    for r in a["results"]:
        rule = siren.rules["by_id"][r["rule_id"]]
        raw = condition(rule, r["inputs"])
        h = inputs_hash(rule, r["inputs"])
        out.append({"rule_id": r["rule_id"], "stored_raw": r["raw"], "rerun_raw": raw, "stored_hash": r["inputs_hash"],
                    "rerun_hash": h, "match": raw == r["raw"] and h == r["inputs_hash"]})
    return {"alert_id": aid, "all_match": all(x["match"] for x in out), "rules": out}


class DeliverCmd(BaseModel):
    user_id: str


@app.post("/api/alerts/{aid}/deliver")
def deliver(aid: str, cmd: DeliverCmd):
    try:
        d = siren.deliver_to(aid, cmd.user_id)
    except KeyError as e:
        _err(e, 404)
    except InvalidTransition as e:
        _err(e, 409)
    return pl._public_delivery(d) if d else {"detail": "already delivered or alert closed"}


@app.post("/api/deliveries/{did}/rendered")
def rendered(did: str, actor: str = "resident-app"):
    if did not in siren.deliveries:
        raise HTTPException(404, "unknown delivery")
    return pl._public_delivery(siren.mark_rendered(did, actor))


@app.post("/api/deliveries/{did}/ack")
def ack(did: str, actor: str = "resident"):
    if did not in siren.deliveries:
        raise HTTPException(404, "unknown delivery")
    try:
        return pl._public_delivery(siren.acknowledge(did, actor))
    except InvalidTransition as e:
        _err(e, 409)


@app.get("/api/audio/{key}")
def audio(key: str):
    if not key.isalnum():
        raise HTTPException(400, "bad key")
    p = elevenlabs.audio_file(key)
    if not p.exists():
        raise HTTPException(404, "clip not cached")
    return FileResponse(p, media_type="audio/mpeg")


class TTSCmd(BaseModel):
    text: str
    language: str = "en"


@app.post("/api/tts")
async def tts(cmd: TTSCmd):
    v = await elevenlabs.synthesize(cmd.text[:400], cmd.language)
    return {**v, "audio_url": f"/api/audio/{v['audio_key']}" if v["audio_key"] else None}


# ------------------------------------------------------------------ residents, Q&A, photos

@app.get("/api/users")
def users():
    return list(siren.users.values())


class UserPatch(BaseModel):
    language: str | None = None
    zone_id: str | None = None
    vehicle: str | None = None
    needs: dict | None = None


@app.patch("/api/users/{uid}")
def patch_user(uid: str, p: UserPatch):
    u = siren.users.get(uid) or _err(KeyError(uid), 404)
    changes = p.model_dump(exclude_none=True)
    lang = changes.pop("language", None)
    for k, v in changes.items():
        u[k] = v
    if lang in ("en", "es"):
        siren.change_language(uid, lang)  # re-delivers the active alert in the new language
    siren._sync_recipient(uid)
    return u


@app.get("/api/residents/{rid}")
def resident(rid: str):
    if rid not in siren.users and rid not in siren.audience:
        raise HTTPException(404, "unknown resident")
    siren.tick()
    return siren.resident_view(rid)


class AskCmd(BaseModel):
    question: str
    user_id: str | None = None
    session_id: str | None = None
    language: str | None = None


@app.post("/api/ask")
async def ask(cmd: AskCmd):
    rid = cmd.session_id or cmd.user_id
    rec = siren.users.get(rid) or siren.audience.get(rid)
    if not rec:
        raise HTTPException(404, "unknown resident")
    if cmd.session_id:
        n = siren.ask_counts.get(cmd.session_id, 0)
        if n >= settings.audience_question_limit:
            raise HTTPException(429, "Question limit reached for this phone")
        siren.ask_counts[cmd.session_id] = n + 1
    lang = cmd.language or rec["language"]
    facts = siren.incident_facts(rec["zone_id"])
    res = await tasks.ask(cmd.question.strip()[:300], lang, facts)
    g = tasks.guidance()
    cites = []
    for c in res.output.get("citations", []):
        if c in g:
            cites.append({"id": c, "text": g[c][lang], "source": g[c]["source"]})
        else:
            f = next((f for f in facts if f["id"] == c), None)
            if f:
                cites.append({"id": c, "text": f[lang], "source": "SIREN incident facts"})
    voice = await elevenlabs.synthesize(res.output["answer"], lang)
    return {"question": cmd.question, "language": lang, **res.output, "citation_details": cites,
            "ai": res.log(), "audio_url": f"/api/audio/{voice['audio_key']}" if voice["audio_key"] else None,
            "voice": voice}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form("en")):
    """Groq Whisper fallback for browsers without the Web Speech API."""
    if settings.demo_offline or not settings.groq_api_key:
        raise HTTPException(503, "Speech-to-text fallback unavailable (offline or no GROQ_API_KEY); type the question")
    data = await audio.read()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.groq.com/openai/v1/audio/transcriptions",
                         headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                         data={"model": settings.groq_whisper_model, "language": language},
                         files={"file": (audio.filename or "q.webm", data, audio.content_type or "audio/webm")})
    if r.status_code != 200:
        raise HTTPException(502, f"transcription failed: HTTP {r.status_code}")
    return {"text": r.json().get("text", ""), "provider": "groq-whisper"}


async def _photo(data: bytes, mime: str, lat: float, lon: float, reporter: str):
    if len(data) > 8_000_000:
        raise HTTPException(413, "photo too large")
    digest = hashlib.sha256(data).hexdigest()[:16]
    d = settings.cache_dir / "photos"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{digest}.{'png' if 'png' in mime else 'jpg'}"
    path.write_bytes(data)
    analysis, check, res = await analyzer.analyze(data, mime)
    rep = siren.add_photo_report(lat=lat, lon=lon, image_path=str(path), analysis=analysis, check=check,
                                 ai=res.log(), reporter=reporter)
    return pl._public_photo(rep)


@app.post("/api/photos")
async def photos(image: UploadFile = File(...), lat: float = Form(...), lon: float = Form(...),
                 reporter: str = Form("resident"), session_id: str | None = Form(None)):
    if session_id:
        n = siren.ask_counts.get("photo:" + session_id, 0)
        if n >= 2:
            raise HTTPException(429, "Photo limit reached for this phone")
        siren.ask_counts["photo:" + session_id] = n + 1
    return await _photo(await image.read(), image.content_type or "image/jpeg", lat, lon, reporter)


@app.get("/api/photos/{pid}/image")
def photo_image(pid: str):
    p = siren.photos.get(pid) or _err(KeyError(pid), 404)
    return FileResponse(p["image_path"])


# ------------------------------------------------------------------ audience mode and lead time

class JoinCmd(BaseModel):
    language: str = "en"
    zone_id: str | None = None
    run: str | None = None


@app.post("/api/audience/join")
def audience_join(cmd: JoinCmd):
    cmd.zone_id = cmd.zone_id or siren.area.get("audience_default_zone") or next(iter(siren.zone_state))
    if cmd.zone_id not in siren.zone_state:
        raise HTTPException(400, "unknown zone")
    if len(siren.audience) >= 300:
        raise HTTPException(429, "audience full")
    return siren.audience_join(cmd.language, cmd.zone_id, cmd.run)


@app.get("/api/audience/summary")
def audience_summary():
    return siren.audience_summary()


@app.get("/api/audience/{sid}/feed")
def audience_feed(sid: str):
    if sid not in siren.audience:
        raise HTTPException(404, "session not found (the demo may have been reset); join again")
    siren.tick()
    return siren.audience_feed(sid)


class AudienceAck(BaseModel):
    delivery_id: str


@app.post("/api/audience/{sid}/ack")
def audience_ack(sid: str, cmd: AudienceAck):
    d = siren.deliveries.get(cmd.delivery_id)
    if sid not in siren.audience or not d or d["user_id"] != sid:
        raise HTTPException(404, "unknown delivery for this session")
    try:
        return pl._public_delivery(siren.acknowledge(cmd.delivery_id, f"audience:{sid[:4]}"))
    except InvalidTransition as e:
        _err(e, 409)


@app.post("/api/audience/reset")
def audience_reset():
    siren.audience_reset()
    return siren.audience_summary()


@app.get("/api/areas")
def areas():
    return {"active": siren.area["id"], "areas": list_areas()}


class AreaCmd(BaseModel):
    id: str


@app.post("/api/area")
def switch_area(cmd: AreaCmd):
    """Switch the replayed area. Starts a fresh replay; audience phones are asked to re-join."""
    global siren
    try:
        new = pl.Siren(sink=siren.sink, area_id=cmd.id)
    except KeyError as e:
        _err(e, 404)
    settings.force_gemini_failure = False
    new.jump(new.start)
    siren = new
    return {"active": siren.area["id"], "area": siren.area}


# ------------------------------------------------------------------ live status anywhere in the US (per person)

@app.get("/api/live/status")
async def live_status(lat: float, lon: float, lang: str = "en"):
    try:
        st = await live.status(lat, lon, lang)
    except live.LiveError as e:
        raise HTTPException(e.status, str(e))
    return st  # voice is generated on demand (POST /api/tts) to protect the free ElevenLabs quota


@app.get("/api/geocode")
async def geocode(q: str):
    try:
        return await live.geocode(q)
    except live.LiveError as e:
        raise HTTPException(e.status, str(e))


@app.post("/api/live/photo")
async def live_photo(image: UploadFile = File(...), lat: float = Form(...), lon: float = Form(...), lang: str = Form("en")):
    data = await image.read()
    if len(data) > 8_000_000:
        raise HTTPException(413, "photo too large")
    return await live.photo_check(data, image.content_type or "image/jpeg", lat, lon, lang)


class LiveAsk(BaseModel):
    question: str
    lat: float
    lon: float
    language: str = "en"


@app.post("/api/live/ask")
async def live_ask(cmd: LiveAsk):
    try:
        st = await live.status(cmd.lat, cmd.lon, cmd.language)
    except live.LiveError as e:
        raise HTTPException(e.status, str(e))
    lang = st["language"]
    facts = live.qa_facts(st)
    res = await tasks.ask(cmd.question.strip()[:300], lang, facts)
    g = tasks.guidance()
    cites = [{"id": c, "text": g[c][lang], "source": g[c]["source"]} if c in g else
             {"id": c, "text": next((f[lang] for f in facts if f["id"] == c), ""), "source": "SIREN live facts"}
             for c in res.output.get("citations", [])]
    voice = await elevenlabs.synthesize(res.output["answer"], lang)
    return {**res.output, "citation_details": cites, "ai": res.log(),
            "audio_url": f"/api/audio/{voice['audio_key']}" if voice["audio_key"] else None}


_lead_all: dict = {}


@app.get("/api/lead-time/all")
def lead_time_all():
    """Timing vs official warnings for every shipped storm (computed once, deterministic)."""
    if not _lead_all:
        for a in list_areas():
            lt = pl.Siren(area_id=a["id"]).lead_time()
            _lead_all[a["id"]] = {"area": a, **lt}
        if siren:
            from . import messages as _m
            _m.set_timezone(siren.area["tz"])  # building other areas switched the module time zone
    return list(_lead_all.values())


@app.get("/api/validation")
def validation():
    """Photo depth validation: manifest of judged photos plus the latest results (if the run has happened)."""
    import json as _json
    d = settings.fixtures_dir / "depth_validation"
    manifest = _json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else []
    results = _json.loads((d / "results.json").read_text()) if (d / "results.json").exists() else None
    return {"manifest": manifest, "results": results}


@app.get("/api/validation/image/{name}")
def validation_image(name: str):
    p = settings.fixtures_dir / "depth_validation" / name
    if "/" in name or ".." in name or not p.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(p)


@app.get("/api/lead-time")
def lead_time():
    return siren.lead_time()


@app.get("/api/zones")
def zones():
    return {"type": "FeatureCollection", "features": siren.fx.zones}


@app.get("/api/facilities")
def facilities():
    """Facilities inside watch zones, tagged with their zone."""
    from .geo import point_in_geom
    out = []
    for f in siren.fx.facilities:
        z = next((z for z in siren.fx.zones if point_in_geom(f["lon"], f["lat"], z["geometry"])), None)
        if z:
            out.append({**f, "zone_id": z["properties"]["zone_id"]})
    return out


@app.get("/api/official-warnings")
def official_warnings():
    return [{k: v for k, v in w.items() if not k.startswith("_")} for w in siren.warnings]


@app.get("/api/rules")
def rules():
    return {k: v for k, v in siren.rules.items() if k != "by_id"}


@app.get("/api/ai-logs")
def ai_logs(limit: int = 100):
    return {"ai": ai_client.AI_LOGS[-limit:], "voice": elevenlabs.VOICE_LOG[-limit:]}


@app.get("/api/health")
async def health(probe: bool = False):
    deps = {
        "gemini": {"configured": bool(settings.gemini_api_key), "model": settings.gemini_model},
        "groq": {"configured": bool(settings.groq_api_key), "model": settings.groq_model},
        "elevenlabs": {"configured": bool(settings.elevenlabs_api_key), "model": settings.elevenlabs_model},
        "database": siren.sink.stats() if siren.sink else {"connected": False, "note": "in-memory (DATABASE_URL unset)"},
        "fixtures": {"readings": len(siren.fx.readings), "zones": len(siren.fx.zones),
                     "facilities": len(siren.fx.facilities), "official_warnings": len(siren.warnings)},
        "cache": {"ai_files": len(list((settings.cache_dir / "ai").glob("*.json"))) if (settings.cache_dir / "ai").exists() else 0,
                  "audio_files": len(list((settings.cache_dir / "audio").glob("*.mp3"))) if (settings.cache_dir / "audio").exists() else 0},
    }
    if probe and not settings.demo_offline:
        async def ping(url):
            try:
                async with httpx.AsyncClient(timeout=4, headers={"User-Agent": settings.user_agent}) as c:
                    r = await c.get(url)
                return {"reachable": r.status_code < 500, "status": r.status_code}
            except Exception as e:
                return {"reachable": False, "error": e.__class__.__name__}
        deps["usgs"] = await ping("https://api.waterdata.usgs.gov/ogcapi/v0/")
        deps["nws"] = await ping("https://api.weather.gov/alerts/active?area=TX&limit=1")
    return {"ok": True, "offline": settings.demo_offline, "time": datetime.now(timezone.utc).isoformat(), "deps": deps}


# ------------------------------------------------------------------ frontend (single-process deploy / offline demo)

_dist = ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _dist / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
