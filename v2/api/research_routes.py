"""
V2 Research Hub API Routes — /api/v2/research/*

Provides on-demand coin analytics: technical profile, instant backtest,
and AI trend prediction.  All endpoints are read-only and isolated from
the production trading fleet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import require_api_key
from .schemas import (
    ResearchPairSchema,
    CoinProfileSchema,
    VCPSetupSchema,
    VCPStageSchema,
    ScorecardSchema,
    TickerSnapshotSchema,
    Week52Schema,
    BacktestRequestSchema,
    BacktestResultSchema,
    PredictRequestSchema,
    PredictResultSchema,
    HorizonForecastSchema,
)

research_router = APIRouter()

# Module-level reference injected by init_router in router.py
_research_service = None


def init_research_router(research_service) -> None:
    """Called by the main init_router to wire the service reference."""
    global _research_service
    _research_service = research_service


# ── Helper: ensure service is available ──────────────────────────────────────

def _get_service():
    if _research_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Research service not initialised",
        )
    return _research_service


# ── GET /research/coins ───────────────────────────────────────────────────────

@research_router.get(
    "/coins",
    response_model=list[ResearchPairSchema],
    dependencies=[Depends(require_api_key)],
    tags=["research"],
    summary="List all searchable CoinDCX trading pairs",
)
async def list_research_coins() -> list[ResearchPairSchema]:
    """Return the full catalogue of supported pairs for the Research Hub."""
    from v2.services.research_service.symbol_normalizer import get_supported_pairs_info
    pairs = get_supported_pairs_info()
    return [ResearchPairSchema(**p) for p in pairs]


# ── GET /research/coin/{symbol:path} ──────────────────────────────────────────

@research_router.get(
    "/coin/{symbol:path}",
    response_model=CoinProfileSchema,
    dependencies=[Depends(require_api_key)],
    tags=["research"],
    summary="Full technical profile, VCP setup, and 100-point scorecard for a coin",
)
async def get_coin_profile(symbol: str) -> CoinProfileSchema:
    """
    Fetch live multi-TF indicators, Minervini VCP detection,
    and 4-pillar quality scorecard for any supported CoinDCX pair.
    """
    svc = _get_service()
    try:
        data = await svc.fetch_full_coin_profile(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Market data fetch failed: {exc}",
        )

    # Build validated response
    ticker = TickerSnapshotSchema(**data["ticker"])
    week52 = Week52Schema(**data["week52"])

    vcp_raw = data["vcp_setup"]
    vcp = VCPSetupSchema(
        detected=vcp_raw["detected"],
        stages=[VCPStageSchema(**s) for s in vcp_raw.get("stages", [])],
        pivot_buy_point=vcp_raw.get("pivot_buy_point"),
        hard_stop_loss=vcp_raw.get("hard_stop_loss"),
        target_1=vcp_raw.get("target_1"),
        target_2=vcp_raw.get("target_2"),
        contraction_count=vcp_raw.get("contraction_count", 0),
        setup_quality=vcp_raw.get("setup_quality", "NO_SETUP"),
    )

    scorecard = ScorecardSchema(**data["scorecard"])

    return CoinProfileSchema(
        pair=data["pair"],
        fetched_at=data["fetched_at"],
        ticker=ticker,
        week52=week52,
        indicators=data["indicators"],
        vcp_setup=vcp,
        scorecard=scorecard,
    )


# ── POST /research/backtest ───────────────────────────────────────────────────

@research_router.post(
    "/backtest",
    response_model=BacktestResultSchema,
    dependencies=[Depends(require_api_key)],
    tags=["research"],
    summary="Run an instant on-demand historical backtest for a coin",
)
async def run_backtest(body: BacktestRequestSchema) -> BacktestResultSchema:
    """
    Execute a single-coin backtest with zero look-ahead bias
    and 1.572% round-trip statutory friction (fee + GST + TDS + slippage).
    """
    svc = _get_service()
    try:
        result = await svc.run_on_demand_backtest(
            symbol=body.symbol,
            strategy=body.strategy,
            days=body.days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {exc}",
        )
    return BacktestResultSchema(**result)


# ── POST /research/predict ────────────────────────────────────────────────────

@research_router.post(
    "/predict",
    response_model=PredictResultSchema,
    dependencies=[Depends(require_api_key)],
    tags=["research"],
    summary="Generate AI multi-horizon trend prediction for a coin",
)
async def predict_trend(body: PredictRequestSchema) -> PredictResultSchema:
    """
    Rule-based multi-horizon forecast (1h, 4h, 24h).
    Analyzes EMA stack, RSI, MACD histogram, RVOL, and Bollinger Band width
    to generate directional bias, confidence score, catalysts, and risk factors.
    """
    svc = _get_service()
    try:
        result = await svc.predict_trend_and_catalysts(symbol=body.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {exc}",
        )

    horizons = {
        k: HorizonForecastSchema(**v)
        for k, v in result["horizons"].items()
    }

    return PredictResultSchema(
        pair=result["pair"],
        predicted_at=result["predicted_at"],
        method=result["method"],
        horizons=horizons,
        key_support_levels=result.get("key_support_levels", []),
        key_resistance_levels=result.get("key_resistance_levels", []),
        bullish_catalysts=result.get("bullish_catalysts", []),
        risk_factors=result.get("risk_factors", []),
        summary=result.get("summary", ""),
    )

