from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

try:
    from .config import YI
except ImportError:
    from core.config import YI


def parse_ak_value(value: object) -> float:
    if value is None or pd.isna(value) or value is False:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text or text in {"False", "None", "nan", "--"}:
        return 0.0

    multiplier = 1.0
    if text.endswith("亿"):
        multiplier = YI
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith("元"):
        text = text[:-1]

    return float(text) * multiplier


def to_yi(value: float) -> float:
    return round(value / YI, 2)


def normalize_period(period: str | None) -> str | None:
    if not period:
        return None
    cleaned = str(period).strip().replace("-", "").replace("/", "")
    if len(cleaned) != 8 or not cleaned.isdigit():
        raise ValueError("period 格式应为 YYYYMMDD，例如 20250630")
    return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"


def normalize_years(years: str | None, default: int = 8) -> int:
    if not years:
        return default
    value = int(years)
    if value <= 0:
        raise ValueError("years 必须是正整数")
    return value


def to_em_symbol(stock: str) -> str:
    stock = stock.strip()
    if stock.startswith(("SH", "SZ")):
        return stock.upper()
    if stock.startswith(("60", "68", "90")):
        return f"SH{stock}"
    return f"SZ{stock}"


def finite_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def json_safe_value(value: object) -> object:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    if isinstance(value, (int, str, bool)) or value is None:
        return value
    if pd.isna(value):
        return None
    return str(value)


def dataframe_preview(df: pd.DataFrame, limit: int = 12) -> dict:
    if df is None or df.empty:
        return {"columns": [], "rows": []}
    preview_df = df.tail(limit) if len(df) > limit else df
    rows = [
        {str(key): json_safe_value(value) for key, value in row.items()}
        for row in preview_df.to_dict(orient="records")
    ]
    return {
        "columns": [str(column) for column in df.columns],
        "rows": rows,
        "rowCount": int(len(df)),
    }
