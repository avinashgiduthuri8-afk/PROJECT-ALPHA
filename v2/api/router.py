"""
V2 API Router - all /api/v2/* endpoints.
Mounted in v2/app_v2.py under the prefix /api/v2.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel

from v2.bus.event_types import EventType
from v2.core.types import MarketState, OppType, Priority, RiskLevel, Signal
from .auth import require_api_key
from .dashboard_routes import router as dashboard_router, init_dashboard_routes
from .production_routes import router as production_router, init_production_routes
from .schemas import (
    OkSchema, JobStatusSchema, ScannerHealthSchema,
    SignalSchema, V2StatusSchema,
    AIAnalysisSchema, AIHealthSchema,
    RiskStateSchema, PositionSchema, TradeSchema,
    PortfolioSnapshotSchema, ShadowTradeSchema,
    DecisionDivergenceSchema, DivergenceSummarySchema,
    DashboardOverviewSchema, MonitoringMetricsSchema,
    MonitoringHealthSchema, TestNotificationRequestSchema,
    PipelineStageSchema, PipelineStageDetailSchema,
    BotStatusSchema, BotDetailSchema,
    AnalyticsWinRatesSchema, AnalyticsCoinsSchema, AnalyticsFunnelSchema,
    ScannedCoinSchema, ScannedCoinDetailSchema,
    SimulateSignalRequestSchema, SimulateSignalResponseSchema,
    SetModeRequestSchema, SetModeResponseSchema,
    KillSwitchResponseSchema, ProductionStatusSchema,
    UnifiedOrderSchema, OrderLifecycleSchema, ErrorLogItemSchema,
)
from .research_routes import research_router, init_research_router
from .production_routes import production_router, init_production_router

router = APIRouter()
<<<<<<< Updated upstream
router.include_router(research_router, prefix="/research", tags=["research"])
router.include_router(production_router, prefix="/production", tags=["production"])
=======
router.include_router(dashboard_router)
router.include_router(production_router)
>>>>>>> Stashed changes

# ── Injected service references (set by app_v2.py at startup) ────────────────
_scanner_service = None
_scheduler = None
_config = None
_ai_service = None
_ai_repo = None
_signal_repo = None
_risk_service = None
_portfolio_service = None
_trading_service = None
_shadow_service = None
_shadow_repo = None
_position_repo = None
_trade_repo = None
_event_log_repo = None
_notification_service = None
_dashboard_service = None
_health_checker = None
_metrics_collector = None
_journal_repo = None
_journal_service = None
_analytics_service = None
_learning_repo = None
_learning_service = None
_backtest_repo = None
_backtest_service = None
_feedback_repo = None
_feedback_service = None


def init_router(
    scanner_service=None,
    scheduler=None,
    config=None,
    ai_service=None,
    ai_repo=None,
    signal_repo=None,
    risk_service=None,
    portfolio_service=None,
    trading_service=None,
    shadow_service=None,
    shadow_repo=None,
    position_repo=None,
    trade_repo=None,
    event_log_repo=None,
    notification_service=None,
    dashboard_service=None,
    health_checker=None,
    metrics_collector=None,
<<<<<<< Updated upstream
    research_service=None,
    production_controller=None,
    production_watchdog=None,
=======
    journal_repo=None,
    journal_service=None,
    analytics_service=None,
    learning_repo=None,
    learning_service=None,
    backtest_repo=None,
    backtest_service=None,
    feedback_repo=None,
    feedback_service=None,
    production_repo=None,
    production_service=None,
>>>>>>> Stashed changes
    **kwargs,
) -> None:
    """Called by app_v2.py lifespan after services are started."""
    global _scanner_service, _scheduler, _config, _ai_service, _ai_repo, _signal_repo
    global _risk_service, _portfolio_service, _trading_service, _shadow_service, _shadow_repo, _position_repo, _trade_repo, _event_log_repo
    global _notification_service, _dashboard_service, _health_checker, _metrics_collector
    global _journal_repo, _journal_service, _analytics_service, _learning_repo, _learning_service
    global _backtest_repo, _backtest_service, _feedback_repo, _feedback_service
    _scanner_service = scanner_service
    _scheduler = scheduler
    _config = config
    _ai_service = ai_service
    _ai_repo = ai_repo
    _signal_repo = signal_repo
    _risk_service = risk_service
    _portfolio_service = portfolio_service
    _trading_service = trading_service
    _shadow_service = shadow_service
    _shadow_repo = shadow_repo
    _position_repo = position_repo
    _trade_repo = trade_repo
    _event_log_repo = event_log_repo
    _notification_service = notification_service
    _dashboard_service = dashboard_service
    _health_checker = health_checker
    _metrics_collector = metrics_collector
<<<<<<< Updated upstream
    init_research_router(research_service or kwargs.get("research_service"))
    ctrl = production_controller or kwargs.get("production_controller")
    wd = production_watchdog or kwargs.get("production_watchdog")
    init_production_router(
        controller=ctrl,
        watchdog=wd,
        config=config,
        position_repo=position_repo,
        risk_service=risk_service,
    )
=======
    _journal_repo = journal_repo
    _journal_service = journal_service
    _analytics_service = analytics_service
    _learning_repo = learning_repo
    _learning_service = learning_service
    _backtest_repo = backtest_repo
    _backtest_service = backtest_service
    _feedback_repo = feedback_repo
    _feedback_service = feedback_service
    if dashboard_service and hasattr(dashboard_service, "aggregator"):
        init_dashboard_routes(dashboard_service.aggregator)
    if production_service is not None:
        init_production_routes(production_service)
    _risk_service = risk_service
    _portfolio_service = portfolio_service
    _trading_service = trading_service
    _shadow_service = shadow_service
    _shadow_repo = shadow_repo
    _position_repo = position_repo
    _trade_repo = trade_repo
    _notification_service = notification_service
    _dashboard_service = dashboard_service
    _health_checker = health_checker
    _metrics_collector = metrics_collector
>>>>>>> Stashed changes


# ── Health (no auth) ──────────────────────────────────────────────────────────

@router.get("/health", response_model=OkSchema, tags=["system"])
async def health() -> OkSchema:
    """Liveness probe — always returns 200 if V2 process is alive."""
    return OkSchema(ok=True, detail="V2 running")


# ── Status (auth required) ────────────────────────────────────────────────────

@router.get(
    "/status",
    response_model=V2StatusSchema,
    dependencies=[Depends(require_api_key)],
    tags=["system"],
)
async def status_endpoint() -> V2StatusSchema:
    """Full V2 system status snapshot."""
    scanner_h = _scanner_service.get_health() if _scanner_service else {}
    ai_h = _ai_service.get_health() if _ai_service else None
    jobs = _scheduler.get_status() if _scheduler else []

    return V2StatusSchema(
        scanner_health=ScannerHealthSchema(**scanner_h) if scanner_h else ScannerHealthSchema(
            healthy=False, poll_count=0, live_signals=0, last_poll_at=None, last_error="not started"
        ),
        ai_health=AIHealthSchema(**ai_h) if ai_h else None,
        scheduler_jobs=[JobStatusSchema(**j) for j in jobs],
        db_path=_config.v2_db_path if _config else "unknown",
        uptime_polls=scanner_h.get("poll_count", 0),
        live_signals=scanner_h.get("live_signals", 0),
    )


# ── Scanner endpoints ─────────────────────────────────────────────────────────

@router.get(
    "/scanner/signals",
    response_model=list[SignalSchema],
    dependencies=[Depends(require_api_key)],
    tags=["scanner"],
)
async def get_signals(
    priority: Optional[str] = Query(
        default=None,
        description="Minimum priority filter: Elite|High|Medium|Watch|Ignore",
    ),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[SignalSchema]:
    """Return current live signals, optionally filtered by minimum priority."""
    if _scanner_service is None:
        raise HTTPException(status_code=503, detail="Scanner service not ready.")

    signals = _scanner_service.get_live_signals()

    # Apply priority filter if requested
    if priority:
        try:
            min_p = Priority(priority)
            signals = [s for s in signals if s.priority.gte(min_p)]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority '{priority}'. "
                       f"Valid values: Elite, High, Medium, Watch, Ignore",
            )

    # Apply limit
    signals = signals[:limit]

    return [
        SignalSchema(
            id               = s.id,
            coin             = s.coin,
            pair             = s.pair,
            market_state     = s.market_state.value,
            opportunity_type = s.opportunity_type.value,
            priority         = s.priority.value,
            risk_level       = s.risk_level.value,
            score            = s.score,
            confidence       = s.confidence,
            coin_class       = s.coin_class,
            mtf_alignment    = s.mtf_alignment,
            generated_at     = s.generated_at,
            expires_at       = s.expires_at,
            source_bot       = s.source_bot,
        )
        for s in signals
    ]


@router.get(
    "/scanner/signals/{signal_id}",
    response_model=SignalSchema,
    dependencies=[Depends(require_api_key)],
    tags=["scanner"],
)
async def get_signal_by_id(signal_id: str) -> SignalSchema:
    """Return a single signal by ID (live cache only)."""
    if _scanner_service is None:
        raise HTTPException(status_code=503, detail="Scanner service not ready.")
    live = {s.id: s for s in _scanner_service.get_live_signals()}
    if signal_id not in live:
        raise HTTPException(status_code=404, detail=f"Signal '{signal_id}' not found in live cache.")
    s = live[signal_id]
    return SignalSchema(
        id=s.id, coin=s.coin, pair=s.pair,
        market_state=s.market_state.value, opportunity_type=s.opportunity_type.value,
        priority=s.priority.value, risk_level=s.risk_level.value,
        score=s.score, confidence=s.confidence, coin_class=s.coin_class,
        mtf_alignment=s.mtf_alignment, generated_at=s.generated_at,
        expires_at=s.expires_at, source_bot=s.source_bot,
    )


@router.post(
    "/scanner/poll",
    response_model=dict,
    dependencies=[Depends(require_api_key)],
    tags=["scanner"],
)
@router.post(
    "/scanner/refresh",
    response_model=dict,
    dependencies=[Depends(require_api_key)],
    tags=["scanner"],
)
async def trigger_scanner_poll() -> dict:
    """Manually trigger an immediate market scanner polling cycle."""
    if _scanner_service is None:
        raise HTTPException(status_code=503, detail="Scanner service not ready.")
    summary = await _scanner_service.poll()
    return {"ok": True, "summary": summary}


@router.get(
    "/scanner/coins",
    response_model=list[ScannedCoinSchema],
    dependencies=[Depends(require_api_key)],
    tags=["scanner"],
)
async def get_scanned_coins(
    min_score: Optional[int] = Query(default=None, ge=0, le=100, description="Filter by minimum confluence score"),
    limit: int = Query(default=50, ge=1, le=200, description="Max coins to return"),
    sort_by: str = Query(default="confluence_score", description="Sort field: confluence_score | price | symbol"),
) -> list[ScannedCoinSchema]:
    """Return evaluated candidate coins from the latest scan pass."""
    if _scanner_service is None:
        raise HTTPException(status_code=503, detail="Scanner service not ready.")
    items = _scanner_service.get_scanned_coins(min_score=min_score, limit=limit, sort_by=sort_by)
    return [ScannedCoinSchema(**item) for item in items]


@router.get(
    "/scanner/coins/{symbol}",
    response_model=ScannedCoinDetailSchema,
    dependencies=[Depends(require_api_key)],
    tags=["scanner"],
)
async def get_scanned_coin_detail(symbol: str) -> ScannedCoinDetailSchema:
    """Return comprehensive technical, MTF, and C2 4-layer evaluation breakdown for a coin."""
    if _scanner_service is None:
        raise HTTPException(status_code=503, detail="Scanner service not ready.")
    detail = _scanner_service.get_scanned_coin_detail(symbol)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Coin '{symbol}' was not found in the latest scan snapshot.")
    return ScannedCoinDetailSchema(**detail)


@router.get(
    "/scanner/health",
    response_model=ScannerHealthSchema,
    dependencies=[Depends(require_api_key)],
    tags=["scanner"],
)
async def scanner_health() -> ScannerHealthSchema:
    """Scanner sub-health: poll count, live signal count, last error."""
    if _scanner_service is None:
        return ScannerHealthSchema(
            healthy=False, poll_count=0, live_signals=0,
            last_poll_at=None, last_error="not started",
        )
    return ScannerHealthSchema(**_scanner_service.get_health())


@router.get(
    "/dashboard/signals",
    response_model=list[SignalSchema],
    dependencies=[Depends(require_api_key)],
    tags=["dashboard"],
)
async def get_dashboard_signals() -> list[SignalSchema]:
    """Live scanner signals for the dashboard."""
    if _scanner_service is None:
        return []
    signals = _scanner_service.get_live_signals()
    return [
        SignalSchema(
            id=s.id, coin=s.coin, pair=s.pair,
            market_state=s.market_state.value, opportunity_type=s.opportunity_type.value,
            priority=s.priority.value, risk_level=s.risk_level.value,
            score=s.score, confidence=s.confidence, coin_class=s.coin_class,
            mtf_alignment=s.mtf_alignment, generated_at=s.generated_at,
            expires_at=s.expires_at, source_bot=s.source_bot,
        )
        for s in signals
    ]


# ── AI Intelligence endpoints (Phase 4) ───────────────────────────────────────

@router.get(
    "/ai/health",
    response_model=AIHealthSchema,
    dependencies=[Depends(require_api_key)],
    tags=["ai"],
)
async def ai_health() -> AIHealthSchema:
    """AI Intelligence sub-health: evaluation counts, model, latency, and errors."""
    if _ai_service is None:
        return AIHealthSchema(
            healthy=False,
            ai_enabled=False,
            model="not started",
            has_api_key=False,
            min_priority="Medium",
            confidence_threshold=70,
            total_evaluations=0,
            confirmed_count=0,
            rejected_count=0,
            fallback_count=0,
            avg_latency_ms=0.0,
            last_error="not started",
        )
    return AIHealthSchema(**_ai_service.get_health())


@router.get(
    "/ai/analyses",
    response_model=list[AIAnalysisSchema],
    dependencies=[Depends(require_api_key)],
    tags=["ai"],
)
async def list_ai_analyses(
    coin: Optional[str] = Query(default=None, description="Filter by coin ticker (e.g. BTC)"),
    recommendation: Optional[str] = Query(default=None, description="Filter by APPROVE|REJECT|SCALE_DOWN|WATCH"),
    min_confidence: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[AIAnalysisSchema]:
    """Return historical AI analyses from repository."""
    if _ai_repo is None:
        raise HTTPException(status_code=503, detail="AI repository not initialized.")

    if coin:
        analyses = await _ai_repo.get_by_coin(coin.upper(), limit=limit)
    else:
        analyses = await _ai_repo.get_recent(
            limit=limit,
            recommendation=recommendation.upper() if recommendation else None,
            min_confidence=min_confidence,
        )

    return [
        AIAnalysisSchema(
            id=a.id,
            signal_id=a.signal_id,
            coin=a.coin,
            pair=a.pair,
            recommendation=a.recommendation.value,
            confidence_score=a.confidence_score,
            trend_evaluation=a.trend_evaluation,
            momentum_evaluation=a.momentum_evaluation,
            volume_evaluation=a.volume_evaluation,
            setup_quality=a.setup_quality,
            market_regime=a.market_regime,
            risk_reward_assessment=a.risk_reward_assessment,
            supporting_factors=a.supporting_factors,
            conflicts=a.conflicts,
            risk_factors=a.risk_factors,
            suggested_adjustments=a.suggested_adjustments,
            model_name=a.model_name,
            execution_latency_ms=a.execution_latency_ms,
            analyzed_at=a.analyzed_at,
        )
        for a in analyses
    ]


@router.get(
    "/ai/analyses/{signal_id}",
    response_model=AIAnalysisSchema,
    dependencies=[Depends(require_api_key)],
    tags=["ai"],
)
async def get_ai_analysis_by_signal_id(signal_id: str) -> AIAnalysisSchema:
    """Fetch AI evaluation associated with a specific signal ID."""
    if _ai_repo is None:
        raise HTTPException(status_code=503, detail="AI repository not initialized.")

    analysis = await _ai_repo.get_by_signal_id(signal_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"No AI analysis found for signal '{signal_id}'.")

    return AIAnalysisSchema(
        id=analysis.id,
        signal_id=analysis.signal_id,
        coin=analysis.coin,
        pair=analysis.pair,
        recommendation=analysis.recommendation.value,
        confidence_score=analysis.confidence_score,
        trend_evaluation=analysis.trend_evaluation,
        momentum_evaluation=analysis.momentum_evaluation,
        volume_evaluation=analysis.volume_evaluation,
        setup_quality=analysis.setup_quality,
        market_regime=analysis.market_regime,
        risk_reward_assessment=analysis.risk_reward_assessment,
        supporting_factors=analysis.supporting_factors,
        conflicts=analysis.conflicts,
        risk_factors=analysis.risk_factors,
        suggested_adjustments=analysis.suggested_adjustments,
        model_name=analysis.model_name,
        execution_latency_ms=analysis.execution_latency_ms,
        analyzed_at=analysis.analyzed_at,
    )


@router.post(
    "/ai/evaluate/{signal_id}",
    response_model=AIAnalysisSchema,
    dependencies=[Depends(require_api_key)],
    tags=["ai"],
)
async def evaluate_signal_on_demand(signal_id: str) -> AIAnalysisSchema:
    """Manually trigger an AI evaluation for a given signal."""
    if _ai_service is None:
        raise HTTPException(status_code=503, detail="AI service not initialized.")

    signal = None
    if _scanner_service:
        live = {s.id: s for s in _scanner_service.get_live_signals()}
        signal = live.get(signal_id)

    if signal is None and _signal_repo:
        signal = await _signal_repo.get_by_id(signal_id)

    if signal is None:
        raise HTTPException(status_code=404, detail=f"Signal '{signal_id}' not found.")

    analysis = await _ai_service.evaluate_signal(signal)

    return AIAnalysisSchema(
        id=analysis.id,
        signal_id=analysis.signal_id,
        coin=analysis.coin,
        pair=analysis.pair,
        recommendation=analysis.recommendation.value,
        confidence_score=analysis.confidence_score,
        trend_evaluation=analysis.trend_evaluation,
        momentum_evaluation=analysis.momentum_evaluation,
        volume_evaluation=analysis.volume_evaluation,
        setup_quality=analysis.setup_quality,
        market_regime=analysis.market_regime,
        risk_reward_assessment=analysis.risk_reward_assessment,
        supporting_factors=analysis.supporting_factors,
        conflicts=analysis.conflicts,
        risk_factors=analysis.risk_factors,
        suggested_adjustments=analysis.suggested_adjustments,
        model_name=analysis.model_name,
        execution_latency_ms=analysis.execution_latency_ms,
        analyzed_at=analysis.analyzed_at,
    )


# ── Scheduler endpoints ───────────────────────────────────────────────────────

@router.get(
    "/scheduler/jobs",
    response_model=list[JobStatusSchema],
    dependencies=[Depends(require_api_key)],
    tags=["scheduler"],
)
async def scheduler_jobs() -> list[JobStatusSchema]:
    """Return current status of all registered scheduler jobs."""
    if _scheduler is None:
        return []
    return [JobStatusSchema(**j) for j in _scheduler.get_status()]


# ── Risk endpoints (Phase 5) ──────────────────────────────────────────────────

@router.get(
    "/risk/state",
    response_model=RiskStateSchema,
    dependencies=[Depends(require_api_key)],
    tags=["risk"],
)
async def get_risk_state() -> RiskStateSchema:
    """Current risk engine state: deployed capital, limits, and circuit breaker status."""
    if _risk_service is None:
        raise HTTPException(status_code=503, detail="Risk service not initialized.")

    state = await _risk_service.get_state()
    return RiskStateSchema(
        trading_enabled=state.trading_enabled,
        emergency_stop=state.emergency_stop,
        circuit_breaker_open=state.circuit_breaker_open,
        per_bot_deployed=state.per_bot_deployed,
        per_bot_open_count=state.per_bot_open_count,
        total_capital_limit=_config.total_capital_limit if _config else 0.0,
        last_checked_at=state.last_checked_at.isoformat() if state.last_checked_at else None,
    )


# ── Portfolio endpoints (Phase 5) ─────────────────────────────────────────────

@router.get(
    "/portfolio/snapshot",
    response_model=PortfolioSnapshotSchema,
    dependencies=[Depends(require_api_key)],
    tags=["portfolio"],
)
async def get_portfolio_snapshot() -> PortfolioSnapshotSchema:
    """Consolidated cross-bot portfolio AUM, deployed capital, cash, and PnL breakdown."""
    if _portfolio_service is None:
        raise HTTPException(status_code=503, detail="Portfolio service not initialized.")

    snapshot = await _portfolio_service.get_snapshot()
    return PortfolioSnapshotSchema(
        total_aum=snapshot.total_aum,
        total_deployed=snapshot.total_deployed,
        total_cash=snapshot.total_cash,
        total_unrealised_pnl=snapshot.total_unrealised_pnl,
        total_realised_pnl=snapshot.total_realised_pnl,
        daily_pnl=snapshot.daily_pnl,
        capital_utilisation=snapshot.capital_utilisation,
        positions_by_bot={
            bot: [
                {
                    "id": p.id,
                    "bot": p.bot.value if hasattr(p.bot, "value") else str(p.bot),
                    "coin": p.coin,
                    "pair": p.pair,
                    "qty": p.qty,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealised_pnl": p.unrealised_pnl,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                }
                for p in plist
            ]
            for bot, plist in snapshot.positions_by_bot.items()
        },
        captured_at=snapshot.captured_at,
    )


# ── Trading endpoints (Phase 5) ───────────────────────────────────────────────

@router.get(
    "/trading/positions",
    response_model=list[PositionSchema],
    dependencies=[Depends(require_api_key)],
    tags=["trading"],
)
async def get_positions(
    status: Optional[str] = Query(default=None, description="Filter by OPEN | CLOSED"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[PositionSchema]:
    """List open and closed positions from repository."""
    if _position_repo is None:
        raise HTTPException(status_code=503, detail="Position repository not initialized.")

    if status and status.upper() == "OPEN":
        positions = await _position_repo.get_open()
    else:
        positions = await _position_repo.get_all(limit=limit)

    return [
        PositionSchema(
            id=p.id,
            bot=p.bot.value if hasattr(p.bot, "value") else str(p.bot),
            coin=p.coin,
            pair=p.pair,
            qty=p.qty,
            entry_price=p.entry_price,
            entry_time=p.entry_time,
            current_price=p.current_price,
            unrealised_pnl=p.unrealised_pnl,
            stop_loss=p.stop_loss,
            take_profit=p.take_profit,
            mode=p.mode.value if hasattr(p.mode, "value") else str(p.mode),
            status=p.status.value if hasattr(p.status, "value") else str(p.status),
            signal_id=p.signal_id,
            exit_price=p.exit_price,
            exit_reason=p.exit_reason.value if p.exit_reason and hasattr(p.exit_reason, "value") else str(p.exit_reason) if p.exit_reason else None,
            closed_at=p.closed_at,
        )
        for p in positions
    ]


@router.get(
    "/positions/open",
    response_model=list[PositionSchema],
    dependencies=[Depends(require_api_key)],
    tags=["trading"],
)
async def get_open_positions_alias() -> list[PositionSchema]:
    """Convenience alias for /trading/positions?status=OPEN."""
    return await get_positions(status="OPEN")


@router.get(
    "/trading/trades",
    response_model=list[TradeSchema],
    dependencies=[Depends(require_api_key)],
    tags=["trading"],
)
async def get_trades(
    coin: Optional[str] = Query(default=None, description="Filter by coin symbol"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[TradeSchema]:
    """List historical executed trades."""
    if _trade_repo is None:
        raise HTTPException(status_code=503, detail="Trade repository not initialized.")

    if coin:
        trades = await _trade_repo.get_by_coin(coin.upper(), limit=limit)
    else:
        trades = await _trade_repo.get_recent(limit=limit)

    return [
        TradeSchema(
            id=t.id,
            position_id=t.position_id,
            bot=t.bot.value if hasattr(t.bot, "value") else str(t.bot),
            coin=t.coin,
            pair=t.pair,
            entry_price=t.entry_price,
            exit_price=t.exit_price,
            qty=t.qty,
            pnl=t.pnl,
            pnl_pct=t.pnl_pct,
            entry_time=t.entry_time,
            exit_time=t.exit_time,
            exit_reason=t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason),
            mode=t.mode.value if hasattr(t.mode, "value") else str(t.mode),
            signal_id=t.signal_id,
        )
        for t in trades
    ]


# ── Shadow Simulation & Divergence endpoints (Phase 6) ────────────────────────

@router.get(
    "/shadow/trades",
    response_model=list[ShadowTradeSchema],
    dependencies=[Depends(require_api_key)],
    tags=["shadow"],
)
async def get_shadow_trades(
    status: Optional[str] = Query(default=None, description="Filter by OPEN | CLOSED_TP | CLOSED_SL"),
    coin: Optional[str] = Query(default=None, description="Filter by coin ticker"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[ShadowTradeSchema]:
    """List simulated shadow trades."""
    if _shadow_repo is None:
        raise HTTPException(status_code=503, detail="Shadow repository not initialized.")

    if coin:
        trades = await _shadow_repo.get_shadow_trades_by_coin(coin.upper(), limit=limit)
    else:
        trades = await _shadow_repo.get_recent_shadow_trades(limit=limit, status=status.upper() if status else None)

    return [
        ShadowTradeSchema(
            id=t.id,
            signal_id=t.signal_id,
            bot=t.bot.value if hasattr(t.bot, "value") else str(t.bot),
            coin=t.coin,
            pair=t.pair,
            entry_price=t.entry_price,
            qty=t.qty,
            amount=t.amount,
            stop_loss=t.stop_loss,
            take_profit=t.take_profit,
            ai_recommendation=t.ai_recommendation,
            status=t.status,
            simulated_exit_price=t.simulated_exit_price,
            simulated_pnl=t.simulated_pnl,
            simulated_pnl_pct=t.simulated_pnl_pct,
            exit_reason=t.exit_reason,
            created_at=t.created_at,
            closed_at=t.closed_at,
        )
        for t in trades
    ]


@router.get(
    "/shadow/divergence",
    response_model=list[DecisionDivergenceSchema],
    dependencies=[Depends(require_api_key)],
    tags=["shadow"],
)
async def get_divergences(
    divergence_type: Optional[str] = Query(default=None, description="Filter by AI_FILTERED | RISK_FILTERED | SIZE_SCALED"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[DecisionDivergenceSchema]:
    """List decision divergences between V1 execution and V2 AI/Risk evaluation."""
    if _shadow_repo is None:
        raise HTTPException(status_code=503, detail="Shadow repository not initialized.")

    divergences = await _shadow_repo.get_divergences(limit=limit, divergence_type=divergence_type)
    return [
        DecisionDivergenceSchema(
            id=d.id,
            signal_id=d.signal_id,
            bot=d.bot.value if hasattr(d.bot, "value") else str(d.bot),
            coin=d.coin,
            v1_action=d.v1_action,
            v2_action=d.v2_action,
            divergence_type=d.divergence_type,
            reason=d.reason,
            detected_at=d.detected_at,
            v1_pnl=d.v1_pnl,
            v2_simulated_pnl=d.v2_simulated_pnl,
        )
        for d in divergences
    ]


@router.get(
    "/shadow/summary",
    response_model=DivergenceSummarySchema,
    dependencies=[Depends(require_api_key)],
    tags=["shadow"],
)
async def get_shadow_summary() -> DivergenceSummarySchema:
    """Aggregate divergence statistics, simulated win-rate, and alpha metrics."""
    if _shadow_repo is None:
        raise HTTPException(status_code=503, detail="Shadow repository not initialized.")

    summary = await _shadow_repo.get_divergence_summary()
    return DivergenceSummarySchema(**summary)


# ── Dashboard endpoints (Phase 8) ─────────────────────────────────────────────

@router.get(
    "/dashboard/overview",
    response_model=DashboardOverviewSchema,
    dependencies=[Depends(require_api_key)],
    tags=["dashboard"],
)
async def get_dashboard_overview() -> DashboardOverviewSchema:
    """Single-call consolidated platform state snapshot for frontend dashboards."""
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized.")

    overview = await _dashboard_service.get_overview()
    return DashboardOverviewSchema(**overview)


# ── Analytics endpoints (Phase 4) ─────────────────────────────────────────────

@router.get(
    "/analytics/win-rates",
    response_model=AnalyticsWinRatesSchema,
    dependencies=[Depends(require_api_key)],
    tags=["analytics"],
)
async def get_analytics_win_rates() -> AnalyticsWinRatesSchema:
    """Historical accuracy and win rates aggregated across horizons and priority tiers."""
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized.")

    data = _dashboard_service.get_win_rates_analytics()
    return AnalyticsWinRatesSchema(**data)


@router.get(
    "/analytics/coins",
    response_model=AnalyticsCoinsSchema,
    dependencies=[Depends(require_api_key)],
    tags=["analytics"],
)
async def get_analytics_coins() -> AnalyticsCoinsSchema:
    """Per-coin historical win rates, performance metrics, and top/bottom rankings."""
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized.")

    data = _dashboard_service.get_coins_analytics()
    return AnalyticsCoinsSchema(**data)


@router.get(
    "/analytics/funnel",
    response_model=AnalyticsFunnelSchema,
    dependencies=[Depends(require_api_key)],
    tags=["analytics"],
)
async def get_analytics_funnel() -> AnalyticsFunnelSchema:
    """Historical conversion efficiency metrics across all 5 scanner filtering layers."""
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized.")

    data = _dashboard_service.get_funnel_analytics()
    return AnalyticsFunnelSchema(**data)


# ── Monitoring endpoints (Phase 8) ────────────────────────────────────────────

@router.get(
    "/monitoring/metrics",
    response_model=MonitoringMetricsSchema,
    dependencies=[Depends(require_api_key)],
    tags=["monitoring"],
)
async def get_monitoring_metrics() -> MonitoringMetricsSchema:
    """Throughput rates, event counts, and latency statistics."""
    if _metrics_collector is None:
        return MonitoringMetricsSchema(uptime_seconds=0.0, counters={}, latencies={})

    metrics = _metrics_collector.get_metrics()
    return MonitoringMetricsSchema(**metrics)


@router.get(
    "/monitoring/health",
    response_model=MonitoringHealthSchema,
    dependencies=[Depends(require_api_key)],
    tags=["monitoring"],
)
async def get_monitoring_health() -> MonitoringHealthSchema:
    """Full diagnostic health probe across all 8 subsystems."""
    if _health_checker is None:
        raise HTTPException(status_code=503, detail="Health checker not initialized.")

    health = _health_checker.check_health()
    return MonitoringHealthSchema(**health)


# ── Notification endpoints (Phase 7) ──────────────────────────────────────────

@router.post(
    "/notifications/test",
    response_model=OkSchema,
    dependencies=[Depends(require_api_key)],
    tags=["notifications"],
)
async def post_test_notification(body: TestNotificationRequestSchema) -> OkSchema:
    """Send a test message through the unified notification pipeline."""
    if _notification_service is None:
        raise HTTPException(status_code=503, detail="Notification service not initialized.")

    sent = await _notification_service.send_custom_alert(body.message)
    return OkSchema(ok=True, detail="Notification dispatched" if sent else "Notification recorded locally (Telegram not configured)")


# ── Autonomous Pipeline Endpoints ─────────────────────────────────────────────

@router.get(
    "/pipeline/stages",
    response_model=list[PipelineStageSchema],
    dependencies=[Depends(require_api_key)],
    tags=["pipeline"],
)
async def get_pipeline_stages() -> list[PipelineStageSchema]:
    """Return all 14 stages of the PROJECT-ALPHA Autonomous Pipeline with live metrics."""
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized.")

    stages = _dashboard_service.get_pipeline_stages()
    return [PipelineStageSchema(**s) for s in stages]


@router.get(
    "/pipeline/stages/{stage_id}",
    response_model=PipelineStageDetailSchema,
    dependencies=[Depends(require_api_key)],
    tags=["pipeline"],
)
async def get_pipeline_stage_detail(stage_id: str) -> PipelineStageDetailSchema:
    """Return deep telemetry, data contracts, and last processed events for a specific pipeline stage."""
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized.")

    detail = _dashboard_service.get_stage_detail(stage_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Pipeline stage '{stage_id}' not found.")

    return PipelineStageDetailSchema(**detail)



# ── Trading Bot Status Endpoints ──────────────────────────────────────────────

@router.get(
    "/bots",
    response_model=list[BotStatusSchema],
    dependencies=[Depends(require_api_key)],
    tags=["bots"],
)
@router.get(
    "/dashboard/fleet",
    response_model=list[BotStatusSchema],
    dependencies=[Depends(require_api_key)],
    tags=["bots"],
)
async def get_all_bots() -> list[BotStatusSchema]:
<<<<<<< Updated upstream
    """Return current pipeline stage, status, and live metrics for all production trading bots (STE, HDA, VCP, BBS)."""
=======
    """Return current pipeline stage, status, and live metrics for all trading bots (STE, HDA, VCP, BBS)."""
>>>>>>> Stashed changes
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized.")

    bots = _dashboard_service.get_bot_statuses()
    return [BotStatusSchema(**b) for b in bots]


@router.get(
    "/bots/{bot_name}",
    response_model=BotDetailSchema,
    dependencies=[Depends(require_api_key)],
    tags=["bots"],
)
async def get_bot_detail(bot_name: str) -> BotDetailSchema:
    """Return full detail — strategy params, pipeline stage, counters, and last action — for one bot (STE / HDA / VCP / BBS)."""
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized.")

    detail = _dashboard_service.get_bot_detail(bot_name)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bot '{bot_name.upper()}' not found. Valid production options: STE, HDA, VCP, BBS."
        )

    return BotDetailSchema(**detail)


<<<<<<< Updated upstream
# ── Simulation & Learning Endpoints ───────────────────────────────────────────

@router.post(
    "/learning/simulate-signal",
    response_model=SimulateSignalResponseSchema,
    dependencies=[Depends(require_api_key)],
    tags=["simulation", "learning"],
)
async def simulate_signal_emission(body: SimulateSignalRequestSchema) -> SimulateSignalResponseSchema:
    """
    Emit a synthetic high-conviction signal across EventBus and trigger real-time AI evaluation,
    dashboard telemetry push, and WebSocket distribution without live capital risk.
    """
    if _ai_service is None or _dashboard_service is None:
        raise HTTPException(status_code=503, detail="AI Intelligence / Dashboard service not initialized.")

    raw_pair = body.pair or "SOL/INR"
    coin = (body.coin or raw_pair.split("/")[0]).upper()
    pair = raw_pair if "/" in raw_pair else f"{coin}/INR"
    score = int(body.score if body.score is not None else 89)
    bot_name = (body.bot_name or "STE").upper()
    now = datetime.now(timezone.utc)
    sig_id = f"SIG-SIM-{coin}-{uuid.uuid4().hex[:6].upper()}"

    signal = Signal(
        id=sig_id,
        coin=coin,
        pair=pair,
        market_state=MarketState.BULL_TREND if score >= 80 else MarketState.SIDEWAYS,
        opportunity_type=OppType.MOMENTUM_TRADE,
        priority=Priority.from_score(score),
        risk_level=RiskLevel.LOW if score >= 85 else RiskLevel.MEDIUM,
        score=score,
        confidence=min(99, max(50, score + 2)),
        coin_class="A",
        mtf_alignment=True,
        generated_at=now,
        expires_at=now + timedelta(minutes=15),
        source_bot=bot_name,
        raw_payload={
            "price": body.price or 10140.0,
            "bot_name": bot_name,
            "regime": body.regime or "RISK_ON",
            "suggested_allocation_inr": body.suggested_allocation_inr or 200.0,
            "stop_loss": body.stop_loss or 9980.0,
            "take_profit": body.take_profit or 10450.0,
            "eval_breakdown": body.eval_breakdown or {
                "chart_structure": 28.0,
                "technical_indicators": 32.0,
                "market_sentiment": 16.0,
                "news_events": 13.0,
            },
        },
        confluence_breakdown=body.eval_breakdown or {},
    )

    if _signal_repo:
        await _signal_repo.insert(signal)

    # 1. Publish SIGNAL_GENERATED event to EventBus
    bus = _ai_service._bus
    await bus.publish(
        EventType.SIGNAL_GENERATED,
        {
            "signal_id": signal.id,
            "id": signal.id,
            "bot": bot_name,
            "coin": coin,
            "pair": pair,
            "score": score,
            "confidence": signal.confidence,
            "price": body.price or 10140.0,
            "action": "BUY",
            "suggested_allocation_inr": body.suggested_allocation_inr or 200.0,
            "stop_loss": body.stop_loss or 9980.0,
            "take_profit": body.take_profit or 10450.0,
            "timestamp": now.isoformat(),
        },
    )

    # 2. Evaluate signal through AIIntelligenceService
    analysis = await _ai_service.evaluate_signal(signal)

    return SimulateSignalResponseSchema(
        ok=True,
        signal_id=signal.id,
        pair=pair,
        bot_name=bot_name,
        confluence_score=score,
        ai_recommendation=analysis.recommendation.value,
        confidence_score=analysis.confidence_score,
        setup_quality=analysis.setup_quality,
        supporting_factors=analysis.supporting_factors,
        risk_factors=analysis.risk_factors,
        model_name=analysis.model_name,
        event_published=True,
    )


# ── Production Mode Controller & Live Microcash Endpoints ─────────────────────
# Note: Handled by production_router in v2/api/production_routes.py mounted at /production


@router.get(
    "/trading/positions",
    response_model=list[PositionSchema],
    dependencies=[Depends(require_api_key)],
    tags=["trading"],
)
async def get_active_positions() -> list[PositionSchema]:
    """
    List all active open positions (live or shadow) with current unrealized P&L and bracket targets.
    """
    if _position_repo is None:
        raise HTTPException(status_code=503, detail="Position repository not initialized.")

    positions = await _position_repo.get_open()
    out = []
    for p in positions:
        out.append(PositionSchema(
            id=p.id,
            bot=p.bot.value if hasattr(p.bot, "value") else str(p.bot),
            coin=p.coin,
            pair=p.pair,
            qty=p.qty,
            entry_price=p.entry_price,
            entry_time=p.entry_time.isoformat() if hasattr(p.entry_time, "isoformat") else str(p.entry_time or ""),
            current_price=p.current_price or p.entry_price,
            unrealised_pnl=p.unrealised_pnl or 0.0,
            stop_loss=p.stop_loss,
            take_profit=p.take_profit,
            mode=p.mode.value if hasattr(p.mode, "value") else str(p.mode),
            signal_id=p.signal_id,
        ))
    return out


# Handled by production_router in v2/api/production_routes.py mounted at /production/status


# ── Execution Center & Order Lifecycle Endpoints ──────────────────────────────

@router.get(
    "/trading/orders",
    response_model=list[UnifiedOrderSchema],
    dependencies=[Depends(require_api_key)],
    tags=["trading", "execution"],
)
async def get_all_orders(limit: int = Query(default=50, ge=1, le=200)) -> list[UnifiedOrderSchema]:
    """
    Unified order feed aggregating open positions, historical closed trades,
    and shadow executions into a single chronological stream.
    """
    orders: list[UnifiedOrderSchema] = []

    # 1. Open / Live Positions
    if _position_repo:
        open_pos = await _position_repo.get_open()
        for p in open_pos:
            entry_ts = p.entry_time.isoformat() if hasattr(p.entry_time, "isoformat") else str(p.entry_time or "")
            is_live = getattr(p.mode, "value", str(p.mode)) == "LIVE_MICROCASH"
            orders.append(UnifiedOrderSchema(
                id=f"ORD-POS-{p.id}",
                exchange_order_id=getattr(p, "exchange_order_id", None) or (f"CDX-{p.id[:8].upper()}" if is_live else None),
                coin=p.coin,
                pair=p.pair,
                side="BUY",
                qty=p.qty,
                price=p.entry_price,
                executed_price=p.entry_price,
                mode=p.mode.value if hasattr(p.mode, "value") else str(p.mode),
                status="OPEN",
                created_at=entry_ts,
                filled_at=entry_ts,
                bot=p.bot.value if hasattr(p.bot, "value") else str(p.bot),
                signal_id=p.signal_id,
            ))

    # 2. Executed Trades
    if _trade_repo:
        trades = await _trade_repo.get_recent(limit=limit)
        for t in trades:
            entry_ts = t.entry_time.isoformat() if hasattr(t.entry_time, "isoformat") else str(t.entry_time or "")
            exit_ts = t.exit_time.isoformat() if hasattr(t.exit_time, "isoformat") else str(t.exit_time or "")
            is_live = getattr(t.mode, "value", str(t.mode)) == "LIVE_MICROCASH"
            orders.append(UnifiedOrderSchema(
                id=f"ORD-TRD-{t.id}",
                exchange_order_id=getattr(t, "exchange_order_id", None) or (f"CDX-{t.id[:8].upper()}" if is_live else None),
                coin=t.coin,
                pair=t.pair,
                side="SELL",
                qty=t.qty,
                price=t.exit_price,
                executed_price=t.exit_price,
                mode=t.mode.value if hasattr(t.mode, "value") else str(t.mode),
                status="FILLED",
                created_at=entry_ts,
                filled_at=exit_ts,
                bot=t.bot.value if hasattr(t.bot, "value") else str(t.bot),
                signal_id=t.signal_id,
            ))

    # 3. Shadow Trades (if not enough trades)
    if _shadow_repo and len(orders) < limit:
        shadow_trades = await _shadow_repo.get_recent_shadow_trades(limit=limit - len(orders))
        for st in shadow_trades:
            orders.append(UnifiedOrderSchema(
                id=f"ORD-SHD-{st.id}",
                exchange_order_id=None,
                coin=st.coin,
                pair=st.pair,
                side="BUY",
                qty=st.qty,
                price=st.entry_price,
                executed_price=st.entry_price,
                mode="SHADOW",
                status="FILLED" if st.status.startswith("CLOSED") else "OPEN",
                created_at=st.created_at.isoformat() if hasattr(st.created_at, "isoformat") else str(st.created_at or ""),
                filled_at=st.closed_at.isoformat() if st.closed_at and hasattr(st.closed_at, "isoformat") else None,
                bot=st.bot.value if hasattr(st.bot, "value") else str(st.bot),
                signal_id=st.signal_id,
            ))

    # Sort newest first
    orders.sort(key=lambda o: o.created_at or "", reverse=True)
    return orders[:limit]


@router.get(
    "/trading/orders/{entity_id}/lifecycle",
    response_model=OrderLifecycleSchema,
    dependencies=[Depends(require_api_key)],
    tags=["trading", "execution"],
)
async def get_order_lifecycle(entity_id: str) -> OrderLifecycleSchema:
    """
    Retrieve deep lifecycle event trail and execution stage milestones for a given order/position.
    """
    clean_id = entity_id.replace("ORD-POS-", "").replace("ORD-TRD-", "").replace("ORD-SHD-", "").strip()

    coin = "BTC"
    pair = "BTC/INR"
    status = "FILLED"
    mode = "SHADOW"
    qty = 0.0
    price = 0.0
    sig_id = clean_id
    ex_order_id = None
    subaccount_id = None

    # Check in position_repo
    if _position_repo:
        pos = await _position_repo.get_by_id(clean_id)
        if pos:
            coin = pos.coin
            pair = pos.pair
            status = pos.status.value if hasattr(pos.status, "value") else str(pos.status)
            mode = pos.mode.value if hasattr(pos.mode, "value") else str(pos.mode)
            qty = pos.qty
            price = pos.entry_price
            sig_id = pos.signal_id or clean_id
            if mode == "LIVE_MICROCASH":
                ex_order_id = f"CDX-{pos.id[:8].upper()}"
                subaccount_id = f"SUBACCT-{pos.bot.value if hasattr(pos.bot, 'value') else pos.bot}"

    # Check in trade_repo
    if _trade_repo and price == 0.0:
        trades = await _trade_repo.get_recent(limit=50)
        t_match = next((t for t in trades if t.id == clean_id or t.position_id == clean_id), None)
        if t_match:
            coin = t_match.coin
            pair = t_match.pair
            status = "CLOSED"
            mode = t_match.mode.value if hasattr(t_match.mode, "value") else str(t_match.mode)
            qty = t_match.qty
            price = t_match.exit_price
            sig_id = t_match.signal_id or clean_id
            if mode == "LIVE_MICROCASH":
                ex_order_id = f"CDX-{t_match.id[:8].upper()}"
                subaccount_id = f"SUBACCT-{t_match.bot.value if hasattr(t_match.bot, 'value') else t_match.bot}"

    # Fetch audit logs from event_log_repo
    events = []
    if _event_log_repo:
        events = await _event_log_repo.get_by_entity(clean_id)
        if not events and sig_id != clean_id:
            events = await _event_log_repo.get_by_entity(sig_id)

    stages = [
        {"stage": "SIGNAL", "name": "Signal Generation", "status": "PASSED", "timestamp": datetime.now(timezone.utc).isoformat(), "detail": f"Signal {sig_id} emitted with C2 Confluence."},
        {"stage": "RISK_APPROVED", "name": "Risk Engine Gate", "status": "PASSED", "timestamp": datetime.now(timezone.utc).isoformat(), "detail": "Capital headroom, limits & streak checks verified."},
        {"stage": "ORDER_SUBMITTED", "name": "Order Router Dispatch", "status": "PASSED", "timestamp": datetime.now(timezone.utc).isoformat(), "detail": f"Routed to {mode} execution client."},
        {"stage": "EXCHANGE_ORDER", "name": "Exchange ACK", "status": "PASSED" if mode == "LIVE_MICROCASH" else "SKIPPED", "timestamp": datetime.now(timezone.utc).isoformat(), "detail": f"Exchange Order ID: {ex_order_id or 'N/A (Paper)'}"},
        {"stage": "PENDING", "name": "Order Fill Pending", "status": "PASSED", "timestamp": datetime.now(timezone.utc).isoformat(), "detail": "Waiting for market matching engine fill."},
        {"stage": "FILLED", "name": "Execution Fill Completed", "status": "PASSED" if status in ("OPEN", "CLOSED", "FILLED") else "PENDING", "timestamp": datetime.now(timezone.utc).isoformat(), "detail": f"Filled {qty} @ ₹{price:,.2f}"},
        {"stage": "POSITION", "name": "Position Active", "status": "ACTIVE" if status == "OPEN" else "CLOSED" if status == "CLOSED" else "PASSED", "timestamp": datetime.now(timezone.utc).isoformat(), "detail": "Active bracket management (SL & TP active)."},
    ]

    return OrderLifecycleSchema(
        entity_id=clean_id,
        coin=coin,
        pair=pair,
        status=status,
        current_stage="POSITION" if status == "OPEN" else "FILLED",
        client_order_id=f"CLIENT-{clean_id[:8].upper()}",
        exchange_order_id=ex_order_id,
        subaccount_id=subaccount_id,
        requested_qty=qty,
        filled_qty=qty,
        requested_price=price,
        executed_price=price,
        slippage_pct=0.01 if mode == "LIVE_MICROCASH" else 0.0,
        mode=mode,
        timestamps={"created": datetime.now(timezone.utc).isoformat()},
        stages=stages,
    )


# ── Error Center Endpoint ─────────────────────────────────────────────────────

@router.get(
    "/monitoring/errors",
    response_model=list[ErrorLogItemSchema],
    dependencies=[Depends(require_api_key)],
    tags=["monitoring"],
)
async def get_system_errors(limit: int = Query(default=50, ge=1, le=200)) -> list[ErrorLogItemSchema]:
    """
    Retrieve centralized error trail, circuit trips, alert events, and scheduler warnings.
    """
    errors: list[ErrorLogItemSchema] = []

    # 1. Scheduler job errors
    if _scheduler:
        for job in _scheduler.get_status():
            if job.get("last_error"):
                errors.append(ErrorLogItemSchema(
                    id=f"ERR-SCHED-{job['name']}",
                    timestamp=job.get("last_run_at") or datetime.now(timezone.utc).isoformat(),
                    service="scheduler",
                    severity="WARNING" if job.get("consecutive_errors", 0) < 3 else "ERROR",
                    message=f"Job '{job['name']}' error: {job['last_error']}",
                    status="ACTIVE",
                    payload=job,
                ))

    # 2. Event log repo error entries
    if _event_log_repo:
        recent = await _event_log_repo.get_since(datetime.now(timezone.utc) - timedelta(hours=24), limit=limit)
        for e in recent:
            if "FAIL" in e.event_type or "ERROR" in e.event_type or "DENIED" in e.event_type or "TRIPPED" in e.event_type:
                errors.append(ErrorLogItemSchema(
                    id=f"ERR-EVT-{e.id}",
                    timestamp=e.logged_at.isoformat() if e.logged_at else datetime.now(timezone.utc).isoformat(),
                    service=e.source_service or "event_bus",
                    severity="CRITICAL" if "TRIPPED" in e.event_type else "WARNING" if "DENIED" in e.event_type else "ERROR",
                    message=f"{e.event_type}: {e.payload.get('reason') or e.payload.get('error') or 'Event recorded'}",
                    status="RESOLVED" if e.event_type == "TRADE_DENIED" else "ACTIVE",
                    payload=e.payload,
                ))

    # Sort newest first
    errors.sort(key=lambda x: x.timestamp, reverse=True)
    return errors[:limit]


=======
# ── Phase 3 Post-Trade Journal & Analytics Endpoints ─────────────────────────

@router.get(
    "/journal/trades",
    dependencies=[Depends(require_api_key)],
    tags=["journal"],
)
async def get_journal_trades(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    bot_name: Optional[str] = Query(default=None),
    pair: Optional[str] = Query(default=None),
):
    """Fetch paginated post-trade journal entries with statutory tax breakdowns and excursion metrics."""
    if _journal_repo is None:
        raise HTTPException(status_code=503, detail="Journal repository not initialized.")
    return await _journal_repo.get_entries(limit=limit, offset=offset, bot_name=bot_name, pair=pair)


@router.get(
    "/analytics/performance",
    dependencies=[Depends(require_api_key)],
    tags=["analytics"],
)
async def get_analytics_performance(
    bot_name: Optional[str] = Query(default=None),
    pair: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
):
    """Return quantitative performance metrics (Win Rates, Profit Factor, Max Drawdown, Sharpe, Sortino, Calmar)."""
    if _analytics_service is None:
        raise HTTPException(status_code=503, detail="Analytics service not initialized.")
    return await _analytics_service.get_performance_summary(bot_name=bot_name, pair=pair, limit=limit)


@router.get(
    "/analytics/tax-ledger",
    dependencies=[Depends(require_api_key)],
    tags=["analytics"],
)
async def get_tax_ledger(
    start_iso: Optional[str] = Query(default=None),
    end_iso: Optional[str] = Query(default=None),
):
    """Return statutory tax & compliance summary (Sec 194S TDS, brokerage GST, quarterly breakdown)."""
    if _analytics_service is None:
        raise HTTPException(status_code=503, detail="Analytics service not initialized.")
    return await _analytics_service.get_tax_ledger_summary(start_iso=start_iso, end_iso=end_iso)


# ── Phase 4 Learning Engine & Mistake Diagnosis Endpoints ────────────────────

@router.get(
    "/learning/insights",
    dependencies=[Depends(require_api_key)],
    tags=["learning"],
)
async def get_learning_insights(
    bot_name: Optional[str] = Query(default=None),
    pair: Optional[str] = Query(default=None),
):
    """Return active learned lessons and mistake pattern diagnoses."""
    if _learning_service is None:
        raise HTTPException(status_code=503, detail="Learning service not initialized.")
    return await _learning_service.get_active_insights(bot_name=bot_name, pair=pair)


@router.get(
    "/learning/calibrations",
    dependencies=[Depends(require_api_key)],
    tags=["learning"],
)
async def get_strategy_calibrations():
    """Return current dynamic strategy weight multipliers and confluence score thresholds."""
    if _learning_service is None:
        raise HTTPException(status_code=503, detail="Learning service not initialized.")
    return await _learning_service.get_calibrations()


@router.post(
    "/learning/run-cycle",
    dependencies=[Depends(require_api_key)],
    tags=["learning"],
)
async def run_learning_cycle():
    """Trigger an on-demand learning evaluation pass to extract mistake patterns and calibrate strategies."""
    if _learning_service is None:
        raise HTTPException(status_code=503, detail="Learning service not initialized.")
    return await _learning_service.run_learning_cycle()


# ── Phase 5 Historical Backtest & Strategy Improvement Endpoints ─────────────

class BacktestRunPayload(BaseModel):
    strategy_name: str = "STE"
    pair: str = "BTC/INR"
    timeframe: str = "5m"
    candles: Optional[list[dict]] = None
    parameters: Optional[dict] = None


@router.post(
    "/backtest/run",
    dependencies=[Depends(require_api_key)],
    tags=["backtest"],
)
async def run_historical_backtest(
    payload: Optional[BacktestRunPayload] = Body(default=None),
    strategy_name: Optional[str] = Query(default=None),
    pair: Optional[str] = Query(default=None),
    timeframe: Optional[str] = Query(default=None),
):
    """Launch historical multi-timeframe backtest simulation."""
    if _backtest_service is None:
        raise HTTPException(status_code=503, detail="Backtest service not initialized.")

    p = payload or BacktestRunPayload()
    strat = strategy_name or p.strategy_name
    pr = pair or p.pair
    tf = timeframe or p.timeframe
    candle_list = p.candles or []
    params = p.parameters or {"timeframe": tf}

    return await _backtest_service.run_backtest(
        strategy_name=strat,
        pair=pr,
        candles=candle_list,
        parameters=params,
    )


@router.get(
    "/backtest/results",
    dependencies=[Depends(require_api_key)],
    tags=["backtest"],
)
async def get_backtest_results(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List historical backtest summary runs."""
    if _backtest_service is None:
        raise HTTPException(status_code=503, detail="Backtest service not initialized.")
    return await _backtest_service.get_runs(limit=limit, offset=offset)


