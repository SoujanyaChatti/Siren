"""Pre-record ElevenLabs clips for the replay demo path only (free plan ~10k characters/month).

Simulates the demo exactly as it is presented (jump to scene 3, play to the Main St crossing, photo report),
collects every alert text residents would hear, prints the character cost, then records the clips into
cache/audio so the offline demo plays them with Wi-Fi off. Text uses the deterministic templates (Gemini off),
so it matches what the offline demo generates.

Usage:  backend/.venv/bin/python scripts/warm_voice.py [--area houston-brays] [--dry-run] [--yes]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DEMO_OFFLINE"] = "true"  # simulate offline (templates), then record with the network below

from app import pipeline as pl  # noqa: E402
from app.ai import tasks  # noqa: E402
from app.depth import analyzer  # noqa: E402
from app.ingest.fixtures import parse_t  # noqa: E402
from app.settings import settings  # noqa: E402
from app.voice import elevenlabs  # noqa: E402

QUESTIONS = {"en": ["What should I do now?", "Can I drive to work?"], "es": ["¿Qué hago ahora?", "¿Puedo manejar al trabajo?"]}


async def collect(area: str) -> list[tuple[str, str]]:
    s = pl.Siren(area_id=area)
    zone = s.area.get("audience_default_zone", "B")
    for lang in ("en", "es"):
        s.audience_join(lang, zone, "warm")
    scenes = {x["id"]: parse_t(x["time"]) for x in s.fx.scenes}
    s.jump(scenes["warning"])
    await s.drain()
    t = scenes["warning"]
    while t < scenes["photo"]:  # presenter presses play: every 15-minute step until the photo scene
        t += timedelta(minutes=15)
        s.clock.jump(t)
        s.tick()
        await s.drain()
    dp = s.area.get("demo_photo")
    if dp:
        img = (settings.fixtures_dir / dp["file"]).read_bytes()
        analysis, check, res = await analyzer.analyze(img, "image/jpeg")
        loc = s.demo_location()
        s.add_photo_report(lat=loc["lat"], lon=loc["lon"], image_path="", analysis=analysis, check=check, ai=res.log(),
                           reporter="warm")
        await s.drain()
    texts: dict[tuple[str, str], None] = {}
    for d in s.deliveries.values():  # everything a resident would see during the demo, including superseded alerts
        if d.get("text"):
            texts[(d["text"], d["language"])] = None
    for u in s.users.values():
        for q in QUESTIONS[u["language"]]:
            r = await tasks.ask(q, u["language"], s.incident_facts(u["zone_id"]))
            texts[(r.output["answer"], u["language"])] = None
    return list(texts)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="houston-brays")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    items = await collect(args.area)
    todo = [(t, l) for t, l in items if not elevenlabs.audio_file(elevenlabs.audio_key(t, l)).exists()]
    chars = sum(len(t) for t, _ in todo)
    print(f"{len(items)} clips on the demo path, {len(todo)} not cached yet, {chars} characters to record")
    for t, l in todo:
        print(f"  [{l}] {t[:90]}…")
    if args.dry_run or not todo:
        return
    if not args.yes and input("Record them now? [y/N] ").strip().lower() != "y":
        return
    settings.demo_offline = False
    settings.elevenlabs_char_budget = max(settings.elevenlabs_char_budget, chars + 1)
    ok = 0
    for t, l in todo:
        rec = await elevenlabs.synthesize(t, l)
        ok += bool(rec["audio_key"])
        if rec["error"]:
            print("  error:", rec["error"])
    print(f"recorded {ok}/{len(todo)} clips into {settings.cache_dir / 'audio'}")


if __name__ == "__main__":
    asyncio.run(main())
