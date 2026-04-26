from __future__ import annotations

import json
from pathlib import Path

import akshare as ak
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ["http://127.0.0.1:3000", "http://localhost:3000"],
        }
    },
)

YI = 100000000
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"

ASSET_MAPPING = {
    "现金": [["货币资金"], ["总现金"]],
    "应收款": [
        ["应收账款", "应收票据", "应收款项融资"],
        ["应收账款", "其中：应收票据", "应收款项融资"],
        ["应收票据及应收账款"],
    ],
    "预付款": [["预付款项"]],
    "存货": [["存货"]],
    "其他流动": [["其他流动资产"]],
    "长期投资": [
        ["长期股权投资", "其他权益工具投资"],
        ["长期股权投资", "其他非流动金融资产"],
        ["长期股权投资"],
    ],
    "固定资产": [["固定资产"], ["其中：固定资产"], ["固定资产合计"]],
    "无形&商誉": [["无形资产", "商誉"], ["无形资产"]],
    "其他固定": [["其他非流动资产"]],
}

LIABILITY_MAPPING = {
    "短期借款": [["短期借款"]],
    "应付款": [
        ["应付账款", "应付票据"],
        ["应付账款", "应付票据及应付账款"],
        ["应付票据及应付账款"],
    ],
    "预收款": [["预收款项", "合同负债"], ["合同负债"], ["预收款项"]],
    "薪酬&税": [["应付职工薪酬", "应交税费"]],
    "其他流动": [["其他流动负债"]],
    "长期借款": [["长期借款"]],
    "其他非流动": [["其他非流动负债"], ["其他非流动负债合计"], ["非流动负债合计"]],
}

REVENUE_CANDIDATES = ["营业总收入", "营业收入", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME"]


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_cache_part(value: object) -> str:
    text = str(value).strip()
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)
    return safe or "default"


def cache_file_path(prefix: str, *parts: object) -> Path:
    filename = "__".join([sanitize_cache_part(prefix), *[sanitize_cache_part(part) for part in parts]])
    return CACHE_DIR / f"{filename}.json"


def load_cached_payload(prefix: str, *parts: object) -> dict | None:
    path = cache_file_path(prefix, *parts)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as cache_file:
        print(f"[INFO] Cache hit: {path.name}")
        return json.load(cache_file)


def save_cached_payload(payload: dict, prefix: str, *parts: object) -> dict:
    ensure_cache_dir()
    path = cache_file_path(prefix, *parts)
    with path.open("w", encoding="utf-8") as cache_file:
        json.dump(payload, cache_file, ensure_ascii=False, indent=2)
    print(f"[INFO] Cache saved: {path.name}")
    return payload


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


def pick_value(row: pd.Series, field_groups: list[list[str]], item_name: str) -> float:
    for group in field_groups:
        matched = [field for field in group if field in row.index]
        if matched:
            total = sum(parse_ak_value(row.get(field)) for field in matched)
            return to_yi(total)

    print(f"[WARN] Balance field not matched for: {item_name}")
    print("[DEBUG] Available columns:")
    print(list(row.index))
    return 0.0


def build_tree_and_bar(row: pd.Series) -> tuple[dict, list[dict]]:
    asset_children = []
    liability_children = []
    bar_data: list[dict] = []

    for label, field_groups in ASSET_MAPPING.items():
        value = pick_value(row, field_groups, label)
        asset_children.append({"name": label, "value": value})
        bar_data.append({"name": label, "value": value, "type": "asset"})

    for label, field_groups in LIABILITY_MAPPING.items():
        value = pick_value(row, field_groups, label)
        liability_children.append({"name": label, "value": value})
        bar_data.append({"name": label, "value": value, "type": "liability"})

    tree_data = {
        "name": "资产负债表",
        "children": [
            {"name": "资产", "children": asset_children},
            {"name": "负债", "children": liability_children},
        ],
    }
    return tree_data, bar_data


