from __future__ import annotations

from statistics import mean

from .data import get_company_data
from .models import AnalysisResponse, CompanyProfile, KeyMetric, MemoSection, RiskFlag


def _pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def run_analysis(ticker: str) -> AnalysisResponse | None:
    company = get_company_data(ticker)
    if not company:
        return None

    annual = company["financials"]["annual"]
    latest = annual[-1]
    previous = annual[-2]
    market = company["financials"]["market"]

    revenue_growth = _pct(latest["revenue"], previous["revenue"])
    profit_growth = _pct(latest["net_profit"], previous["net_profit"])
    receivable_growth = _pct(latest["accounts_receivable"], previous["accounts_receivable"])
    inventory_growth = _pct(latest["inventory"], previous["inventory"])
    ocf_to_profit = latest["operating_cash_flow"] / latest["net_profit"] if latest["net_profit"] else 0
    average_roe = mean(item["roe"] for item in annual[-3:])

    metrics = [
        KeyMetric(
            label="Revenue Growth",
            value=_format_pct(revenue_growth),
            interpretation="Used to judge whether top-line expansion is still intact.",
        ),
        KeyMetric(
            label="Net Profit Growth",
            value=_format_pct(profit_growth),
            interpretation="Checks whether earnings growth keeps pace with revenue.",
        ),
        KeyMetric(
            label="OCF / Net Profit",
            value=f"{ocf_to_profit:.2f}x",
            interpretation="A quick quality-of-earnings signal from cash conversion.",
        ),
        KeyMetric(
            label="ROE (3Y Avg)",
            value=_format_pct(average_roe),
            interpretation="Core profitability anchor for quality and valuation framing.",
        ),
        KeyMetric(
            label="PE / PB",
            value=f"{market['pe_ttm']:.1f}x / {market['pb']:.2f}x",
            interpretation="Current market valuation compared with business quality.",
        ),
        KeyMetric(
            label="Dividend Yield",
            value=_format_pct(market["dividend_yield"]),
            interpretation="Useful for mature cash-generating businesses and downside support.",
        ),
    ]

    quality_score = 78
    risk_flags: list[RiskFlag] = []

    if receivable_growth > revenue_growth + 0.12:
        quality_score -= 18
        risk_flags.append(
            RiskFlag(
                level="high",
                title="Receivables outgrowing revenue",
                detail=(
                    f"Accounts receivable grew {_format_pct(receivable_growth)} versus revenue growth "
                    f"of {_format_pct(revenue_growth)}. This can signal weaker collection quality."
                ),
            )
        )

    if inventory_growth > revenue_growth + 0.10:
        quality_score -= 12
        risk_flags.append(
            RiskFlag(
                level="medium",
                title="Inventory accumulation",
                detail=(
                    f"Inventory grew {_format_pct(inventory_growth)}, faster than revenue. "
                    "This deserves follow-up on sell-through and potential impairment risk."
                ),
            )
        )

    if ocf_to_profit < 0.7:
        quality_score -= 20
        risk_flags.append(
            RiskFlag(
                level="high",
                title="Weak cash conversion",
                detail=(
                    f"Operating cash flow covers only {ocf_to_profit:.2f}x of net profit. "
                    "Reported earnings may be less reliable than the headline profit suggests."
                ),
            )
        )

    goodwill_ratio = latest["goodwill"] / latest["shareholders_equity"] if latest["shareholders_equity"] else 0
    if goodwill_ratio > 0.12:
        quality_score -= 8
        risk_flags.append(
            RiskFlag(
                level="medium",
                title="Meaningful goodwill balance",
                detail=(
                    f"Goodwill is {_format_pct(goodwill_ratio)} of equity. "
                    "The acquisition logic and impairment risk should be monitored."
                ),
            )
        )

    if latest["construction_in_progress"] > latest["fixed_assets"] * 0.3:
        quality_score -= 8
        risk_flags.append(
            RiskFlag(
                level="medium",
                title="Heavy capital build-out",
                detail="Construction in progress is elevated relative to fixed assets, so future returns on capex need validation.",
            )
        )

    quality_score = max(25, min(95, quality_score))
    valuation_stance = _build_valuation_stance(company["industry"], average_roe, market["pe_ttm"], market["pb"], ocf_to_profit)
    margin_of_safety = _build_margin_of_safety(company["industry"], quality_score, market["pe_ttm"], market["pb"], market["dividend_yield"])
    memo = _build_memo(company, revenue_growth, profit_growth, quality_score, valuation_stance, margin_of_safety, risk_flags)

    return AnalysisResponse(
        company=CompanyProfile(
            ticker=company["ticker"],
            name=company["name"],
            industry=company["industry"],
            description=company["description"],
        ),
        metrics=metrics,
        quality_score=quality_score,
        valuation_stance=valuation_stance,
        margin_of_safety=margin_of_safety,
        risk_flags=risk_flags,
        memo=memo,
    )


