from __future__ import annotations

import sys
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

try:
    from ..core.cache import get_cache_overview, list_recent_cache_files
    from ..core.config import APP_STARTED_AT
except ImportError:
    from core.cache import get_cache_overview, list_recent_cache_files
    from core.config import APP_STARTED_AT


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
        "commodityPrices": "/api/commodity-prices?symbols=AL,CU,RB&days=30",
        "industryData": "/api/industry-data?stock=600519&industries=auto&years=8",
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


def register_system_routes(app: FastAPI) -> None:
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
