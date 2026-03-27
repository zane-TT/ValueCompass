from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import AnalysisRequest, AnalysisResponse
from .services import run_analysis


app = FastAPI(title="Equity Research Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
