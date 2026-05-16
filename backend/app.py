from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import akshare as ak
import akshare.stock_feature.stock_disclosure_cninfo as disclosure_cninfo
import httpx
import pandas as pd
import requests
from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from openai import OpenAI
from dotenv import load_dotenv

try:
    from pypdf import PdfReader
except ImportError:
    bundled_python_packages = r"C:\Users\1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages"
    if bundled_python_packages not in sys.path:
        sys.path.append(bundled_python_packages)
    from pypdf import PdfReader

app = FastAPI(title="ValueCompass API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

YI = 100000000
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
FRONTEND_OUT_DIR = BASE_DIR.parent / "frontend" / "out"
load_dotenv(BASE_DIR / ".env")
DEFAULT_OPENAI_BASE_URL = "https://api.openai-proxy.org/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.4-nano-2026-03-17"
DEFAULT_OPENAI_TEMPERATURE = 0.1
APP_STARTED_AT = datetime.now(timezone.utc)
AK_DATA_CACHE_TTL_SECONDS = 300
AK_SUBPROCESS_TIMEOUT_SECONDS = 45


class InflightCall:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


INFLIGHT_LOCK = threading.Lock()
INFLIGHT_CALLS: dict[tuple[object, ...], InflightCall] = {}
AK_DATA_CACHE: dict[tuple[object, ...], tuple[float, pd.DataFrame]] = {}


def get_frontend_file(path: str) -> Path | None:
    candidate = (FRONTEND_OUT_DIR / path).resolve()
    try:
        candidate.relative_to(FRONTEND_OUT_DIR.resolve())
    except ValueError:
        return None

    return candidate if candidate.is_file() else None

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
            return json.load(cache_file)
    except json.JSONDecodeError:
        print(f"[WARN] Cache corrupted, rebuilding: {path.name}")
        path.unlink(missing_ok=True)
        return None


def save_cached_payload(payload: dict, prefix: str, *parts: object) -> dict:
    ensure_cache_dir()
    path = cache_file_path(prefix, *parts)
    tmp_path = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as cache_file:
        json.dump(payload, cache_file, ensure_ascii=False, indent=2)
    tmp_path.replace(path)
    print(f"[INFO] Cache saved: {path.name}")
    return payload


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


def get_ak_dataframe_cached(key: tuple[object, ...], builder: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    now = time.monotonic()
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
    fallback_payload = rule_classify_profit_driver_model(profile_payload, main_business_payload)

    try:
        ai_payload = ai_classify_profit_driver_model(profile_payload, main_business_payload)
        return ai_payload or fallback_payload
    except Exception as exc:
        print(f"[WARN] AI driver model classification unavailable, fallback to rules: {exc}")
        fallback_payload["aiError"] = str(exc)
        return fallback_payload


def get_profit_driver_model_payload_with_cache(stock: str, refresh: bool = False) -> dict:
    return get_cached_payload_or_build(
        "profit_driver_model_v1",
        stock,
        builder=lambda: build_profit_driver_model_payload(stock=stock),
        refresh=refresh,
    )


def build_health_payload() -> dict:
    now = datetime.now(timezone.utc)
    endpoints = {
        "dashboardData": "/api/dashboard-data?stock=600519&years=8",
        "balance": "/api/balance?stock=600519",
        "revenueMarketCap": "/api/revenue-market-cap?stock=000333&years=8",
        "revenueStructure": "/api/revenue-structure?stock=600519&years=8",
        "profitMarketCap": "/api/profit-market-cap?stock=600519&years=8",
        "cashFlowQuality": "/api/cash-flow-quality?stock=600519&years=8",
        "peerCompanies": "/api/peer-companies?stock=600519&limit=6",
        "peTrend": "/api/pe-trend?stock=600519&years=8",
        "profitDriverModel": "/api/profit-driver-model?stock=600519",
        "aiAnalysis": "POST /api/ai-analysis",
        "businessTypeAnalysis": "POST /api/business-type-analysis",
    }
    return {
        "status": "ok",
        "service": "ValueCompass backend",
        "startedAt": APP_STARTED_AT.isoformat(),
        "now": now.isoformat(),
        "uptimeSeconds": round((now - APP_STARTED_AT).total_seconds(), 3),
        "pythonVersion": sys.version.split()[0],
        "cache": get_cache_overview(),
        "availableEndpoints": endpoints,
    }


def build_cache_stats_payload(limit: int = 10) -> dict:
    recent_limit = max(1, min(int(limit), 50))
    return {
        "status": "ok",
        "cache": get_cache_overview(),
        "recentFiles": list_recent_cache_files(limit=recent_limit),
    }


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
            "revenue_structure_v5",
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
        or "其他" in normalized_name
        or "补充" in normalized_name
        or "抵销" in normalized_name
        or "相互抵销" in normalized_name
    )


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
            "revenue_structure_v5",
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


@app.get("/api/health")
def api_health():
    return build_health_payload()


@app.get("/api/cache/stats")
def api_cache_stats(limit: str = "10"):
    limit = limit.strip() or "10"
    try:
        recent_limit = max(1, min(int(limit), 50))
    except ValueError:
        return JSONResponse(
            {"error": "limit must be an integer between 1 and 50."},
            status_code=400,
        )

    return build_cache_stats_payload(limit=recent_limit)


@app.get("/")
@app.get("/{path:path}")
def serve_frontend(path: str = ""):
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    requested_file = get_frontend_file(path) if path else None
    if requested_file is not None:
        return FileResponse(requested_file)

    index_file = FRONTEND_OUT_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)

    return JSONResponse(
        {
            "message": "Frontend has not been built yet. Run `npm run build` in frontend first.",
            "healthApi": "/api/health",
            "cacheStatsApi": "/api/cache/stats?limit=10",
        },
        status_code=503,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5001)
