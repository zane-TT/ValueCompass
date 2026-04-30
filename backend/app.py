from __future__ import annotations

import json
import math
import os
import re
import sys
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import akshare as ak
import akshare.stock_feature.stock_disclosure_cninfo as disclosure_cninfo
import httpx
import pandas as pd
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv

try:
    from pypdf import PdfReader
except ImportError:
    bundled_python_packages = r"C:\Users\1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages"
    if bundled_python_packages not in sys.path:
        sys.path.append(bundled_python_packages)
    from pypdf import PdfReader

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
load_dotenv(BASE_DIR / ".env")
DEFAULT_OPENAI_BASE_URL = "https://api.openai-proxy.org/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.4-nano-2026-03-17"
DEFAULT_OPENAI_TEMPERATURE = 0.1

AI_ANALYSIS_SYSTEM_PROMPT = """
你是一名A股财报分析助手。

请基于给定的结构化数据，用简洁、专业、偏业务解读的中文输出分析结论。
要求：
1. 不要编造不存在的数据。
2. 先给一段总评，再给3条要点。
3. 重点结合资产负债结构、营收与市值趋势、净利润与市值趋势、市盈率区间。
4. 语言尽量让非财务背景的产品经理也能看懂。
5. 不要写投资建议，不要承诺收益。
""".strip()

BUSINESS_TYPE_SYSTEM_PROMPT = """
你是一名专业的上市公司商业模式分析师。

任务：
请根据提供的公司年报、财报数据、主营业务说明，以及结构化财务趋势数据，判断这家公司属于什么类型的公司。

重要要求：
1. 不要只根据行业名称判断。
2. 不要只根据关键词判断。
3. 必须根据以下证据判断：
   - 收入主要来自哪里
   - 利润主要来自哪里
   - 收入增长主要来自哪里
   - 成本结构是什么
   - 资产结构是什么
   - 现金流特征是什么
4. 如果信息不足，必须说明“无法确定”，不要编造。
5. 所有判断都要给出依据。
6. 最终输出 JSON，且只能输出 JSON。

额外判断约束：
1. 不要因为公司有“生产、制造、包装”等环节，就直接判为“成本制造型”。
2. 如果收入主要来自产品销售，同时毛利率高且稳定、利润集中于核心品牌产品、公司概况或主营构成显示品牌/渠道/定价权重要，应优先判为“品牌产品型”。
3. “成本制造型”更适用于毛利率不高，核心竞争力主要来自规模、成本控制、产能效率，而不是品牌溢价。
4. 如果证据同时支持“品牌产品型”和“成本制造型”，要明确比较毛利率、利润集中度、品牌表述和资产结构后再判断，不能偷懒。

判断标准：

品牌产品型：
收入主要来自产品销售，毛利率高且稳定，核心竞争力来自品牌、渠道、定价权。

成本制造型：
收入主要来自产品销售，但毛利率不高，核心竞争力来自规模、成本控制、产能效率。

技术产品型：
收入来自技术产品、设备、软件或高技术制造，研发投入较高，技术壁垒重要。

履约服务型：
收入来自服务交付，比如物流、餐饮、酒店、配送、运维，利润受人工、履约成本影响较大。

平台撮合型：
收入来自佣金、广告、平台服务费、交易撮合，核心看 GMV、用户数、商家数、抽佣率。

订阅服务型：
收入来自会员费、SaaS 订阅、长期服务合同，核心看续费率、客户留存、ARPU。

项目交付型：
收入来自工程、地产、软件定制、大项目交付，核心看合同、完工进度、应收账款、现金流。

资产运营型：
收入来自固定资产或稀缺资产运营，比如高速、机场、港口、电力、水务、租赁，核心看资产收益率和现金流稳定性。

金融利差型：
收入来自利息收入、金融资产收益、资金成本差，核心看净息差、不良率、拨备、资本充足率。

资源周期型：
收入和利润受商品价格周期影响，比如煤炭、有色、石油、钢铁、化工周期品。

混合型：
如果公司有两个以上重要业务，且收入或利润占比都较大，请判断为混合型，并说明各业务占比
""".strip()

PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]

BUSINESS_EXPLANATION_RULES = [
    {
        "keywords": ["集装箱航运", "航运业务", "班轮"],
        "businessDescription": "核心是为客户提供集装箱海运运输服务，收入通常来自不同航线的运价、舱位利用率和附加费。",
        "priceDrivers": ["全球贸易需求", "航线运价", "船舶运力供给", "港口拥堵", "燃油成本", "汇率"],
    },
    {
        "keywords": ["码头业务", "港口", "码头"],
        "businessDescription": "核心是港口装卸、堆存和中转服务，收入通常和吞吐量、航线网络覆盖以及港口费率相关。",
        "priceDrivers": ["港口吞吐量", "区域贸易活跃度", "收费标准", "枢纽港地位", "人工与能耗成本"],
    },
    {
        "keywords": ["茅台酒", "白酒", "系列酒"],
        "businessDescription": "核心是酒类产品销售，收入通常来自出厂价、渠道结构、销量和高端产品占比。",
        "priceDrivers": ["终端需求", "品牌力", "渠道结构", "出厂价调整", "产品结构升级", "政策环境"],
    },
    {
        "keywords": ["家用空调", "消费电器", "冰箱", "洗衣机", "厨电"],
        "businessDescription": "核心是耐用消费品销售，收入通常来自销量、ASP、渠道折扣和新品迭代。",
        "priceDrivers": ["终端消费需求", "原材料价格", "渠道去库存", "以旧换新政策", "产品升级"],
    },
    {
        "keywords": ["软件", "SaaS", "云服务"],
        "businessDescription": "核心是软件许可或持续订阅服务，收入通常来自客户数、续费率和客单价。",
        "priceDrivers": ["客户扩张", "续费率", "ARPU", "产品迭代能力", "行业数字化投入"],
    },
]

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

