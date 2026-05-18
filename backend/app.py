from __future__ import annotations

import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener

import akshare as ak
import httpx
import pandas as pd
import requests
from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI

try:
    from .core.cache import (
        get_ak_dataframe_cached,
        get_cached_payload_or_build,
        load_cached_payload,
        load_latest_cached_payload,
        sanitize_cache_part,
        save_cached_payload,
    )
    from .integrations.akshare_client import (
        run_python_json_subprocess,
        stock_profile_cninfo_isolated,
        temporary_disable_proxy_env,
    )
    from .integrations.cninfo import get_latest_report_text_payload_v2
    from .core.config import (
        BASE_DIR,
        YI,
    )
    from .core.openai_settings import get_openai_settings
    from .core.utils import (
        dataframe_preview,
        finite_float,
        json_safe_value,
        normalize_period,
        normalize_years,
        parse_ak_value,
        to_em_symbol,
        to_yi,
    )
    from .api.frontend import register_frontend_routes
    from .api.system import build_cache_stats_payload, build_health_payload, register_system_routes
except ImportError:
    from core.cache import (
        get_ak_dataframe_cached,
        get_cached_payload_or_build,
        load_cached_payload,
        load_latest_cached_payload,
        sanitize_cache_part,
        save_cached_payload,
    )
    from integrations.akshare_client import (
        run_python_json_subprocess,
        stock_profile_cninfo_isolated,
        temporary_disable_proxy_env,
    )
    from integrations.cninfo import get_latest_report_text_payload_v2
    from core.config import (
        BASE_DIR,
        YI,
    )
    from core.openai_settings import get_openai_settings
    from core.utils import (
        dataframe_preview,
        finite_float,
        json_safe_value,
        normalize_period,
        normalize_years,
        parse_ak_value,
        to_em_symbol,
        to_yi,
    )
    from api.frontend import register_frontend_routes
    from api.system import build_cache_stats_payload, build_health_payload, register_system_routes

try:
    from .industry.service import IndustryDataDeps, build_industry_data_payload as build_industry_data_payload_from_service
except ImportError:
    from industry.service import IndustryDataDeps, build_industry_data_payload as build_industry_data_payload_from_service

