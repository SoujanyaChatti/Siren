import os
import sys
from pathlib import Path

os.environ["DEMO_OFFLINE"] = "true"
os.environ.setdefault("SIREN_CACHE_DIR", str(Path(__file__).parent / "_cache"))
os.environ["DATABASE_URL"] = ""
for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "ELEVENLABS_API_KEY"):
    os.environ[k] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
