"""
V2 API Router — all /api/v2/* endpoints.

Mounted in v2/app_v2.py under the prefix /api/v2.

V2.1 endpoints:
  GET /api/v2/health                  — liveness (no auth)
  GET /api/v2/status                  — full system status (auth required)
  GET /api/v2/scanner/signals         — live signal list (auth required)
  GET /api/v2/scanner/signals/{id}    — single signal (auth required)
  GET /api/v2/scanner/health          — scanner sub-health (auth required)
  GET /api/v2/scheduler/jobs          — scheduler job statuses (auth required)

Later phases add /api/v2/portfolio, /api/v2/risk, /api/v2/trades, etc.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from v2.core.types import Priority
from .auth import require_api_key
from .schemas import (
    OkSchema, JobStatusSchema, ScannerHealthSchema,
    SignalSchema, V2StatusSchema,
    AIAnalysisSchema, AIHealthSchema,
    RiskStateSchema, PositionSchema, TradeSchema,
    PortfolioSnapshotSchema, ShadowTradeSchema,
    DecisionDivergenceSchema, DivergenceSummarySchema,
)

router = APIRouter()

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
) -> None:
    """Called by app_v2.py lifespan after services are started."""
    global _scanner_service, _scheduler, _config, _ai_service, _ai_repo, _signal_repo
    global _risk_service, _portfolio_service, _trading_service, _shadow_service, _shadow_repo, _position_repo, _trade_repo
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


