from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .classifier import infer_industry_modules, normalize_industry_modules


@dataclass(frozen=True)
class IndustryDataDeps:
    normalize_stock_code: Callable[[str], str]
    normalize_years: Callable[..., int]
    get_main_business_payload: Callable[[str], dict]
    get_company_profile_payload: Callable[[str], dict]
    get_latest_report_text_payload: Callable[..., dict]
    build_baijiu_operating_metrics: Callable[[str, dict, dict], dict]
    build_nonferrous_chemical_metrics: Callable[[str, dict, dict], dict]
    build_shipping_metrics: Callable[[str, dict, dict], dict]
    build_financial_sector_metrics: Callable[[str, int, dict], dict]
    build_game_internet_metrics: Callable[[str, dict, dict], dict]
    build_auto_new_energy_metrics: Callable[[str, dict, dict], dict]


def build_industry_data_payload(
    stock: str,
    industries: str | None,
    years: str | None,
    deps: IndustryDataDeps,
) -> dict:
    normalized_stock = deps.normalize_stock_code(stock)
    normalized_years = deps.normalize_years(years, default=8)
    is_auto = str(industries or "auto").strip().lower() in {"", "auto", "自动", "infer", "inferred"}

    main_business_payload = deps.get_main_business_payload(normalized_stock)
    profile_payload = deps.get_company_profile_payload(normalized_stock)
    industry_inference = infer_industry_modules(profile_payload, main_business_payload) if is_auto else None
    modules = industry_inference["modules"] if industry_inference else normalize_industry_modules(industries)
    annual_report_payload = deps.get_latest_report_text_payload(
        stock=normalized_stock,
        category="年报",
        cache_key="annual_report_v1",
    )

    builders: dict[str, Callable[[], dict]] = {
        "baijiu": lambda: deps.build_baijiu_operating_metrics(
            normalized_stock,
            main_business_payload,
            annual_report_payload,
        ),
        "nonferrous_chemical": lambda: deps.build_nonferrous_chemical_metrics(
            normalized_stock,
            main_business_payload,
            annual_report_payload,
        ),
        "shipping": lambda: deps.build_shipping_metrics(normalized_stock, main_business_payload, annual_report_payload),
        "financial": lambda: deps.build_financial_sector_metrics(
            normalized_stock,
            normalized_years,
            annual_report_payload,
        ),
        "game_internet": lambda: deps.build_game_internet_metrics(
            normalized_stock,
            main_business_payload,
            annual_report_payload,
        ),
        "auto_new_energy": lambda: deps.build_auto_new_energy_metrics(
            normalized_stock,
            main_business_payload,
            annual_report_payload,
        ),
    }

    data: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for module in modules:
        try:
            data[module] = builders[module]()
        except Exception as exc:
            print(f"[WARN] Industry module failed, module={module}: {exc}")
            errors[module] = str(exc)

    return {
        "tool": "industry_data",
        "status": "partial" if errors else "ok",
        "stock": normalized_stock,
        "industries": modules,
        "industryInference": industry_inference
        or {
            "mode": "manual",
            "modules": modules,
            "input": industries,
        },
        "data": data,
        "errors": errors,
        "source": ["AKShare", "巨潮资讯", "东方财富主营构成", "国家统计局/公开宏观指标", "海关进出口公开指标"],
    }
