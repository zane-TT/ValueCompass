from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

YI = 100000000
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "cache"
FRONTEND_OUT_DIR = BASE_DIR.parent / "frontend" / "out"
load_dotenv(BASE_DIR / ".env")

DEFAULT_OPENAI_BASE_URL = "https://api.openai-proxy.org/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.4-nano-2026-03-17"
DEFAULT_OPENAI_TEMPERATURE = 0.1
APP_STARTED_AT = datetime.now(timezone.utc)
AK_DATA_CACHE_TTL_SECONDS = 300
AK_SUBPROCESS_TIMEOUT_SECONDS = 45

PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]
