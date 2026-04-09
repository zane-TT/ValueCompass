from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .langchain_demo import run_langchain_openai_demo
from .models import AgentDemoRequest, AgentDemoResponse, AnalysisRequest, AnalysisResponse
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