def generate_balance_conclusion(bar_data: list[dict]) -> str:
    asset_total = sum(item["value"] for item in bar_data if item["type"] == "asset")
    liability_total = sum(item["value"] for item in bar_data if item["type"] == "liability")
    lookup = {item["name"]: item["value"] for item in bar_data}

    cash_ratio = lookup.get("现金", 0) / asset_total if asset_total else 0
    inventory_ratio = lookup.get("存货", 0) / asset_total if asset_total else 0
    receivable_ratio = lookup.get("应收款", 0) / asset_total if asset_total else 0
    liability_ratio = liability_total / asset_total if asset_total else 0

    if liability_ratio < 0.5 and cash_ratio > 0.25:
        return "财务结构比较健康"
    if inventory_ratio > 0.2 or receivable_ratio > 0.2:
        return "存货/应收压力较大"
    return "资产结构需要继续观察"


def load_balance_sheet(stock: str) -> pd.DataFrame:
    print(f"[INFO] Fetching balance sheet, stock={stock}")
    df = ak.stock_financial_debt_ths(symbol=stock, indicator="按报告期")
    print("[DEBUG] Balance columns:")
    print(df.columns.tolist())
    return df


def get_balance_payload(stock: str, period: str | None) -> dict:
    normalized_period = normalize_period(period)
    df = load_balance_sheet(stock)

    if df is None or df.empty:
        raise ValueError(f"未获取到股票 {stock} 的资产负债表数据")

    df = df.copy()
    df["报告期_dt"] = pd.to_datetime(df["报告期"], errors="coerce")
    df = df.sort_values("报告期_dt", ascending=False)

    if normalized_period:
        df = df[df["报告期"] == normalized_period]
        if df.empty:
            raise ValueError(f"未找到股票 {stock} 在 {normalized_period} 的报告期数据")

    row = df.iloc[0]
    tree_data, bar_data = build_tree_and_bar(row)

    return {
        "stock": stock,
        "title": f"{stock} 资产负债表",
        "reportDate": row["报告期"],
        "unit": "亿元",
        "treeData": tree_data,
        "barData": bar_data,
        "conclusion": generate_balance_conclusion(bar_data),
    }


def load_profit_sheet(stock: str) -> pd.DataFrame:
    em_symbol = to_em_symbol(stock)
    print(f"[INFO] Fetching quarterly profit sheet, symbol={em_symbol}")
    df = ak.stock_profit_sheet_by_quarterly_em(symbol=em_symbol)
    print("[DEBUG] Profit columns:")
    print(df.columns.tolist())
    return df


def load_market_cap(stock: str, years: int) -> pd.DataFrame:
    if years <= 1:
        period = "近一年"
    elif years <= 3:
        period = "近三年"
    elif years <= 5:
        period = "近五年"
    elif years <= 10:
        period = "近十年"
    else:
        period = "全部"

    print(f"[INFO] Fetching valuation, stock={stock}, period={period}")
    df = ak.stock_zh_valuation_baidu(symbol=stock, indicator="总市值", period=period)
    print("[DEBUG] Valuation columns:")
    print(df.columns.tolist())
    return df


def find_revenue_column(df: pd.DataFrame) -> str:
    for column in REVENUE_CANDIDATES:
        if column in df.columns:
            return column

    print("[ERROR] Revenue field not matched, available columns:")
    print(df.columns.tolist())
    raise ValueError("利润表中未找到营业总收入字段，请查看后端打印的 columns")


