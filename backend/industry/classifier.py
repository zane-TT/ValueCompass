from __future__ import annotations

import re


INDUSTRY_MODULES = ["baijiu", "nonferrous_chemical", "shipping", "financial", "game_internet", "auto_new_energy"]


INDUSTRY_MODULE_KEYWORDS: dict[str, list[str]] = {
    "baijiu": ["白酒", "酒类", "茅台", "五粮液", "泸州老窖", "酿造", "制酒", "高粱", "酱香", "浓香"],
    "nonferrous_chemical": [
        "有色",
        "铝",
        "铜",
        "锌",
        "铅",
        "镍",
        "锡",
        "氧化铝",
        "电解铝",
        "化工",
        "煤化工",
        "炼化",
        "PVC",
        "纯碱",
        "尿素",
        "甲醇",
        "玻璃",
        "PTA",
        "乙二醇",
    ],
    "shipping": ["航运", "海运", "集装箱", "港口", "码头", "船舶", "船队", "班轮", "货运", "TEU", "吞吐量"],
    "financial": ["银行", "保险", "证券", "券商", "信托", "资管", "资产管理", "贷款", "存款", "保费", "承保", "经纪"],
    "game_internet": ["游戏", "互联网", "软件", "信息服务", "广告", "平台", "网络", "在线", "用户", "流量", "云服务"],
    "auto_new_energy": ["汽车", "乘用车", "整车", "新能源", "电池", "锂电", "碳酸锂", "储能", "光伏", "充电", "车型"],
}


INDUSTRY_ALIASES = {
    "白酒": "baijiu",
    "有色": "nonferrous_chemical",
    "化工": "nonferrous_chemical",
    "航运": "shipping",
    "银行": "financial",
    "保险": "financial",
    "券商": "financial",
    "游戏": "game_internet",
    "互联网": "game_internet",
    "汽车": "auto_new_energy",
    "新能源": "auto_new_energy",
}

FIELD_WEIGHTS = {
    "industry": 5,
    "main_business": 4,
    "main_business_items": 4,
    "company_name": 2,
    "business_scope": 1,
}


def normalize_industry_modules(industries: str | None) -> list[str]:
    text = str(industries or "all").strip().lower()
    if text in {"", "all", "全部", "*"}:
        return INDUSTRY_MODULES
    if text in {"auto", "自动", "infer", "inferred"}:
        return []

    selected = []
    for item in re.split(r"[,，\s]+", text):
        module = INDUSTRY_ALIASES.get(item, item)
        if module in INDUSTRY_MODULES and module not in selected:
            selected.append(module)
    return selected or INDUSTRY_MODULES


def score_text_for_modules(text: str, field: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    text_lower = str(text or "").lower()
    weight = FIELD_WEIGHTS[field]
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    for module, keywords in INDUSTRY_MODULE_KEYWORDS.items():
        matched = [keyword for keyword in keywords if keyword and keyword.lower() in text_lower]
        if matched:
            scores[module] = len(matched) * weight
            evidence[module] = [f"{field}:{keyword}" for keyword in matched[:8]]
    return scores, evidence


def infer_industry_modules(profile_payload: dict, main_business_payload: dict, max_modules: int = 2) -> dict:
    items = main_business_payload.get("items") if isinstance(main_business_payload, dict) else []
    item_text = " ".join(
        [
            " ".join([str(item.get("categoryType") or ""), str(item.get("itemName") or "")])
            for item in items
            if isinstance(item, dict)
        ]
    )
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    fields = {
        "industry": str(profile_payload.get("industry") or ""),
        "main_business": str(profile_payload.get("mainBusiness") or ""),
        "main_business_items": item_text,
        "company_name": str(profile_payload.get("companyName") or ""),
        "business_scope": str(profile_payload.get("businessScope") or ""),
    }
    for field, text in fields.items():
        field_scores, field_evidence = score_text_for_modules(text, field)
        for module, score in field_scores.items():
            scores[module] = scores.get(module, 0) + score
            evidence.setdefault(module, []).extend(field_evidence.get(module, []))

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_score = ranked[0][1] if ranked else 0
    selected = [
        module
        for module, score in ranked
        if score >= 2 and (score == top_score or score >= max(2, top_score * 0.6))
    ][:max_modules]
    if not selected and ranked:
        selected = [ranked[0][0]]
    if not selected:
        selected = INDUSTRY_MODULES

    return {
        "mode": "auto",
        "modules": selected,
        "scores": scores,
        "evidence": {module: evidence.get(module, []) for module in selected},
        "confidence": "high" if top_score >= 3 else "medium" if top_score >= 1 else "low",
        "fallback": not bool(ranked),
    }
