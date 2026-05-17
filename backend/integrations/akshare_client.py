from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from typing import Any

import pandas as pd

try:
    from ..core.config import AK_SUBPROCESS_TIMEOUT_SECONDS, BASE_DIR, PROXY_ENV_KEYS
except ImportError:
    from core.config import AK_SUBPROCESS_TIMEOUT_SECONDS, BASE_DIR, PROXY_ENV_KEYS


@contextmanager
def temporary_disable_proxy_env():
    original_values = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
    try:
        for key in PROXY_ENV_KEYS:
            os.environ[key] = ""
        yield
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_python_json_subprocess(code: str, *args: str, timeout: int = AK_SUBPROCESS_TIMEOUT_SECONDS) -> Any:
    env = os.environ.copy()
    for key in PROXY_ENV_KEYS:
        env[key] = ""

    completed = subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=str(BASE_DIR),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"AKShare subprocess failed: {detail}")

    output_lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    if not output_lines:
        raise RuntimeError("AKShare subprocess returned empty output.")
    return json.loads(output_lines[-1])


def stock_profile_cninfo_isolated(stock: str) -> pd.DataFrame:
    code = r"""
import json
import sys
import akshare as ak

stock = sys.argv[1]
df = ak.stock_profile_cninfo(symbol=stock)
print(json.dumps(df.to_dict(orient="records"), ensure_ascii=False))
"""
    records = run_python_json_subprocess(code, stock)
    return pd.DataFrame(records)