NET_PROFIT_CANDIDATES = [
    "归属于母公司所有者的净利润",
    "归属于母公司股东的净利润",
    "归母净利润",
    "净利润",
    "PARENT_NETPROFIT",
    "NETPROFIT_PARENT_COMPANY_OWNERS",
    "NETPROFIT",
]


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


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

    try:
        with path.open("r", encoding="utf-8") as cache_file:
            print(f"[INFO] Cache hit: {path.name}")
            return json.load(cache_file)
    except json.JSONDecodeError:
        print(f"[WARN] Cache corrupted, rebuilding: {path.name}")
        path.unlink(missing_ok=True)
        return None


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
    with temporary_disable_proxy_env():
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
    with temporary_disable_proxy_env():
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
    with temporary_disable_proxy_env():
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


def find_net_profit_column(df: pd.DataFrame) -> str:
    for column in NET_PROFIT_CANDIDATES:
        if column in df.columns:
            return column

    print("[ERROR] Net profit field not matched, available columns:")
    print(df.columns.tolist())
    raise ValueError("利润表中未找到净利润字段，请查看后端打印的 columns")


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


def build_profit_bars(df: pd.DataFrame, years: int) -> list[dict]:
    if df is None or df.empty:
        raise ValueError("未获取到利润表数据")

    profit_column = find_net_profit_column(df)
    date_column = "REPORT_DATE" if "REPORT_DATE" in df.columns else "报告期"
    if date_column not in df.columns:
        print("[ERROR] Profit date field not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("利润表中未找到报告期字段，请查看后端打印的 columns")

    profit_df = df[[date_column, profit_column]].copy()
    profit_df["date"] = pd.to_datetime(profit_df[date_column], errors="coerce")
    profit_df["value"] = profit_df[profit_column].apply(parse_ak_value)
    profit_df = profit_df.dropna(subset=["date"]).sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    profit_df = profit_df[profit_df["date"] >= cutoff]
    if profit_df.empty:
        raise ValueError(f"最近 {years} 年没有可用的净利润数据")

    return [
        {"date": row.date.strftime("%Y-%m-%d"), "value": to_yi(row.value)}
        for row in profit_df.itertuples()
    ]


def build_market_cap_line(df: pd.DataFrame, years: int, report_points: list[dict]) -> list[dict]:
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

    report_dates = []
    for item in report_points:
        report_date = pd.to_datetime(item["date"], errors="coerce")
        if pd.notna(report_date):
            report_dates.append(report_date.normalize())

    if not report_dates:
        raise ValueError("未获取到可用于对齐市值的报告期日期")

    quarterly_points: list[dict] = []
    for report_date in report_dates:
        matched = line_df[line_df["date"] <= report_date]
        if matched.empty:
            continue

        latest_row = matched.iloc[-1]
        quarterly_points.append(
            {
                "date": report_date.strftime("%Y-%m-%d"),
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


def generate_profit_market_cap_conclusion(
    profit_bars: list[dict], market_cap_line: list[dict]
) -> str:
    if not profit_bars or not market_cap_line:
        return "净利润和市值走势需要结合观察"

    profit_growth = profit_bars[-1]["value"] - profit_bars[0]["value"]
    market_cap_growth = market_cap_line[-1]["value"] - market_cap_line[0]["value"]

    if profit_growth > 0 and market_cap_growth <= 0:
        return "如果净利润增长但市值不涨，可能是估值压缩"
    if profit_growth <= 0 and market_cap_growth > 0:
        return "如果净利润下降但市值上涨，可能是市场在提前交易预期"
    if profit_growth > 0 and market_cap_growth > profit_growth:
        return "如果市值涨得比净利润快，可能是估值扩张"
    return "净利润和市值走势需要结合观察"


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


def get_profit_market_cap_payload(stock: str, years: int) -> dict:
    profit_bars = build_profit_bars(load_profit_sheet(stock), years)
    market_cap_line = build_market_cap_line(load_market_cap(stock, years), years, profit_bars)

    return {
        "stock": stock,
        "title": f"{stock} 净利润与市值对比",
        "unit": "亿元",
        "leftAxisName": "归母净利润",
        "rightAxisName": "总市值",
        "profitBars": profit_bars,
        "marketCapLine": market_cap_line,
        "conclusion": generate_profit_market_cap_conclusion(profit_bars, market_cap_line),
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

    with temporary_disable_proxy_env():
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

    # 保持你当前逻辑：只展示正市盈率。
    pe_df = pe_df.dropna(subset=["date", "value"])
    pe_df = pe_df[pe_df["value"] > 0]
    pe_df = pe_df.sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    pe_df = pe_df[pe_df["date"] >= cutoff]

    if pe_df.empty:
        raise ValueError(f"最近 {years} 年没有可用的市盈率数据")

    mean_line = round(float(pe_df["value"].mean()), 2)

    # 保持你当前逻辑：均值线上下各 1 个标准差。
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


def get_balance_payload_with_cache(stock: str, period: str | None) -> dict:
    normalized_period = normalize_period(period)
    cached_payload = load_cached_payload("balance", stock, normalized_period or "latest")
    if cached_payload is not None:
        return cached_payload

    payload = get_balance_payload(stock=stock, period=period)
    save_cached_payload(payload, "balance", stock, normalized_period or "latest")
    return payload


def get_revenue_market_cap_payload_with_cache(stock: str, years: int) -> dict:
    cached_payload = load_cached_payload("revenue_market_cap_v2", stock, years)
    if cached_payload is not None:
        return cached_payload

    payload = get_revenue_market_cap_payload(stock=stock, years=years)
    save_cached_payload(payload, "revenue_market_cap_v2", stock, years)
    return payload


def get_profit_market_cap_payload_with_cache(stock: str, years: int) -> dict:
    cached_payload = load_cached_payload("profit_market_cap_v1", stock, years)
    if cached_payload is not None:
        return cached_payload

    payload = get_profit_market_cap_payload(stock=stock, years=years)
    save_cached_payload(payload, "profit_market_cap_v1", stock, years)
    return payload


def get_pe_trend_payload_with_cache(stock: str, years: int) -> dict:
    cached_payload = load_cached_payload("pe_trend_v1", stock, years)
    if cached_payload is not None:
        return cached_payload

    payload = build_pe_trend_payload(stock=stock, years=years)
    save_cached_payload(payload, "pe_trend_v1", stock, years)
    return payload


def load_company_profile(stock: str) -> pd.DataFrame:
    print(f"[INFO] Fetching company profile, stock={stock}")
    with temporary_disable_proxy_env():
        df = ak.stock_profile_cninfo(symbol=stock)
    print("[DEBUG] Company profile columns:")
    print(df.columns.tolist())
    return df


def load_main_business_composition(stock: str) -> pd.DataFrame:
    symbol = to_em_symbol(stock)
    print(f"[INFO] Fetching main business composition, symbol={symbol}")
    with temporary_disable_proxy_env():
        df = ak.stock_zygc_em(symbol=symbol)
    print("[DEBUG] Main business columns:")
    print(df.columns.tolist())
    return df


def get_company_profile_payload_with_cache(stock: str) -> dict:
    cached_payload = load_cached_payload("company_profile_v1", stock)
    if cached_payload is not None:
        return cached_payload

    df = load_company_profile(stock)
    if df is None or df.empty:
        raise ValueError(f"Unable to fetch company profile for stock {stock}.")

    row = df.iloc[0]
    payload = {
        "stock": stock,
        "companyName": row.get("公司名称", ""),
        "industry": row.get("所属行业", ""),
        "mainBusiness": row.get("主营业务", ""),
        "businessScope": row.get("经营范围", ""),
        "companyIntro": row.get("机构简介", ""),
    }
    save_cached_payload(payload, "company_profile_v1", stock)
    return payload


def get_main_business_payload_with_cache(stock: str) -> dict:
    cached_payload = load_cached_payload("main_business_v1", stock)
    if cached_payload is not None:
        return cached_payload

    df = load_main_business_composition(stock)
    if df is None or df.empty:
        raise ValueError(f"Unable to fetch main business composition for stock {stock}.")

    df = df.copy()
    if "报告日期" in df.columns:
        df["报告日期_dt"] = pd.to_datetime(df["报告日期"], errors="coerce")
        latest_date = df["报告日期_dt"].max()
        if pd.notna(latest_date):
            df = df[df["报告日期_dt"] == latest_date]

    summary_items = []
    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        summary_items.append(
            {
                "reportDate": str(row_dict.get("报告日期") or ""),
                "categoryType": row_dict.get("分类类型"),
                "itemName": row_dict.get("主营构成"),
                "revenue": to_yi(parse_ak_value(row_dict.get("主营收入"))),
                "revenueRatio": round(float(row_dict.get("收入比例", 0) or 0), 4),
                "cost": to_yi(parse_ak_value(row_dict.get("主营成本"))),
                "costRatio": round(float(row_dict.get("成本比例", 0) or 0), 4),
                "profit": to_yi(parse_ak_value(row_dict.get("主营利润"))),
                "profitRatio": round(float(row_dict.get("利润比例", 0) or 0), 4),
                "grossMargin": round(float(row_dict.get("毛利率", 0) or 0), 4),
            }
        )

    payload = {
        "stock": stock,
        "items": summary_items,
    }
    save_cached_payload(payload, "main_business_v1", stock)
    return payload


def is_supplementary_item(item_name: str) -> bool:
    normalized_name = (item_name or "").strip()
    return not normalized_name or "其他" in normalized_name or "补充" in normalized_name


def filter_business_items(items: list[dict], category_type: str) -> list[dict]:
    filtered_items = [
        sanitize_business_item(item)
        for item in items
        if item.get("categoryType") == category_type and not is_supplementary_item(item.get("itemName", ""))
    ]
    return sorted(filtered_items, key=lambda item: item.get("revenue") or 0, reverse=True)


def build_dominance_summary(items: list[dict]) -> dict | None:
    if not items:
        return None

    leader = items[0]
    ratio = float(leader.get("revenueRatio", 0) or 0)
    return {
        "itemName": leader.get("itemName", ""),
        "revenue": leader.get("revenue", 0),
        "revenueRatio": round(ratio, 4),
        "isHighlyConcentrated": ratio >= 0.6,
    }


def build_margin_summary(items: list[dict]) -> dict | None:
    if not items:
        return None

    finite_items = [item for item in items if item.get("grossMargin") is not None]
    if not finite_items:
        return None

    sorted_items = sorted(finite_items, key=lambda item: item.get("grossMargin") or 0, reverse=True)
    leader = sorted_items[0]
    return {
        "itemName": leader.get("itemName", ""),
        "grossMargin": round(float(leader.get("grossMargin", 0) or 0), 4),
        "revenue": leader.get("revenue", 0),
        "revenueRatio": round(float(leader.get("revenueRatio", 0) or 0), 4),
    }


def parse_percentage_value(raw_value: str) -> float:
    cleaned = (raw_value or "").replace(",", "").replace("%", "").strip()
    if not cleaned:
        return 0.0
    return float(cleaned) / 100


def sanitize_numeric(value: object) -> float | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def sanitize_business_item(item: dict) -> dict:
    sanitized = dict(item)
    numeric_fields = [
        "revenue",
        "revenueRatio",
        "cost",
        "costRatio",
        "profit",
        "profitRatio",
        "grossMargin",
        "revenueGrowth",
        "costGrowth",
    ]
    for field in numeric_fields:
        if field in sanitized:
            sanitized[field] = sanitize_numeric(sanitized.get(field))
    return sanitized


def infer_business_explanation(
    item_name: str,
    company_main_business: str,
    industry: str,
) -> dict:
    search_text = " ".join([item_name or "", company_main_business or "", industry or ""])
    for rule in BUSINESS_EXPLANATION_RULES:
        if any(keyword in search_text for keyword in rule["keywords"]):
            return {
                "businessDescription": rule["businessDescription"],
                "priceDrivers": rule["priceDrivers"],
            }

    return {
        "businessDescription": "这是公司主营业务中的一个收入单元，建议结合年报里的业务模式、客户结构和成本结构一起看。",
        "priceDrivers": ["行业供需", "产品或服务定价", "销量", "成本变化", "竞争格局"],
    }


def enrich_business_items(
    items: list[dict],
    company_main_business: str,
    industry: str,
) -> list[dict]:
    enriched_items: list[dict] = []
    for item in items:
        enriched_item = dict(item)
        enriched_item.update(
            infer_business_explanation(
                item_name=str(item.get("itemName", "")),
                company_main_business=company_main_business,
                industry=industry,
            )
        )
        enriched_items.append(enriched_item)
    return enriched_items


def extract_sales_mode_breakdown(report_text: str) -> list[dict]:
    if not report_text:
        return []

    start_markers = ["主营业务分销售模式情况", "主营业务分销售模式"]
    end_markers = ["产销量情况分析表", "重大采购合同", "成本分析表", "主要销售客户及主要供应商情况"]
    row_pattern = re.compile(
        r"^(?P<name>[A-Za-z\u4e00-\u9fff（）()·\-]+)\s+"
        r"(?P<revenue>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<cost>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<gross_margin>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<revenue_growth>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<cost_growth>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<margin_change>.+)$"
    )

    started = False
    items: list[dict] = []
    for raw_line in report_text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue

        if not started and any(marker in line for marker in start_markers):
            started = True
            continue

        if not started:
            continue

        if any(marker in line for marker in end_markers):
            break

        match = row_pattern.match(line)
        if not match:
            continue

        item_name = match.group("name")
        if is_supplementary_item(item_name):
            continue

        items.append(
            sanitize_business_item(
                {
                    "itemName": item_name,
                    "revenue": to_yi(parse_ak_value(match.group("revenue"))),
                    "cost": to_yi(parse_ak_value(match.group("cost"))),
                    "grossMargin": round(parse_percentage_value(match.group("gross_margin")), 4),
                    "revenueGrowth": round(parse_percentage_value(match.group("revenue_growth")), 4),
                    "costGrowth": round(parse_percentage_value(match.group("cost_growth")), 4),
                    "grossMarginChangeText": match.group("margin_change").strip(),
                }
            )
        )

    total_revenue = sum((item.get("revenue") or 0) for item in items)
    for item in items:
        revenue = item.get("revenue") or 0
        item["revenueRatio"] = round(revenue / total_revenue, 4) if total_revenue else 0.0

    return sorted(items, key=lambda item: item.get("revenue") or 0, reverse=True)


def find_bar_item(bar_data: list[dict], item_name: str) -> dict | None:
    for item in bar_data:
        if item.get("name") == item_name:
            return item
    return None


def build_revenue_insight_points(
    product_items: list[dict],
    region_items: list[dict],
    channel_items: list[dict],
    contract_liability_item: dict | None,
) -> list[str]:
    insights: list[str] = []

    product_dominance = build_dominance_summary(product_items)
    if product_dominance:
        ratio = product_dominance["revenueRatio"] * 100
        if product_dominance["isHighlyConcentrated"]:
            insights.append(f"收入高度集中在{product_dominance['itemName']}，收入占比约{ratio:.1f}%。")
        else:
            insights.append(f"当前第一大产品是{product_dominance['itemName']}，收入占比约{ratio:.1f}%。")

    product_margin = build_margin_summary(product_items)
    if product_margin:
        insights.append(
            f"{product_margin['itemName']}毛利率约{product_margin['grossMargin'] * 100:.1f}%，是最值得优先跟踪的盈利单元。"
        )

    region_dominance = build_dominance_summary(region_items)
    if region_dominance:
        ratio = region_dominance["revenueRatio"] * 100
        insights.append(f"{region_dominance['itemName']}市场贡献收入约{ratio:.1f}%，区域结构较为清晰。")

    if len(channel_items) >= 2:
        direct_items = [item for item in channel_items if "直销" in item.get("itemName", "")]
        wholesale_items = [
            item
            for item in channel_items
            if "批发" in item.get("itemName", "") or "代理" in item.get("itemName", "")
        ]
        if direct_items and wholesale_items:
            direct_item = direct_items[0]
            wholesale_item = wholesale_items[0]
            if direct_item["grossMargin"] > wholesale_item["grossMargin"]:
                insights.append(
                    f"直销毛利率高于批发代理，说明渠道利润回流对盈利质量有明显帮助。"
                )
            if direct_item["revenueGrowth"] > wholesale_item["revenueGrowth"]:
                insights.append(
                    f"直销增速快于批发代理，说明公司在主动强化自营或数字化渠道。"
                )

    if contract_liability_item and contract_liability_item.get("value", 0) > 0:
        insights.append(
            f"预收/合同负债约{contract_liability_item['value']}亿元，可作为客户预付款意愿的辅助观察指标。"
        )

    return insights


def get_revenue_structure_payload(stock: str, years: int = 8) -> dict:
    profile_payload = get_company_profile_payload_with_cache(stock=stock)
    main_business_payload = get_main_business_payload_with_cache(stock=stock)
    annual_report_payload = get_latest_report_text_payload_v2(stock=stock, category="年报", cache_key="annual_report_v1")
    balance_payload = get_balance_payload_with_cache(stock=stock, period=None)
    revenue_market_cap_payload = get_revenue_market_cap_payload_with_cache(stock=stock, years=years)

    items = main_business_payload.get("items", [])
    company_main_business = str(profile_payload.get("mainBusiness", ""))
    industry = str(profile_payload.get("industry", ""))

    product_items = enrich_business_items(
        filter_business_items(items, "按产品分类"),
        company_main_business=company_main_business,
        industry=industry,
    )
    region_items = enrich_business_items(
        filter_business_items(items, "按地区分类"),
        company_main_business=company_main_business,
        industry=industry,
    )
    industry_items = enrich_business_items(
        filter_business_items(items, "按行业分类"),
        company_main_business=company_main_business,
        industry=industry,
    )
    channel_items = enrich_business_items(
        extract_sales_mode_breakdown(annual_report_payload.get("textExcerpt", "")),
        company_main_business=company_main_business,
        industry=industry,
    )
    contract_liability_item = find_bar_item(balance_payload.get("barData", []), "预收款")

    insight_points = build_revenue_insight_points(
        product_items=product_items,
        region_items=region_items,
        channel_items=channel_items,
        contract_liability_item=contract_liability_item,
    )

    payload = {
        "stock": stock,
        "companyName": profile_payload.get("companyName", ""),
        "industry": profile_payload.get("industry", ""),
        "reportDate": annual_report_payload.get("date", ""),
        "analysisDimensionCoverage": {
            "product": bool(product_items),
            "region": bool(region_items),
            "channel": bool(channel_items),
            "industry": bool(industry_items),
            "contractLiability": contract_liability_item is not None,
        },
        "businessSummary": {
            "mainBusiness": profile_payload.get("mainBusiness", ""),
            "companyIntro": profile_payload.get("companyIntro", ""),
            "trendConclusion": revenue_market_cap_payload.get("conclusion", ""),
        },
        "breakdowns": {
            "byProduct": product_items,
            "byRegion": region_items,
            "byChannel": channel_items,
            "byIndustry": industry_items,
        },
        "highlights": {
            "topProduct": build_dominance_summary(product_items),
            "topRegion": build_dominance_summary(region_items),
            "topChannel": build_dominance_summary(channel_items),
            "bestGrossMarginProduct": build_margin_summary(product_items),
            "bestGrossMarginChannel": build_margin_summary(channel_items),
            "contractLiability": contract_liability_item,
        },
        "insightPoints": insight_points,
        "sourceDocuments": {
            "annualReportTitle": annual_report_payload.get("title", ""),
            "annualReportPdfUrl": annual_report_payload.get("pdfUrl", ""),
        },
    }
    return payload


def load_disclosure_reports(stock: str, category: str, start_date: str = "20200101", end_date: str = "20300101") -> pd.DataFrame:
    print(f"[INFO] Fetching disclosure reports, stock={stock}, category={category}")
    with temporary_disable_proxy_env():
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=stock,
            category=category,
            start_date=start_date,
            end_date=end_date,
        )
    print("[DEBUG] Disclosure report columns:")
    print(df.columns.tolist())
    return df


def fetch_pdf_text_from_cninfo(adjunct_url: str, max_pages: int = 15, max_chars: int = 20000) -> str:
    if not adjunct_url:
        return ""

    pdf_url = adjunct_url
    if not pdf_url.startswith("http"):
        pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}"

    with temporary_disable_proxy_env():
        response = requests.get(pdf_url, timeout=60, proxies={"http": None, "https": None})
        response.raise_for_status()

    reader = PdfReader(BytesIO(response.content))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            parts.append(text)
        if sum(len(item) for item in parts) >= max_chars:
            break

    combined_text = "\n".join(parts).strip()
    return combined_text[:max_chars]


def get_latest_report_text_payload_with_cache(stock: str, category: str, cache_key: str) -> dict:
    cached_payload = load_cached_payload(cache_key, stock)
    if cached_payload is not None:
        return cached_payload

    df = load_disclosure_reports(stock=stock, category=category)
    if df is None or df.empty:
        payload = {"stock": stock, "category": category, "title": "", "date": "", "pdfUrl": "", "textExcerpt": ""}
        save_cached_payload(payload, cache_key, stock)
        return payload

    df = df.copy()
    df["公告时间_dt"] = pd.to_datetime(df["公告时间"], errors="coerce")
    df = df.sort_values("公告时间_dt", ascending=False)
    latest_row = df.iloc[0]

    # Rebuild raw payload to get adjunctUrl / PDF path.
    with temporary_disable_proxy_env():
        report_df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=stock,
            category=category,
            start_date="20200101",
            end_date="20300101",
        )

    # Call raw endpoint directly for PDF path because AKShare output hides adjunctUrl.
    with temporary_disable_proxy_env():
        import akshare as _ak
        stock_json = _ak.stock_feature.stock_disclosure_cninfo.__get_stock_json("沪深京")
        category_dict = _ak.stock_feature.stock_disclosure_cninfo.__get_category_dict()
        payload = {
            "pageNum": "1",
            "pageSize": "30",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{stock},{stock_json[stock]}",
            "searchkey": "",
            "secid": "",
            "category": f"{category_dict[category]}",
            "trade": "",
            "seDate": "2020-01-01~2030-01-01",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        raw_response = requests.post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data=payload,
            timeout=60,
            proxies={"http": None, "https": None},
        )
        raw_response.raise_for_status()
        raw_json = raw_response.json()

    selected_item = None
    for item in raw_json.get("announcements", []):
        announcement_title = item.get("announcementTitle", "")
        if announcement_title == latest_row["公告标题"]:
            selected_item = item
            break

    adjunct_url = selected_item.get("adjunctUrl", "") if selected_item else ""
    pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}" if adjunct_url else ""
    text_excerpt = fetch_pdf_text_from_cninfo(adjunct_url) if adjunct_url else ""

    payload = {
        "stock": stock,
        "category": category,
        "title": latest_row["公告标题"],
        "date": str(latest_row["公告时间"]),
        "pdfUrl": pdf_url,
        "textExcerpt": text_excerpt,
    }
    save_cached_payload(payload, cache_key, stock)
    return payload