app = FastAPI(title="ValueCompass API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_origin_regex=r"https?://(127\.0\.0\.1|localhost):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

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

BUSINESS_EXPLANATION_RULES = [
    {
        "keywords": ["集装箱航运", "航运业务", "班轮"],
        "businessDescription": "这块本质上是海运服务，不是制造产品。公司把客户的货物装进集装箱，在全球航线之间完成运输，收入主要来自运价、舱位利用率和各类附加费。",
        "priceDrivers": ["全球贸易需求", "航线运价", "船舶运力供给", "港口拥堵", "燃油成本", "汇率"],
        "businessCategory": "service",
    },
    {
        "keywords": ["码头业务", "港口", "码头"],
        "businessDescription": "这块也是服务。公司依托港口和码头资源，向船公司和货主提供装卸、堆存和中转服务，收入通常和吞吐量、港口费率、枢纽地位相关。",
        "priceDrivers": ["港口吞吐量", "区域贸易活跃度", "收费标准", "枢纽港地位", "人工与能耗成本"],
        "businessCategory": "service",
    },
    {
        "keywords": ["茅台酒", "白酒", "系列酒"],
        "businessDescription": "核心是酒类产品销售，收入通常来自出厂价、渠道结构、销量和高端产品占比。",
        "priceDrivers": ["终端需求", "品牌力", "渠道结构", "出厂价调整", "产品结构升级", "政策环境"],
        "businessCategory": "product",
    },
    {
        "keywords": ["家用空调", "消费电器", "冰箱", "洗衣机", "厨电"],
        "businessDescription": "核心是耐用消费品销售，收入通常来自销量、ASP、渠道折扣和新品迭代。",
        "priceDrivers": ["终端消费需求", "原材料价格", "渠道去库存", "以旧换新政策", "产品升级"],
        "businessCategory": "product",
    },
    {
        "keywords": ["氧化铝", "氧化铝产品"],
        "businessDescription": "这是电解铝上游的基础原料，收入主要跟氧化铝销量、市场价格和铝土矿/能源成本相关。它通常比终端铝材更偏资源和周期属性。",
        "priceDrivers": ["氧化铝现货价格", "铝土矿成本", "烧碱和能源价格", "电解铝开工率", "进口供应"],
        "businessCategory": "product",
    },
    {
        "keywords": ["铝加工", "铝加工产品", "铝材", "铝板", "铝带", "铝箔", "铝合金"],
        "businessDescription": "这是把铝进一步加工成板带箔、型材或合金材料的业务，收入不只看铝价，还要看加工费、产品结构和下游客户需求。",
        "priceDrivers": ["铝价", "加工费", "产品规格结构", "汽车和包装需求", "电力与人工成本", "出口订单"],
        "businessCategory": "product",
    },
    {
        "keywords": ["电解铝", "原铝", "铝锭", "铝液"],
        "businessDescription": "这是铝产业链中游的冶炼产品，收入对铝价和产量非常敏感，利润重点看电力成本、氧化铝成本和产能利用率。",
        "priceDrivers": ["沪铝价格", "电力成本", "氧化铝成本", "产能利用率", "库存周期", "限电限产政策"],
        "businessCategory": "product",
    },
    {
        "keywords": ["炭素", "预焙阳极", "阳极炭块"],
        "businessDescription": "这是电解铝生产消耗的配套材料，收入通常跟电解铝开工、阳极价格、石油焦和煤沥青等原料成本相关。",
        "priceDrivers": ["电解铝开工率", "预焙阳极价格", "石油焦成本", "煤沥青成本", "配套产能利用率"],
        "businessCategory": "product",
    },
    {
        "keywords": ["工程及金属索具"],
        "businessDescription": "这是偏工程场景的金属索具，通常用于吊装、连接、固定和大型设备配套。收入更容易跟基建、能源、桥梁、海工和大型制造项目的开工节奏相关。",
        "priceDrivers": ["工程项目开工", "大客户订单", "钢材成本", "安全认证要求", "定制化规格", "项目交付周期"],
        "businessCategory": "product",
    },
    {
        "keywords": ["钢丝绳及钢丝绳索具", "钢丝绳"],
        "businessDescription": "这类产品更像标准化程度较高的承载和牵引材料，常用于起重、矿山、港口、工程机械等场景。重点看销量、规格结构和原材料成本传导。",
        "priceDrivers": ["钢材价格", "工业开工率", "起重和矿山需求", "规格结构", "出口订单", "产能利用率"],
        "businessCategory": "product",
    },
    {
        "keywords": ["合成纤维吊装带索具", "吊装带"],
        "businessDescription": "这是轻量化、柔性吊装类产品，应用上更看重安全性、耐磨性和对特殊吊装场景的适配。毛利率通常要结合材料成本、认证和定制能力一起看。",
        "priceDrivers": ["化纤材料成本", "安全认证", "定制化需求", "工业吊装场景", "替代钢制索具需求", "出口需求"],
        "businessCategory": "product",
    },
    {
        "keywords": ["链条及链条索具", "链条"],
        "businessDescription": "这是链条连接和承载类产品，单项收入占比不高时，更多用于补齐吊装和索具体系。观察重点是它是否能和主力索具产品形成配套销售。",
        "priceDrivers": ["配套销售能力", "钢材成本", "设备制造需求", "维修替换需求", "产品规格结构", "客户复购"],
        "businessCategory": "product",
    },
    {
        "keywords": ["工程及金属索具", "钢丝绳", "索具", "吊装带", "链条", "缆绳"],
        "businessDescription": "核心是工程吊装、连接和承载类产品销售。它不是普通消费品，更接近工业基础件，收入主要跟下游工程项目、设备制造和基建施工需求相关。",
        "priceDrivers": ["工程项目需求", "钢材和纤维材料成本", "产品安全认证", "定制化能力", "下游资本开支", "出口订单"],
        "businessCategory": "product",
    },
    {
        "keywords": ["软件", "SaaS", "云服务"],
        "businessDescription": "这块更接近持续服务。公司通过软件许可、订阅或云服务持续向客户交付能力，收入通常来自客户数、续费率和客单价。",
        "priceDrivers": ["客户扩张", "续费率", "ARPU", "产品迭代能力", "行业数字化投入"],
        "businessCategory": "service",
    },
]

DRIVER_MODEL_REGISTRY: dict[str, dict] = {
    "aluminum_commodity": {
        "label": "铝商品价格驱动",
        "description": "适用于电解铝、氧化铝、铝加工等以铝价和单位成本为核心的公司。",
        "marketData": [
            {"metric": "shfe_aluminum", "label": "沪铝期货/现货", "unit": "元/吨", "sourcePriority": ["SHFE", "SMM", "长江有色"]},
            {"metric": "alumina_price", "label": "氧化铝价格", "unit": "元/吨", "sourcePriority": ["SHFE", "SMM"]},
            {"metric": "power_cost_proxy", "label": "电力成本代理", "unit": "元/度", "sourcePriority": ["公司披露", "区域电价"]},
            {"metric": "prebaked_anode_price", "label": "预焙阳极/炭素价格", "unit": "元/吨", "sourcePriority": ["SMM", "行业价格"]},
        ],
        "operatingData": ["铝产品产量", "铝产品销量", "铝产品收入", "铝产品成本", "单吨毛利"],
        "formula": "铝产品利润 ≈ 销量 × (铝价 - 氧化铝成本 - 电力成本 - 阳极等辅料成本 - 其他单吨成本)",
    },
    "oil_gas_integrated": {
        "label": "综合油气多分部驱动",
        "description": "适用于上游油气、炼化、销售和天然气业务并存的综合能源公司。",
        "marketData": [
            {"metric": "brent_crude", "label": "Brent 原油", "unit": "美元/桶", "sourcePriority": ["ICE", "EIA"]},
            {"metric": "wti_crude", "label": "WTI 原油", "unit": "美元/桶", "sourcePriority": ["NYMEX", "EIA"]},
            {"metric": "dubai_oman_crude", "label": "Dubai/Oman 原油", "unit": "美元/桶", "sourcePriority": ["DME", "市场行情"]},
            {"metric": "domestic_fuel_price_adjustment", "label": "国内成品油调价", "unit": "元/吨", "sourcePriority": ["发改委"]},
            {"metric": "import_lng_price", "label": "进口 LNG/JCC 相关成本", "unit": "美元/MMBtu", "sourcePriority": ["海关", "JCC", "JKM"]},
            {"metric": "chemical_spread", "label": "炼化/化工价差", "unit": "元/吨", "sourcePriority": ["商品行情", "行业数据"]},
            {"metric": "usd_cny", "label": "美元兑人民币", "unit": "汇率", "sourcePriority": ["央行", "外汇交易中心"]},
        ],
        "operatingData": ["原油产量", "天然气产量", "原油实现价格", "天然气实现价格", "炼厂加工量", "天然气销量", "分部经营利润"],
        "formula": "经营利润 ≈ 上游油气利润 + 炼化价差利润 + 销售利润 + 天然气购销价差利润 - 总部及其他",
    },
    "container_shipping": {
        "label": "集装箱运价驱动",
        "description": "适用于以集装箱航运为核心，利润对运价指数和箱量敏感的公司。",
        "marketData": [
            {"metric": "scfi", "label": "上海出口集装箱运价指数 SCFI", "unit": "指数", "sourcePriority": ["上海航运交易所"]},
            {"metric": "ccfi", "label": "中国出口集装箱运价指数 CCFI", "unit": "指数", "sourcePriority": ["上海航运交易所"]},
            {"metric": "fbx", "label": "Freightos Baltic Index", "unit": "美元/FEU", "sourcePriority": ["Freightos"]},
            {"metric": "drewry_wci", "label": "Drewry WCI", "unit": "美元/FEU", "sourcePriority": ["Drewry"]},
            {"metric": "vlsfo_fuel", "label": "低硫燃料油 VLSFO", "unit": "美元/吨", "sourcePriority": ["船燃行情", "新加坡燃油"]},
            {"metric": "usd_cny", "label": "美元兑人民币", "unit": "汇率", "sourcePriority": ["央行", "外汇交易中心"]},
            {"metric": "port_congestion", "label": "港口拥堵/绕航影响", "unit": "事件/指数", "sourcePriority": ["航运新闻", "AIS/港口数据"]},
        ],
        "operatingData": ["集装箱运输量TEU", "单箱收入", "单箱成本", "燃油成本", "分航线收入", "码头吞吐量"],
        "formula": "航运利润 ≈ 箱量 × (单箱收入 - 单箱成本) + 码头利润；单箱收入由运价指数、长协价和航线结构共同决定",
    },
    "generic_volume_price": {
        "label": "通用量价驱动",
        "description": "适用于未命中专用模型但可按销量、价格、成本和费用率分析的公司。",
        "marketData": [],
        "operatingData": ["销量/产量", "ASP", "单位成本", "毛利率", "费用率", "订单或合同负债"],
        "formula": "利润 ≈ 销量 × (单价 - 单位成本) - 期间费用 - 税费",
    },
    "generic_spread": {
        "label": "通用价差驱动",
        "description": "适用于成本端和产品端都有市场价格，利润主要取决于价差的公司。",
        "marketData": [{"metric": "input_output_spread", "label": "产品-原料价差", "unit": "元/吨", "sourcePriority": ["商品行情", "行业数据"]}],
        "operatingData": ["产量", "产品售价", "原料成本", "单位加工费", "毛利率"],
        "formula": "利润 ≈ 产销量 × 产品原料价差 - 固定成本 - 费用",
    },
}

KNOWN_DRIVER_MODELS = list(DRIVER_MODEL_REGISTRY.keys())

COMMODITY_FUTURES_SYMBOLS: dict[str, dict[str, str]] = {
    "CU": {"name": "铜", "unit": "元/吨"},
    "AL": {"name": "铝", "unit": "元/吨"},
    "ZN": {"name": "锌", "unit": "元/吨"},
    "PB": {"name": "铅", "unit": "元/吨"},
    "NI": {"name": "镍", "unit": "元/吨"},
    "SN": {"name": "锡", "unit": "元/吨"},
    "AU": {"name": "黄金", "unit": "元/克"},
    "AG": {"name": "白银", "unit": "元/千克"},
    "RB": {"name": "螺纹钢", "unit": "元/吨"},
    "HC": {"name": "热轧卷板", "unit": "元/吨"},
    "WR": {"name": "线材", "unit": "元/吨"},
    "SS": {"name": "不锈钢", "unit": "元/吨"},
    "FU": {"name": "燃料油", "unit": "元/吨"},
    "BU": {"name": "沥青", "unit": "元/吨"},
    "RU": {"name": "天然橡胶", "unit": "元/吨"},
    "SP": {"name": "纸浆", "unit": "元/吨"},
    "BR": {"name": "丁二烯橡胶", "unit": "元/吨"},
    "SC": {"name": "原油", "unit": "元/桶"},
    "NR": {"name": "20号胶", "unit": "元/吨"},
    "LU": {"name": "低硫燃料油", "unit": "元/吨"},
    "BC": {"name": "国际铜", "unit": "元/吨"},
    "AO": {"name": "氧化铝", "unit": "元/吨"},
    "A": {"name": "豆一", "unit": "元/吨"},
    "B": {"name": "豆二", "unit": "元/吨"},
    "M": {"name": "豆粕", "unit": "元/吨"},
    "Y": {"name": "豆油", "unit": "元/吨"},
    "P": {"name": "棕榈油", "unit": "元/吨"},
    "C": {"name": "玉米", "unit": "元/吨"},
    "CS": {"name": "玉米淀粉", "unit": "元/吨"},
    "JD": {"name": "鸡蛋", "unit": "元/500千克"},
    "L": {"name": "聚乙烯", "unit": "元/吨"},
    "V": {"name": "PVC", "unit": "元/吨"},
    "PP": {"name": "聚丙烯", "unit": "元/吨"},
    "J": {"name": "焦炭", "unit": "元/吨"},
    "JM": {"name": "焦煤", "unit": "元/吨"},
    "I": {"name": "铁矿石", "unit": "元/吨"},
    "EG": {"name": "乙二醇", "unit": "元/吨"},
    "EB": {"name": "苯乙烯", "unit": "元/吨"},
    "PG": {"name": "液化石油气", "unit": "元/吨"},
    "LH": {"name": "生猪", "unit": "元/吨"},
    "CF": {"name": "棉花", "unit": "元/吨"},
    "SR": {"name": "白糖", "unit": "元/吨"},
    "TA": {"name": "PTA", "unit": "元/吨"},
    "OI": {"name": "菜籽油", "unit": "元/吨"},
    "MA": {"name": "甲醇", "unit": "元/吨"},
    "FG": {"name": "玻璃", "unit": "元/吨"},
    "RM": {"name": "菜籽粕", "unit": "元/吨"},
    "SF": {"name": "硅铁", "unit": "元/吨"},
    "SM": {"name": "锰硅", "unit": "元/吨"},
    "AP": {"name": "苹果", "unit": "元/吨"},
    "UR": {"name": "尿素", "unit": "元/吨"},
    "CJ": {"name": "红枣", "unit": "元/吨"},
    "SA": {"name": "纯碱", "unit": "元/吨"},
    "PK": {"name": "花生", "unit": "元/吨"},
    "PF": {"name": "短纤", "unit": "元/吨"},
    "PX": {"name": "对二甲苯", "unit": "元/吨"},
    "SH": {"name": "烧碱", "unit": "元/吨"},
    "SI": {"name": "工业硅", "unit": "元/吨"},
    "LC": {"name": "碳酸锂", "unit": "元/吨"},
}

DEFAULT_COMMODITY_SYMBOLS = list(COMMODITY_FUTURES_SYMBOLS.keys())

MARKET_INDEX_CONFIG: dict[str, dict] = {
    "sp500": {
        "name": "S&P 500",
        "displayName": "标普500",
        "peSource": "multpl",
        "peUrl": "https://www.multpl.com/s-p-500-pe-ratio/table/by-month",
        "priceSymbol": "标普500",
        "yahooSymbol": "^GSPC",
        "yahooFallbackSymbols": ["SPY"],
        "sourceLabel": "Multpl S&P 500 PE Ratio (TTM/as-reported) / FRED DGS10",
        "sourceQuality": "S&P 500 PE 为公开历史序列，非 S&P Dow Jones 官方授权数据；适合估值温度判断，不适合做交易级精确口径。",
    },
    "nasdaq100": {
        "name": "Nasdaq 100",
        "displayName": "纳斯达克100",
        "peSource": "worldperatio",
        "peUrl": "https://worldperatio.com/index/nasdaq-100/",
        "priceSymbol": "纳斯达克",
        "yahooSymbol": "^NDX",
        "yahooFallbackSymbols": ["QQQ"],
        "sourceLabel": "World PE Ratio Nasdaq 100 / FRED DGS10",
        "sourceQuality": "Nasdaq 100 PE 为第三方公开网页口径，非 Nasdaq 官方授权数据；当前只用于参考估值分位。",
    },
    "csi300": {
        "name": "CSI 300",
        "displayName": "沪深300",
        "peSource": "etfrun_legulegu_csindex",
        "peUrl": "https://www.etf.run/index/SSE/000300",
        "csindexSymbol": "000300",
        "etfRunMarket": "SSE",
        "etfRunSymbol": "000300",
        "leguleguSymbol": "沪深300",
        "sourceLabel": "ETF.run 指数等权 PE TTM / 乐咕乐股与中证指数官网备用",
        "sourceQuality": "沪深300 PE 优先使用 ETF.run 历史等权 PE TTM 序列，速度较快但与指数整体滚动市盈率口径不同；如外部源不可用，回退到乐咕乐股或中证指数官网最近估值数据。",
    },
    "csi500": {
        "name": "CSI 500",
        "displayName": "中证500",
        "peSource": "etfrun_legulegu_csindex",
        "peUrl": "https://www.etf.run/index/SSE/000905",
        "csindexSymbol": "000905",
        "etfRunMarket": "SSE",
        "etfRunSymbol": "000905",
        "leguleguSymbol": "中证500",
        "sourceLabel": "ETF.run 指数等权 PE TTM / 乐咕乐股与中证指数官网备用",
        "sourceQuality": "中证500 PE 优先使用 ETF.run 历史等权 PE TTM 序列，速度较快但与指数整体滚动市盈率口径不同；如外部源不可用，回退到乐咕乐股或中证指数官网最近估值数据。",
    },
    "dividend_low_vol_100": {
        "name": "CSI Dividend Low Volatility 100",
        "displayName": "红利低波100",
        "peSource": "etfrun_csindex",
        "peUrl": "https://www.etf.run/index/CSI/930955",
        "csindexSymbol": "930955",
        "etfRunMarket": "CSI",
        "etfRunSymbol": "930955",
        "etfRunUrl": "https://www.etf.run/index/CSI/930955",
        "sourceLabel": "ETF.run 指数估值 / 中证指数官网备用",
        "sourceQuality": "红利低波100 优先使用 ETF.run 页面内嵌的等权 PE_TTM 历史序列；若失败，再回退中证指数官网近期估值，且不会用短序列计算长期分位。",
    },
}

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

CASH_FLOW_OPERATE_CANDIDATES = [
    "NETCASH_OPERATE",
    "NETCASH_OPERATENOTE",
    "经营活动产生的现金流量净额",
    "经营活动产生的现金流量净额(元)",
]

PEER_COMPANY_GROUPS = [
    {
        "group": "白酒",
        "keywords": ["白酒", "酒", "茅台", "五粮液", "泸州老窖", "酱香", "浓香", "清香"],
        "peers": [
            {"stock": "600519", "name": "贵州茅台"},
            {"stock": "000858", "name": "五粮液"},
            {"stock": "000568", "name": "泸州老窖"},
            {"stock": "600809", "name": "山西汾酒"},
            {"stock": "002304", "name": "洋河股份"},
            {"stock": "000596", "name": "古井贡酒"},
            {"stock": "603369", "name": "今世缘"},
            {"stock": "600702", "name": "舍得酒业"},
        ],
    },
    {
        "group": "家电",
        "keywords": ["家电", "空调", "冰箱", "洗衣机", "消费电器", "厨房电器", "暖通"],
        "peers": [
            {"stock": "000333", "name": "美的集团"},
            {"stock": "000651", "name": "格力电器"},
            {"stock": "600690", "name": "海尔智家"},
            {"stock": "000921", "name": "海信家电"},
            {"stock": "002032", "name": "苏泊尔"},
            {"stock": "002508", "name": "老板电器"},
        ],
    },
    {
        "group": "航运物流",
        "keywords": ["航运", "海运", "集装箱", "港口", "码头", "船舶", "物流", "货运"],
        "peers": [
            {"stock": "601919", "name": "中远海控"},
            {"stock": "601872", "name": "招商轮船"},
            {"stock": "600026", "name": "中远海能"},
            {"stock": "601598", "name": "中国外运"},
            {"stock": "601866", "name": "中远海发"},
            {"stock": "001872", "name": "招商港口"},
        ],
    },
    {
        "group": "游戏软件",
        "keywords": ["游戏", "手游", "网络游戏", "软件", "互联网", "云服务", "数字娱乐"],
        "peers": [
            {"stock": "300052", "name": "中青宝"},
            {"stock": "002555", "name": "三七互娱"},
            {"stock": "002624", "name": "完美世界"},
            {"stock": "300418", "name": "昆仑万维"},
            {"stock": "300002", "name": "神州泰岳"},
            {"stock": "300031", "name": "宝通科技"},
        ],
    },
    {
        "group": "金属索具",
        "keywords": ["索具", "钢丝绳", "金属制品", "吊装", "链条", "缆绳", "钢绞线", "起重", "通用设备"],
        "peers": [
            {"stock": "600992", "name": "贵绳股份"},
            {"stock": "603028", "name": "赛福天"},
            {"stock": "000890", "name": "法尔胜"},
            {"stock": "002132", "name": "恒星科技"},
            {"stock": "603278", "name": "大业股份"},
            {"stock": "603969", "name": "银龙股份"},
        ],
    },
    {
        "group": "新能源汽车",
        "keywords": ["汽车", "新能源车", "整车", "乘用车", "商用车", "电动车"],
        "peers": [
            {"stock": "002594", "name": "比亚迪"},
            {"stock": "601633", "name": "长城汽车"},
            {"stock": "600104", "name": "上汽集团"},
            {"stock": "000625", "name": "长安汽车"},
            {"stock": "601238", "name": "广汽集团"},
        ],
    },
    {
        "group": "银行",
        "keywords": ["银行", "商业银行", "存款", "贷款", "利息净收入"],
        "peers": [
            {"stock": "600036", "name": "招商银行"},
            {"stock": "601398", "name": "工商银行"},
            {"stock": "601939", "name": "建设银行"},
            {"stock": "601288", "name": "农业银行"},
            {"stock": "000001", "name": "平安银行"},
        ],
    },
]

DEFAULT_PEER_COMPANIES = [
    {"stock": "600519", "name": "贵州茅台"},
    {"stock": "000333", "name": "美的集团"},
    {"stock": "601919", "name": "中远海控"},
    {"stock": "300052", "name": "中青宝"},
]


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
    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching balance sheet, stock={stock}")
        with temporary_disable_proxy_env():
            return ak.stock_financial_debt_ths(symbol=stock, indicator="按报告期")

    df = get_ak_dataframe_cached(("balance_sheet", stock), fetch)
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

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching quarterly profit sheet, symbol={em_symbol}")
        with temporary_disable_proxy_env():
            return ak.stock_profit_sheet_by_quarterly_em(symbol=em_symbol)

    df = get_ak_dataframe_cached(("profit_sheet", em_symbol), fetch)
    print("[DEBUG] Profit columns:")
    print(df.columns.tolist())
    return df


def load_cash_flow_sheet(stock: str) -> pd.DataFrame:
    em_symbol = to_em_symbol(stock)

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching quarterly cash flow sheet, symbol={em_symbol}")
        with temporary_disable_proxy_env():
            return ak.stock_cash_flow_sheet_by_quarterly_em(symbol=em_symbol)

    df = get_ak_dataframe_cached(("cash_flow_sheet", em_symbol), fetch)
    print("[DEBUG] Cash flow columns:")
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

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching valuation, stock={stock}, period={period}")
        with temporary_disable_proxy_env():
            return ak.stock_zh_valuation_baidu(symbol=stock, indicator="总市值", period=period)

    df = get_ak_dataframe_cached(("market_cap", stock, period), fetch)
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


def find_operating_cash_flow_column(df: pd.DataFrame) -> str:
    for column in CASH_FLOW_OPERATE_CANDIDATES:
        if column in df.columns:
            return column

    print("[ERROR] Operating cash flow field not matched, available columns:")
    print(df.columns.tolist())
    raise ValueError("现金流量表中未找到经营现金流字段，请查看后端打印的 columns")


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


def build_cash_flow_bars(df: pd.DataFrame, years: int) -> list[dict]:
    if df is None or df.empty:
        raise ValueError("未获取到现金流量表数据")

    cash_flow_column = find_operating_cash_flow_column(df)
    date_column = "REPORT_DATE" if "REPORT_DATE" in df.columns else "报告期"
    if date_column not in df.columns:
        print("[ERROR] Cash flow date field not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("现金流量表中未找到报告期字段，请查看后端打印的 columns")

    cash_flow_df = df[[date_column, cash_flow_column]].copy()
    cash_flow_df["date"] = pd.to_datetime(cash_flow_df[date_column], errors="coerce")
    cash_flow_df["value"] = cash_flow_df[cash_flow_column].apply(parse_ak_value)
    cash_flow_df = cash_flow_df.dropna(subset=["date"]).sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    cash_flow_df = cash_flow_df[cash_flow_df["date"] >= cutoff]
    if cash_flow_df.empty:
        raise ValueError(f"最近 {years} 年没有可用的经营现金流数据")

    return [
        {"date": row.date.strftime("%Y-%m-%d"), "value": to_yi(row.value)}
        for row in cash_flow_df.itertuples()
    ]


def build_cash_to_profit_ratio(
    operating_cash_flow: list[dict], net_profit: list[dict]
) -> list[dict]:
    profit_lookup = {item["date"]: item["value"] for item in net_profit}
    ratio_points: list[dict] = []

    for cash_item in operating_cash_flow:
        profit_value = profit_lookup.get(cash_item["date"])
        if profit_value is None or abs(profit_value) < 0.000001:
            continue

        ratio_points.append(
            {
                "date": cash_item["date"],
                "value": round(cash_item["value"] / profit_value, 2),
            }
        )

    return ratio_points


def generate_cash_flow_quality_conclusion(
    operating_cash_flow: list[dict],
    net_profit: list[dict],
    cash_to_profit_ratio: list[dict],
) -> str:
    if not operating_cash_flow or not net_profit:
        return "现金流和利润质量需要更多数据后再判断。"

    recent_cash = operating_cash_flow[-4:]
    recent_ratios = cash_to_profit_ratio[-4:]
    latest_cash = recent_cash[-1]
    latest_profit = net_profit[-1]
    positive_cash_count = sum(1 for item in recent_cash if item["value"] > 0)
    negative_cash_streak = 0
    for item in reversed(recent_cash):
        if item["value"] < 0:
            negative_cash_streak += 1
        else:
            break

    valid_positive_profit_ratios = [
        item for item in recent_ratios if item["value"] > 0 and math.isfinite(item["value"])
    ]
    ratio_above_one_count = sum(1 for item in valid_positive_profit_ratios if item["value"] >= 1)
    latest_ratio = cash_to_profit_ratio[-1]["value"] if cash_to_profit_ratio else None

    if negative_cash_streak >= 2:
        return (
            f"利润质量有压力：经营现金流已连续 {negative_cash_streak} 个报告期为负，"
            "利润尚未稳定转化为现金。"
        )

    if latest_profit["value"] > 0 and latest_cash["value"] < 0:
        return (
            f"利润质量有压力：最新报告期净利润为 {latest_profit['value']} 亿元，"
            f"但经营现金流为 {latest_cash['value']} 亿元，需要关注回款和营运资金占用。"
        )

    if valid_positive_profit_ratios and ratio_above_one_count >= math.ceil(len(valid_positive_profit_ratios) / 2):
        ratio_text = f"，最新净现比约 {latest_ratio} 倍" if latest_ratio is not None else ""
        return f"利润质量较好：最近几个报告期经营现金流多数为正，净现比大多高于 1{ratio_text}。"

    if positive_cash_count >= math.ceil(len(recent_cash) / 2):
        ratio_text = f"，最新净现比约 {latest_ratio} 倍" if latest_ratio is not None else ""
        return f"利润质量一般：经营现金流整体为正，但现金流对净利润的覆盖还不稳定{ratio_text}。"

    return "利润质量有压力：最近几个报告期经营现金流偏弱，需要继续观察利润是否能转化为现金。"


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


def get_cash_flow_quality_payload(stock: str, years: int) -> dict:
    operating_cash_flow = build_cash_flow_bars(load_cash_flow_sheet(stock), years)
    net_profit = build_profit_bars(load_profit_sheet(stock), years)
    cash_to_profit_ratio = build_cash_to_profit_ratio(operating_cash_flow, net_profit)

    return {
        "stock": stock,
        "title": f"{stock} 现金流与盈利质量",
        "unit": "亿元",
        "operatingCashFlow": operating_cash_flow,
        "netProfit": net_profit,
        "cashToProfitRatio": cash_to_profit_ratio,
        "conclusion": generate_cash_flow_quality_conclusion(
            operating_cash_flow,
            net_profit,
            cash_to_profit_ratio,
        ),
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

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching PE TTM, stock={stock}, period={period}")
        with temporary_disable_proxy_env():
            return ak.stock_zh_valuation_baidu(
                symbol=stock,
                indicator="市盈率(TTM)",
                period=period,
            )

    df = get_ak_dataframe_cached(("pe_ttm", stock, period), fetch)
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


def get_balance_payload_with_cache(stock: str, period: str | None, refresh: bool = False) -> dict:
    normalized_period = normalize_period(period)
    return get_cached_payload_or_build(
        "balance",
        stock,
        normalized_period or "latest",
        builder=lambda: get_balance_payload(stock=stock, period=period),
        refresh=refresh,
    )


def get_revenue_market_cap_payload_with_cache(stock: str, years: int, refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "revenue_market_cap_v2",
        stock,
        years,
        builder=lambda: get_revenue_market_cap_payload(stock=stock, years=years),
        refresh=refresh,
    )


def get_profit_market_cap_payload_with_cache(stock: str, years: int, refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "profit_market_cap_v1",
        stock,
        years,
        builder=lambda: get_profit_market_cap_payload(stock=stock, years=years),
        refresh=refresh,
    )


def get_cash_flow_quality_payload_with_cache(stock: str, years: int, refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "cash_flow_quality_v1",
        stock,
        years,
        builder=lambda: get_cash_flow_quality_payload(stock=stock, years=years),
        refresh=refresh,
    )


def get_pe_trend_payload_with_cache(stock: str, years: int, refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "pe_trend_v1",
        stock,
        years,
        builder=lambda: build_pe_trend_payload(stock=stock, years=years),
        refresh=refresh,
    )


def load_company_profile(stock: str) -> pd.DataFrame:
    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching company profile in subprocess, stock={stock}")
        return stock_profile_cninfo_isolated(stock)

    df = get_ak_dataframe_cached(("company_profile", stock), fetch)
    print("[DEBUG] Company profile columns:")
    print(df.columns.tolist())
    return df


def load_main_business_composition(stock: str) -> pd.DataFrame:
    symbol = to_em_symbol(stock)

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching main business composition, symbol={symbol}")
        with temporary_disable_proxy_env():
            return ak.stock_zygc_em(symbol=symbol)

    df = get_ak_dataframe_cached(("main_business", symbol), fetch)
    print("[DEBUG] Main business columns:")
    print(df.columns.tolist())
    return df


def get_company_profile_payload_with_cache(stock: str, refresh: bool = False) -> dict:
    def build() -> dict:
        df = load_company_profile(stock)
        if df is None or df.empty:
            raise ValueError(f"Unable to fetch company profile for stock {stock}.")

        row = df.iloc[0]
        return {
            "stock": stock,
            "companyName": row.get("公司名称", ""),
            "industry": row.get("所属行业", ""),
            "mainBusiness": row.get("主营业务", ""),
            "businessScope": row.get("经营范围", ""),
            "companyIntro": row.get("机构简介", ""),
        }

    return get_cached_payload_or_build("company_profile_v1", stock, builder=build, refresh=refresh)


def get_main_business_payload_with_cache(stock: str, refresh: bool = False) -> dict:
    def build() -> dict:
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

        return {
            "stock": stock,
            "items": summary_items,
        }

    return get_cached_payload_or_build("main_business_v1", stock, builder=build, refresh=refresh)


def normalize_stock_code(stock: str) -> str:
    match = re.search(r"\d{6}", str(stock or ""))
    return match.group(0) if match else str(stock or "").strip()


def compact_company_name(name: object, fallback: str = "") -> str:
    text = str(name or fallback or "").strip()
    for suffix in ["股份有限公司", "有限责任公司", "有限公司", "集团股份", "集团"]:
        text = text.replace(suffix, "")
    return text[:8] if len(text) > 8 else text


def collect_peer_match_texts(profile_payload: dict, main_business_payload: dict) -> tuple[str, str]:
    primary_parts = [
        profile_payload.get("companyName", ""),
        profile_payload.get("industry", ""),
        profile_payload.get("mainBusiness", ""),
    ]
    for item in main_business_payload.get("items", []):
        primary_parts.extend(
            [
                item.get("itemName", ""),
                item.get("categoryType", ""),
            ]
        )

    scope_parts = [
        profile_payload.get("businessScope", ""),
        profile_payload.get("companyIntro", ""),
    ]
    return (
        " ".join(str(part) for part in primary_parts if part),
        " ".join(str(part) for part in scope_parts if part),
    )


def score_peer_group(primary_text: str, scope_text: str, keywords: list[str]) -> dict:
    primary_hits = [keyword for keyword in keywords if keyword and keyword in primary_text]
    scope_hits = [keyword for keyword in keywords if keyword and keyword in scope_text and keyword not in primary_hits]
    score = len(primary_hits) * 3 + len(scope_hits)

    # 经营范围经常包含大量边缘业务，单个弱命中不能决定同行归类。
    if not primary_hits and len(scope_hits) < 2:
        score = 0

    return {
        "score": score,
        "primaryHits": primary_hits,
        "scopeHits": scope_hits,
        "hits": primary_hits + scope_hits,
    }


def build_peer_candidates(stock: str, limit: int) -> dict:
    normalized_stock = normalize_stock_code(stock)
    profile_payload = get_company_profile_payload_with_cache(normalized_stock)

    try:
        main_business_payload = get_main_business_payload_with_cache(normalized_stock)
    except Exception as exc:
        print(f"[WARN] Main business data unavailable for peer scoring, stock={normalized_stock}, error={exc}")
        main_business_payload = {"items": []}

    primary_text, scope_text = collect_peer_match_texts(profile_payload, main_business_payload)
    ranked_groups = sorted(
        (
            {
                "group": group["group"],
                "keywords": group["keywords"],
                "peers": group["peers"],
                **score_peer_group(primary_text, scope_text, group["keywords"]),
            }
            for group in PEER_COMPANY_GROUPS
        ),
        key=lambda item: item["score"],
        reverse=True,
    )
    selected_group = ranked_groups[0] if ranked_groups and ranked_groups[0]["score"] > 0 else None
    seed_peers = selected_group["peers"] if selected_group else DEFAULT_PEER_COMPANIES
    source = "industry_keyword" if selected_group else "default_watchlist"
    source_label = selected_group["group"] if selected_group else "常用观察池"

    peers = []
    for index, peer in enumerate(seed_peers):
        peer_stock = normalize_stock_code(peer["stock"])
        if peer_stock == normalized_stock:
            continue

        keyword_hits = len(selected_group["hits"]) if selected_group else 0
        score = 50 + min(keyword_hits * 10, 30) + max(0, 12 - index * 2)
        reasons = [f"命中{source_label}业务关键词"] if selected_group else ["未识别到明确行业，使用常用样本"]
        if selected_group and selected_group["primaryHits"]:
            reasons.append("主营业务或主营构成匹配")
        elif selected_group:
            reasons.append("经营范围多关键词匹配")

        peers.append(
            {
                "stock": peer_stock,
                "name": peer["name"],
                "score": min(score, 95),
                "reasons": reasons,
                "source": source,
            }
        )

    return {
        "stock": normalized_stock,
        "companyName": compact_company_name(profile_payload.get("companyName"), normalized_stock),
        "industry": profile_payload.get("industry", ""),
        "source": source,
        "sourceLabel": source_label,
        "peers": peers[: max(1, limit)],
    }


def get_peer_companies_payload_with_cache(stock: str, limit: int, refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "peer_companies_v1",
        stock,
        limit,
        builder=lambda: build_peer_candidates(stock=stock, limit=limit),
        refresh=refresh,
    )


def build_driver_model_segment(
    model: str,
    segment_name: str,
    confidence: float,
    evidence: list[str],
    source: str,
) -> dict:
    registry_item = DRIVER_MODEL_REGISTRY.get(model, DRIVER_MODEL_REGISTRY["generic_volume_price"])
    return {
        "segmentName": segment_name,
        "driverModel": model,
        "driverModelLabel": registry_item["label"],
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "source": source,
        "evidence": evidence[:6],
        "requiredMarketData": registry_item["marketData"],
        "requiredOperatingData": registry_item["operatingData"],
        "formula": registry_item["formula"],
        "description": registry_item["description"],
        "dataStatus": "requirements_only",
    }


def parse_report_number_to_float(text: str) -> float | None:
    cleaned = str(text or "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_annual_report_year(report_payload: dict) -> int | None:
    for value in [report_payload.get("date"), report_payload.get("title"), report_payload.get("textExcerpt")]:
        match = re.search(r"(20\d{2})", str(value or ""))
        if match:
            return int(match.group(1))
    return None


def extract_aluminum_capacity_from_report(report_payload: dict, product_kind: str = "primary_aluminum") -> dict | None:
    text = str(report_payload.get("textExcerpt") or "")
    if not text:
        return None

    if product_kind == "aluminum_processing":
        label = "绿色铝合金年产规模"
        output_terms = r"(?:铝加工|铝合金|绿色铝合金)"
        patterns = [
            ("reported_capacity", r"形成年产[^。\n]{0,140}?绿色铝合\s*金\s*([0-9,.]+)\s*万吨"),
            ("reported_capacity", r"年产[^。\n]{0,30}?绿色铝合\s*金\s*([0-9,.]+)\s*万吨"),
            ("reported_output", rf"(?:公司|本公司|报告期内)[^。\n]{{0,60}}?{output_terms}[^。\n]{{0,30}}(?:产量|生产量|销量|销售量)[^0-9]{{0,8}}([0-9,.]+)\s*万吨"),
        ]
    else:
        label = "电解铝年产规模"
        output_terms = r"(?:铝商品|电解铝|原铝)"
        patterns = [
            ("reported_capacity", r"形成年产[^。\n]{0,80}?电解铝\s*([0-9,.]+)\s*万吨"),
            ("reported_capacity", r"年产[^。\n]{0,20}?电解铝\s*([0-9,.]+)\s*万吨"),
            ("reported_output", rf"(?:公司|本公司|报告期内)[^。\n]{{0,60}}?{output_terms}[^。\n]{{0,30}}(?:产量|生产量|销量|销售量)[^0-9]{{0,8}}([0-9,.]+)\s*万吨"),
        ]
    for basis, pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        wan_ton = parse_report_number_to_float(match.group(1))
        if not wan_ton:
            continue
        start, end = match.span()
        return {
            "basis": basis,
            "label": label.replace("年产规模", "实际产销量") if basis == "reported_output" else label,
            "volumeWanTon": round(wan_ton, 2),
            "volumeTon": round(wan_ton * 10000, 0),
            "sourceText": text[max(0, start - 40) : min(len(text), end + 60)].replace("\n", " ").strip(),
        }
    return None


def extract_report_net_profit_yi(report_payload: dict) -> float | None:
    text = str(report_payload.get("textExcerpt") or "")
    patterns = [
        r"归属于上市公司股东的净利润（元）\s*([0-9,]+\.\d+)",
        r"归属于上市公司股东的净利润[^0-9]{0,20}([0-9,]+\.\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = parse_report_number_to_float(match.group(1))
        if value:
            return round(value / YI, 2)
    return None


def find_main_business_item(main_business_payload: dict, keywords: list[str]) -> dict | None:
    items = main_business_payload.get("items") if isinstance(main_business_payload, dict) else []
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("itemName") or "")
        category = str(item.get("categoryType") or "")
        if "产品" not in category:
            continue
        if any(keyword in name for keyword in keywords):
            return item
    for item in items:
        if isinstance(item, dict) and any(keyword in str(item.get("itemName") or "") for keyword in keywords):
            return item
    return None


def find_product_business_item(main_business_payload: dict, segment_name: str = "") -> dict | None:
    items = main_business_payload.get("items") if isinstance(main_business_payload, dict) else []
    if not isinstance(items, list):
        return None

    segment_text = str(segment_name or "")
    if segment_text:
        for item in items:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("itemName") or "")
            if (
                item_name
                and item_name in segment_text
                and "补充" not in item_name
                and finite_float(item.get("revenue")) > 0
                and finite_float(item.get("cost")) > 0
            ):
                return item

    product_items = [
        item
        for item in items
        if isinstance(item, dict)
        and "产品" in str(item.get("categoryType") or "")
        and "补充" not in str(item.get("itemName") or "")
        and finite_float(item.get("revenue")) > 0
        and finite_float(item.get("cost")) > 0
    ]
    if segment_text:
        for item in product_items:
            item_name = str(item.get("itemName") or "")
            if item_name and (item_name in segment_text or segment_text in item_name):
                return item
            if any(keyword in segment_text for keyword in ["茅台", "白酒", "核心产品"]) and any(
                keyword in item_name for keyword in ["茅台", "酒"]
            ):
                return item
    if product_items:
        return max(product_items, key=lambda item: finite_float(item.get("revenue")))

    usable_items = [
        item
        for item in items
        if isinstance(item, dict)
        and "补充" not in str(item.get("itemName") or "")
        and finite_float(item.get("revenue")) > 0
        and finite_float(item.get("cost")) > 0
    ]
    return max(usable_items, key=lambda item: finite_float(item.get("revenue"))) if usable_items else None


def extract_baijiu_operating_volume(report_payload: dict) -> dict | None:
    text = str(report_payload.get("textExcerpt") or "")
    if not text:
        return None

    sales_match = re.search(
        r"酒类\s+吨\s+(?P<production>[0-9,.]+)\s+(?P<sales>[0-9,.]+)\s+(?P<inventory>[0-9,.]+)",
        text,
    )
    capacity_match = re.search(
        r"茅台酒制酒车间\s+(?P<design>[0-9,.]+)\s+(?P<actual>[0-9,.]+)",
        text,
    )
    if not sales_match and not capacity_match:
        return None

    payload: dict[str, Any] = {
        "basis": "reported_wine_sales_volume",
        "label": "酒类披露销量",
        "source": "年报酒制造行业经营性信息",
    }
    if sales_match:
        production = parse_report_number_to_float(sales_match.group("production")) or 0
        sales = parse_report_number_to_float(sales_match.group("sales")) or 0
        inventory = parse_report_number_to_float(sales_match.group("inventory")) or 0
        payload.update(
            {
                "productionTon": round(production, 2),
                "salesTon": round(sales, 2),
                "inventoryTon": round(inventory, 2),
                "volumeTon": round(sales, 2),
                "volumeWanTon": round(sales / 10000, 4),
            }
        )
    if capacity_match:
        design = parse_report_number_to_float(capacity_match.group("design")) or 0
        actual = parse_report_number_to_float(capacity_match.group("actual")) or 0
        payload.update(
            {
                "moutaiDesignCapacityTon": round(design, 2),
                "moutaiActualBaseWineOutputTon": round(actual, 2),
            }
        )
        if not sales_match:
            payload.update(
                {
                    "basis": "reported_moutai_base_wine_output",
                    "label": "茅台酒基酒实际产能",
                    "volumeTon": round(actual, 2),
                    "volumeWanTon": round(actual / 10000, 4),
                }
            )
    return payload


def extract_baijiu_cost_components(report_payload: dict) -> list[dict]:
    text = str(report_payload.get("textExcerpt") or "")
    components = []
    for name in ["直接材料", "直接人工", "制造费用", "燃料动力", "运输费"]:
        match = re.search(
            rf"{name}\s+(?P<amount>[0-9,.]+)\s+(?P<ratio>[0-9,.]+)\s+(?P<last>[0-9,.]+)\s+(?P<last_ratio>[0-9,.]+)\s+(?P<change>[0-9,.\-]+)",
            text,
        )
        if not match:
            continue
        components.append(
            {
                "name": name,
                "amountYuan": parse_report_number_to_float(match.group("amount")),
                "costRatioPct": parse_report_number_to_float(match.group("ratio")),
                "lastYearAmountYuan": parse_report_number_to_float(match.group("last")),
                "lastYearCostRatioPct": parse_report_number_to_float(match.group("last_ratio")),
                "changePct": parse_report_number_to_float(match.group("change")),
            }
        )
    return components


def build_consumer_product_profit_calculation(
    stock: str,
    main_business_payload: dict,
    annual_report_payload: dict,
    segment_name: str = "",
) -> dict | None:
    business_item = find_product_business_item(main_business_payload, segment_name=segment_name)
    if not business_item:
        return None

    revenue_yi = finite_float(business_item.get("revenue"))
    cost_yi = finite_float(business_item.get("cost"))
    profit_yi = finite_float(business_item.get("profit"))
    if revenue_yi <= 0 or cost_yi <= 0:
        return None

    volume_payload = extract_baijiu_operating_volume(annual_report_payload)
    volume_ton = finite_float((volume_payload or {}).get("volumeTon"))
    if volume_ton <= 0:
        return None

    report_year_match = re.search(r"(20\d{2})", str(business_item.get("reportDate") or ""))
    report_year = int(report_year_match.group(1)) if report_year_match else extract_annual_report_year(annual_report_payload)
    revenue_ratio = finite_float(business_item.get("revenueRatio"), 1.0)
    estimated_product_volume_ton = max(volume_ton * revenue_ratio, 1.0)
    implied_selling_price = revenue_yi * YI / estimated_product_volume_ton
    implied_cost_per_ton = cost_yi * YI / estimated_product_volume_ton
    implied_gross_profit_per_ton = profit_yi * YI / estimated_product_volume_ton if profit_yi > 0 else implied_selling_price - implied_cost_per_ton

    product_profit_items = [
        finite_float(item.get("profit"))
        for item in main_business_payload.get("items", [])
        if isinstance(item, dict) and "产品" in str(item.get("categoryType") or "") and finite_float(item.get("profit")) > 0
    ]
    gross_profit_total_yi = sum(product_profit_items)
    net_profit_yi = extract_report_net_profit_yi(annual_report_payload)
    net_bridge_ratio = None
    if net_profit_yi and gross_profit_total_yi > 0:
        net_bridge_ratio = max(0.0, min(net_profit_yi / gross_profit_total_yi, 1.0))

    cost_components = extract_baijiu_cost_components(annual_report_payload)
    forecast_scenarios = [
        build_profit_forecast_scenario(
            "保守",
            implied_selling_price * 0.98,
            estimated_product_volume_ton * 0.98,
            implied_cost_per_ton * 1.03,
            profit_yi,
            net_bridge_ratio,
            "售价下调2%，销量下调2%，单位成本上调3%，用于观察价格和成本压力。",
        ),
        build_profit_forecast_scenario(
            "中性",
            implied_selling_price,
            estimated_product_volume_ton,
            implied_cost_per_ton * 1.01,
            profit_yi,
            net_bridge_ratio,
            "沿用披露分部收入与估算销量，单位成本小幅上调1%。",
        ),
        build_profit_forecast_scenario(
            "乐观",
            implied_selling_price * 1.02,
            estimated_product_volume_ton * 1.02,
            implied_cost_per_ton,
            profit_yi,
            net_bridge_ratio,
            "售价提升2%，销量提升2%，单位成本维持年报水平。",
        ),
    ]
    neutral_forecast = next(item for item in forecast_scenarios if item["name"] == "中性")

    assumptions = [
        "年报披露了产品分部收入、成本和毛利，因此可先形成分部毛利计算。",
        "年报披露的是酒类整体生产量、销售量、库存量；未直接披露茅台酒单品销售量，因此按收入占比分摊酒类销量作为估算口径。",
        "茅台酒基酒实际产能可用于判断供给约束，但它不是当期瓶装酒销量，不能直接等同为销量。",
        "成本构成目前是酒类整体口径，不是茅台酒单品口径。",
    ]

    prediction_plan = {
        "headline": "未来12个月售价、销量、成本敏感性预测",
        "logic": [
            f"先锁定最新年报中“{business_item.get('itemName')}”分部收入、成本和毛利。",
            "再用酒类披露销售量和该产品收入占比估算产品销量，形成 ASP 与单位成本的可计算口径。",
            "最后用售价、销量、单位成本三档假设，估算未来12个月毛利区间。",
        ],
        "evidence": [
            f"{business_item.get('reportDate')} {business_item.get('itemName')}收入 {round(revenue_yi, 2)} 亿元、成本 {round(cost_yi, 2)} 亿元、毛利 {round(profit_yi, 2)} 亿元。",
            f"年报披露酒类销售量 {round(volume_ton, 2)} 吨，按收入占比估算该分部销量 {round(estimated_product_volume_ton, 2)} 吨。",
            f"估算 ASP {round(implied_selling_price, 2)} 元/吨，单位成本 {round(implied_cost_per_ton, 2)} 元/吨。",
        ],
        "confidence": "medium-low",
        "watchItems": ["茅台酒批价", "直销占比", "经销商库存", "合同负债", "酒类销量", "直接材料/人工成本"],
        "risks": [
            "销量是估算口径，不是公司直接披露的茅台酒单品销量。",
            "吨价不能直接等同瓶价，吨与瓶之间还需要酒度、规格和产品结构换算。",
            "批价、渠道库存和真实终端动销仍需第三方或渠道数据库。",
        ],
    }

    return {
        "status": "calculated",
        "model": "generic_volume_price",
        "segmentName": str(business_item.get("itemName") or segment_name or "主营产品"),
        "reportYear": report_year,
        "sourceData": {
            "businessItem": {
                "itemName": business_item.get("itemName"),
                "reportDate": business_item.get("reportDate"),
                "revenueYi": round(revenue_yi, 2),
                "costYi": round(cost_yi, 2),
                "grossProfitYi": round(profit_yi, 2),
                "grossMargin": business_item.get("grossMargin"),
            },
            "reportedVolumeOrCapacity": volume_payload,
            "baselineMarketPrice": {
                "year": report_year,
                "averageClosePrice": round(implied_selling_price, 2),
                "unit": "元/吨",
                "source": "年报分部收入/估算销量",
            },
            "latestMarketPrice": None,
            "ytdMarketPrice": None,
            "recent90dMarketPrice": None,
            "netProfitYi": net_profit_yi,
            "costComponents": cost_components,
        },
        "derivedInputs": {
            "revenueImpliedSalesVolumeWanTon": round(estimated_product_volume_ton / 10000, 4),
            "conservativeVolumeWanTon": round(estimated_product_volume_ton / 10000, 4),
            "volumeBasis": "reported_total_wine_sales_allocated_by_revenue_ratio",
            "impliedSellingPricePerTon": round(implied_selling_price, 2),
            "impliedCostPerTon": round(implied_cost_per_ton, 2),
            "impliedGrossProfitPerTon": round(implied_gross_profit_per_ton, 2),
            "netProfitToGrossProfitRatio": round(net_bridge_ratio, 4) if net_bridge_ratio is not None else None,
        },
        "result": {
            "baselineGrossProfitYi": round(profit_yi, 2),
            "estimatedGrossProfitYi": neutral_forecast["grossProfitYi"],
            "estimatedGrossProfitDeltaYi": neutral_forecast["grossProfitDeltaYi"],
            "estimatedNetProfitYi": neutral_forecast["netProfitYi"],
            "currentPriceResetGrossProfitYi": round(profit_yi, 2),
            "currentPriceResetGrossProfitDeltaYi": 0,
            "currentPriceResetNetProfitYi": round(profit_yi * net_bridge_ratio, 2) if net_bridge_ratio is not None else None,
            "forecastHorizon": "未来12个月",
            "formula": "未来12个月毛利 = 情景销量 × (情景ASP - 情景单位成本)",
        },
        "forecast12m": forecast_scenarios,
        "assumptions": assumptions,
        "predictionPlan": prediction_plan,
    }


def load_aluminum_latest_price() -> dict | None:
    def fetch() -> pd.DataFrame:
        print("[INFO] Fetching aluminum futures spot, symbol=AL0")
        with temporary_disable_proxy_env():
            return ak.futures_zh_spot(symbol="AL0", market="CF", adjust="0")

    try:
        df = get_ak_dataframe_cached(("futures_zh_spot", "AL0"), fetch)
        if df is None or df.empty:
            return None
        row = df.iloc[0]
        current_price = finite_float(row.get("current_price"))
        if current_price <= 0:
            current_price = finite_float(row.get("last_settle_price"))
        if current_price <= 0:
            return None
        return {
            "symbol": "AL0",
            "name": str(row.get("symbol") or "铝连续"),
            "price": round(current_price, 2),
            "lastSettlePrice": round(finite_float(row.get("last_settle_price")), 2),
            "unit": "元/吨",
            "time": str(row.get("time") or ""),
            "source": "akshare.futures_zh_spot(Sina)",
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        print(f"[WARN] Aluminum latest price unavailable: {exc}")
        return None


def load_aluminum_annual_average_price(year: int | None) -> dict | None:
    if not year:
        return None

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching aluminum futures history, symbol=AL0, year={year}")
        with temporary_disable_proxy_env():
            return ak.futures_main_sina(symbol="AL0", start_date=f"{year}0101", end_date=f"{year}1231")

    try:
        df = get_ak_dataframe_cached(("futures_main_sina", "AL0", year), fetch)
        if df is None or df.empty or "收盘价" not in df.columns:
            return None
        close = pd.to_numeric(df["收盘价"], errors="coerce").dropna()
        close = close[close > 0]
        if close.empty:
            return None
        return {
            "year": year,
            "averageClosePrice": round(float(close.mean()), 2),
            "lastClosePrice": round(float(close.iloc[-1]), 2),
            "tradeDays": int(close.shape[0]),
            "unit": "元/吨",
            "source": "akshare.futures_main_sina(Sina)",
        }
    except Exception as exc:
        print(f"[WARN] Aluminum annual average price unavailable: {exc}")
        return None


def load_aluminum_price_window(start_date: datetime, end_date: datetime, label: str) -> dict | None:
    start = start_date.strftime("%Y%m%d")
    end = end_date.strftime("%Y%m%d")

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching aluminum futures history, symbol=AL0, window={label}")
        with temporary_disable_proxy_env():
            return ak.futures_main_sina(symbol="AL0", start_date=start, end_date=end)

    try:
        df = get_ak_dataframe_cached(("futures_main_sina", "AL0", label, start, end), fetch)
        if df is None or df.empty or "收盘价" not in df.columns:
            return None
        close = pd.to_numeric(df["收盘价"], errors="coerce").dropna()
        close = close[close > 0]
        if close.empty:
            return None
        return {
            "label": label,
            "startDate": start_date.date().isoformat(),
            "endDate": end_date.date().isoformat(),
            "averageClosePrice": round(float(close.mean()), 2),
            "lastClosePrice": round(float(close.iloc[-1]), 2),
            "tradeDays": int(close.shape[0]),
            "unit": "元/吨",
            "source": "akshare.futures_main_sina(Sina)",
        }
    except Exception as exc:
        print(f"[WARN] Aluminum price window unavailable, label={label}: {exc}")
        return None


def normalize_commodity_symbols(symbols: str | None, max_symbols: int = 80) -> list[str]:
    text = str(symbols or "").strip()
    if not text or text.lower() in {"all", "全部", "*"}:
        return DEFAULT_COMMODITY_SYMBOLS[:max_symbols]

    normalized: list[str] = []
    for raw_symbol in re.split(r"[,，\s]+", text):
        symbol = raw_symbol.strip().upper()
        if not symbol:
            continue
        symbol = re.sub(r"\d+$", "", symbol)
        if symbol and symbol not in normalized:
            normalized.append(symbol)

    return normalized[:max_symbols] or DEFAULT_COMMODITY_SYMBOLS[:max_symbols]


def get_commodity_meta(symbol: str) -> dict[str, str]:
    return COMMODITY_FUTURES_SYMBOLS.get(symbol, {"name": symbol, "unit": ""})


def normalize_commodity_days(days: str | None, default: int = 30) -> int:
    try:
        value = int(str(days or default).strip())
    except ValueError:
        value = default
    return max(1, min(value, 365))


def load_commodity_realtime_prices(symbols: list[str]) -> list[dict]:
    if not symbols:
        return []

    futures_symbols = [f"{symbol}0" for symbol in symbols]
    symbol_query = ",".join(futures_symbols)

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching commodity realtime futures, symbols={symbol_query}")
        with temporary_disable_proxy_env():
            return ak.futures_zh_spot(symbol=symbol_query, market="CF", adjust="0")

    try:
        df = get_ak_dataframe_cached(("commodity_realtime_futures", symbol_query), fetch)
    except Exception as exc:
        print(f"[WARN] Commodity realtime futures unavailable, symbols={symbol_query}: {exc}")
        return []

    if df is None or df.empty:
        return []

    items: list[dict] = []
    for index, row in df.reset_index(drop=True).iterrows():
        requested_symbol = symbols[index] if index < len(symbols) else ""
        meta = get_commodity_meta(requested_symbol)
        current_price = finite_float(row.get("current_price"))
        if current_price <= 0:
            current_price = finite_float(row.get("last_settle_price"))
        if current_price <= 0:
            continue
        items.append(
            {
                "symbol": requested_symbol,
                "contract": f"{requested_symbol}0" if requested_symbol else "",
                "name": str(row.get("symbol") or meta["name"]),
                "price": round(current_price, 4),
                "open": round(finite_float(row.get("open")), 4),
                "high": round(finite_float(row.get("high")), 4),
                "low": round(finite_float(row.get("low")), 4),
                "lastSettlePrice": round(finite_float(row.get("last_settle_price")), 4),
                "volume": round(finite_float(row.get("volume")), 4),
                "hold": round(finite_float(row.get("hold")), 4),
                "unit": meta.get("unit", ""),
                "time": str(row.get("time") or ""),
                "source": "akshare.futures_zh_spot(Sina)",
                "fetchedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
    return items


def load_commodity_spot_basis_series(symbols: list[str], start_date: datetime, end_date: datetime) -> list[dict]:
    if not symbols:
        return []

    start = start_date.strftime("%Y%m%d")
    end = end_date.strftime("%Y%m%d")
    vars_list = [symbol for symbol in symbols if symbol]
    vars_key = ",".join(vars_list)

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching commodity spot basis, symbols={vars_key}, start={start}, end={end}")
        with temporary_disable_proxy_env():
            return ak.futures_spot_price_daily(start_day=start, end_day=end, vars_list=vars_list)

    try:
        df = get_ak_dataframe_cached(("commodity_spot_basis_daily", vars_key, start, end), fetch)
    except Exception as exc:
        print(f"[WARN] Commodity spot basis unavailable, symbols={vars_key}: {exc}")
        return []

    if df is None or df.empty:
        return []

    records: list[dict] = []
    for _, row in df.iterrows():
        symbol = str(row.get("symbol") or "").upper()
        meta = get_commodity_meta(symbol)
        records.append(
            {
                "date": str(row.get("date") or ""),
                "symbol": symbol,
                "name": meta.get("name", symbol),
                "spotPrice": round(finite_float(row.get("spot_price")), 4),
                "nearContract": str(row.get("near_contract") or ""),
                "nearContractPrice": round(finite_float(row.get("near_contract_price")), 4),
                "dominantContract": str(row.get("dominant_contract") or ""),
                "dominantContractPrice": round(finite_float(row.get("dominant_contract_price")), 4),
                "nearBasis": round(finite_float(row.get("near_basis")), 4),
                "dominantBasis": round(finite_float(row.get("dom_basis")), 4),
                "nearBasisRate": round(finite_float(row.get("near_basis_rate")), 6),
                "dominantBasisRate": round(finite_float(row.get("dom_basis_rate")), 6),
                "unit": meta.get("unit", ""),
                "source": "akshare.futures_spot_price_daily(100ppi)",
            }
        )
    return records


def build_commodity_prices_payload(symbols: str | None = None, days: str | None = None) -> dict:
    normalized_symbols = normalize_commodity_symbols(symbols)
    normalized_days = normalize_commodity_days(days)
    today = datetime.now(timezone.utc)
    start_date = today - timedelta(days=normalized_days)

    with ThreadPoolExecutor(max_workers=2) as executor:
        realtime_future = executor.submit(load_commodity_realtime_prices, normalized_symbols)
        spot_basis_future = executor.submit(load_commodity_spot_basis_series, normalized_symbols, start_date, today)
        realtime = realtime_future.result()
        spot_basis_series = spot_basis_future.result()

    latest_spot_basis_by_symbol: dict[str, dict] = {}
    for item in spot_basis_series:
        symbol = item.get("symbol")
        if symbol:
            latest_spot_basis_by_symbol[symbol] = item

    realtime_symbols = {item.get("symbol") for item in realtime}
    spot_basis_symbols = set(latest_spot_basis_by_symbol.keys())
    data_gaps = []
    for symbol in normalized_symbols:
        missing_parts = []
        if symbol not in realtime_symbols:
            missing_parts.append("实时连续期货")
        if symbol not in spot_basis_symbols:
            missing_parts.append("现货价/基差")
        if missing_parts:
            data_gaps.append(
                {
                    "symbol": symbol,
                    "name": get_commodity_meta(symbol).get("name", symbol),
                    "missing": missing_parts,
                }
            )

    status = "ok" if not data_gaps else "partial" if realtime or spot_basis_series else "empty"
    return {
        "tool": "commodity_prices",
        "status": status,
        "symbols": normalized_symbols,
        "days": normalized_days,
        "metrics": {
            "realtimeFutures": realtime,
            "latestSpotBasis": list(latest_spot_basis_by_symbol.values()),
            "spotBasisSeries": spot_basis_series,
        },
        "source": [
            "akshare.futures_zh_spot(Sina)",
            "akshare.futures_spot_price_daily(100ppi)",
        ],
        "dataGaps": data_gaps,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }


def find_table_date_column(df: pd.DataFrame) -> str | None:
    for column in df.columns:
        text = str(column).lower()
        if any(keyword in text for keyword in ["日期", "时间", "月份", "date", "time", "month"]):
            return str(column)
    return None


def prepare_industry_table(df: pd.DataFrame, max_age_days: int | None = None) -> tuple[pd.DataFrame, str | None]:
    if df is None or df.empty:
        return df, None
    date_column = find_table_date_column(df)
    if not date_column or date_column not in df.columns:
        return df, None

    cleaned = df.copy()
    parsed_dates = pd.to_datetime(cleaned[date_column], errors="coerce")
    today_ts = pd.Timestamp(datetime.now().date())
    cleaned = cleaned[(parsed_dates.isna()) | (parsed_dates <= today_ts)].copy()
    parsed_dates = pd.to_datetime(cleaned[date_column], errors="coerce")
    if parsed_dates.notna().any():
        cleaned = cleaned.assign(__date_sort=parsed_dates).sort_values("__date_sort").drop(columns=["__date_sort"])
        latest_date = parsed_dates.max().date()
        if max_age_days is not None and latest_date < today_ts.date() - timedelta(days=max_age_days):
            return cleaned.iloc[0:0], f"数据最新日期为 {latest_date.isoformat()}，已超过 {max_age_days} 天，暂不作为当前监控指标展示。"
    return cleaned, None


def industry_cache_day() -> str:
    return datetime.now().date().isoformat()


def safe_ak_table(tool_key: str, builder: Callable[[], pd.DataFrame], limit: int = 12, max_age_days: int | None = None) -> dict:
    try:
        df = get_ak_dataframe_cached((tool_key, industry_cache_day()), builder)
        df, stale_error = prepare_industry_table(df, max_age_days=max_age_days)
        if stale_error:
            return {"status": "stale", "error": stale_error, "columns": [str(column) for column in df.columns], "rows": [], "rowCount": 0}
        return {
            "status": "ok" if df is not None and not df.empty else "empty",
            **dataframe_preview(df, limit=limit),
        }
    except Exception as exc:
        print(f"[WARN] Industry table unavailable, key={tool_key}: {exc}")
        return {"status": "error", "error": str(exc), "columns": [], "rows": []}


def build_industry_table_group(tasks: dict[str, Callable[[], dict]], max_workers: int = 4) -> dict:
    if not tasks:
        return {}
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(tasks), max_workers)) as executor:
        future_map = {executor.submit(builder): key for key, builder in tasks.items()}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                print(f"[WARN] Industry table task failed, key={key}: {exc}")
                results[key] = {"status": "error", "error": str(exc), "columns": [], "rows": []}
    return {key: results.get(key, {"status": "empty", "columns": [], "rows": []}) for key in tasks}


def build_nbs_operating_indicators() -> dict:
    return {
        "status": "partial",
        "source": "AKShare / 国家统计局及公开宏观经营指标",
        "tables": build_industry_table_group({
            "industrialProductionYoy": lambda: safe_ak_table(
                "nbs_industrial_production_yoy",
                lambda: ak.macro_china_industrial_production_yoy(),
                limit=12,
            ),
            "industrialValueAdded": lambda: safe_ak_table(
                "nbs_industrial_value_added",
                lambda: ak.macro_china_gyzjz(),
                limit=12,
            ),
            "manufacturingPmi": lambda: safe_ak_table("nbs_manufacturing_pmi", lambda: ak.macro_china_pmi(), limit=12),
            "ppi": lambda: safe_ak_table("nbs_ppi", lambda: ak.macro_china_ppi(), limit=12),
            "electricityConsumption": lambda: safe_ak_table(
                "nbs_electricity_consumption",
                lambda: ak.macro_china_society_electricity(),
                limit=12,
            ),
            "enterpriseBoomIndex": lambda: safe_ak_table(
                "nbs_enterprise_boom_index",
                lambda: ak.macro_china_enterprise_boom_index(),
                limit=12,
            ),
        }, max_workers=4),
        "dataGaps": ["当前为宏观经营景气和工业需求代理指标，尚未映射到细分行业产量、库存和订单口径。"],
    }


def build_customs_trade_indicators() -> dict:
    return {
        "status": "partial",
        "source": "AKShare / 海关进出口公开指标",
        "tables": build_industry_table_group({
            "customsImportExportOverview": lambda: safe_ak_table(
                "customs_import_export_overview",
                lambda: ak.macro_china_hgjck(),
                limit=12,
            ),
            "exportsYoyUsd": lambda: safe_ak_table("customs_exports_yoy_usd", lambda: ak.macro_china_exports_yoy(), limit=12),
            "importsYoyUsd": lambda: safe_ak_table("customs_imports_yoy_usd", lambda: ak.macro_china_imports_yoy(), limit=12),
            "tradeBalanceUsd": lambda: safe_ak_table(
                "customs_trade_balance_usd",
                lambda: ak.macro_china_trade_balance(),
                limit=12,
            ),
        }, max_workers=4),
        "dataGaps": ["当前为总量进出口和同比指标，尚未接入 HS 编码、目的地、商品分项或公司出口口径。"],
    }


def build_energy_cost_indicators() -> dict:
    def format_market_date(value) -> str:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.notna(parsed):
            return parsed.date().isoformat()
        return str(value or datetime.now().date())

    def fetch_foreign_future_series(symbol: str, name: str, unit: str) -> pd.DataFrame:
        rows = []
        hist_df = ak.futures_foreign_hist(symbol=symbol)
        if hist_df is not None and not hist_df.empty:
            for _, row in hist_df.tail(90).iterrows():
                rows.append(
                    {
                        "日期": format_market_date(row.get("date")),
                        "名称": name,
                        "价格": round(finite_float(row.get("close")), 4),
                        "开盘": round(finite_float(row.get("open")), 4),
                        "最高": round(finite_float(row.get("high")), 4),
                        "最低": round(finite_float(row.get("low")), 4),
                        "成交量": round(finite_float(row.get("volume")), 4),
                        "单位": unit,
                        "来源": "日线收盘",
                    }
                )

        try:
            realtime_df = ak.futures_foreign_commodity_realtime(symbol=symbol)
            if realtime_df is not None and not realtime_df.empty:
                row = realtime_df.iloc[0]
                quote_date = format_market_date(row.get("日期") or datetime.now().date())
                rows = [item for item in rows if str(item.get("日期")) != quote_date]
                rows.append(
                    {
                        "日期": quote_date,
                        "名称": str(row.get("名称") or name),
                        "价格": round(finite_float(row.get("最新价")), 4),
                        "开盘": round(finite_float(row.get("开盘价")), 4),
                        "最高": round(finite_float(row.get("最高价")), 4),
                        "最低": round(finite_float(row.get("最低价")), 4),
                        "涨跌额": round(finite_float(row.get("涨跌额")), 4),
                        "涨跌幅": round(finite_float(row.get("涨跌幅")), 4),
                        "行情时间": str(row.get("行情时间") or ""),
                        "单位": unit,
                        "来源": "实时行情",
                    }
                )
        except Exception as exc:
            print(f"[WARN] Foreign futures realtime unavailable, symbol={symbol}: {exc}")

        return pd.DataFrame(rows)

    return {
        "status": "partial",
        "source": "AKShare / 外盘原油与碳排放期货行情",
        "tables": build_industry_table_group({
            "wtiCrudeOil": lambda: safe_ak_table(
                "foreign_future_wti_crude_v2",
                lambda: fetch_foreign_future_series("CL", "WTI 原油", "美元/桶"),
                limit=45,
                max_age_days=7,
            ),
            "brentCrudeOil": lambda: safe_ak_table(
                "foreign_future_brent_crude_v2",
                lambda: fetch_foreign_future_series("OIL", "布伦特原油", "美元/桶"),
                limit=45,
                max_age_days=7,
            ),
            "euaCarbon": lambda: safe_ak_table(
                "foreign_future_eua_carbon_v2",
                lambda: fetch_foreign_future_series("EUA", "欧洲碳排放 EUA", "欧元/吨"),
                limit=45,
                max_age_days=7,
            ),
        }, max_workers=3),
        "dataGaps": ["当前展示 WTI、布伦特和 EUA 碳排放期货行情；国内碳市场分交易所数据源稳定性较差，暂不放入默认监控。"],
    }


def extract_report_operating_metrics(report_text: str, metric_patterns: dict[str, list[str]]) -> dict[str, list[dict]]:
    metrics: dict[str, list[dict]] = {}
    text = str(report_text or "")
    compact_text = " ".join(text.split())
    for metric, patterns in metric_patterns.items():
        matches: list[dict] = []
        for pattern in patterns:
            for match in re.finditer(pattern, compact_text, flags=re.IGNORECASE):
                value = parse_report_number_to_float(match.group("value")) if "value" in match.groupdict() else None
                unit = match.group("unit") if "unit" in match.groupdict() else ""
                start, end = match.span()
                matches.append(
                    {
                        "value": value,
                        "unit": unit,
                        "sourceText": compact_text[max(0, start - 80) : min(len(compact_text), end + 120)],
                    }
                )
                if len(matches) >= 8:
                    break
            if len(matches) >= 8:
                break
        metrics[metric] = matches
    return metrics


def summarize_business_items_for_operating_metrics(main_business_payload: dict) -> list[dict]:
    items = main_business_payload.get("items") if isinstance(main_business_payload, dict) else []
    if not isinstance(items, list):
        return []
    summarized = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        summarized.append(
            {
                "categoryType": item.get("categoryType"),
                "itemName": item.get("itemName"),
                "revenue": item.get("revenue"),
                "cost": item.get("cost"),
                "profit": item.get("profit"),
                "grossMargin": item.get("grossMargin"),
                "revenueRatio": item.get("revenueRatio"),
            }
        )
    return summarized


def build_baijiu_operating_metrics(stock: str, main_business_payload: dict, annual_report_payload: dict) -> dict:
    report_text = str(annual_report_payload.get("textExcerpt") or "")
    metric_patterns = {
        "salesVolumeOrProduction": [
            r"(?P<label>销量|销售量|产量|生产量|基酒产量)[^0-9]{0,20}(?P<value>[0-9,.]+)\s*(?P<unit>吨|万吨|千升|万千升|瓶|万瓶)",
            r"(?P<value>[0-9,.]+)\s*(?P<unit>吨|万吨|千升|万千升|瓶|万瓶)[^。]{0,20}(?P<label>销量|销售量|产量|生产量|基酒产量)",
        ],
        "dealerOrChannel": [
            r"(?P<label>经销商|批发代理|直销|渠道)[^。]{0,40}(?P<value>[0-9,.]+)\s*(?P<unit>家|%|％|亿元|亿)",
        ],
        "inventoryOrContractLiability": [
            r"(?P<label>库存|合同负债|预收款|预收账款)[^。]{0,40}(?P<value>[0-9,.]+)\s*(?P<unit>亿元|亿|万元|万)",
        ],
        "expenseRate": [
            r"(?P<label>销售费用率|管理费用率|研发费用率|财务费用率)[^0-9]{0,20}(?P<value>[0-9,.]+)\s*(?P<unit>%|％)",
        ],
    }
    extracted = extract_report_operating_metrics(report_text, metric_patterns)
    data_gaps = []
    if not extracted["salesVolumeOrProduction"]:
        data_gaps.append("缺少稳定的销量/产量披露，ASP 和单位成本只能在披露量存在时反推。")
    data_gaps.extend(
        [
            "未接入第三方批价、渠道动销和经销商库存数据库。",
            "费用率目前只能从公司整体财报或年报文本抽取，尚不能稳定按产品/渠道拆分。",
        ]
    )
    return {
        "tool": "baijiu_operating_metrics",
        "status": "partial",
        "stock": stock,
        "metrics": {
            "macroOperatingIndicators": build_nbs_operating_indicators(),
            "customsTradeIndicators": build_customs_trade_indicators(),
        },
        "source": ["AKShare 宏观经营指标", "海关公开指标"],
        "dataGaps": data_gaps,
    }


def build_nonferrous_chemical_metrics(stock: str, main_business_payload: dict, annual_report_payload: dict) -> dict:
    commodity_symbols = "AL,AO,CU,ZN,PB,NI,SN,SC,FU,BU,UR,SA,MA,FG,TA,EG,EB,PP,L,V,PX,SH,LC,I,J,JM"
    report_text = str(annual_report_payload.get("textExcerpt") or "")
    metric_patterns = {
        "productionOrSales": [
            r"(?P<label>产量|销量|生产量|销售量|产能)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>吨|万吨|千吨|万吨/年)",
            r"(?P<value>[0-9,.]+)\s*(?P<unit>吨|万吨|千吨|万吨/年)[^。]{0,30}(?P<label>产量|销量|生产量|销售量|产能)",
        ],
        "unitCostOrPrice": [
            r"(?P<label>单位成本|单吨成本|平均售价|销售均价)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>元/吨|元)",
        ],
    }
    metrics = build_industry_table_group(
        {
            "macroOperatingIndicators": lambda: build_nbs_operating_indicators(),
            "customsTradeIndicators": lambda: build_customs_trade_indicators(),
            "energyCostIndicators": lambda: build_energy_cost_indicators(),
            "commodityPrices": lambda: build_commodity_prices_payload(symbols=commodity_symbols, days="30"),
        },
        max_workers=4,
    )
    return {
        "tool": "nonferrous_chemical_metrics",
        "status": "partial",
        "stock": stock,
        "metrics": metrics,
        "source": ["AKShare 商品期货/现货基差", "AKShare 能源成本", "海关公开指标"],
        "dataGaps": ["电力成本、阳极、石油焦、煤沥青等专用成本项尚未逐项接入；产品-原料价差序列还未按具体行业模型封装。"],
    }


def build_shipping_metrics(stock: str, main_business_payload: dict, annual_report_payload: dict) -> dict:
    tables = {
        "bdi": safe_ak_table("shipping_bdi", lambda: ak.macro_shipping_bdi()),
        "bci": safe_ak_table("shipping_bci", lambda: ak.macro_shipping_bci()),
        "bpi": safe_ak_table("shipping_bpi", lambda: ak.macro_shipping_bpi()),
        "bcti": safe_ak_table("shipping_bcti", lambda: ak.macro_shipping_bcti()),
        "bdti": safe_ak_table("shipping_bdti", lambda: ak.macro_china_bdti_index()),
        "chinaFreightIndex": safe_ak_table("shipping_china_freight", lambda: ak.macro_china_freight_index()),
    }
    report_text = str(annual_report_payload.get("textExcerpt") or "")
    metric_patterns = {
        "teuOrThroughput": [
            r"(?P<label>TEU|箱量|吞吐量|货运量|集装箱运输量)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>万TEU|TEU|万吨|万箱|箱)",
            r"(?P<value>[0-9,.]+)\s*(?P<unit>万TEU|TEU|万吨|万箱|箱)[^。]{0,30}(?P<label>TEU|箱量|吞吐量|货运量|集装箱运输量)",
        ],
        "unitRevenueCost": [
            r"(?P<label>单箱收入|单箱成本|单箱运费)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>元/TEU|美元/FEU|元|美元)",
        ],
    }
    return {
        "tool": "shipping_metrics",
        "status": "partial",
        "stock": stock,
        "metrics": {
            "macroOperatingIndicators": build_nbs_operating_indicators(),
            "customsTradeIndicators": build_customs_trade_indicators(),
            "energyCostIndicators": build_energy_cost_indicators(),
            "freightIndices": tables,
            "fuelPrices": build_commodity_prices_payload(symbols="SC,FU,LU", days="30"),
        },
        "source": ["AKShare 航运宏观指数", "AKShare 商品价格"],
        "dataGaps": ["未接入 SCFI/CCFI 官方逐航线明细、长协运价、船队运力和港口 AIS 拥堵数据。"],
    }


def build_financial_sector_metrics(stock: str, years: int, annual_report_payload: dict | None = None) -> dict:
    report_text = str((annual_report_payload or {}).get("textExcerpt") or "")
    metric_patterns = {
        "bankQuality": [
            r"(?P<label>净息差|不良贷款率|不良率|拨备覆盖率|资本充足率|核心一级资本充足率)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>%|％|BP|bp)?",
        ],
        "aumOrCommission": [
            r"(?P<label>AUM|资产管理规模|代理买卖证券业务净收入|佣金率|手续费及佣金净收入)[^0-9]{0,40}(?P<value>[0-9,.]+)\s*(?P<unit>亿元|亿|万元|%|％)?",
        ],
        "insuranceProfit": [
            r"(?P<label>承保利润|综合成本率|原保险保费收入|新业务价值)[^0-9]{0,40}(?P<value>[0-9,.]+)\s*(?P<unit>亿元|亿|万元|%|％)?",
        ],
    }
    return {
        "tool": "financial_sector_metrics",
        "status": "partial",
        "stock": stock,
        "metrics": {
            "macroOperatingIndicators": build_nbs_operating_indicators(),
            "customsTradeIndicators": build_customs_trade_indicators(),
            "lpr": safe_ak_table("macro_china_lpr", lambda: ak.macro_china_lpr(), limit=12),
            "moneySupply": safe_ak_table("macro_china_money_supply", lambda: ak.macro_china_money_supply(), limit=12),
            "newCredit": safe_ak_table("macro_china_new_financial_credit", lambda: ak.macro_china_new_financial_credit(), limit=12),
            "insuranceIncome": safe_ak_table("macro_china_insurance_income", lambda: ak.macro_china_insurance_income(), limit=12),
        },
        "source": ["AKShare 宏观利率/保险数据", "AKShare 货币供应/社融/保险数据"],
        "dataGaps": ["净息差、不良率、拨备覆盖率、AUM、佣金率等公司维度指标需要稳定行业数据源。"],
    }


def build_game_internet_metrics(stock: str, main_business_payload: dict, annual_report_payload: dict) -> dict:
    report_text = str(annual_report_payload.get("textExcerpt") or "")
    metric_patterns = {
        "users": [
            r"(?P<label>DAU|MAU|月活跃用户|日活跃用户|付费用户)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>万|万人|亿|人)",
        ],
        "monetization": [
            r"(?P<label>ARPU|付费率|流水|充值流水|广告收入|买量成本)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>元|万元|亿元|%|％)",
        ],
        "licenses": [
            r"(?P<label>版号|游戏版号|上线|公测)[^。]{0,80}(?P<value>[0-9,.]+)?\s*(?P<unit>款|个)?",
        ],
    }
    return {
        "tool": "game_internet_metrics",
        "status": "partial",
        "stock": stock,
        "metrics": {
            "macroOperatingIndicators": build_nbs_operating_indicators(),
            "customsTradeIndicators": build_customs_trade_indicators(),
            "movieBoxOfficeProxy": safe_ak_table("movie_boxoffice_realtime", lambda: ak.movie_boxoffice_realtime(), limit=10),
        },
        "source": ["AKShare 电影票房代理数据", "AKShare 宏观经营指标"],
        "dataGaps": ["游戏 DAU/MAU、ARPU、买量成本、流水和版号生命周期缺少稳定免费标准源，当前主要依赖公司披露文本。"],
    }


def build_auto_new_energy_metrics(stock: str, main_business_payload: dict, annual_report_payload: dict) -> dict:
    report_text = str(annual_report_payload.get("textExcerpt") or "")
    metric_patterns = {
        "vehicleSales": [
            r"(?P<label>销量|交付量|产量|出口量)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>辆|万辆|台|万台)",
            r"(?P<value>[0-9,.]+)\s*(?P<unit>辆|万辆|台|万台)[^。]{0,30}(?P<label>销量|交付量|产量|出口量)",
        ],
        "unitEconomics": [
            r"(?P<label>单车收入|单车毛利|自行车收入|平均售价)[^0-9]{0,30}(?P<value>[0-9,.]+)\s*(?P<unit>元|万元|亿元)",
        ],
    }
    return {
        "tool": "auto_new_energy_metrics",
        "status": "partial",
        "stock": stock,
        "metrics": {
            "macroOperatingIndicators": build_nbs_operating_indicators(),
            "customsTradeIndicators": build_customs_trade_indicators(),
            "energyCostIndicators": build_energy_cost_indicators(),
            "cpcaTotalRetail": safe_ak_table("car_market_total_retail", lambda: ak.car_market_total_cpca(indicator="零售"), limit=12),
            "cpcaTotalWholesale": safe_ak_table("car_market_total_wholesale", lambda: ak.car_market_total_cpca(indicator="批发"), limit=12),
            "cpcaTotalExport": safe_ak_table("car_market_total_export", lambda: ak.car_market_total_cpca(indicator="出口"), limit=12),
            "cpcaNewEnergy": safe_ak_table("car_market_fuel_new_energy", lambda: ak.car_market_fuel_cpca(symbol="整体市场"), limit=12),
            "batteryMaterials": build_commodity_prices_payload(symbols="LC,NI,CU,AL,SI", days="30"),
        },
        "source": ["AKShare 乘联会/盖世汽车", "AKShare 商品价格"],
        "dataGaps": ["车型结构、单车收入、单车毛利和出口分车型数据尚未按公司维度标准化。"],
    }


def build_industry_data_payload(industries: str | None = None, years: str | None = "8") -> dict:
    payload = build_industry_data_payload_from_service(
        industries=industries,
        years=years,
        deps=IndustryDataDeps(
            normalize_years=normalize_years,
            build_baijiu_operating_metrics=build_baijiu_operating_metrics,
            build_nonferrous_chemical_metrics=build_nonferrous_chemical_metrics,
            build_shipping_metrics=build_shipping_metrics,
            build_financial_sector_metrics=build_financial_sector_metrics,
            build_game_internet_metrics=build_game_internet_metrics,
            build_auto_new_energy_metrics=build_auto_new_energy_metrics,
        ),
    )
    payload["fetchedAt"] = datetime.now(timezone.utc).isoformat()
    return payload


def build_profit_forecast_scenario(
    name: str,
    price: float,
    volume_ton: float,
    cost_per_ton: float,
    baseline_gross_profit_yi: float,
    net_bridge_ratio: float | None,
    reason: str,
) -> dict:
    gross_profit_yi = volume_ton * (price - cost_per_ton) / YI
    net_profit_yi = gross_profit_yi * net_bridge_ratio if net_bridge_ratio is not None else None
    return {
        "name": name,
        "forecastHorizon": "未来12个月",
        "pricePerTon": round(price, 2),
        "volumeWanTon": round(volume_ton / 10000, 2),
        "costPerTon": round(cost_per_ton, 2),
        "grossProfitYi": round(gross_profit_yi, 2),
        "grossProfitDeltaYi": round(gross_profit_yi - baseline_gross_profit_yi, 2),
        "netProfitYi": round(net_profit_yi, 2) if net_profit_yi is not None else None,
        "reason": reason,
    }


def build_aluminum_profit_calculation(
    stock: str,
    main_business_payload: dict,
    annual_report_payload: dict,
    segment_name: str = "",
) -> dict | None:
    is_primary_aluminum = any(keyword in segment_name for keyword in ["电解铝", "冶炼", "原铝"])
    is_processing = not is_primary_aluminum and any(keyword in segment_name for keyword in ["铝加工", "铝材", "铝合金"])
    product_kind = "aluminum_processing" if is_processing else "primary_aluminum"
    business_item = find_main_business_item(
        main_business_payload,
        ["铝加工产品", "铝材加工", "绿色铝合金", "铝合金"] if is_processing else ["电解铝", "原铝", "铝产品"],
    )
    if not business_item:
        return None

    revenue_yi = finite_float(business_item.get("revenue"))
    cost_yi = finite_float(business_item.get("cost"))
    profit_yi = finite_float(business_item.get("profit"))
    if revenue_yi <= 0 or cost_yi <= 0:
        return None

    report_year_match = re.search(r"(20\d{2})", str(business_item.get("reportDate") or ""))
    report_year = int(report_year_match.group(1)) if report_year_match else extract_annual_report_year(annual_report_payload)
    latest_price = load_aluminum_latest_price()
    annual_price = load_aluminum_annual_average_price(report_year)
    baseline_price = finite_float((annual_price or {}).get("averageClosePrice")) or finite_float((latest_price or {}).get("price"))
    latest_price_value = finite_float((latest_price or {}).get("price"))
    if baseline_price <= 0 or latest_price_value <= 0:
        return None
    today = datetime.now()
    ytd_price = load_aluminum_price_window(datetime(today.year, 1, 1), today, "ytd")
    recent90_price = load_aluminum_price_window(today - timedelta(days=90), today, "recent_90d")

    capacity = extract_aluminum_capacity_from_report(annual_report_payload, product_kind=product_kind)
    reported_volume_ton = finite_float((capacity or {}).get("volumeTon"))
    revenue_implied_volume_ton = revenue_yi * YI / baseline_price
    conservative_volume_ton = revenue_implied_volume_ton
    volume_basis = "revenue_implied_sales_volume"
    if reported_volume_ton > 0:
        conservative_volume_ton = min(reported_volume_ton, revenue_implied_volume_ton)
        volume_basis = "min_reported_capacity_and_revenue_implied_sales"
    if conservative_volume_ton <= 0:
        return None

    implied_selling_price = revenue_yi * YI / conservative_volume_ton
    implied_cost_per_ton = cost_yi * YI / conservative_volume_ton
    implied_gross_profit_per_ton = profit_yi * YI / conservative_volume_ton if profit_yi > 0 else implied_selling_price - implied_cost_per_ton
    estimated_gross_profit_yi = latest_price_value * conservative_volume_ton / YI - cost_yi
    estimated_gross_profit_delta_yi = estimated_gross_profit_yi - profit_yi
    product_profit_items = [
        finite_float(item.get("profit"))
        for item in main_business_payload.get("items", [])
        if isinstance(item, dict) and "产品" in str(item.get("categoryType") or "") and finite_float(item.get("profit")) > 0
    ]
    gross_profit_total_yi = sum(product_profit_items)
    net_profit_yi = extract_report_net_profit_yi(annual_report_payload)
    net_bridge_ratio = None
    estimated_net_profit_yi = None
    if net_profit_yi and gross_profit_total_yi > 0:
        net_bridge_ratio = max(0.0, min(net_profit_yi / gross_profit_total_yi, 1.0))
        estimated_net_profit_yi = estimated_gross_profit_yi * net_bridge_ratio

    ytd_price_value = finite_float((ytd_price or {}).get("averageClosePrice"))
    recent90_price_value = finite_float((recent90_price or {}).get("averageClosePrice"))
    price_candidates = [value for value in [latest_price_value, ytd_price_value, recent90_price_value] if value > 0]
    conservative_price = min(price_candidates) if price_candidates else latest_price_value
    neutral_price = recent90_price_value or ytd_price_value or latest_price_value
    optimistic_price = max(price_candidates) if price_candidates else latest_price_value
    capacity_limited_volume = reported_volume_ton if reported_volume_ton > 0 else conservative_volume_ton * 1.03
    forecast_scenarios = [
        build_profit_forecast_scenario(
            "保守",
            conservative_price,
            min(capacity_limited_volume, conservative_volume_ton * 0.98),
            implied_cost_per_ton * 1.03,
            profit_yi,
            net_bridge_ratio,
            "价格取年初以来、近90日和最新价中的低值；销量按保守销量下调2%；单吨成本上调3%。",
        ),
        build_profit_forecast_scenario(
            "中性",
            neutral_price,
            min(capacity_limited_volume, conservative_volume_ton),
            implied_cost_per_ton * 1.01,
            profit_yi,
            net_bridge_ratio,
            "价格取近90日均价；销量沿用保守销量；单吨成本上调1%。",
        ),
        build_profit_forecast_scenario(
            "乐观",
            optimistic_price,
            min(capacity_limited_volume, conservative_volume_ton * 1.03),
            implied_cost_per_ton,
            profit_yi,
            net_bridge_ratio,
            "价格取年初以来、近90日和最新价中的高值；销量在产能约束内提升3%；单吨成本维持年报水平。",
        ),
    ]
    neutral_forecast = next(item for item in forecast_scenarios if item["name"] == "中性")

    assumptions = [
        "销量采用保守口径：按披露产能与收入/报告期铝均价反推销量取较低值。",
        "单吨成本沿用最新年报分部成本，不主动假设氧化铝、电力、阳极等成本下降。",
        "最新铝价使用 AL0 铝连续行情，报告期基准价使用 AL0 年度收盘均价。",
        "未来12个月预测采用三情景，不把单一最新价当作全年均价。",
    ]
    if capacity and capacity.get("basis") == "reported_capacity":
        assumptions.append(f"年报披露的是{capacity.get('label')}而非明确销量，因此不会直接把产能全量当成销量。")

    prediction_plan = {
        "headline": "未来12个月铝价驱动利润预测",
        "logic": [
            f"先锁定最新年报中“{business_item.get('itemName')}”分部的收入、成本和毛利，避免用公司总收入混算。",
            "再用报告期 AL0 年度均价反推该分部可解释销量，并与年报披露产能取较低值，避免把产能当满产销量。",
            "最后用年初以来均价、近90日均价和最新价组合成保守/中性/乐观三档，预测未来12个月毛利区间。",
        ],
        "evidence": [
            f"{business_item.get('reportDate')} {business_item.get('itemName')}收入 {round(revenue_yi, 2)} 亿元、成本 {round(cost_yi, 2)} 亿元、毛利 {round(profit_yi, 2)} 亿元。",
            f"{report_year} 年 AL0 收盘均价 {round(baseline_price, 2)} 元/吨，最新 AL0 {round(latest_price_value, 2)} 元/吨。",
            f"年初以来 AL0 均价 {round(ytd_price_value, 2) if ytd_price_value else '-'} 元/吨，近90日均价 {round(recent90_price_value, 2) if recent90_price_value else '-'} 元/吨。",
            f"保守销量 {round(conservative_volume_ton / 10000, 2)} 万吨，反推单吨成本 {round(implied_cost_per_ton, 2)} 元/吨。",
        ],
        "confidence": "medium",
        "watchItems": ["AL0/沪铝价格", "氧化铝价格", "云南电力成本", "阳极炭素价格", "公司实际产销量披露"],
        "risks": [
            "铝加工产品售价不完全等同原铝价格，深加工费和产品结构会影响弹性。",
            "如果氧化铝、电力、阳极等成本同步上涨，毛利改善会低于只替换铝价的结果。",
            "年报披露产能不是实际销量，当前用收入反推销量作为保守替代。",
        ],
    }

    return {
        "status": "calculated",
        "model": "aluminum_commodity",
        "segmentName": str(business_item.get("itemName") or "电解铝"),
        "reportYear": report_year,
        "sourceData": {
            "businessItem": {
                "itemName": business_item.get("itemName"),
                "reportDate": business_item.get("reportDate"),
                "revenueYi": round(revenue_yi, 2),
                "costYi": round(cost_yi, 2),
                "grossProfitYi": round(profit_yi, 2),
                "grossMargin": business_item.get("grossMargin"),
            },
            "reportedVolumeOrCapacity": capacity,
            "baselineMarketPrice": annual_price,
            "latestMarketPrice": latest_price,
            "ytdMarketPrice": ytd_price,
            "recent90dMarketPrice": recent90_price,
            "netProfitYi": net_profit_yi,
        },
        "derivedInputs": {
            "revenueImpliedSalesVolumeWanTon": round(revenue_implied_volume_ton / 10000, 2),
            "conservativeVolumeWanTon": round(conservative_volume_ton / 10000, 2),
            "volumeBasis": volume_basis,
            "impliedSellingPricePerTon": round(implied_selling_price, 2),
            "impliedCostPerTon": round(implied_cost_per_ton, 2),
            "impliedGrossProfitPerTon": round(implied_gross_profit_per_ton, 2),
            "netProfitToGrossProfitRatio": round(net_bridge_ratio, 4) if net_bridge_ratio is not None else None,
        },
        "result": {
            "baselineGrossProfitYi": round(profit_yi, 2),
            "estimatedGrossProfitYi": neutral_forecast["grossProfitYi"],
            "estimatedGrossProfitDeltaYi": neutral_forecast["grossProfitDeltaYi"],
            "estimatedNetProfitYi": neutral_forecast["netProfitYi"],
            "currentPriceResetGrossProfitYi": round(estimated_gross_profit_yi, 2),
            "currentPriceResetGrossProfitDeltaYi": round(estimated_gross_profit_delta_yi, 2),
            "currentPriceResetNetProfitYi": round(estimated_net_profit_yi, 2) if estimated_net_profit_yi is not None else None,
            "forecastHorizon": "未来12个月",
            "formula": "未来12个月毛利 = 情景销量 × (情景铝价 - 情景单吨成本)",
        },
        "forecast12m": forecast_scenarios,
        "assumptions": assumptions,
        "predictionPlan": prediction_plan,
    }


def attach_profit_driver_calculations(
    payload: dict,
    stock: str,
    main_business_payload: dict,
    annual_report_payload: dict,
) -> dict:
    segments = payload.get("segments") if isinstance(payload.get("segments"), list) else []
    calculations: list[dict] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_name = str(segment.get("segmentName") or "")
        driver_model = str(segment.get("driverModel") or "")
        if driver_model == "aluminum_commodity":
            segment_calculation = build_aluminum_profit_calculation(
                stock,
                main_business_payload,
                annual_report_payload,
                segment_name=segment_name,
            )
        elif driver_model in {"generic_volume_price", "generic_spread"}:
            segment_calculation = build_consumer_product_profit_calculation(
                stock,
                main_business_payload,
                annual_report_payload,
                segment_name=segment_name,
            )
        else:
            segment_calculation = None
        if segment_calculation:
            segment["calculation"] = segment_calculation
            segment["dataStatus"] = "calculated"
            calculations.append(segment_calculation)

    if calculations:
        payload["calculations"] = calculations
        payload["dataGaps"] = [
            "茅台酒单品销量、瓶价和单位成本未由公司直接披露；当前用产品收入/成本和酒类整体销量做估算口径。",
            "批价、渠道库存、终端动销、分产品费用率仍需要第三方渠道或商业数据库。",
        ]
    return payload


def normalize_driver_model(model: object) -> str:
    text = str(model or "").strip()
    return text if text in DRIVER_MODEL_REGISTRY else "generic_volume_price"


def rule_classify_profit_driver_model(profile_payload: dict, main_business_payload: dict) -> dict:
    company_name = str(profile_payload.get("companyName", ""))
    industry = str(profile_payload.get("industry", ""))
    main_business = str(profile_payload.get("mainBusiness", ""))
    business_scope = str(profile_payload.get("businessScope", ""))
    item_names = [str(item.get("itemName", "")) for item in main_business_payload.get("items", [])[:12]]
    text = " ".join([company_name, industry, main_business, business_scope, *item_names])

    segments: list[dict] = []
    if any(keyword in text for keyword in ["电解铝", "氧化铝", "铝加工", "铝锭", "原铝", "铝产品"]):
        segments.append(
            build_driver_model_segment(
                "aluminum_commodity",
                "铝产品",
                0.86,
                ["主营或收入拆分中出现电解铝、氧化铝、铝加工等铝产业链关键词。"],
                "rule",
            )
        )

    if any(keyword in text for keyword in ["石油", "天然气", "炼油", "成品油", "油气", "勘探"]):
        segments.append(
            build_driver_model_segment(
                "oil_gas_integrated",
                "油气与炼化业务",
                0.84,
                ["主营或行业中出现油气、炼油、天然气等综合能源关键词。"],
                "rule",
            )
        )

    if any(keyword in text for keyword in ["集装箱", "航运", "班轮", "海运", "码头", "港口"]):
        segments.append(
            build_driver_model_segment(
                "container_shipping",
                "集装箱航运/码头",
                0.86,
                ["主营或收入拆分中出现集装箱航运、班轮、码头或港口关键词。"],
                "rule",
            )
        )

    if not segments:
        generic_model = "generic_spread" if any(keyword in text for keyword in ["化工", "钢铁", "冶炼", "原料", "价差"]) else "generic_volume_price"
        segments.append(
            build_driver_model_segment(
                generic_model,
                "主营业务",
                0.45,
                ["未命中专用行业模型，先使用通用利润驱动框架。"],
                "rule",
            )
        )

    return {
        "stock": profile_payload.get("stock", ""),
        "companyName": company_name,
        "status": "ok",
        "source": "rule",
        "companyType": "mixed" if len(segments) > 1 else segments[0]["driverModel"],
        "segments": segments,
        "dataGaps": ["尚未接入对应市场数据连接器，当前输出为数据需求清单和计算框架。"],
        "knownDriverModels": KNOWN_DRIVER_MODELS,
    }


def ai_classify_profit_driver_model(profile_payload: dict, main_business_payload: dict) -> dict | None:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return None

    settings = get_openai_settings()
    context = {
        "stock": profile_payload.get("stock", ""),
        "companyName": profile_payload.get("companyName", ""),
        "industry": profile_payload.get("industry", ""),
        "mainBusiness": profile_payload.get("mainBusiness", ""),
        "businessScope": profile_payload.get("businessScope", ""),
        "revenueItems": main_business_payload.get("items", [])[:20],
        "knownDriverModels": KNOWN_DRIVER_MODELS,
        "driverModelRegistry": {
            key: {
                "label": value["label"],
                "description": value["description"],
                "marketMetrics": [metric["metric"] for metric in value["marketData"]],
                "operatingData": value["operatingData"],
            }
            for key, value in DRIVER_MODEL_REGISTRY.items()
        },
    }
    client = OpenAI(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        http_client=httpx.Client(trust_env=False),
    )
    prompt = (
        "你是上市公司利润驱动模型识别器。请只从 knownDriverModels 中选择模型；如果没有专用模型，选择 generic_volume_price 或 generic_spread。\n"
        "不要编造行情数值，不要输出 URL。你只负责选择利润驱动模型、业务分部、证据和数据缺口。\n"
        "输出严格 JSON，格式：\n"
        "{"
        "\"companyType\":\"\","
        "\"segments\":[{\"segmentName\":\"\",\"driverModel\":\"\",\"confidence\":0.0,\"evidence\":[\"...\"]}],"
        "\"dataGaps\":[\"...\"]"
        "}\n\n"
        f"输入：\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )
    response = client.chat.completions.create(
        model=settings["model"],
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "你只输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
    )
    content = response.choices[0].message.content if response.choices else ""
    parsed = json.loads((content or "").strip())
    raw_segments = parsed.get("segments", [])
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("AI driver classification returned no segments.")

    segments = []
    for segment in raw_segments[:6]:
        if not isinstance(segment, dict):
            continue
        model = normalize_driver_model(segment.get("driverModel"))
        evidence = segment.get("evidence") if isinstance(segment.get("evidence"), list) else []
        segments.append(
            build_driver_model_segment(
                model,
                str(segment.get("segmentName") or DRIVER_MODEL_REGISTRY[model]["label"]),
                float(segment.get("confidence") or 0.6),
                [str(item) for item in evidence],
                "ai",
            )
        )

    if not segments:
        raise ValueError("AI driver classification segments were invalid.")

    return {
        "stock": profile_payload.get("stock", ""),
        "companyName": profile_payload.get("companyName", ""),
        "status": "ok",
        "source": "ai",
        "companyType": parsed.get("companyType") or ("mixed" if len(segments) > 1 else segments[0]["driverModel"]),
        "segments": segments,
        "dataGaps": parsed.get("dataGaps") if isinstance(parsed.get("dataGaps"), list) else [],
        "knownDriverModels": KNOWN_DRIVER_MODELS,
    }


def build_profit_driver_model_payload(stock: str) -> dict:
    profile_payload = get_company_profile_payload_with_cache(stock=stock)
    main_business_payload = get_main_business_payload_with_cache(stock=stock)
    annual_report_payload = get_latest_report_text_payload_v2(stock=stock, category="年报", cache_key="annual_report_v1")
    fallback_payload = rule_classify_profit_driver_model(profile_payload, main_business_payload)

    try:
        ai_payload = ai_classify_profit_driver_model(profile_payload, main_business_payload)
        payload = ai_payload or fallback_payload
    except Exception as exc:
        print(f"[WARN] AI driver model classification unavailable, fallback to rules: {exc}")
        fallback_payload["aiError"] = str(exc)
        payload = fallback_payload

    return attach_profit_driver_calculations(payload, stock, main_business_payload, annual_report_payload)


def get_profit_driver_model_payload_with_cache(stock: str, refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "profit_driver_model_v3",
        stock,
        builder=lambda: build_profit_driver_model_payload(stock=stock),
        refresh=refresh,
    )


def clean_market_number(value: object) -> float:
    text = str(value or "").replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else 0.0


def parse_worldperatio_points(html: str) -> list[dict]:
    match = re.search(r"detailPE_data\s*=\s*\[(.*?)\];", html, flags=re.S)
    if not match:
        return []
    points: list[dict] = []
    pattern = r"Date\.UTC\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\),\s*(-?\d+(?:\.\d+)?)"
    for year, month, day, value in re.findall(pattern, match.group(1)):
        date = datetime(int(year), int(month) + 1, int(day)).date().isoformat()
        points.append({"date": date, "pe": round(float(value), 2)})
    return points


MONTH_ABBR_TO_NUMBER = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def parse_trendonify_pe_points(html: str) -> list[dict]:
    points: list[dict] = []
    seen: set[str] = set()
    pattern = r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\s+(-?\d+(?:\.\d+)?)\b"
    for month_text, year_text, value_text in re.findall(pattern, html):
        year = int(year_text)
        month = MONTH_ABBR_TO_NUMBER[month_text]
        pe = float(value_text)
        if pe <= 0:
            continue
        date = datetime(year, month, 1).date().isoformat()
        if date in seen:
            continue
        seen.add(date)
        points.append({"date": date, "pe": round(pe, 2)})
    return sorted(points, key=lambda item: item["date"])


def load_trendonify_pe_points(index_code: str, refresh: bool = False) -> list[dict]:
    config = MARKET_INDEX_CONFIG[index_code]

    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching {config['name']} PE history from Trendonify")
        with temporary_disable_proxy_env():
            response = requests.get(
                config["peUrl"],
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=3,
                proxies={"http": None, "https": None},
            )
            response.raise_for_status()
        return pd.DataFrame(parse_trendonify_pe_points(response.text))

    df = get_ak_dataframe_cached(("market_index_pe", "trendonify", index_code), fetch, refresh=refresh)
    if df is None or df.empty:
        return []
    df = df.copy()
    df["pe"] = pd.to_numeric(df["pe"], errors="coerce")
    df = df.dropna(subset=["date", "pe"])
    df = df[df["pe"] > 0]
    return sorted(df.to_dict("records"), key=lambda item: item["date"])


def load_sp500_pe_points(refresh: bool = False) -> list[dict]:
    def fetch() -> pd.DataFrame:
        print("[INFO] Fetching S&P 500 PE history from Multpl")
        with temporary_disable_proxy_env():
            response = requests.get(
                MARKET_INDEX_CONFIG["sp500"]["peUrl"],
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=3,
                proxies={"http": None, "https": None},
            )
            response.raise_for_status()
            tables = pd.read_html(StringIO(response.text))
        return tables[0] if tables else pd.DataFrame()

    df = get_ak_dataframe_cached(("market_index_pe", "sp500"), fetch, refresh=refresh)
    if df is None or df.empty:
        return []
    points = []
    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        date = pd.to_datetime(row_dict.get("Date"), errors="coerce")
        pe = clean_market_number(row_dict.get("Value"))
        if pd.isna(date) or pe <= 0:
            continue
        points.append({"date": date.date().isoformat(), "pe": round(pe, 2)})
    return sorted(points, key=lambda item: item["date"])


def load_nasdaq100_pe_points(refresh: bool = False) -> list[dict]:
    def fetch() -> pd.DataFrame:
        print("[INFO] Fetching Nasdaq 100 PE history from World PE Ratio")
        with temporary_disable_proxy_env():
            response = requests.get(
                MARKET_INDEX_CONFIG["nasdaq100"]["peUrl"],
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=3,
                proxies={"http": None, "https": None},
            )
            response.raise_for_status()
        return pd.DataFrame(parse_worldperatio_points(response.text))

    df = get_ak_dataframe_cached(("market_index_pe", "nasdaq100"), fetch, refresh=refresh)
    if df is None or df.empty:
        return []
    df = df.copy()
    df["pe"] = pd.to_numeric(df["pe"], errors="coerce")
    df = df.dropna(subset=["date", "pe"])
    df = df[df["pe"] > 0]
    return sorted(df.to_dict("records"), key=lambda item: item["date"])


def load_legulegu_index_pe_points(symbol: str) -> list[dict]:
    code = r"""
import json
import sys
import akshare as ak

symbol = sys.argv[1]
df = ak.stock_index_pe_lg(symbol=symbol)
records = df.to_dict(orient="records")
print(json.dumps(records, ensure_ascii=False, default=str))
"""
    records = run_python_json_subprocess(code, symbol, timeout=12)
    points: list[dict] = []
    for row in records:
        date = pd.to_datetime(row.get("日期"), errors="coerce")
        pe = finite_float(row.get("滚动市盈率"))
        if pd.notna(date) and pe > 0:
            points.append({"date": date.date().isoformat(), "pe": round(pe, 2)})
    return sorted(points, key=lambda item: item["date"])


def load_csindex_recent_pe_points(symbol: str, refresh: bool = False) -> list[dict]:
    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching CSIndex valuation, symbol={symbol}")
        url = (
            "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
            f"autofile/indicator/{symbol}indicator.xls"
        )
        with temporary_disable_proxy_env():
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=4,
                proxies={"http": None, "https": None},
            )
            response.raise_for_status()
        return pd.read_excel(BytesIO(response.content))

    df = get_ak_dataframe_cached(("csindex_value", symbol), fetch, refresh=refresh)
    if df is None or df.empty:
        return []
    df = df.copy()
    if len(df.columns) >= 10:
        df.columns = ["日期", "指数代码", "指数中文全称", "指数中文简称", "指数英文全称", "指数英文简称", "市盈率1", "市盈率2", "股息率1", "股息率2"]
    points: list[dict] = []
    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        date = pd.to_datetime(row_dict.get("日期"), format="%Y%m%d", errors="coerce")
        if pd.isna(date):
            date = pd.to_datetime(row_dict.get("日期"), errors="coerce")
        pe = finite_float(row_dict.get("市盈率2") or row_dict.get("市盈率1"))
        if pd.notna(date) and pe > 0:
            points.append({"date": date.date().isoformat(), "pe": round(pe, 2)})
    return sorted(points, key=lambda item: item["date"])


def load_etfrun_index_pe_points(market: str, symbol: str, refresh: bool = False) -> list[dict]:
    def fetch() -> pd.DataFrame:
        print(f"[INFO] Fetching ETF.run index PE history, market={market}, symbol={symbol}")
        url = f"https://www.etf.run/index/{market}/{symbol}"
        with temporary_disable_proxy_env():
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
                proxies={"http": None, "https": None},
            )
            response.raise_for_status()
        match = re.search(
            r'\\"compressedIndexDaily\\":\{\\"fieldNames\\":(\[.*?\]),\\"values\\":(\[\[.*?\]\])\}',
            response.text,
        )
        if not match:
            raise ValueError("ETF.run compressedIndexDaily not found.")
        field_names = json.loads(match.group(1).replace('\\"', '"'))
        values = json.loads(match.group(2).replace('\\"', '"'))
        return pd.DataFrame(values, columns=field_names)

    try:
        df = get_ak_dataframe_cached(("etfrun_index_pe", market, symbol), fetch, refresh=refresh)
    except Exception as exc:
        print(f"[WARN] ETF.run index PE unavailable, market={market}, symbol={symbol}: {exc}")
        return []

    if df is None or df.empty or "date" not in df.columns or "equalWeightedPeTtm" not in df.columns:
        return []

    points: list[dict] = []
    for row in df.to_dict(orient="records"):
        date = pd.to_datetime(row.get("date"), errors="coerce")
        pe = finite_float(row.get("equalWeightedPeTtm"))
        if pd.notna(date) and pe > 0:
            points.append({"date": date.date().isoformat(), "pe": round(pe, 2)})
    return sorted(points, key=lambda item: item["date"])


def is_market_index_history_sufficient(index_code: str, years: int, pe_points: list[dict]) -> tuple[bool, str]:
    try:
        ensure_market_index_history_span(index_code, years, pe_points)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def load_china_index_pe_points(index_code: str, years: int = 5, refresh: bool = False) -> list[dict]:
    config = MARKET_INDEX_CONFIG[index_code]
    source_errors: list[str] = []
    etfrun_market = config.get("etfRunMarket")
    etfrun_symbol = config.get("etfRunSymbol")
    if etfrun_market and etfrun_symbol:
        points = load_etfrun_index_pe_points(etfrun_market, etfrun_symbol, refresh=refresh)
        if points:
            is_sufficient, reason = is_market_index_history_sufficient(index_code, years, points)
            if is_sufficient:
                return points
            source_errors.append(f"ETF.run: {reason}")
        else:
            source_errors.append("ETF.run: 未返回可用 PE 历史")

    if index_code == "dividend_low_vol_100":
        points = load_csindex_recent_pe_points(config["csindexSymbol"], refresh=refresh)
        is_sufficient, reason = is_market_index_history_sufficient(index_code, years, points)
        if is_sufficient:
            return points
        detail = "; ".join([*source_errors, f"中证指数官网: {reason or '未返回可用 PE 历史'}"])
        raise ValueError(f"{config['displayName']} 暂未抓到足够 {years} 年估值历史：{detail}")

    symbol = config["leguleguSymbol"]
    try:
        print(f"[INFO] Fetching China index PE history from Legulegu, symbol={symbol}")
        points = load_legulegu_index_pe_points(symbol)
        if points:
            is_sufficient, reason = is_market_index_history_sufficient(index_code, years, points)
            if is_sufficient:
                return points
            source_errors.append(f"乐咕乐股: {reason}")
        else:
            source_errors.append("乐咕乐股: 未返回可用 PE 历史")
    except Exception as exc:
        print(f"[WARN] Legulegu index PE unavailable: {symbol}: {exc}")
        source_errors.append(f"乐咕乐股: {exc}")
    points = load_csindex_recent_pe_points(config["csindexSymbol"], refresh=refresh)
    is_sufficient, reason = is_market_index_history_sufficient(index_code, years, points)
    if is_sufficient:
        return points
    detail = "; ".join([*source_errors, f"中证指数官网: {reason or '未返回可用 PE 历史'}"])
    raise ValueError(f"{config['displayName']} 暂未抓到足够 {years} 年估值历史：{detail}")


def load_cached_market_ten_year_yield() -> dict | None:
    payload = load_cached_payload("treasury_yield_v1", "us_10y")
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if isinstance(observations, list) and observations:
        latest = observations[-1]
        if isinstance(latest, dict) and latest.get("value") is not None:
            return {
                "date": str(latest.get("date") or ""),
                "value": round(float(latest["value"]), 2),
                "unit": "%",
                "source": str(payload.get("source") or "FRED DGS10"),
            }
    return None


def load_ten_year_yield_dataframe(refresh: bool = False) -> pd.DataFrame:
    def fetch() -> pd.DataFrame:
        print("[INFO] Fetching US 10Y treasury yield history from FRED")
        request = Request(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
            headers={"User-Agent": "curl/8.0"},
        )
        opener = build_opener(ProxyHandler({}))
        with opener.open(request, timeout=20) as response:
            return pd.read_csv(BytesIO(response.read()))

    df = get_ak_dataframe_cached(("fred", "DGS10"), fetch, refresh=refresh)
    if df is None or df.empty or "DGS10" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df.get("observation_date"), errors="coerce")
    df["value"] = pd.to_numeric(df["DGS10"], errors="coerce")
    df = df.dropna(subset=["date", "value"])
    return df.sort_values("date")


def build_treasury_yield_payload(refresh: bool = False) -> dict:
    df = load_ten_year_yield_dataframe(refresh=refresh)
    observations = [
        {"date": row.date.date().isoformat(), "value": round(float(row.value), 2)}
        for row in df.itertuples(index=False)
        if finite_float(row.value) >= 0
    ]
    return {
        "series": "DGS10",
        "name": "US 10Y Treasury Constant Maturity Rate",
        "unit": "%",
        "source": "FRED DGS10",
        "observations": observations,
    }


def get_treasury_yield_payload_with_cache(refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "treasury_yield_v1",
        "us_10y",
        builder=lambda: build_treasury_yield_payload(refresh=refresh),
        refresh=refresh,
    )


def build_ten_year_yield_bundle(years: int, refresh: bool = False) -> tuple[dict | None, list[dict]]:
    try:
        payload = get_treasury_yield_payload_with_cache(refresh=refresh)
        observations = payload.get("observations") if isinstance(payload, dict) else None
        if not isinstance(observations, list) or not observations:
            return None, []
        df = pd.DataFrame(observations)
        df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
        df["value"] = pd.to_numeric(df.get("value"), errors="coerce")
        df = df.dropna(subset=["date", "value"]).sort_values("date")
        if df.empty:
            return None, []
        latest = df.iloc[-1]
        current_yield = {
            "date": latest.date.date().isoformat(),
            "value": round(float(latest.value), 2),
            "unit": "%",
            "source": str(payload.get("source") or "FRED DGS10"),
        }
        cutoff = datetime.now().date() - timedelta(days=max(years, 1) * 365)
        history_df = df[df["date"].dt.date >= cutoff].copy()
        if history_df.empty:
            return current_yield, []
        history_df["month"] = history_df["date"].dt.to_period("M")
        history_df = history_df.groupby("month", as_index=False).tail(1)
        history_points = [
            {"date": row.date.date().isoformat(), "value": round(float(row.value), 2)}
            for row in history_df.itertuples(index=False)
            if finite_float(row.value) >= 0
        ]
        return current_yield, history_points
    except Exception as exc:
        print(f"[WARN] US 10Y yield unavailable: {exc}")
        if refresh:
            return None, []
        return load_cached_market_ten_year_yield(), []


def load_china_ten_year_yield_dataframe(refresh: bool = False) -> pd.DataFrame:
    def fetch() -> pd.DataFrame:
        print("[INFO] Fetching China 10Y treasury yield history from AKShare")
        return ak.bond_zh_us_rate()

    df = get_ak_dataframe_cached(("bond_zh_us_rate",), fetch, refresh=refresh)
    if df is None or df.empty or "中国国债收益率10年" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df.get("日期"), errors="coerce")
    df["value"] = pd.to_numeric(df["中国国债收益率10年"], errors="coerce")
    df = df.dropna(subset=["date", "value"])
    return df.sort_values("date")


def build_china_treasury_yield_payload(refresh: bool = False) -> dict:
    df = load_china_ten_year_yield_dataframe(refresh=refresh)
    observations = [
        {"date": row.date.date().isoformat(), "value": round(float(row.value), 4)}
        for row in df.itertuples(index=False)
        if finite_float(row.value) >= 0
    ]
    return {
        "series": "CN10Y",
        "name": "China 10Y Treasury Yield",
        "unit": "%",
        "source": "AKShare bond_zh_us_rate",
        "observations": observations,
    }


def get_china_treasury_yield_payload_with_cache(refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "treasury_yield_v1",
        "cn_10y",
        builder=lambda: build_china_treasury_yield_payload(refresh=refresh),
        refresh=refresh,
    )


def build_china_ten_year_yield_bundle(years: int, refresh: bool = False) -> tuple[dict | None, list[dict]]:
    try:
        payload = get_china_treasury_yield_payload_with_cache(refresh=refresh)
        observations = payload.get("observations") if isinstance(payload, dict) else None
        if not isinstance(observations, list) or not observations:
            return None, []
        df = pd.DataFrame(observations)
        df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
        df["value"] = pd.to_numeric(df.get("value"), errors="coerce")
        df = df.dropna(subset=["date", "value"]).sort_values("date")
        if df.empty:
            return None, []
        latest = df.iloc[-1]
        current_yield = {
            "date": latest.date.date().isoformat(),
            "value": round(float(latest.value), 4),
            "unit": "%",
            "source": str(payload.get("source") or "AKShare bond_zh_us_rate"),
        }
        cutoff = datetime.now().date() - timedelta(days=max(years, 1) * 365)
        history_df = df[df["date"].dt.date >= cutoff].copy()
        if history_df.empty:
            return current_yield, []
        history_df["month"] = history_df["date"].dt.to_period("M")
        history_df = history_df.groupby("month", as_index=False).tail(1)
        history_points = [
            {"date": row.date.date().isoformat(), "value": round(float(row.value), 4)}
            for row in history_df.itertuples(index=False)
            if finite_float(row.value) >= 0
        ]
        return current_yield, history_points
    except Exception as exc:
        print(f"[WARN] China 10Y yield unavailable: {exc}")
        return None, []


def load_ten_year_yield(refresh: bool = False) -> dict | None:
    if not refresh:
        cached_ten_year_yield = load_cached_market_ten_year_yield()
        if cached_ten_year_yield is not None:
            return cached_ten_year_yield
    current_yield, _ = build_ten_year_yield_bundle(years=1, refresh=refresh)
    return current_yield


def load_ten_year_yield_points(years: int, refresh: bool = False) -> list[dict]:
    _, history_points = build_ten_year_yield_bundle(years=years, refresh=refresh)
    return history_points


def load_yahoo_index_price_points(symbol: str, years: int, refresh: bool = False) -> list[dict]:
    def fetch() -> pd.DataFrame:
        end_ts = int(datetime.now(timezone.utc).timestamp())
        start_ts = int((datetime.now(timezone.utc) - timedelta(days=max(years, 1) * 370)).timestamp())
        url = (
            f"https://query2.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
            f"?period1={start_ts}&period2={end_ts}&interval=1mo&events=history"
        )
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        opener = build_opener(ProxyHandler({}))
        with opener.open(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not isinstance(result, dict):
            return pd.DataFrame()
        timestamps = result.get("timestamp") or []
        quotes = (((result.get("indicators") or {}).get("quote") or [None])[0] or {})
        closes = quotes.get("close") or []
        rows = []
        for timestamp, close in zip(timestamps, closes):
            value = finite_float(close)
            if value > 0:
                rows.append(
                    {
                        "date": datetime.fromtimestamp(int(timestamp), timezone.utc).date().isoformat(),
                        "close": value,
                    }
                )
        return pd.DataFrame(rows)

    df = get_ak_dataframe_cached(("yahoo_index_price", symbol, years), fetch, refresh=refresh)
    if df is None or df.empty:
        return []
    points = []
    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        date = pd.to_datetime(row_dict.get("date"), errors="coerce")
        value = finite_float(row_dict.get("close"))
        if pd.notna(date) and value > 0:
            points.append({"date": date.date().isoformat(), "value": round(value, 2)})
    return sorted(points, key=lambda item: item["date"])


def load_market_index_price_points(config: dict, refresh: bool = False) -> list[dict]:
    try:
        yahoo_symbols = [config.get("yahooSymbol"), *(config.get("yahooFallbackSymbols") or [])]
        for yahoo_symbol in [symbol for symbol in yahoo_symbols if symbol]:
            try:
                yahoo_points = load_yahoo_index_price_points(str(yahoo_symbol), years=30, refresh=refresh)
                if yahoo_points:
                    return yahoo_points
            except Exception as exc:
                print(f"[WARN] Yahoo index price history unavailable: {yahoo_symbol}: {exc}")

        def fetch() -> pd.DataFrame:
            if config.get("priceSymbol"):
                print(f"[INFO] Fetching global index price history, symbol={config['priceSymbol']}")
                with temporary_disable_proxy_env():
                    return ak.index_global_hist_em(symbol=config["priceSymbol"])
            if config.get("csindexSymbol"):
                symbol = f"sh{config['csindexSymbol']}"
                print(f"[INFO] Fetching China index price history, symbol={symbol}")
                return ak.stock_zh_index_daily(symbol=symbol)
            return pd.DataFrame()

        price_key = config.get("priceSymbol") or config.get("csindexSymbol") or config.get("name")
        df = get_ak_dataframe_cached(("market_index_price", price_key), fetch, refresh=refresh)
        if df is None or df.empty:
            return []
        date_col = next((col for col in ["日期", "date", "Date"] if col in df.columns), None)
        close_col = next((col for col in ["收盘", "close", "Close"] if col in df.columns), None)
        if not date_col or not close_col:
            return []
        points = []
        for row in df.itertuples(index=False):
            row_dict = row._asdict()
            date = pd.to_datetime(row_dict.get(date_col), errors="coerce")
            value = finite_float(row_dict.get(close_col))
            if pd.notna(date) and value > 0:
                points.append({"date": date.date().isoformat(), "value": round(value, 2)})
        return sorted(points, key=lambda item: item["date"])
    except Exception as exc:
        print(f"[WARN] Index price history unavailable: {config.get('priceSymbol') or config.get('csindexSymbol')}: {exc}")
        return []

def percentile_rank(values: list[float], current: float) -> float:
    if not values:
        return 0.0
    return round(sum(1 for value in values if value <= current) / len(values), 4)


def classify_valuation_zone(percentile: float) -> str:
    if percentile >= 0.85:
        return "extreme"
    if percentile >= 0.60:
        return "expensive"
    if percentile >= 0.20:
        return "fair"
    return "cheap"


def annualized_index_return(price_points: list[dict]) -> float:
    points = [
        {
            "date": pd.to_datetime(point.get("date"), errors="coerce"),
            "value": finite_float(point.get("value")),
        }
        for point in price_points
        if isinstance(point, dict)
    ]
    points = [point for point in points if pd.notna(point["date"]) and point["value"] > 0]
    if len(points) < 2:
        return 0
    points = sorted(points, key=lambda item: item["date"])
    start = points[0]
    end = points[-1]
    days = (end["date"].date() - start["date"].date()).days
    if days <= 0 or start["value"] <= 0 or end["value"] <= 0:
        return 0
    years = days / 365.25
    if years <= 0:
        return 0
    return round(((end["value"] / start["value"]) ** (1 / years) - 1) * 100, 2)


def filter_market_index_price_points(config: dict, years: int, refresh: bool = False) -> list[dict]:
    cutoff = datetime.now().date() - timedelta(days=max(years, 1) * 365)
    points = load_market_index_price_points(config, refresh=refresh)
    filtered_points = []
    for point in points:
        date = pd.to_datetime(point.get("date"), errors="coerce")
        if pd.notna(date) and date.date() >= cutoff:
            filtered_points.append(point)
    return filtered_points or points


def build_market_index_valuation_payload(index_code: str, years: int = 20, refresh: bool = False) -> dict:
    code = str(index_code or "sp500").lower()
    alias_map = {
        "nasdaq": "nasdaq100",
        "hs300": "csi300",
        "000300": "csi300",
        "沪深300": "csi300",
        "csi500": "csi500",
        "zz500": "csi500",
        "sh500": "csi500",
        "000905": "csi500",
        "中证500": "csi500",
        "上证500": "csi500",
        "930955": "dividend_low_vol_100",
        "红利低波100": "dividend_low_vol_100",
        "红利低波动100": "dividend_low_vol_100",
        "dividend100": "dividend_low_vol_100",
        "dividend_low_vol": "dividend_low_vol_100",
    }
    code = alias_map.get(code, code)
    config = MARKET_INDEX_CONFIG.get(code, MARKET_INDEX_CONFIG["sp500"])

    if code in {"csi300", "csi500", "dividend_low_vol_100"}:
        pe_points = load_china_index_pe_points(code, years=years, refresh=refresh)
    else:
        pe_loader = load_nasdaq100_pe_points if code == "nasdaq100" else load_sp500_pe_points
        pe_points = pe_loader(refresh=refresh)

    if not pe_points:
        raise ValueError(f"Unable to fetch PE history for {config['displayName']}.")

    cutoff = datetime.now().date() - timedelta(days=max(years, 1) * 365)
    filtered_points = [point for point in pe_points if pd.to_datetime(point["date"]).date() >= cutoff]
    if not filtered_points:
        filtered_points = pe_points
    ensure_market_index_history_span(code, years, filtered_points)

    values = [float(point["pe"]) for point in filtered_points if finite_float(point.get("pe")) > 0]
    current = filtered_points[-1]
    current_pe = float(current["pe"])
    mean_pe = round(sum(values) / len(values), 2)
    median_pe = round(float(pd.Series(values).median()), 2)
    low_line = round(float(pd.Series(values).quantile(0.2)), 2)
    high_line = round(float(pd.Series(values).quantile(0.8)), 2)
    percentile = percentile_rank(values, current_pe)
    return {
        "indexCode": code,
        "indexName": config["name"],
        "displayName": config["displayName"],
        "status": "ok",
        "sourceLabel": config["sourceLabel"],
        "dataQuality": {
            "peHistory": "available",
            "eps": "not_used",
            "interestRate": "not_connected",
            "notes": [
                "PE 使用公开网页月度序列，口径为 TTM 或站点披露的估算口径。",
                config.get("sourceQuality", ""),
                "历史年化回报使用指数点位从区间起点到终点计算 CAGR；美股指数为价格指数口径，不含股息再投资。",
            ],
        },
        "summary": {
            "currentDate": current["date"],
            "currentPe": round(current_pe, 2),
            "meanPe": mean_pe,
            "medianPe": median_pe,
            "lowLine": low_line,
            "highLine": high_line,
            "percentile": percentile,
            "valuationZone": classify_valuation_zone(percentile),
            "earningsYield": 0,
            "tenYearYield": None,
            "equityRiskPremium": None,
            "years": years,
        },
        "peLine": filtered_points,
        "priceLine": [],
        "interestRateLine": [],
        "interestRateLabel": "",
        "conclusion": f"{config['displayName']} 当前 PE 为 {current_pe:.2f}x，处于近 {years} 年历史分位 {percentile * 100:.1f}%。",
        "sourceUrls": [config["peUrl"]],
    }


def build_limited_market_index_valuation_payload(index_code: str, years: int, reason: object, refresh: bool = False) -> dict:
    code = str(index_code or "sp500").lower()
    config = MARKET_INDEX_CONFIG.get(code, MARKET_INDEX_CONFIG["sp500"])
    csindex_symbol = config.get("csindexSymbol")
    if not csindex_symbol:
        raise ValueError(str(reason))

    pe_points = load_csindex_recent_pe_points(csindex_symbol, refresh=refresh)
    if not pe_points:
        raise ValueError(str(reason))

    values = [float(point["pe"]) for point in pe_points if finite_float(point.get("pe")) > 0]
    if not values:
        raise ValueError(str(reason))

    current = pe_points[-1]
    current_pe = float(current["pe"])
    mean_pe = round(sum(values) / len(values), 2)
    median_pe = round(float(pd.Series(values).median()), 2)
    low_line = round(float(pd.Series(values).quantile(0.2)), 2)
    high_line = round(float(pd.Series(values).quantile(0.8)), 2)
    percentile = percentile_rank(values, current_pe)
    return {
        "indexCode": code,
        "indexName": config["name"],
        "displayName": config["displayName"],
        "status": "limited_history",
        "sourceLabel": f"{config['sourceLabel']} / CSIndex recent fallback",
        "dataQuality": {
            "peHistory": "limited",
            "eps": "not_used",
            "interestRate": "not_connected",
            "notes": [
                f"Long-history PE sources are unavailable, so this response uses recent CSIndex valuation data instead: {reason}",
                f"Only {len(pe_points)} recent PE samples are available; this is not a valid {years}-year historical percentile.",
            ],
        },
        "summary": {
            "currentDate": current["date"],
            "currentPe": round(current_pe, 2),
            "meanPe": mean_pe,
            "medianPe": median_pe,
            "lowLine": low_line,
            "highLine": high_line,
            "percentile": percentile,
            "valuationZone": classify_valuation_zone(percentile),
            "earningsYield": 0,
            "tenYearYield": None,
            "equityRiskPremium": None,
            "years": years,
        },
        "peLine": pe_points,
        "priceLine": [],
        "interestRateLine": [],
        "interestRateLabel": "",
        "conclusion": f"{config['displayName']} current PE is {current_pe:.2f}x. Long-history sources are unavailable, so recent valuation data is shown as a fallback.",
        "sourceUrls": [config["peUrl"]],
    }


def ensure_market_index_history_span(index_code: str, years: int, pe_points: list[dict]) -> None:
    if years < 5 or not pe_points:
        return

    dates = [pd.to_datetime(point.get("date"), errors="coerce").date() for point in pe_points]
    dates = [date for date in dates if pd.notna(date)]
    if len(dates) < 12:
        raise ValueError(f"{index_code} PE 历史样本过短，不能用于 {years} 年历史分位。")
    span_days = (max(dates) - min(dates)).days
    required_days = years * 365 * 0.7
    if span_days < required_days:
        raise ValueError(
            f"{index_code} PE 历史跨度仅 {span_days} 天，不能当作 {years} 年历史分位；请配置长历史估值源或刷新数据。"
        )


def is_market_index_cache_usable(payload: dict | None, index_code: str, years: int) -> bool:
    if payload is None:
        return False
    if payload.get("status") == "limited_history":
        print(f"[WARN] Limited market index payload ignored, index={index_code}, years={years}")
        return False
    try:
        ensure_market_index_history_span(index_code, years, payload.get("peLine") if isinstance(payload.get("peLine"), list) else [])
    except Exception as exc:
        print(f"[WARN] Market index cache ignored, index={index_code}, years={years}: {exc}")
        return False
    return True


def save_market_index_valuation_payload(payload: dict, index_code: str, years: int) -> dict:
    if payload.get("status") != "ok":
        raise ValueError(f"Refusing to cache non-ok market index payload: status={payload.get('status')}")
    ensure_market_index_history_span(index_code, years, payload.get("peLine") if isinstance(payload.get("peLine"), list) else [])
    cache_payload = dict(payload)
    cache_payload["summary"] = dict(payload.get("summary") or {})
    cache_payload["dataQuality"] = dict(payload.get("dataQuality") or {})
    cache_payload["summary"]["tenYearYield"] = None
    cache_payload["summary"]["equityRiskPremium"] = None
    cache_payload["dataQuality"]["interestRate"] = "not_connected"
    cache_payload["priceLine"] = []
    cache_payload["interestRateLine"] = []
    cache_payload["interestRateLabel"] = ""
    return save_cached_payload(cache_payload, "market_index_valuation_v4", index_code, years)


def enrich_market_index_valuation_with_interest(payload: dict, years: int, refresh: bool = False) -> dict:
    code = str(payload.get("indexCode") or "").lower()
    us_rate_indexes = {"sp500", "nasdaq100"}
    china_rate_indexes = {"csi300", "csi500", "dividend_low_vol_100"}
    if code not in us_rate_indexes | china_rate_indexes:
        return payload

    if code in china_rate_indexes:
        ten_year_yield, interest_rate_points = build_china_ten_year_yield_bundle(years=years, refresh=refresh)
        rate_label = "CN 10Y"
        rate_url = "https://yield.chinabond.com.cn/"
    else:
        ten_year_yield, interest_rate_points = build_ten_year_yield_bundle(years=years, refresh=refresh)
        rate_label = "US 10Y"
        rate_url = "https://fred.stlouisfed.org/series/DGS10"

    enriched = dict(payload)
    enriched["summary"] = dict(payload.get("summary") or {})
    enriched["dataQuality"] = dict(payload.get("dataQuality") or {})
    config = MARKET_INDEX_CONFIG.get(code)
    price_points = filter_market_index_price_points(config, years, refresh=refresh) if config else []
    if price_points:
        enriched["priceLine"] = price_points
    enriched["summary"]["earningsYield"] = annualized_index_return(price_points)
    enriched["summary"]["tenYearYield"] = ten_year_yield
    annualized_return = finite_float(enriched["summary"].get("earningsYield"))
    enriched["summary"]["equityRiskPremium"] = (
        round(annualized_return - float(ten_year_yield["value"]), 2)
        if ten_year_yield and ten_year_yield.get("value") is not None and annualized_return != 0
        else None
    )
    enriched["dataQuality"]["interestRate"] = "available" if ten_year_yield or interest_rate_points else "not_connected"
    enriched["interestRateLine"] = interest_rate_points
    enriched["interestRateLabel"] = rate_label if interest_rate_points else ""
    if ten_year_yield or interest_rate_points:
        source_urls = list(enriched.get("sourceUrls") or [])
        if rate_url not in source_urls:
            source_urls.append(rate_url)
        enriched["sourceUrls"] = source_urls
    return enriched


def get_market_index_valuation_payload_with_cache(index_code: str, years: int, refresh: bool = False) -> dict:
    code = str(index_code or "sp500").lower()
    alias_map = {
        "nasdaq": "nasdaq100",
        "hs300": "csi300",
        "000300": "csi300",
        "沪深300": "csi300",
        "zz500": "csi500",
        "sh500": "csi500",
        "000905": "csi500",
        "中证500": "csi500",
        "上证500": "csi500",
        "930955": "dividend_low_vol_100",
        "红利低波100": "dividend_low_vol_100",
        "红利低波动100": "dividend_low_vol_100",
        "dividend100": "dividend_low_vol_100",
        "dividend_low_vol": "dividend_low_vol_100",
    }
    code = alias_map.get(code, code)
    if not refresh:
        current_cache = load_cached_payload("market_index_valuation_v4", code, years)
        if is_market_index_cache_usable(current_cache, code, years):
            return enrich_market_index_valuation_with_interest(current_cache, years, refresh=refresh)

    stale_cache = None
    if not refresh:
        stale_cache = load_latest_cached_payload(f"market_index_valuation_v*__{sanitize_cache_part(code)}__{sanitize_cache_part(years)}.json")
        if not is_market_index_cache_usable(stale_cache, code, years):
            stale_cache = None

    if stale_cache is not None:
        stale_cache = dict(stale_cache)
        stale_cache["status"] = "stale_cache"
        stale_cache.setdefault("dataQuality", {}).setdefault("notes", []).append("外部估值源较慢，当前先展示最近一次缓存数据。")
        return enrich_market_index_valuation_with_interest(stale_cache, years, refresh=refresh)

    try:
        payload = build_market_index_valuation_payload(index_code=code, years=years, refresh=refresh)
        save_market_index_valuation_payload(payload, code, years)
        return enrich_market_index_valuation_with_interest(payload, years, refresh=refresh)
    except Exception as exc:
        if stale_cache is not None:
            stale_cache = dict(stale_cache)
            stale_cache["status"] = "stale_cache"
            stale_cache.setdefault("dataQuality", {}).setdefault("notes", []).append(f"外部估值源暂不可用，使用最近缓存：{exc}")
            return enrich_market_index_valuation_with_interest(stale_cache, years, refresh=refresh)
        limited_payload = build_limited_market_index_valuation_payload(code, years, exc, refresh=refresh)
        return enrich_market_index_valuation_with_interest(limited_payload, years, refresh=refresh)


def build_dashboard_data_payload(
    stock: str,
    period: str | None,
    years: int,
    include_peers: bool = True,
    refresh: bool = False,
) -> dict:
    tasks: dict[str, Callable[[], Any]] = {
        "balance": lambda: get_balance_payload_with_cache(stock=stock, period=period, refresh=refresh),
        "revenueMarketCap": lambda: get_revenue_market_cap_payload_with_cache(stock=stock, years=years, refresh=refresh),
        "peTrend": lambda: get_pe_trend_payload_with_cache(stock=stock, years=years, refresh=refresh),
        "profitMarketCap": lambda: get_profit_market_cap_payload_with_cache(stock=stock, years=years, refresh=refresh),
        "cashFlowQuality": lambda: get_cash_flow_quality_payload_with_cache(stock=stock, years=years, refresh=refresh),
        "revenueStructure": lambda: get_cached_payload_or_build(
            "revenue_structure_v8",
            stock,
            years,
            builder=lambda: get_revenue_structure_payload(stock=stock, years=years),
            refresh=refresh,
        ),
        "health": build_health_payload,
        "cacheStats": lambda: build_cache_stats_payload(limit=5),
        "profitDriverModel": lambda: get_profit_driver_model_payload_with_cache(stock=stock, refresh=refresh),
    }
    if include_peers:
        tasks["peerCompanies"] = lambda: get_peer_companies_payload_with_cache(
            stock=stock,
            limit=6,
            refresh=refresh,
        )

    data: dict[str, Any] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as executor:
        future_to_key = {executor.submit(task): key for key, task in tasks.items()}
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                data[key] = future.result()
            except Exception as exc:
                print(f"[ERROR] dashboard task failed, key={key}: {exc}")
                errors[key] = str(exc)

    return {
        "status": "partial" if errors else "ok",
        "stock": stock,
        "period": period or "latest",
        "years": years,
        "data": data,
        "errors": errors,
    }


def is_supplementary_item(item_name: str) -> bool:
    normalized_name = (item_name or "").strip()
    return (
        not normalized_name
        or normalized_name.startswith("其中")
        or "其他" in normalized_name
        or "补充" in normalized_name
        or "抵销" in normalized_name
        or "相互抵销" in normalized_name
    )


GENERIC_BUSINESS_BUCKET_NAMES = {
    "销售",
    "商品销售",
    "产品销售",
    "营销板块",
    "营销业务",
    "主营业务",
    "主营业",
    "合计",
}


def is_generic_business_bucket(item_name: object) -> bool:
    normalized_name = re.sub(r"\s+", "", str(item_name or ""))
    normalized_name = normalized_name.strip("：:（）()")
    return normalized_name in GENERIC_BUSINESS_BUCKET_NAMES


def remove_overlapping_summary_items(items: list[dict]) -> list[dict]:
    if len(items) < 2:
        return items

    ratio_sum = sum(float(item.get("revenueRatio") or 0) for item in items)
    has_generic_bucket = any(is_generic_business_bucket(item.get("itemName")) for item in items)
    if ratio_sum <= 1.05 or not has_generic_bucket:
        return items

    refined_items = [item for item in items if not is_generic_business_bucket(item.get("itemName"))]
    return refined_items or items


def filter_business_items(items: list[dict], category_type: str) -> list[dict]:
    filtered_items = [
        sanitize_business_item(item)
        for item in items
        if item.get("categoryType") == category_type and not is_supplementary_item(item.get("itemName", ""))
    ]
    filtered_items = remove_overlapping_summary_items(filtered_items)
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


POSITIONING_WATCH_METRICS = {
    "product": ["销量", "单价", "毛利率", "存货周转", "渠道结构"],
    "service": ["订单量", "履约能力", "利用率", "单位服务价格", "回款效率"],
    "platform": ["GMV", "抽佣率", "商家数", "活跃用户", "广告/服务费变现"],
}


def _positioning_keywords() -> dict[str, list[str]]:
    return {
        "product": [
            "产品",
            "商品",
            "白酒",
            "家电",
            "设备",
            "药品",
            "芯片",
            "汽车",
            "材料",
            "制造",
            "生产",
            "零部件",
        ],
        "service": [
            "服务",
            "航运",
            "物流",
            "运输",
            "租赁",
            "港口",
            "码头",
            "交付",
            "履约",
            "工程",
            "运维",
        ],
        "platform": [
            "平台",
            "佣金",
            "抽佣",
            "广告",
            "撮合",
            "信息服务",
            "技术服务费",
            "商家",
            "用户",
            "流量",
            "交易服务",
            "服务费",
            "会员费",
        ],
    }


def build_positioning_evidence_item(signal_type: str, label: str, detail: str) -> dict:
    return {
        "type": signal_type,
        "label": label,
        "detail": detail,
    }


def infer_company_positioning(
    company_main_business: str,
    industry: str,
    product_items: list[dict],
    channel_items: list[dict] | None = None,
) -> dict:
    keywords = _positioning_keywords()
    item_names = [str(item.get("itemName", "")).strip() for item in product_items if str(item.get("itemName", "")).strip()]
    top_item_names = item_names[:3]
    top_items_text = "、".join(top_item_names)
    channel_names = [str(item.get("itemName", "")).strip() for item in (channel_items or []) if str(item.get("itemName", "")).strip()]
    search_text = " ".join(top_item_names + channel_names + [company_main_business or "", industry or ""])

    score_map = {"product": 0.0, "service": 0.0, "platform": 0.0}
    evidence_map = {"product": [], "service": [], "platform": []}

    def add_signal(target: str, score: float, signal_type: str, label: str, detail: str) -> None:
        score_map[target] += score
        evidence_map[target].append(build_positioning_evidence_item(signal_type, label, detail))

    for target, keyword_list in keywords.items():
        matched = [keyword for keyword in keyword_list if keyword in search_text]
        if matched:
            sample = "、".join(matched[:3])
            label_map = {
                "product": "主营描述更像卖货",
                "service": "主营描述更像卖能力",
                "platform": "主营描述更像平台收费",
            }
            detail_map = {
                "product": f"主营业务、行业或收入项里出现了 {sample} 等表述，更接近自有商品或设备销售。",
                "service": f"主营业务、行业或收入项里出现了 {sample} 等表述，更接近运输、交付、租赁或工程服务。",
                "platform": f"主营业务、行业或收入项里出现了 {sample} 等表述，更接近佣金、广告或撮合收费。",
            }
            add_signal(target, 1.6 if target != "platform" else 2.0, "keyword", label_map[target], detail_map[target])

    if product_items:
        top_item = product_items[0]
        top_ratio = float(top_item.get("revenueRatio") or 0)
        top_margin = top_item.get("grossMargin")
        if top_ratio >= 0.5 and top_items_text:
            add_signal(
                "product",
                1.0,
                "revenue_structure",
                "收入按具体品类拆分较明显",
                f"前几大收入项集中在 {top_items_text}，更像按具体商品或产品线管理收入。",
            )
        if top_margin is not None and float(top_margin) >= 0.45:
            add_signal(
                "platform",
                0.8,
                "margin_profile",
                "高毛利更像轻资产收费",
                "核心收入项毛利率较高，和平台型公司常见的佣金、广告或技术服务收费更接近。",
            )

    if channel_names:
        direct_indicators = [name for name in channel_names if any(keyword in name for keyword in ["直营", "经销", "线下", "门店"])]
        if direct_indicators:
            add_signal(
                "product",
                0.7,
                "channel_structure",
                "渠道拆分更像卖货公司",
                f"渠道里出现 { '、'.join(direct_indicators[:2]) } 等表述，说明公司更像围绕商品销售来组织渠道。",
            )
        platform_indicators = [name for name in channel_names if any(keyword in name for keyword in ["平台", "线上", "广告", "商家", "撮合"])]
        if platform_indicators:
            add_signal(
                "platform",
                1.1,
                "channel_structure",
                "渠道拆分带有平台生态特征",
                f"渠道里出现 { '、'.join(platform_indicators[:2]) } 等表述，说明收入更可能来自平台流量或交易撮合。",
            )

    if not any(score_map.values()):
        add_signal(
            "service",
            0.2,
            "fallback",
            "公开线索有限",
            "当前公开描述不足以强判具体模式，先按服务/业务单元视角理解主营收入。",
        )

    sorted_scores = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
    company_nature, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1]
    total_score = sum(score_map.values())
    confidence = 0.45 if total_score <= 0 else min(0.95, round(0.45 + max(top_score - second_score, 0) / max(total_score, 1) * 0.5, 2))

    primary_unit_label = {
        "product": "产品",
        "service": "业务",
        "platform": "平台业务",
    }[company_nature]
    rationale_map = {
        "product": "这家公司更像靠销售自有商品或设备赚钱，所以拆收入时直接按产品线看最合适。",
        "service": "这家公司更像卖运输、交付、租赁或工程能力，所以这里的“按产品”更适合理解成“按业务单元”看。",
        "platform": "这家公司更像通过撮合、流量、广告或技术服务收费赚钱，所以这里的核心不是卖货，而是看平台业务怎么变现。",
    }

    support_evidence = evidence_map[company_nature][:4]
    conflict_evidence = []
    for other_type, _score in sorted_scores[1:]:
        if score_map[other_type] <= 0:
            continue
        dominant_label = {
            "product": "仍有卖货特征",
            "service": "仍有服务履约特征",
            "platform": "仍有平台收费特征",
        }[other_type]
        dominant_detail = {
            "product": "部分描述仍然像自营商品或设备销售，说明它不一定是纯轻资产模式。",
            "service": "部分描述仍然像运输、交付或工程履约，说明它不只是单纯卖货。",
            "platform": "部分描述仍然像平台抽佣、广告或撮合收费，说明它可能带有平台生态。",
        }[other_type]
        conflict_evidence.append(build_positioning_evidence_item("cross_signal", dominant_label, dominant_detail))

    return {
        "companyNature": company_nature,
        "confidence": confidence,
        "primaryUnitLabel": primary_unit_label,
        "rationale": rationale_map[company_nature],
        "evidence": {
            "supports": support_evidence,
            "conflicts": conflict_evidence[:3],
        },
        "watchMetrics": POSITIONING_WATCH_METRICS[company_nature],
    }


def build_interpreted_main_business_summary(
    company_main_business: str,
    company_positioning: dict,
    product_items: list[dict],
) -> str:
    top_item_names = [str(item.get("itemName", "")).strip() for item in product_items[:2] if str(item.get("itemName", "")).strip()]
    top_items_text = "、".join(top_item_names)
    company_nature = company_positioning.get("companyNature", "service")

    if company_nature == "service":
        if top_items_text:
            return f"可以把它理解成一家以{top_items_text}为核心的服务型公司。它主要不是卖实体产品，而是向客户出售运输、交付、租赁或组织能力。"
        return "可以把它理解成一家服务型公司。它主要不是卖实体产品，而是向客户出售运输、交付、租赁或物流能力。"

    if company_nature == "product":
        if top_items_text:
            return f"可以把它理解成一家以{top_items_text}为核心的产品型公司。它主要通过销售自己的商品、设备或消费品来赚钱，价格和销量通常是最关键的观察点。"
        return "可以把它理解成一家产品型公司。它主要通过销售自己的商品、设备或消费品来赚钱。"

    if top_items_text:
        return f"可以把它理解成一家以{top_items_text}为核心的平台型公司。它更像靠撮合交易、广告或技术服务收费赚钱，重点不是囤货，而是平台生态和变现效率。"
    return "可以把它理解成一家平台型公司。它更像靠撮合交易、广告或技术服务收费赚钱，而不是依赖持有货物赚价差。"


def infer_business_explanation(
    item_name: str,
    company_main_business: str,
    industry: str,
    dimension: str,
    company_positioning: dict,
) -> dict:
    if dimension == "region":
        region_name = (item_name or "").strip()
        if "国外" in region_name or "海外" in region_name or "境外" in region_name:
            return {
                "businessDescription": "这是公司海外市场收入。它主要反映公司能否把产品卖到境外，以及出口价格、汇率和海外需求对收入的影响。",
                "priceDrivers": ["海外需求", "出口报价", "汇率", "贸易政策", "海运费用", "海外竞争格局"],
            }
        if "国内" in region_name or "境内" in region_name:
            return {
                "businessDescription": "这是公司国内市场收入。它主要反映本土客户需求、国内价格周期和区域供需格局对收入的影响。",
                "priceDrivers": ["国内需求景气度", "本土客户订单", "国内报价水平", "区域供需", "运输半径", "竞争格局"],
            }
        return {
            "businessDescription": "这不是单独的一项产品或服务，而是公司在这个地区拿到的收入。看地区拆分，主要是为了判断公司依赖哪些市场，以及海外和国内的需求差异。",
            "priceDrivers": ["区域需求景气度", "当地运价或报价水平", "汇率", "贸易政策", "竞争格局"],
        }

    if dimension == "channel":
        return {
            "businessDescription": "这不是产品分类，而是收入通过什么销售或交付渠道实现。看渠道拆分，主要是为了判断利润有没有回流到公司自己手里。",
            "priceDrivers": ["直销占比", "经销体系议价能力", "客户结构", "渠道费用", "回款效率"],
        }

    if dimension == "industry":
        return {
            "businessDescription": "这反映的是公司把收入分配到哪些行业或应用场景，不是单独的一款产品。看这块主要是为了判断公司最终服务的是哪些下游需求。",
            "priceDrivers": ["下游行业景气度", "客户资本开支", "行业需求波动", "竞争格局", "定价能力"],
        }

    search_sources = [item_name or "", company_main_business or "", industry or ""]
    item_text = search_sources[0]
    fallback_text = " ".join(search_sources[1:])
    for rule in BUSINESS_EXPLANATION_RULES:
        if any(keyword in item_text for keyword in rule["keywords"]):
            return {
                "businessDescription": rule["businessDescription"],
                "priceDrivers": rule["priceDrivers"],
            }

    for rule in BUSINESS_EXPLANATION_RULES:
        if any(keyword in fallback_text for keyword in rule["keywords"]):
            label = company_positioning.get("primaryUnitLabel", "业务")
            business_category = rule.get("businessCategory", "service")
            if business_category == "product":
                description = f"这块可以理解成公司的一个{label}单元，核心还是围绕具体商品销售展开。建议继续结合客户结构、渠道结构和成本结构一起看。"
            elif company_positioning.get("companyNature") == "platform":
                description = f"这块更适合理解成公司的一个{label}单元，核心不是持有货物赚差价，而是看平台流量、商家生态和收费效率怎么变。"
            else:
                description = f"这块更适合理解成公司的一个{label}单元，核心卖的是运输、交付、订阅或其他服务能力，而不是狭义上的实体产品。"
            return {
                "businessDescription": description,
                "priceDrivers": rule["priceDrivers"],
            }

    label = company_positioning.get("primaryUnitLabel", "业务")
    if dimension == "product":
        clean_item_name = (item_name or label or "这项业务").strip()
        if company_positioning.get("companyNature") == "product":
            return {
                "businessDescription": f"{clean_item_name}是公司收入拆分里的一个具体产品线。看它时不要只看收入占比，还要结合售价周期、销量、单位成本和毛利率变化来判断盈利质量。",
                "priceDrivers": ["产品价格", "销量", "原材料成本", "能源成本", "产品结构", "下游需求"],
            }
        if company_positioning.get("companyNature") == "service":
            return {
                "businessDescription": f"{clean_item_name}更适合理解为一个业务交付单元。重点不是单件产品卖了多少，而是客户需求、合同价格、履约成本和产能/人员利用率。",
                "priceDrivers": ["客户订单", "合同价格", "履约成本", "利用率", "交付效率", "竞争格局"],
            }
        return {
            "businessDescription": f"{clean_item_name}是公司收入拆分里的一个平台或业务单元。重点看流量、客户活跃度、收费率和变现效率，而不是只看收入规模。",
            "priceDrivers": ["流量增长", "客户活跃度", "收费率", "广告或服务变现", "竞争格局"],
        }

    if company_positioning.get("companyNature") == "platform":
        return {
            "businessDescription": f"这是公司主营收入里的一个{label}单元。判断它重要不重要，建议优先看流量、商家生态、抽佣率和平台变现效率，而不是只看卖了多少货。",
            "priceDrivers": ["流量增长", "商家活跃度", "抽佣率", "广告变现", "竞争格局"],
        }
    return {
        "businessDescription": f"这是公司主营收入里的一个{label}单元。判断它重要不重要，建议一起看客户是谁、怎么收费、成本怎么变。",
        "priceDrivers": ["行业供需", "产品或服务定价", "销量或利用率", "成本变化", "竞争格局"],
    }


def enrich_business_items(
    items: list[dict],
    company_main_business: str,
    industry: str,
    dimension: str,
    company_positioning: dict,
) -> list[dict]:
    enriched_items: list[dict] = []
    for item in items:
        enriched_item = dict(item)
        enriched_item.update(
            infer_business_explanation(
                item_name=str(item.get("itemName", "")),
                company_main_business=company_main_business,
                industry=industry,
                dimension=dimension,
                company_positioning=company_positioning,
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


def should_use_ai_revenue_explanations() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def build_ai_explanation_items(
    product_items: list[dict],
    region_items: list[dict],
    channel_items: list[dict],
    industry_items: list[dict],
) -> list[dict]:
    combined_items: list[dict] = []
    for dimension, items in [
        ("product", product_items),
        ("region", region_items),
        ("channel", channel_items),
        ("industry", industry_items),
    ]:
        for item in items[:8]:
            combined_items.append(
                {
                    "dimension": dimension,
                    "itemName": item.get("itemName", ""),
                    "revenue": item.get("revenue"),
                    "revenueRatio": item.get("revenueRatio"),
                    "grossMargin": item.get("grossMargin"),
                    "revenueGrowth": item.get("revenueGrowth"),
                }
            )
    return combined_items


def merge_ai_explanations(items: list[dict], dimension: str, explanation_lookup: dict[tuple[str, str], dict]) -> list[dict]:
    merged_items: list[dict] = []
    for item in items:
        merged_item = dict(item)
        item_name = str(item.get("itemName", ""))
        ai_explanation = explanation_lookup.get((dimension, item_name))
        if ai_explanation:
            description = str(ai_explanation.get("businessDescription", "")).strip()
            drivers = ai_explanation.get("priceDrivers")
            if description:
                merged_item["businessDescription"] = description
            if isinstance(drivers, list):
                clean_drivers = [str(driver).strip() for driver in drivers if str(driver).strip()]
                if clean_drivers:
                    merged_item["priceDrivers"] = clean_drivers[:6]
            merged_item["explanationSource"] = "ai"
        else:
            merged_item["explanationSource"] = "rule"
        merged_items.append(merged_item)
    return merged_items


def enrich_revenue_items_with_ai_explanations(
    stock: str,
    profile_payload: dict,
    company_positioning: dict,
    product_items: list[dict],
    region_items: list[dict],
    channel_items: list[dict],
    industry_items: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    if not should_use_ai_revenue_explanations():
        return product_items, region_items, channel_items, industry_items

    explanation_items = build_ai_explanation_items(product_items, region_items, channel_items, industry_items)
    if not explanation_items:
        return product_items, region_items, channel_items, industry_items

    try:
        settings = get_openai_settings()
        client = OpenAI(
            api_key=settings["api_key"],
            base_url=settings["base_url"],
            http_client=httpx.Client(trust_env=False),
        )
        company_context = {
            "stock": stock,
            "companyName": profile_payload.get("companyName", ""),
            "industry": profile_payload.get("industry", ""),
            "mainBusiness": profile_payload.get("mainBusiness", ""),
            "businessScope": profile_payload.get("businessScope", ""),
            "companyPositioning": company_positioning,
        }
        user_prompt = (
            "你是上市公司业务分析师。请根据公司资料和收入拆分项，为每个条目生成更贴近业务实质的中文解释。\n"
            "要求：\n"
            "1. 只能基于给定信息做审慎判断，不要编造未提供的客户、价格或产能数据。\n"
            "2. businessDescription 用 1-2 句中文，解释这个收入项到底卖的是什么/代表什么，以及观察重点。\n"
            "3. priceDrivers 给 4-6 个短词，表示价格或收入变化的主要影响因素。\n"
            "4. 不要使用模板化重复话术；同一公司下不同产品、地区、渠道要体现差异。\n"
            "5. 只输出 JSON，格式为 {\"items\":[{\"dimension\":\"product\",\"itemName\":\"...\",\"businessDescription\":\"...\",\"priceDrivers\":[\"...\"]}]}。\n\n"
            f"公司资料：\n{json.dumps(company_context, ensure_ascii=False, indent=2)}\n\n"
            f"收入拆分项：\n{json.dumps(explanation_items, ensure_ascii=False, indent=2)}"
        )
        response = client.chat.completions.create(
            model=settings["model"],
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "你只输出严格 JSON，不输出 Markdown。"},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        parsed = json.loads((content or "").strip())
        parsed_items = parsed.get("items", [])
        if not isinstance(parsed_items, list):
            raise ValueError("AI explanation payload missing items list.")

        explanation_lookup: dict[tuple[str, str], dict] = {}
        for item in parsed_items:
            if not isinstance(item, dict):
                continue
            dimension = str(item.get("dimension", "")).strip()
            item_name = str(item.get("itemName", "")).strip()
            if dimension and item_name:
                explanation_lookup[(dimension, item_name)] = item

        return (
            merge_ai_explanations(product_items, "product", explanation_lookup),
            merge_ai_explanations(region_items, "region", explanation_lookup),
            merge_ai_explanations(channel_items, "channel", explanation_lookup),
            merge_ai_explanations(industry_items, "industry", explanation_lookup),
        )
    except Exception as exc:
        print(f"[WARN] AI revenue explanations unavailable, fallback to rules: {exc}")
        return product_items, region_items, channel_items, industry_items


def get_revenue_structure_payload(stock: str, years: int = 8) -> dict:
    profile_payload = get_company_profile_payload_with_cache(stock=stock)
    main_business_payload = get_main_business_payload_with_cache(stock=stock)
    annual_report_payload = get_latest_report_text_payload_v2(stock=stock, category="年报", cache_key="annual_report_v1")
    balance_payload = get_balance_payload_with_cache(stock=stock, period=None)
    revenue_market_cap_payload = get_revenue_market_cap_payload_with_cache(stock=stock, years=years)
    profit_driver_model_payload = get_profit_driver_model_payload_with_cache(stock=stock)

    items = main_business_payload.get("items", [])
    company_main_business = str(profile_payload.get("mainBusiness", ""))
    industry = str(profile_payload.get("industry", ""))
    raw_product_items = filter_business_items(items, "按产品分类")
    raw_channel_items = extract_sales_mode_breakdown(annual_report_payload.get("textExcerpt", ""))
    company_positioning = infer_company_positioning(
        company_main_business=company_main_business,
        industry=industry,
        product_items=raw_product_items,
        channel_items=raw_channel_items,
    )

    product_items = enrich_business_items(
        raw_product_items,
        company_main_business=company_main_business,
        industry=industry,
        dimension="product",
        company_positioning=company_positioning,
    )
    region_items = enrich_business_items(
        filter_business_items(items, "按地区分类"),
        company_main_business=company_main_business,
        industry=industry,
        dimension="region",
        company_positioning=company_positioning,
    )
    industry_items = enrich_business_items(
        filter_business_items(items, "按行业分类"),
        company_main_business=company_main_business,
        industry=industry,
        dimension="industry",
        company_positioning=company_positioning,
    )
    channel_items = enrich_business_items(
        raw_channel_items,
        company_main_business=company_main_business,
        industry=industry,
        dimension="channel",
        company_positioning=company_positioning,
    )
    product_items, region_items, channel_items, industry_items = enrich_revenue_items_with_ai_explanations(
        stock=stock,
        profile_payload=profile_payload,
        company_positioning=company_positioning,
        product_items=product_items,
        region_items=region_items,
        channel_items=channel_items,
        industry_items=industry_items,
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
            "interpretedMainBusiness": build_interpreted_main_business_summary(
                company_main_business=company_main_business,
                company_positioning=company_positioning,
                product_items=product_items,
            ),
            "companyIntro": profile_payload.get("companyIntro", ""),
            "trendConclusion": revenue_market_cap_payload.get("conclusion", ""),
        },
        "companyPositioning": company_positioning,
        "profitDriverModel": profit_driver_model_payload,
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
    cash_flow_payload = get_cash_flow_quality_payload_with_cache(stock=stock, years=years)
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
        "cashFlowQuality": {
            "conclusion": cash_flow_payload.get("conclusion"),
            "operatingCashFlow": sample_series_points(cash_flow_payload.get("operatingCashFlow", [])),
            "netProfit": sample_series_points(cash_flow_payload.get("netProfit", [])),
            "cashToProfitRatio": sample_series_points(cash_flow_payload.get("cashToProfitRatio", [])),
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
        context=context,
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
    context: dict | None = None,
) -> dict:
    settings = get_openai_settings()
    context = context or build_ai_analysis_context(stock=stock, period=period, years=years)
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
def api_pe_trend(stock: str = "000333", years: str = "8", refresh: str = ""):
    stock = stock.strip() or "000333"
    years_param = years
    should_refresh = refresh == "1"

    try:
        years = normalize_years(years_param, default=8)

        return get_pe_trend_payload_with_cache(stock=stock, years=years, refresh=should_refresh)

    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "stock": stock, "years": years_param},
            status_code=400,
        )


@app.get("/api/balance")
def api_balance(stock: str = "600519", period: str | None = None):
    stock = stock.strip() or "600519"

    try:
        return get_balance_payload_with_cache(stock=stock, period=period)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "stock": stock, "period": period},
            status_code=400,
        )


