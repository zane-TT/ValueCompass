from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .config import AK_DATA_CACHE_TTL_SECONDS, CACHE_DIR


class InflightCall:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


INFLIGHT_LOCK = threading.Lock()
INFLIGHT_CALLS: dict[tuple[object, ...], InflightCall] = {}
AK_DATA_CACHE: dict[tuple[object, ...], tuple[float, pd.DataFrame]] = {}


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_cache_part(value: object) -> str:
    text = str(value).strip()
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)
    return safe or "default"


def cache_file_path(prefix: str, *parts: object) -> Path:
    filename = "__".join([sanitize_cache_part(prefix), *[sanitize_cache_part(part) for part in parts]])
    return CACHE_DIR / f"{filename}.json"


def sanitize_json_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json_payload(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if pd.isna(value) and not isinstance(value, (str, bytes, bytearray)):
        return None
    return value


def run_singleflight(key: tuple[object, ...], builder: Callable[[], Any]) -> Any:
    with INFLIGHT_LOCK:
        call = INFLIGHT_CALLS.get(key)
        if call is None:
            call = InflightCall()
            INFLIGHT_CALLS[key] = call
            owner = True
        else:
            owner = False

    if not owner:
        print(f"[INFO] Waiting for in-flight build: {key}")
        call.event.wait()
        if call.error is not None:
            raise call.error
        return call.result

    try:
        call.result = builder()
        return call.result
    except BaseException as exc:
        call.error = exc
        raise
    finally:
        with INFLIGHT_LOCK:
            INFLIGHT_CALLS.pop(key, None)
        call.event.set()


def load_cached_payload(prefix: str, *parts: object) -> dict | None:
    path = cache_file_path(prefix, *parts)
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as cache_file:
            print(f"[INFO] Cache hit: {path.name}")
            return sanitize_json_payload(json.load(cache_file))
    except json.JSONDecodeError:
        print(f"[WARN] Cache corrupted, rebuilding: {path.name}")
        path.unlink(missing_ok=True)
        return None


def load_latest_cached_payload(pattern: str) -> dict | None:
    try:
        for path in sorted(CACHE_DIR.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                with path.open("r", encoding="utf-8") as cache_file:
                    print(f"[INFO] Stale cache hit: {path.name}")
                    return sanitize_json_payload(json.load(cache_file))
            except json.JSONDecodeError:
                print(f"[WARN] Cache corrupted, ignoring: {path.name}")
                path.unlink(missing_ok=True)
    except Exception as exc:
        print(f"[WARN] Latest cache lookup failed: {pattern}: {exc}")
    return None


def save_cached_payload(payload: dict, prefix: str, *parts: object) -> dict:
    ensure_cache_dir()
    path = cache_file_path(prefix, *parts)
    tmp_path = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
    clean_payload = sanitize_json_payload(payload)
    with tmp_path.open("w", encoding="utf-8") as cache_file:
        json.dump(clean_payload, cache_file, ensure_ascii=False, indent=2, allow_nan=False)
    tmp_path.replace(path)
    print(f"[INFO] Cache saved: {path.name}")
    return clean_payload


def get_cached_payload_or_build(
    prefix: str,
    *parts: object,
    builder: Callable[[], dict],
    refresh: bool = False,
) -> dict:
    if not refresh:
        cached_payload = load_cached_payload(prefix, *parts)
        if cached_payload is not None:
            return cached_payload

    def build_and_save() -> dict:
        if not refresh:
            cached_payload = load_cached_payload(prefix, *parts)
            if cached_payload is not None:
                return cached_payload
        payload = builder()
        save_cached_payload(payload, prefix, *parts)
        return payload

    return run_singleflight(("payload", prefix, *parts), build_and_save)


def get_ak_dataframe_cached(key: tuple[object, ...], builder: Callable[[], pd.DataFrame], refresh: bool = False) -> pd.DataFrame:
    now = time.monotonic()
    if not refresh:
        with INFLIGHT_LOCK:
            cached = AK_DATA_CACHE.get(key)
            if cached is not None:
                cached_at, cached_df = cached
                if now - cached_at < AK_DATA_CACHE_TTL_SECONDS:
                    print(f"[INFO] AK data memory cache hit: {key}")
                    return cached_df.copy()
                AK_DATA_CACHE.pop(key, None)

    df = run_singleflight(("ak-data", *key), builder)
    with INFLIGHT_LOCK:
        AK_DATA_CACHE[key] = (time.monotonic(), df.copy())
    return df.copy()


def get_cache_overview() -> dict:
    cache_files = sorted(CACHE_DIR.glob("*.json"))
    total_bytes = sum(path.stat().st_size for path in cache_files)
    return {
        "directory": str(CACHE_DIR),
        "exists": CACHE_DIR.exists(),
        "fileCount": len(cache_files),
        "totalBytes": total_bytes,
    }


def list_recent_cache_files(limit: int = 10) -> list[dict]:
    cache_files = sorted(
        CACHE_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    recent_files = []
    for path in cache_files[:limit]:
        stat = path.stat()
        recent_files.append(
            {
                "name": path.name,
                "sizeBytes": stat.st_size,
                "modifiedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    return recent_files