def build_revenue_bars(df: pd.DataFrame, years: int) -> list[dict]:
    if df is None or df.empty:
        raise ValueError("未获取到利润表数据")

    revenue_column = find_revenue_column(df)
    date_column = "REPORT_DATE" if "REPORT_DATE" in df.columns else "报告期"
    if date_column not in df.columns:
        print("[ERROR] Profit date field not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("利润表中未找到报告期字段，请查看后端打印的 columns")

    revenue_df = df[[date_column, revenue_column]].copy()
    revenue_df["date"] = pd.to_datetime(revenue_df[date_column], errors="coerce")
    revenue_df["value"] = revenue_df[revenue_column].apply(parse_ak_value)
    revenue_df = revenue_df.dropna(subset=["date"]).sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    revenue_df = revenue_df[revenue_df["date"] >= cutoff]
    if revenue_df.empty:
        raise ValueError(f"最近 {years} 年没有可用的营业收入数据")

    return [
        {"date": row.date.strftime("%Y-%m-%d"), "value": to_yi(row.value)}
        for row in revenue_df.itertuples()
    ]


def build_market_cap_line(
    df: pd.DataFrame, years: int, revenue_bars: list[dict]
) -> list[dict]:
    if df is None or df.empty:
        raise ValueError("未获取到总市值数据")

    if "date" not in df.columns or "value" not in df.columns:
        print("[ERROR] Valuation fields not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("总市值数据字段不符合预期，请查看后端打印的 columns")

    line_df = df[["date", "value"]].copy()
    line_df["date"] = pd.to_datetime(line_df["date"], errors="coerce")
    line_df["value"] = pd.to_numeric(line_df["value"], errors="coerce")
    line_df = line_df.dropna(subset=["date", "value"]).sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    line_df = line_df[line_df["date"] >= cutoff]
    if line_df.empty:
        raise ValueError(f"最近 {years} 年没有可用的总市值数据")

    revenue_dates = []
    for item in revenue_bars:
        revenue_date = pd.to_datetime(item["date"], errors="coerce")
        if pd.notna(revenue_date):
            revenue_dates.append(revenue_date.normalize())

    if not revenue_dates:
        raise ValueError("未获取到可用于对齐市值的季度营收日期")

    quarterly_points: list[dict] = []
    for revenue_date in revenue_dates:
        matched = line_df[line_df["date"] <= revenue_date]
        if matched.empty:
            continue

        latest_row = matched.iloc[-1]
        quarterly_points.append(
            {
                "date": revenue_date.strftime("%Y-%m-%d"),
                "value": round(float(latest_row["value"]), 2),
            }
        )

    if not quarterly_points:
        raise ValueError(f"最近 {years} 年没有可用于季度对齐的总市值数据")

    return quarterly_points


def generate_revenue_market_cap_conclusion(
    revenue_bars: list[dict], market_cap_line: list[dict]
) -> str:
    if not revenue_bars or not market_cap_line:
        return "业绩增长和市值走势需要结合观察"

    revenue_growth = revenue_bars[-1]["value"] - revenue_bars[0]["value"]
    market_cap_growth = market_cap_line[-1]["value"] - market_cap_line[0]["value"]

    if revenue_growth > 0 and market_cap_growth <= 0:
        return "如果业绩增长但市值不涨，可能是估值压缩"
    if revenue_growth > 0 and market_cap_growth > revenue_growth:
        return "如果市值涨得比业绩快，可能是估值扩张"
    return "业绩增长和市值走势需要结合观察"


def get_revenue_market_cap_payload(stock: str, years: int) -> dict:
    revenue_bars = build_revenue_bars(load_profit_sheet(stock), years)
    market_cap_line = build_market_cap_line(load_market_cap(stock, years), years, revenue_bars)

    return {
        "stock": stock,
        "title": f"{stock} 市值与业绩增长趋势",
        "unit": "亿元",
        "leftAxisName": "营业总收入",
        "rightAxisName": "总市值",
        "revenueBars": revenue_bars,
        "marketCapLine": market_cap_line,
        "conclusion": generate_revenue_market_cap_conclusion(revenue_bars, market_cap_line),
    }

def valuation_period_from_years(years: int) -> str:
    if years <= 1:
        return "近一年"
    if years <= 3:
        return "近三年"
    if years <= 5:
        return "近五年"
    if years <= 10:
        return "近十年"
    return "全部"


def load_pe_ttm(stock: str, years: int) -> pd.DataFrame:
    period = valuation_period_from_years(years)
    print(f"[INFO] Fetching PE TTM, stock={stock}, period={period}")

    df = ak.stock_zh_valuation_baidu(
        symbol=stock,
        indicator="市盈率(TTM)",
        period=period,
    )

    print("[DEBUG] PE columns:")
    print(df.columns.tolist())
    return df


def build_pe_trend_payload(stock: str, years: int) -> dict:
    df = load_pe_ttm(stock, years)

    if df is None or df.empty:
        raise ValueError("未获取到市盈率数据")

    if "date" not in df.columns or "value" not in df.columns:
        print("[ERROR] PE fields not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("市盈率数据字段不符合预期，请查看后端打印的 columns")

    pe_df = df[["date", "value"]].copy()
    pe_df["date"] = pd.to_datetime(pe_df["date"], errors="coerce")
    pe_df["value"] = pd.to_numeric(pe_df["value"], errors="coerce")

    # 过滤空值和异常值；市盈率小于等于 0 一般不适合直接画估值区间
    pe_df = pe_df.dropna(subset=["date", "value"])
    pe_df = pe_df[pe_df["value"] > 0]
    pe_df = pe_df.sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    pe_df = pe_df[pe_df["date"] >= cutoff]

    if pe_df.empty:
        raise ValueError(f"最近 {years} 年没有可用的市盈率数据")

    mean_line = round(float(pe_df["value"].mean()), 2)

    # 最像你截图的方式：均值线上下各 1 个标准差
    std_value = float(pe_df["value"].std())
    low_line = round(max(0, mean_line - std_value), 2)
    high_line = round(mean_line + std_value, 2)

    pe_line = [
        {
            "date": row.date.strftime("%Y-%m-%d"),
            "value": round(float(row.value), 2),
        }
        for row in pe_df.itertuples()
    ]

    latest_pe = pe_line[-1]["value"]
    if latest_pe <= low_line:
        conclusion = "当前市盈率接近低估区间"
    elif latest_pe >= high_line:
        conclusion = "当前市盈率接近高估区间"
    else:
        conclusion = "当前市盈率处于正常估值区间"

    return {
        "stock": stock,
        "title": f"{stock} 市盈率趋势",
        "unit": "倍",
        "peLine": pe_line,
        "meanLine": mean_line,
        "lowLine": low_line,
        "highLine": high_line,
        "conclusion": conclusion,
    }


@app.get("/api/pe-trend")
def api_pe_trend():
    stock = request.args.get("stock", "000333").strip() or "000333"
    years_param = request.args.get("years", "8")
    refresh = request.args.get("refresh") == "1"

    try:
        years = normalize_years(years_param, default=8)

        if not refresh:
            cached_payload = load_cached_payload("pe_trend_v1", stock, years)
            if cached_payload is not None:
                return jsonify(cached_payload)

        payload = build_pe_trend_payload(stock=stock, years=years)
        save_cached_payload(payload, "pe_trend_v1", stock, years)
        return jsonify(payload)

    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "years": years_param}), 400


@app.get("/api/balance")
def api_balance():
    stock = request.args.get("stock", "600519").strip() or "600519"
    period = request.args.get("period")

    try:
        normalized_period = normalize_period(period)
        cached_payload = load_cached_payload("balance", stock, normalized_period or "latest")
        if cached_payload is not None:
            return jsonify(cached_payload)

        payload = get_balance_payload(stock=stock, period=period)
        save_cached_payload(payload, "balance", stock, normalized_period or "latest")
        return jsonify(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "period": period}), 400


@app.get("/api/revenue-market-cap")
def api_revenue_market_cap():
    stock = request.args.get("stock", "000333").strip() or "000333"
    years_param = request.args.get("years", "8")

    try:
        years = normalize_years(years_param, default=8)
        cached_payload = load_cached_payload("revenue_market_cap_v2", stock, years)
        if cached_payload is not None:
            return jsonify(cached_payload)

        payload = get_revenue_market_cap_payload(stock=stock, years=years)
        save_cached_payload(payload, "revenue_market_cap_v2", stock, years)
        return jsonify(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "years": years_param}), 400


@app.get("/")
def health_message():
    return jsonify(
        {
            "message": "Flask API is running. Use the Next frontend for the UI.",
            "balanceApi": "/api/balance?stock=600519",
            "trendApi": "/api/revenue-market-cap?stock=000333&years=8",
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5001)