def get_latest_report_text_payload_v2(stock: str, category: str, cache_key: str) -> dict:
    cached_payload = load_cached_payload(cache_key, stock)
    if cached_payload is not None:
        return cached_payload

    df = load_disclosure_reports(stock=stock, category=category)
    if df is None or df.empty:
        payload = {"stock": stock, "category": category, "title": "", "date": "", "pdfUrl": "", "textExcerpt": ""}
        save_cached_payload(payload, cache_key, stock)
        return payload

    df = df.copy()
    df["公告时间_dt"] = pd.to_datetime(df["公告时间"], errors="coerce")
    df = df.sort_values("公告时间_dt", ascending=False)
    latest_row = df.iloc[0]

    with temporary_disable_proxy_env():
        stock_json = disclosure_cninfo.__get_stock_json("沪深京")
        category_dict = disclosure_cninfo.__get_category_dict()
        query_payload = {
            "pageNum": "1",
            "pageSize": "30",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{stock},{stock_json[stock]}",
            "searchkey": "",
            "secid": "",
            "category": f"{category_dict[category]}",
            "trade": "",
            "seDate": "2020-01-01~2030-01-01",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        raw_response = requests.post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data=query_payload,
            timeout=60,
            proxies={"http": None, "https": None},
        )
        raw_response.raise_for_status()
        raw_json = raw_response.json()

    selected_item = None
    for item in raw_json.get("announcements", []):
        if item.get("announcementTitle", "") == latest_row["公告标题"]:
            selected_item = item
            break

    adjunct_url = selected_item.get("adjunctUrl", "") if selected_item else ""
    pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}" if adjunct_url else ""
    text_excerpt = fetch_pdf_text_from_cninfo(adjunct_url) if adjunct_url else ""

    payload = {
        "stock": stock,
        "category": category,
        "title": latest_row["公告标题"],
        "date": str(latest_row["公告时间"]),
        "pdfUrl": pdf_url,
        "textExcerpt": text_excerpt,
    }
    save_cached_payload(payload, cache_key, stock)
    return payload


