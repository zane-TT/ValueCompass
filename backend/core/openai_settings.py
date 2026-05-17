from __future__ import annotations

import os

try:
    from .config import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL, DEFAULT_OPENAI_TEMPERATURE
except ImportError:
    from core.config import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL, DEFAULT_OPENAI_TEMPERATURE


def normalize_openai_base_url(base_url: str | None) -> str:
    text = (base_url or DEFAULT_OPENAI_BASE_URL).strip().rstrip("/")
    if not text:
        text = DEFAULT_OPENAI_BASE_URL
    if not text.endswith("/v1"):
        text = f"{text}/v1"
    return text


def get_openai_settings() -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY. Please configure it in your local environment before using /api/ai-analysis.")

    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    base_url = normalize_openai_base_url(os.getenv("OPENAI_BASE_URL"))

    temperature_text = os.getenv("OPENAI_TEMPERATURE", str(DEFAULT_OPENAI_TEMPERATURE)).strip()
    try:
        temperature = float(temperature_text)
    except ValueError as exc:
        raise ValueError("OPENAI_TEMPERATURE must be a number.") from exc

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
    }
