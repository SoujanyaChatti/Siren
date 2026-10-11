"""ElevenLabs text-to-speech with a content-hash cache (cache/audio). Offline mode reads cache only.
If no clip is available, the frontend shows the transcript and can fall back to the browser voice."""
from __future__ import annotations

import hashlib
import logging

import httpx

from ..settings import settings

log = logging.getLogger("siren.voice")
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
VOICE_LOG: list[dict] = []
_spent = {"chars": 0}


def _voice(language: str) -> str:
    return settings.elevenlabs_voice_es if language == "es" else settings.elevenlabs_voice_en


def audio_key(text: str, language: str) -> str:
    blob = f"{settings.elevenlabs_model}|{_voice(language)}|{language}|{text}"
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def audio_file(key: str):
    d = settings.cache_dir / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.mp3"


async def synthesize(text: str, language: str) -> dict:
    """Returns {"audio_key": str|None, "provider": ..., "cache_hit": bool, "error": str|None}."""
    key = audio_key(text, language)
    path = audio_file(key)
    if path.exists() and path.stat().st_size > 0:
        rec = {"audio_key": key, "provider": "elevenlabs", "cache_hit": True, "error": None}
    elif settings.demo_offline:
        rec = {"audio_key": None, "provider": "none", "cache_hit": False, "error": "offline mode, clip not cached"}
    elif not settings.elevenlabs_api_key:
        rec = {"audio_key": None, "provider": "none", "cache_hit": False, "error": "no ELEVENLABS_API_KEY"}
    elif _spent["chars"] + len(text) > settings.elevenlabs_char_budget:
        rec = {"audio_key": None, "provider": "none", "cache_hit": False, "error": "ElevenLabs character budget reached"}
    else:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(TTS_URL.format(voice=_voice(language)),
                                 headers={"xi-api-key": settings.elevenlabs_api_key, "accept": "audio/mpeg"},
                                 json={"text": text, "model_id": settings.elevenlabs_model,
                                       "language_code": language})
            r.raise_for_status()
            path.write_bytes(r.content)
            _spent["chars"] += len(text)
            rec = {"audio_key": key, "provider": "elevenlabs", "cache_hit": False, "error": None}
        except Exception as e:  # quota, network: transcript still shown
            log.warning("elevenlabs failed: %s", e)
            rec = {"audio_key": None, "provider": "none", "cache_hit": False, "error": f"{e.__class__.__name__}: {e}"[:200]}
    VOICE_LOG.append({**rec, "language": language, "chars": len(text)})
    del VOICE_LOG[:-300]
    return rec