def top_bar_items(items: list[dict], item_type: str, limit: int = 4) -> list[dict]:
    filtered_items = [item for item in items if item.get("type") == item_type]
    sorted_items = sorted(filtered_items, key=lambda item: item.get("value", 0), reverse=True)
    return [{"name": item["name"], "value": item["value"]} for item in sorted_items[:limit]]


def sample_series_points(items: list[dict], max_points: int = 6) -> list[dict]:
    if len(items) <= max_points:
        return items

    sampled: list[dict] = []
    step = max(1, len(items) // max_points)
    for index in range(0, len(items), step):
        sampled.append(items[index])
        if len(sampled) >= max_points - 1:
            break

    sampled.append(items[-1])
    return sampled


def build_ai_analysis_context(stock: str, period: str | None, years: int) -> dict:
    balance_payload = get_balance_payload_with_cache(stock=stock, period=period)
    revenue_payload = get_revenue_market_cap_payload_with_cache(stock=stock, years=years)
    profit_payload = get_profit_market_cap_payload_with_cache(stock=stock, years=years)
    pe_payload = get_pe_trend_payload_with_cache(stock=stock, years=years)
    profile_payload = get_company_profile_payload_with_cache(stock=stock)
    main_business_payload = get_main_business_payload_with_cache(stock=stock)
    annual_report_payload = get_latest_report_text_payload_v2(stock=stock, category="年报", cache_key="annual_report_v1")
    semiannual_report_payload = get_latest_report_text_payload_v2(stock=stock, category="半年报", cache_key="semiannual_report_v1")

    return {
        "stock": stock,
        "period": period or "latest",
        "years": years,
        "unit": "亿元",
        "companyProfile": profile_payload,
        "mainBusinessComposition": main_business_payload.get("items", []),
        "latestAnnualReport": annual_report_payload,
        "latestSemiannualReport": semiannual_report_payload,
        "balance": {
            "reportDate": balance_payload.get("reportDate"),
            "conclusion": balance_payload.get("conclusion"),
            "topAssets": top_bar_items(balance_payload.get("barData", []), "asset"),
            "topLiabilities": top_bar_items(balance_payload.get("barData", []), "liability"),
        },
        "revenueMarketCap": {
            "conclusion": revenue_payload.get("conclusion"),
            "revenueBars": sample_series_points(revenue_payload.get("revenueBars", [])),
            "marketCapLine": sample_series_points(revenue_payload.get("marketCapLine", [])),
        },
        "profitMarketCap": {
            "conclusion": profit_payload.get("conclusion"),
            "profitBars": sample_series_points(profit_payload.get("profitBars", [])),
            "marketCapLine": sample_series_points(profit_payload.get("marketCapLine", [])),
        },
        "peTrend": {
            "conclusion": pe_payload.get("conclusion"),
            "meanLine": pe_payload.get("meanLine"),
            "lowLine": pe_payload.get("lowLine"),
            "highLine": pe_payload.get("highLine"),
            "peLine": sample_series_points(pe_payload.get("peLine", [])),
        },
    }


def generate_ai_analysis(stock: str, period: str | None, years: int, company_material: str | None = None) -> dict:
    settings = get_openai_settings()
    context = build_ai_analysis_context(stock=stock, period=period, years=years)
    business_type_result = generate_business_type_analysis(
        stock=stock,
        period=period,
        years=years,
        company_material=company_material,
    )
    business_type_analysis = business_type_result.get("analysis")

    client = OpenAI(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        http_client=httpx.Client(trust_env=False),
    )

    prompt_sections = [
        "请基于下面的财报和估值数据，生成一段中文分析。\n"
        "输出格式：\n"
        "1. 第一段：总评，2到3句。\n"
        "2. 第二段：用“要点：”开头，列出3条核心观察，每条单独一行，以“- ”开头。\n"
        "3. 第三段：用“风险提示：”开头，写1到2句。\n"
        "4. 不要使用 markdown 标题，不要输出 JSON。\n"
        "5. 请在总评里显式说明该公司更接近哪一类商业模式，以及这个分类如何解释当前财务结构和增长特征。\n\n",
        "【结构化财务趋势数据】\n",
        json.dumps(context, ensure_ascii=False, indent=2),
    ]

    if company_material and company_material.strip():
        prompt_sections.extend(
            [
                "\n\n【用户提供的公司资料】\n",
                company_material.strip(),
            ]
        )

    if business_type_analysis:
        prompt_sections.extend(
            [
                "\n\n【商业模式分类结果】\n",
                json.dumps(business_type_analysis, ensure_ascii=False, indent=2),
            ]
        )

    user_prompt = "".join(prompt_sections)

    response = client.chat.completions.create(
        model=settings["model"],
        temperature=settings["temperature"],
        messages=[
            {"role": "system", "content": AI_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    analysis_text = response.choices[0].message.content if response.choices else ""
    analysis_text = (analysis_text or "").strip()
    if not analysis_text:
        raise ValueError("OpenAI returned an empty analysis.")

    return {
        "stock": stock,
        "period": period or "latest",
        "years": years,
        "model": settings["model"],
        "analysis": analysis_text,
        "businessTypeAnalysis": business_type_analysis,
        "dataContext": context,
    }


def generate_business_type_analysis(
    stock: str,
    period: str | None,
    years: int,
    company_material: str | None = None,
) -> dict:
    settings = get_openai_settings()
    context = build_ai_analysis_context(stock=stock, period=period, years=years)
    client = OpenAI(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        http_client=httpx.Client(trust_env=False),
    )

    schema_template = {
        "company_name": "",
        "business_type": "",
        "confidence": 0.0,
        "main_revenue_source": "",
        "main_profit_source": "",
        "growth_driver": "",
        "key_evidence": [
            {"evidence_type": "收入结构", "description": ""},
            {"evidence_type": "利润结构", "description": ""},
            {"evidence_type": "资产结构", "description": ""},
            {"evidence_type": "现金流特征", "description": ""},
        ],
        "why_this_type": "",
        "not_other_types_reason": [{"type": "", "reason": ""}],
        "risks": [],
        "missing_data": [],
        "final_summary": "",
    }

    user_prompt = (
        "请基于以下两部分信息完成判断，并严格输出 JSON：\n"
        "A. 用户提供的公司资料\n"
        "B. 系统整理的结构化财务趋势数据\n\n"
        "判断时一定要显式考虑收入来源、利润来源、增长驱动、成本结构、资产结构、现金流特征。"
        "如果用户资料里缺少成本结构或现金流特征，请结合结构化数据判断；如果仍不足，请写入 missing_data，且必要时输出“无法确定”。\n\n"
        f"JSON 模板：\n{json.dumps(schema_template, ensure_ascii=False, indent=2)}\n\n"
        f"【公司资料】\n{(company_material or '无额外公司资料，仅使用结构化财务趋势数据判断。').strip()}\n\n"
        f"【结构化财务趋势数据】\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )

    response = client.chat.completions.create(
        model=settings["model"],
        temperature=settings["temperature"],
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": BUSINESS_TYPE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content if response.choices else ""
    content = (content or "").strip()
    if not content:
        raise ValueError("OpenAI returned an empty business type analysis.")

    try:
        analysis_json = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI did not return valid JSON: {content}") from exc

    return {
        "stock": stock,
        "period": period or "latest",
        "years": years,
        "model": settings["model"],
        "analysis": analysis_json,
        "dataContext": context,
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


@app.get("/api/revenue-structure")
def api_revenue_structure():
    stock = request.args.get("stock", "600519").strip() or "600519"
    years_param = request.args.get("years", "8")
    refresh = request.args.get("refresh") == "1"

    try:
        years = normalize_years(years_param, default=8)

        if not refresh:
            cached_payload = load_cached_payload("revenue_structure_v1", stock, years)
            if cached_payload is not None:
                return jsonify(cached_payload)

        payload = get_revenue_structure_payload(stock=stock, years=years)
        save_cached_payload(payload, "revenue_structure_v1", stock, years)
        return jsonify(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "years": years_param}), 400


@app.get("/api/profit-market-cap")
def api_profit_market_cap():
    stock = request.args.get("stock", "600519").strip() or "600519"
    years_param = request.args.get("years", "8")
    refresh = request.args.get("refresh") == "1"

    try:
        years = normalize_years(years_param, default=8)

        if not refresh:
            cached_payload = load_cached_payload("profit_market_cap_v1", stock, years)
            if cached_payload is not None:
                return jsonify(cached_payload)

        payload = get_profit_market_cap_payload(stock=stock, years=years)
        save_cached_payload(payload, "profit_market_cap_v1", stock, years)
        return jsonify(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "years": years_param}), 400


@app.post("/api/ai-analysis")
def api_ai_analysis():
    payload = request.get_json(silent=True) or {}

    stock = str(payload.get("stock", "600519")).strip() or "600519"
    period = payload.get("period")
    years_param = str(payload.get("years", "8")).strip() or "8"
    company_material = str(payload.get("companyMaterial", "")).strip()

    try:
        years = normalize_years(years_param, default=8)
        result = generate_ai_analysis(
            stock=stock,
            period=period,
            years=years,
            company_material=company_material or None,
        )
        return jsonify(result)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return (
            jsonify(
                {
                    "error": str(exc),
                    "stock": stock,
                    "period": period,
                    "years": years_param,
                }
            ),
            400,
        )


@app.post("/api/business-type-analysis")
def api_business_type_analysis():
    payload = request.get_json(silent=True) or {}

    stock = str(payload.get("stock", "600519")).strip() or "600519"
    period = payload.get("period")
    years_param = str(payload.get("years", "8")).strip() or "8"
    company_material = str(payload.get("companyMaterial", "")).strip()

    try:
        if not company_material:
            raise ValueError("companyMaterial is required.")

        years = normalize_years(years_param, default=8)
        result = generate_business_type_analysis(
            stock=stock,
            period=period,
            years=years,
            company_material=company_material,
        )
        return jsonify(result)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return (
            jsonify(
                {
                    "error": str(exc),
                    "stock": stock,
                    "period": period,
                    "years": years_param,
                }
            ),
            400,
        )


@app.get("/")
def health_message():
    return jsonify(
        {
            "message": "Flask API is running. Use the Next frontend for the UI.",
            "balanceApi": "/api/balance?stock=600519",
            "trendApi": "/api/revenue-market-cap?stock=000333&years=8",
            "revenueStructureApi": "/api/revenue-structure?stock=600519&years=8",
            "profitTrendApi": "/api/profit-market-cap?stock=600519&years=8",
            "peApi": "/api/pe-trend?stock=600519&years=8",
            "aiAnalysisApi": "POST /api/ai-analysis",
            "businessTypeAnalysisApi": "POST /api/business-type-analysis",
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5001)
