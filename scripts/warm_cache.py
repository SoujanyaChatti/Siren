"""Fill cache/ai and cache/audio by running the demo path once against the live APIs.

After this, DEMO_OFFLINE=true replays the same Gemini/Groq outputs and ElevenLabs clips with Wi-Fi off.
Cache keys are hashes of (task, model, language, input), so only changed inputs are regenerated.

Usage (from repo root, keys in .env):
    backend/.venv/bin/python scripts/warm_cache.py                 # zone B audience (en+es) + personas, with voice
    backend/.venv/bin/python scripts/warm_cache.py --zones A B C   # every zone
    backend/.venv/bin/python scripts/warm_cache.py --no-voice      # text only (save ElevenLabs credits)

ElevenLabs' free plan is roughly 10 minutes of speech a month: voice only what the demo plays.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DEMO_OFFLINE"] = "false"

from app import pipeline as pl  # noqa: E402
from app.ai import tasks  # noqa: E402
from app.depth import analyzer  # noqa: E402
from app.settings import settings  # noqa: E402
from app.voice import elevenlabs  # noqa: E402

QUESTIONS = {
    "en": ["What should I do now?", "Can I drive to work?", "How deep is the water?", "My mother uses a wheelchair. What should we do?"],
    "es": ["¿Qué debo hacer ahora?", "¿Puedo manejar al trabajo?", "¿Qué tan profunda está el agua?", "Mi mamá usa silla de ruedas. ¿Qué hacemos?"],
}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zones", nargs="+", default=["B"])
    ap.add_argument("--no-voice", action="store_true")
    args = ap.parse_args()
    settings.demo_offline = False
    if args.no_voice:
        settings.elevenlabs_api_key = ""
    missing = [k for k in ("gemini_api_key", "elevenlabs_api_key") if not getattr(settings, k)]
    print(f"Gemini model {settings.gemini_model}; missing keys: {missing or 'none'}")

    s = pl.Siren()
    for z in args.zones:
        for lang in ("en", "es"):
            s.audience_join(lang, z, "warm")
    t = pl.REPLAY_START
    while t <= pl.REPLAY_END:
        s.clock.jump(t)
        s.tick()
        await s.drain()
        if t.isoformat().startswith("2024-07-08T14:30"):
            img = (settings.fixtures_dir / "photos" / "demo_underpass.jpg").read_bytes()
            analysis, check, res = await analyzer.analyze(img, "image/jpeg")
            print(f"  photo: path={res.path} depth={analysis.get('depth_in')} status={check['status']} {res.fallback_reasons}")
            road = s.fx.zone("B")["properties"]["roads"][0]
            s.add_photo_report(lat=road["lat"], lon=road["lon"], image_path="", analysis=analysis, check=check,
                               ai=res.log(), reporter="warm")
            await s.drain()
        t += pl.STEP
    paths: dict[str, int] = {}
    for a in s.alerts.values():
        p = (a.get("ai") or {}).get("path", "none")
        paths[p] = paths.get(p, 0) + 1
    print(f"alerts: {len(s.alerts)} explanation paths {paths}")
    tpaths: dict[str, int] = {}
    for d in s.deliveries.values():
        p = (d.get("translation") or {}).get("path", "en-template")
        tpaths[p] = tpaths.get(p, 0) + 1
    print(f"deliveries: {len(s.deliveries)} translation paths {tpaths}")

    # Common questions at the photo scene for each zone/language
    s2 = pl.Siren()
    s2.jump(pl.REPLAY_START.replace(hour=14, minute=30))
    await s2.drain()
    for z in args.zones:
        facts = s2.incident_facts(z)
        for lang, qs in QUESTIONS.items():
            for q in qs:
                r = await tasks.ask(q, lang, facts)
                await elevenlabs.synthesize(r.output["answer"], lang)
                print(f"  ask[{z}/{lang}] {q!r}: {r.path} {r.output['citations']}")
    ai_files = len(list((settings.cache_dir / "ai").glob("*.json")))
    audio_files = len(list((settings.cache_dir / "audio").glob("*.mp3")))
    print(f"cache: {ai_files} AI outputs, {audio_files} audio clips in {settings.cache_dir}")
    print("NOTE: offline audience phones only hit the cache when their alert text matches exactly (same zone, "
          "language, alert time). Personas and Zone B audience are covered by default.")


if __name__ == "__main__":
    asyncio.run(main())
