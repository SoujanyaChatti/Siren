"""AI fallback chain: Gemini Flash (structured output) -> Groq (text tasks) -> deterministic template.

Every output is validated; anything that fails validation is discarded and the next path is tried.
Outputs are cached by a hash of (task, model, language, input) so the demo runs offline from cache/.
Every call is logged (task, model, latency, cache hit, validation result, fallback reason).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from ..settings import settings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class TransientAIError(Exception):
    """429 / timeout / 5xx: worth one retry, then fall back."""


@dataclass
class AIResult:
    task: str
    output: dict
    path: str                 # gemini | groq | template | fixture
    model: str
    cache_hit: bool
    latency_ms: int
    validation_errors: list[str] = field(default_factory=list)
    fallback_reasons: list[str] = field(default_factory=list)
    language: str = "en"
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def log(self) -> dict:
        d = asdict(self)
        d.pop("output")
        return d


AI_LOGS: list[dict] = []


def cache_key(task: str, model: str, language: str, payload: Any, image: bytes | None = None) -> str:
    blob = json.dumps({"task": task, "model": model, "language": language, "input": payload},
                      sort_keys=True, ensure_ascii=False, default=str)
    h = hashlib.sha256(blob.encode())
    if image is not None:
        h.update(hashlib.sha256(image).digest())
    return h.hexdigest()[:24]


def _cache_path(task: str, key: str):
    d = settings.cache_dir / "ai"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{task}-{key}.json"


def cache_get(task: str, key: str) -> dict | None:
    p = _cache_path(task, key)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return None
    return None


def cache_put(task: str, key: str, record: dict) -> None:
    _cache_path(task, key).write_text(json.dumps(record, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- providers

async def _gemini(system: str, user: str, schema: dict, image: bytes | None, mime: str | None) -> dict:
    if settings.force_gemini_failure:
        raise TransientAIError("forced Gemini failure (director panel)")
    if not settings.gemini_api_key:
        raise RuntimeError("no GEMINI_API_KEY")
    parts: list[dict] = [{"text": user}]
    if image is not None:
        parts.append({"inline_data": {"mime_type": mime or "image/jpeg", "data": base64.b64encode(image).decode()}})
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0.2},
    }
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(GEMINI_URL.format(model=settings.gemini_model), json=body,
                             headers={"x-goog-api-key": settings.gemini_api_key})
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise TransientAIError(f"gemini network: {e.__class__.__name__}") from e
    if r.status_code == 429 or r.status_code >= 500:
        raise TransientAIError(f"gemini HTTP {r.status_code}")
    r.raise_for_status()
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


async def _groq(system: str, user: str, schema: dict) -> dict:
    if not settings.groq_api_key:
        raise RuntimeError("no GROQ_API_KEY")
    sys = system + "\nRespond with a single JSON object matching this schema: " + json.dumps(schema)
    body = {"model": settings.groq_model, "temperature": 0.2, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}]}
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {settings.groq_api_key}"})
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise TransientAIError(f"groq network: {e.__class__.__name__}") from e
    if r.status_code == 429 or r.status_code >= 500:
        raise TransientAIError(f"groq HTTP {r.status_code}")
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


# ---------------------------------------------------------------- chain

async def run(task: str, *, system: str, payload: Any, schema: dict, validate: Callable[[dict], list[str]],
              template: Callable[[], dict], language: str = "en", image: bytes | None = None,
              image_mime: str | None = None, allow_groq: bool = True,
              offline_fixture: Callable[[], dict | None] | None = None) -> AIResult:
    t0 = time.monotonic()
    reasons: list[str] = []
    user = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=1, default=str)

    def done(output, path, model, hit, errs=()):
        res = AIResult(task, output, path, model, hit, int((time.monotonic() - t0) * 1000),
                       list(errs), reasons, language)
        AI_LOGS.append(res.log())
        del AI_LOGS[:-500]
        return res

    providers: list[tuple[str, str]] = [("gemini", settings.gemini_model)]
    if allow_groq and image is None:
        providers.append(("groq", settings.groq_model))

    for name, model in providers:
        key = cache_key(task, model, language, payload, image)
        if name == "gemini" and settings.force_gemini_failure:
            reasons.append("gemini: forced failure (director panel)")
            continue
        cached = cache_get(task, key)
        if cached is not None:
            errs = validate(cached["output"])
            if not errs:
                return done(cached["output"], name, model, True)
            reasons.append(f"{name}: cached output failed validation {errs}")
        if settings.demo_offline:
            reasons.append(f"{name}: offline mode, no cached output")
            continue
        out = None
        for attempt in range(3):  # retry with backoff on 429 / 503 / timeout
            try:
                out = await (_gemini(system, user, schema, image, image_mime) if name == "gemini"
                             else _groq(system, user, schema))
                break
            except TransientAIError as e:
                reasons.append(f"{name}: {e}")
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
            except Exception as e:  # missing key, bad response, JSON error
                reasons.append(f"{name}: {e.__class__.__name__}: {e}"[:200])
                break
        if out is None:
            continue
        errs = validate(out)
        if errs:
            reasons.append(f"{name}: validation failed {errs}")
            AI_LOGS.append({"task": task, "model": model, "path": name, "validation_errors": errs,
                            "discarded": True, "at": datetime.now(timezone.utc).isoformat()})
            continue
        cache_put(task, key, {"output": out, "model": model, "path": name, "created": datetime.now(timezone.utc).isoformat()})
        return done(out, name, model, False)

    if offline_fixture is not None:
        fx = offline_fixture()
        if fx is not None:
            reasons.append("using committed fixture analysis")
            return done(fx, "fixture", fx.get("_model", "fixture"), True)
    return done(template(), "template", "deterministic-template", False)