@app.get("/api/revenue-market-cap")
def api_revenue_market_cap(stock: str = "000333", years: str = "8"):
    stock = stock.strip() or "000333"
    years_param = years

    try:
        years = normalize_years(years_param, default=8)
        return get_revenue_market_cap_payload_with_cache(stock=stock, years=years)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "stock": stock, "years": years_param},
            status_code=400,
        )


@app.get("/api/revenue-structure")
def api_revenue_structure(stock: str = "600519", years: str = "8", refresh: str = ""):
    stock = stock.strip() or "600519"
    years_param = years
    should_refresh = refresh == "1"

    try:
        years = normalize_years(years_param, default=8)

        return get_cached_payload_or_build(
            "revenue_structure_v8",
            stock,
            years,
            builder=lambda: get_revenue_structure_payload(stock=stock, years=years),
            refresh=should_refresh,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "stock": stock, "years": years_param},
            status_code=400,
        )


@app.get("/api/profit-market-cap")
def api_profit_market_cap(stock: str = "600519", years: str = "8", refresh: str = ""):
    stock = stock.strip() or "600519"
    years_param = years
    should_refresh = refresh == "1"

    try:
        years = normalize_years(years_param, default=8)

        return get_profit_market_cap_payload_with_cache(stock=stock, years=years, refresh=should_refresh)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "stock": stock, "years": years_param},
            status_code=400,
        )