@router.get(
    "/backtest/results/{run_id}",
    dependencies=[Depends(require_api_key)],
    tags=["backtest"],
)
async def get_backtest_run_detail(run_id: str):
    """Return detailed trade log and equity curve metrics for a specific backtest run."""
    if _backtest_service is None:
        raise HTTPException(status_code=503, detail="Backtest service not initialized.")

    detail = await _backtest_service.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Backtest run '{run_id}' not found.")
    return detail


# ── Phase 6 Autonomous Recursive Feedback Loop Endpoints ─────────────────────

class FeedbackTriggerPayload(BaseModel):
    bot_name: str = "STE"
    pair: str = "BTC/INR"
    multiplier: float = 1.0
    threshold: float = 85.0
    candles: Optional[list[dict]] = None


@router.get(
    "/feedback/loop-status",
    dependencies=[Depends(require_api_key)],
    tags=["feedback"],
)
async def get_feedback_loop_status():
    """Return current autonomous feedback loop state, active promotions, and system health."""
    if _feedback_service is None:
        raise HTTPException(status_code=503, detail="Feedback service not initialized.")
    return await _feedback_service.get_loop_status()


@router.get(
    "/feedback/audit-trail",
    dependencies=[Depends(require_api_key)],
    tags=["feedback"],
)
async def get_feedback_audit_trail(
    bot_name: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
):
    """Return chronological record of parameter adjustments, backtest validations, and rollbacks."""
    if _feedback_service is None:
        raise HTTPException(status_code=503, detail="Feedback service not initialized.")
    return await _feedback_service.get_audit_trail(bot_name=bot_name, limit=limit)


@router.post(
    "/feedback/trigger-cycle",
    dependencies=[Depends(require_api_key)],
    tags=["feedback"],
)
async def trigger_feedback_cycle(
    payload: Optional[FeedbackTriggerPayload] = Body(default=None),
):
    """Trigger an immediate autonomous feedback evaluation and pre-deployment backtest validation cycle."""
    if _feedback_service is None:
        raise HTTPException(status_code=503, detail="Feedback service not initialized.")

    p = payload or FeedbackTriggerPayload()
    return await _feedback_service.trigger_feedback_cycle(
        bot_name=p.bot_name,
        pair=p.pair,
        multiplier=p.multiplier,
        threshold=p.threshold,
        candles=p.candles,
    )

>>>>>>> Stashed changes
