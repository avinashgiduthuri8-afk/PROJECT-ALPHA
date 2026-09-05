"""
V2 Dashboard Command & Control API Routes.

Exposes REST endpoints for fleet monitoring, signal rankings, bot pause/resume controls,
and global emergency stop circuit breaker triggers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from v2.api.auth import require_api_key

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_dashboard_aggregator: Optional[Any] = None


def init_dashboard_routes(aggregator: Any) -> None:
    """Initialize router state with DashboardAggregator instance."""
    global _dashboard_aggregator
    _dashboard_aggregator = aggregator


def get_aggregator() -> Any:
    if _dashboard_aggregator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard aggregator service not initialized.",
        )
    return _dashboard_aggregator


@router.get(
    "/overview",
    dependencies=[Depends(require_api_key)],
)
async def get_dashboard_overview():
    """Return comprehensive system snapshot for UI dashboard initialization."""
    agg = get_aggregator()
    return await agg.get_overview_snapshot()


@router.get(
    "/fleet",
    dependencies=[Depends(require_api_key)],
)
async def get_fleet_telemetry():
    """Return per-bot telemetry and capital allocation metrics."""
    agg = get_aggregator()
    overview = await agg.get_overview_snapshot()
    return {
        "execution_fleet": overview.get("execution_fleet", {}),
        "total_allocated_inr": 1000000.0,
    }


@router.get(
    "/signals",
    dependencies=[Depends(require_api_key)],
)
async def get_ranked_signals(
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return top ranked signals and scanner conversion funnel metrics."""
    agg = get_aggregator()
    overview = await agg.get_overview_snapshot()
    return {
        "funnel": overview.get("scanner_funnel", {}),
        "top_signals": [],
    }


@router.post(
    "/fleet/{bot_name}/pause",
    dependencies=[Depends(require_api_key)],
)
async def pause_fleet_bot(
    bot_name: str = Path(..., description="Bot name: STE, HDA, VCP, BBS"),
):
    """Temporarily pause trade execution for a specific sub-account bot."""
    agg = get_aggregator()
    bot_upper = bot_name.upper()
    if bot_upper not in ("STE", "HDA", "VCP", "BBS"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bot name '{bot_name}'. Must be one of STE, HDA, VCP, BBS.",
        )
    agg.pause_bot(bot_upper)
    return {
        "status": "PAUSED",
        "bot_name": bot_upper,
        "message": f"Trade execution for bot '{bot_upper}' has been paused.",
    }


@router.post(
    "/fleet/{bot_name}/resume",
    dependencies=[Depends(require_api_key)],
)
async def resume_fleet_bot(
    bot_name: str = Path(..., description="Bot name: STE, HDA, VCP, BBS"),
):
    """Resume automated trade execution for a specific bot."""
    agg = get_aggregator()
    bot_upper = bot_name.upper()
    if bot_upper not in ("STE", "HDA", "VCP", "BBS"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bot name '{bot_name}'. Must be one of STE, HDA, VCP, BBS.",
        )
    agg.resume_bot(bot_upper)
    return {
        "status": "ACTIVE",
        "bot_name": bot_upper,
        "message": f"Trade execution for bot '{bot_upper}' has been resumed.",
    }


@router.post(
    "/emergency-stop",
    dependencies=[Depends(require_api_key)],
)
async def emergency_stop():
    """Trip global circuit breaker and halt all live order routing immediately."""
    agg = get_aggregator()
    agg.trigger_emergency_stop()
    return {
        "status": "EMERGENCY_STOP_TRIPPED",
        "message": "Global circuit breaker tripped. All automated order routing halted.",
    }