@app.get("/api/cash-flow-quality")
def api_cash_flow_quality(stock: str = "600519", years: str = "8", refresh: str = ""):
    stock = stock.strip() or "600519"
    years_param = years
    should_refresh = refresh == "1"

    try:
        years = normalize_years(years_param, default=8)

        return get_cash_flow_quality_payload_with_cache(stock=stock, years=years, refresh=should_refresh)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "stock": stock, "years": years_param},
            status_code=400,
        )


@app.get("/api/peer-companies")
def api_peer_companies(stock: str = "600519", limit: str = "6", refresh: str = ""):
    stock = normalize_stock_code(stock.strip() or "600519")
    limit_param = limit
    should_refresh = refresh == "1"

    try:
        try:
            normalized_limit = int(limit_param)
        except ValueError:
            normalized_limit = 6
        normalized_limit = max(3, min(normalized_limit, 10))

        return get_peer_companies_payload_with_cache(
            stock=stock,
            limit=normalized_limit,
            refresh=should_refresh,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "stock": stock, "limit": limit_param},
            status_code=400,
        )


@app.get("/api/profit-driver-model")
def api_profit_driver_model(stock: str = "600519", refresh: str = ""):
    stock = normalize_stock_code(stock.strip() or "600519")
    try:
        return get_profit_driver_model_payload_with_cache(stock=stock, refresh=refresh == "1")
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "stock": stock},
            status_code=400,
        )


