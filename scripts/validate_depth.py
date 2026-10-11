"""Photo depth validation: run the analyzer on openly licensed flood photos with judged depths.

Manifest: fixtures/depth_validation/manifest.json, a list of
  {"file": "name.jpg", "url": "...commons page...", "license": "...",
   "true_low_in": 12, "true_high_in": 16, "basis": "water at mid-wheel on a sedan"}
"True" depth is a human judgement from visible reference objects, given as a range; the midpoint is used for MAE.

Usage:  DEMO_OFFLINE=false backend/.venv/bin/python scripts/validate_depth.py
Writes fixtures/depth_validation/results.json and prints MAE and range coverage. Be honest about sample size.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DEMO_OFFLINE", "false")

from app.depth import analyzer  # noqa: E402
from app.settings import settings  # noqa: E402

DIR = ROOT / "fixtures" / "depth_validation"


async def main() -> None:
    manifest = json.loads((DIR / "manifest.json").read_text())
    rows = []
    for item in manifest:
        img = (DIR / item["file"]).read_bytes()
        mime = mimetypes.guess_type(item["file"])[0] or "image/jpeg"
        analysis, check, res = await analyzer.analyze(img, mime)
        for attempt in range(3):  # free-tier rate limits: wait and retry instead of scoring the template fallback
            if res.path == "gemini":
                break
            print(f"  {item['file']}: {res.fallback_reasons[-1:]} -> waiting 25 s")
            await asyncio.sleep(25)
            analysis, check, res = await analyzer.analyze(img, mime)
        if not res.cache_hit:
            await asyncio.sleep(5)
        truth = (item["true_low_in"] + item["true_high_in"]) / 2
        est = analysis.get("depth_in")
        row = {"file": item["file"], "truth_mid_in": truth, "truth_range": [item["true_low_in"], item["true_high_in"]],
               "estimate_in": est, "range": [analysis.get("depth_low_in"), analysis.get("depth_high_in")],
               "confidence": analysis.get("confidence"), "status": check["status"], "path": res.path}
        if est is not None:
            row["abs_error_in"] = abs(est - truth)
            row["truth_in_range"] = analysis["depth_low_in"] <= truth <= analysis["depth_high_in"]
        rows.append(row)
        print(f"{item['file']:40s} truth {truth:5.1f}  est {est}  range {row['range']}  {check['status']}  ({res.path})")
    scored = [r for r in rows if "abs_error_in" in r and r["path"] == "gemini"]
    summary = {
        "n_photos": len(rows), "n_scored": len(scored),
        "mae_in": round(statistics.mean(r["abs_error_in"] for r in scored), 1) if scored else None,
        "range_coverage": round(sum(r["truth_in_range"] for r in scored) / len(scored), 2) if scored else None,
        "verified_share": round(sum(r["status"] == "verified" for r in rows) / len(rows), 2) if rows else None,
        "note": "Small sample of human-judged depths; not a benchmark.",
    }
    from datetime import datetime, timezone
    (DIR / "results.json").write_text(json.dumps({"summary": summary, "rows": rows, "model": settings.gemini_model,
                                                  "run_at": datetime.now(timezone.utc).isoformat()}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
