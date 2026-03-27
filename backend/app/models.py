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