@app.get("/api/market-index-valuation")
def api_market_index_valuation(index: str = "sp500", years: str = "5", refresh: str = ""):
    try:
        normalized_years = normalize_years(years, default=5)
        return get_market_index_valuation_payload_with_cache(
            index_code=index,
            years=normalized_years,
            refresh=refresh == "1",
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {"error": str(exc), "index": index, "years": years},
            status_code=400,
        )


@app.get("/api/commodity-prices")
def api_commodity_prices(symbols: str = "all", days: str = "30"):
    try:
        return get_cached_payload_or_build(
            "commodity_prices_v1",
            symbols or "all",
            normalize_commodity_days(days),
            builder=lambda: build_commodity_prices_payload(symbols=symbols, days=days),
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {
                "error": str(exc),
                "symbols": symbols,
                "days": days,
            },
            status_code=400,
        )


@app.get("/api/industry-data")
def api_industry_data(industries: str = "baijiu", years: str = "8", refresh: str = ""):
    try:
        normalized_years = normalize_years(years, default=8)
        return get_cached_payload_or_build(
            "industry_data_v5",
            industries or "all",
            normalized_years,
            industry_cache_day(),
            builder=lambda: build_industry_data_payload(industries=industries, years=str(normalized_years)),
            refresh=refresh == "1",
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {
                "error": str(exc),
                "industries": industries,
                "years": years,
            },
            status_code=400,
        )


@app.get("/api/dashboard-data")
def api_dashboard_data(
    stock: str = "600519",
    period: str | None = None,
    years: str = "8",
    includePeers: str = "1",
    refresh: str = "",
):
    stock = stock.strip() or "600519"
    years_param = years
    try:
        normalized_years = normalize_years(years_param, default=8)
        payload = build_dashboard_data_payload(
            stock=stock,
            period=period,
            years=normalized_years,
            include_peers=includePeers != "0",
            refresh=refresh == "1",
        )
        return payload
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {
                "error": str(exc),
                "stock": stock,
                "period": period,
                "years": years_param,
            },
            status_code=400,
        )


@app.post("/api/ai-analysis")
def api_ai_analysis(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
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
        return result
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {
                "error": str(exc),
                "stock": stock,
                "period": period,
                "years": years_param,
            },
            status_code=400,
        )


@app.post("/api/business-type-analysis")
def api_business_type_analysis(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
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
        return result
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return JSONResponse(
            {
                "error": str(exc),
                "stock": stock,
                "period": period,
                "years": years_param,
            },
            status_code=400,
        )


register_system_routes(app)
register_frontend_routes(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5001)

