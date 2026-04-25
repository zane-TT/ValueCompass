from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    ticker: str = Field(..., description="Ticker symbol matching the sample or future live connector.")


class KeyMetric(BaseModel):
    label: str
    value: str
    interpretation: str


class RiskFlag(BaseModel):
    level: Literal["low", "medium", "high"]
    title: str
    detail: str


class MemoSection(BaseModel):
    title: str
    body: str


class CompanyProfile(BaseModel):
    ticker: str
    name: str
    industry: str
    description: str


class AnalysisResponse(BaseModel):
    company: CompanyProfile
    metrics: list[KeyMetric]
    quality_score: int
    valuation_stance: str
    margin_of_safety: str
    risk_flags: list[RiskFlag]
    memo: list[MemoSection]


class AgentDemoRequest(BaseModel):
    question: str = Field(..., description="Natural-language question for the LangChain + OpenAI demo.")
    ticker: str | None = Field(default=None, description="Optional target ticker that the agent can use in tool calls.")


class AgentToolCall(BaseModel):
    name: str
    args: dict
    result: dict | list | str


class AgentDemoResponse(BaseModel):
    answer: str
    model: str
    tool_calls: list[AgentToolCall]


class BulletinItemModel(BaseModel):
    title: str
    publish_date: str
    url: str
    bulletin_type: str


class FinancialReportRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol (e.g., 600519)")
    report_type: Literal["annual", "semiannual", "q1", "q3"] = Field(
        default="annual",
        description="Type of report: annual (年度报告), semiannual (半年报), q1 (一季报), q3 (三季报)"
    )


class FinancialReportResponse(BaseModel):
    ticker: str
    company_name: str
    bulletins: list[BulletinItemModel]
    fetched_at: str


class YearlyFinancialData(BaseModel):
    year: str
    revenue: float | None
    net_profit: float | None
    total_assets: float | None
    pe_ratio: float | None
    pb_ratio: float | None


class FinancialHistoryRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol (e.g., 600519)")
    start_year: str = Field(default="2010", description="Start year for data retrieval")
    end_year: str = Field(default="2025", description="End year for data retrieval")


class FinancialHistoryResponse(BaseModel):
    ticker: str
    company_name: str
    yearly_data: list[YearlyFinancialData]
    fetched_at: str