def _build_valuation_stance(industry: str, average_roe: float, pe: float, pb: float, ocf_to_profit: float) -> str:
    if industry == "consumer_staples":
        if average_roe > 0.25 and pe < 28 and pb < 9.5 and ocf_to_profit > 0.9:
            return "High-quality consumer compounder trading in a reasonable zone relative to its profitability."
        return "Quality looks strong, but valuation should be weighed carefully against long-run growth durability."

    if industry == "industrials":
        if pb < 1.8 and pe < 18 and average_roe >= 0.10:
            return "Asset-based valuation is not stretched, but the case depends on execution and cash conversion improving."
        return "The headline multiple is not demanding, yet weak quality reduces valuation comfort."

    return "Valuation requires more peer and industry-specific context."


def _build_margin_of_safety(industry: str, quality_score: int, pe: float, pb: float, dividend_yield: float) -> str:
    if industry == "consumer_staples":
        if quality_score >= 80 and pe < 25:
            return "Margin of safety comes from durable brand economics, strong cash flow, and a valuation below peak quality premiums."
        return "Margin of safety is moderate; quality is real, but price still assumes continued stability."

    if industry == "industrials":
        if pb <= 1.5 and quality_score >= 65:
            return "Downside protection is mostly balance-sheet based rather than growth based."
        return "Margin of safety is thin until receivables, inventory, and cash conversion improve."

    if dividend_yield > 0.04:
        return "Dividend support offers some downside cushion."
    return "Safety margin is currently uncertain."


def _build_memo(
    company: dict,
    revenue_growth: float,
    profit_growth: float,
    quality_score: int,
    valuation_stance: str,
    margin_of_safety: str,
    risk_flags: list[RiskFlag],
) -> list[MemoSection]:
    thesis = (
        f"{company['name']} shows {_format_pct(revenue_growth)} revenue growth and "
        f"{_format_pct(profit_growth)} profit growth. The current business framing is: "
        f"{company['description']}"
    )

    if quality_score >= 80:
        quality_line = "Financial quality is supportive: profitability is strong and profit is backed by cash generation."
    elif quality_score >= 60:
        quality_line = "Financial quality is mixed, so balance-sheet and cash-flow follow-up remains important."
    else:
        quality_line = "Financial quality is fragile, and the growth story needs more proof in cash and asset quality."

    risk_text = (
        "Key risks include: " + "; ".join(flag.title.lower() for flag in risk_flags)
        if risk_flags
        else "No major accounting-quality flags were triggered by the current rules."
    )

    falsification_points = [
        "If revenue growth decelerates for multiple periods while valuation remains elevated, the thesis weakens.",
        "If operating cash flow continues to trail profit, the quality case should be downgraded.",
    ]

    if company["industry"] == "consumer_staples":
        falsification_points.append("If margin structure breaks or pricing power fades, the premium multiple is harder to defend.")

    if company["industry"] == "industrials":
        falsification_points.append("If capex rises but returns on new capacity stay low, the asset story loses credibility.")

    if risk_flags:
        falsification_points.append("Any worsening in receivables, inventory, or goodwill indicators should trigger a fresh review.")

    return [
        MemoSection(title="Investment Logic", body=f"{thesis} {quality_line}"),
        MemoSection(title="Valuation View", body=f"{valuation_stance} {margin_of_safety}"),
        MemoSection(title="Risk Review", body=risk_text),
        MemoSection(title="Falsification Points", body=" ".join(falsification_points)),
    ]
