from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .classifier import normalize_industry_modules


INDUSTRY_SAMPLE_STOCKS = {
    "baijiu": "600519",
    "nonferrous_chemical": "601600",
    "shipping": "601919",
    "financial": "601288",
    "game_internet": "300052",
    "auto_new_energy": "002594",
}


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
    industries: str | None,
    years: str | None,
    deps: IndustryDataDeps,
) -> dict:
    normalized_years = deps.normalize_years(years, default=8)
    modules = normalize_industry_modules(industries)
    sample_stocks = {
        module: deps.normalize_stock_code(INDUSTRY_SAMPLE_STOCKS[module])
        for module in modules
        if module in INDUSTRY_SAMPLE_STOCKS
    }

    def module_context(module: str) -> tuple[str, dict, dict]:
        sample_stock = sample_stocks[module]
        return (
            sample_stock,
            deps.get_main_business_payload(sample_stock),
            deps.get_latest_report_text_payload(
                stock=sample_stock,
                category="年报",
                cache_key="annual_report_v1",
            ),
        )

    builders: dict[str, Callable[[], dict]] = {
        "baijiu": lambda: deps.build_baijiu_operating_metrics(*module_context("baijiu")),
        "nonferrous_chemical": lambda: deps.build_nonferrous_chemical_metrics(*module_context("nonferrous_chemical")),
        "shipping": lambda: deps.build_shipping_metrics(*module_context("shipping")),
        "financial": lambda: deps.build_financial_sector_metrics(
            sample_stocks["financial"],
            normalized_years,
            module_context("financial")[2],
        ),
        "game_internet": lambda: deps.build_game_internet_metrics(*module_context("game_internet")),
        "auto_new_energy": lambda: deps.build_auto_new_energy_metrics(*module_context("auto_new_energy")),
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
        "industries": modules,
        "sampleStocks": sample_stocks,
        "industryInference": {
            "mode": "manual",
            "modules": modules,
            "input": industries,
        },
        "data": data,
        "errors": errors,
        "source": [
            "AKShare",
            "巨潮资讯",
            "东方财富主营构成",
            "国家统计局/公开宏观指标",
            "海关进出口公开指标",
            "能源价格、库存与碳市场公开指标",
        ],
    }
