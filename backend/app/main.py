from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .langchain_demo import run_langchain_openai_demo
from .models import (
    AgentDemoRequest,
    AgentDemoResponse,
    AnalysisRequest,
    AnalysisResponse,
    BulletinItemModel,
    FinancialHistoryRequest,
    FinancialHistoryResponse,
    FinancialReportRequest,
    FinancialReportResponse,
    YearlyFinancialData,
)
from .scraper import (
    get_annual_reports,
    get_financial_history,
    get_quarterly_reports,
    get_semiannual_reports,
)
from .services import run_analysis

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Equity Research Agent API", version="0.1.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGIN",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sample-tickers")
def sample_tickers() -> list[dict[str, str]]:
    return [
        {"ticker": "600519", "name": "Kweichow Moutai Sample"},
        {"ticker": "300999", "name": "Growth Hardware Sample"},
    ]


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalysisRequest) -> AnalysisResponse:
    result = run_analysis(request.ticker)
    if not result:
        raise HTTPException(status_code=404, detail="Ticker not found in MVP sample dataset.")
    return result


@app.post("/agent-demo", response_model=AgentDemoResponse)
def agent_demo(request: AgentDemoRequest) -> AgentDemoResponse:
    try:
        return run_langchain_openai_demo(request.question, request.ticker)
    except RuntimeError as exc:
        print(exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"agent_demo unexpected error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/financial-reports", response_model=FinancialReportResponse)
async def get_financial_reports(request: FinancialReportRequest) -> FinancialReportResponse:
    try:
        if request.report_type == "annual":
            report = await get_annual_reports(request.ticker)
        elif request.report_type == "semiannual":
            report = await get_semiannual_reports(request.ticker)
        elif request.report_type in ("q1", "q3"):
            quarter = int(request.report_type[1])
            report = await get_quarterly_reports(request.ticker, quarter)
        else:
            raise HTTPException(status_code=400, detail="Invalid report type")
        
        return FinancialReportResponse(
            ticker=report.ticker,
            company_name=report.company_name,
            bulletins=[
                BulletinItemModel(
                    title=b.title,
                    publish_date=b.publish_date,
                    url=b.url,
                    bulletin_type=b.bulletin_type
                )
                for b in report.bulletins
            ],
            fetched_at=report.fetched_at
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch from Sina Finance: {str(exc)}")
    except Exception as exc:
        print(f"get_financial_reports unexpected error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/financial-history", response_model=FinancialHistoryResponse)
async def get_financial_history_api(request: FinancialHistoryRequest) -> FinancialHistoryResponse:
    try:
        result = await get_financial_history(request.ticker, request.start_year, request.end_year)
        
        return FinancialHistoryResponse(
            ticker=result.ticker,
            company_name=result.company_name,
            yearly_data=[
                YearlyFinancialData(
                    year=data.year,
                    revenue=data.revenue,
                    net_profit=data.net_profit,
                    total_assets=data.total_assets,
                    pe_ratio=data.pe_ratio,
                    pb_ratio=data.pb_ratio
                )
                for data in result.yearly_data
            ],
            fetched_at=result.fetched_at
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch financial data: {str(exc)}")
    except Exception as exc:
        print(f"get_financial_history_api unexpected error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
