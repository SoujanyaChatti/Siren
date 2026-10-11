"""Settings: everything comes from the environment (.env), never hardcoded."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None or v == "" else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    demo_offline: bool = field(default_factory=lambda: _bool("DEMO_OFFLINE", True))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-flash-latest"))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
    groq_whisper_model: str = field(default_factory=lambda: os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"))
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", ""))
    elevenlabs_model: str = field(default_factory=lambda: os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5"))
    elevenlabs_voice_en: str = field(default_factory=lambda: os.getenv("ELEVENLABS_VOICE_EN", "EXAVITQu4vr4xnSDxMaL"))
    elevenlabs_voice_es: str = field(default_factory=lambda: os.getenv("ELEVENLABS_VOICE_ES", "EXAVITQu4vr4xnSDxMaL"))
    # Free plan is ~10k characters/month: stop calling ElevenLabs after this many new characters per server run
    elevenlabs_char_budget: int = field(default_factory=lambda: int(os.getenv("ELEVENLABS_CHAR_BUDGET", "8000")))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    cors_origins: str = field(default_factory=lambda: os.getenv("CORS_ORIGINS", "*"))
    public_frontend_url: str = field(default_factory=lambda: os.getenv("PUBLIC_FRONTEND_URL", ""))
    user_agent: str = field(default_factory=lambda: os.getenv(
        "SIREN_USER_AGENT", "SIREN-hackathon/0.1 (flood alert demo)"))
    audience_question_limit: int = field(default_factory=lambda: int(os.getenv("AUDIENCE_QUESTION_LIMIT", "3")))
    # Live status (free, keyless NOAA/USGS/NWS feeds). Independent of DEMO_OFFLINE, which governs AI and voice.
    allow_live_data: bool = field(default_factory=lambda: _bool("ALLOW_LIVE_DATA", True))
    default_area: str = field(default_factory=lambda: os.getenv("SIREN_AREA", "houston-brays"))
    fixtures_dir: Path = ROOT / "fixtures"
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("SIREN_CACHE_DIR", str(ROOT / "cache"))))
    # Runtime toggle from the director panel: pretend Gemini returned 429 to show the fallback.
    force_gemini_failure: bool = False


settings = Settings()
