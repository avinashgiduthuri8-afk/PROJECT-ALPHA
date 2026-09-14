"""
PROJECT-ALPHA API Pydantic response schemas.

These are the wire types returned by /api/* and backward-compatible /api/v2/* endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── Signal ────────────────────────────────────────────────────────────────────


class SignalSchema(BaseModel):
    id: str
    coin: str
    pair: str
    market_state: str
    opportunity_type: str
    priority: str
    risk_level: str
    score: int
    confidence: int
    coin_class: str | None
    mtf_alignment: bool
    generated_at: datetime
    expires_at: datetime
    source_bot: str = "scanner_v1"

    model_config = {"from_attributes": True}


# ── Scanner health ────────────────────────────────────────────────────────────


class ScannerHealthSchema(BaseModel):
    healthy: bool
    poll_count: int
    live_signals: int
    last_poll_at: str | None
    last_error: str | None


# ── Scheduler job status ──────────────────────────────────────────────────────


class JobStatusSchema(BaseModel):
    name: str
    enabled: bool
    interval_s: int
    run_count: int
    error_count: int
    consecutive_errors: int
    last_run_at: str | None
    last_duration_ms: int | None
    last_error: str | None


# ── AI Intelligence (Phase 4) ─────────────────────────────────────────────


class AIAnalysisSchema(BaseModel):
    id: str
    signal_id: str
    coin: str
    pair: str
    recommendation: str
    confidence_score: int
    trend_evaluation: str
    momentum_evaluation: str
    volume_evaluation: str
    setup_quality: str
    market_regime: str
    risk_reward_assessment: str
    supporting_factors: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    suggested_adjustments: dict[str, Any] = Field(default_factory=dict)
    model_name: str
    execution_latency_ms: float
    analyzed_at: datetime

    model_config = {"from_attributes": True}


class AIHealthSchema(BaseModel):
    healthy: bool
    ai_enabled: bool
    model: str
    has_api_key: bool
    min_priority: str
    confidence_threshold: int
    total_evaluations: int
    confirmed_count: int
    rejected_count: int
    fallback_count: int
    avg_latency_ms: float
    last_error: str | None = None
    circuit_breaker: dict[str, Any] | None = None


# ── System status ─────────────────────────────────────────────────────────────


class StatusSchema(BaseModel):
    version: str = "2.1.0"
    status: str = "ok"
    scanner_health: ScannerHealthSchema
    ai_health: AIHealthSchema | None = None
    scheduler_jobs: list[JobStatusSchema]
    db_path: str
    uptime_polls: int
    live_signals: int


# Backward-compatible schema alias
V2StatusSchema = StatusSchema


# ── Risk & Portfolio (Phase 5) ─────────────────────────────────────────────


class RiskStateSchema(BaseModel):
    trading_enabled: bool
    emergency_stop: bool
    circuit_breaker_open: bool
    per_bot_deployed: dict[str, float] = Field(default_factory=dict)
    per_bot_open_count: dict[str, int] = Field(default_factory=dict)
    total_capital_limit: float = 0.0
    last_checked_at: str | None = None


class PositionSchema(BaseModel):
    id: str
    bot: str
    coin: str
    pair: str
    qty: float
    entry_price: float
    entry_time: datetime
    current_price: float | None = None
    unrealised_pnl: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    mode: str
    status: str
    signal_id: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    closed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ManualCloseRequestSchema(BaseModel):
    exit_price: float | None = Field(
        default=None,
        description="Optional custom exit price (defaults to current market price)",
    )
    reason: str = Field(default="MANUAL", description="Reason for closure")


class ModifyPositionRequestSchema(BaseModel):
    stop_loss: float | None = Field(default=None, description="Updated Stop Loss price")
    take_profit: float | None = Field(
        default=None, description="Updated Take Profit price"
    )
    trailing_stop_pct: float | None = Field(
        default=None, description="Trailing stop percentage (e.g. 2.0 for 2%)"
    )


class TrailingProfitRequestSchema(BaseModel):
    enabled: bool = Field(default=True, description="Enable or disable profit trailing")
    trailing_pct: float = Field(
        default=2.0, description="Trailing step percentage (e.g. 1.5, 2.0, 3.0)"
    )


class TradeSchema(BaseModel):
    id: str
    position_id: str
    bot: str
    coin: str
    pair: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str
    mode: str
    signal_id: str | None = None

    model_config = {"from_attributes": True}


class PortfolioSnapshotSchema(BaseModel):
    total_aum: float
    total_deployed: float
    total_cash: float
    total_unrealised_pnl: float
    total_realised_pnl: float
    daily_pnl: float
    capital_utilisation: float
    positions_by_bot: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime


# ── Shadow Mode & Divergence (Phase 6) ───────────────────────────────────────


class ShadowTradeSchema(BaseModel):
    id: str
    signal_id: str
    bot: str
    coin: str
    pair: str
    entry_price: float
    qty: float
    amount: float
    stop_loss: float | None = None
    take_profit: float | None = None
    ai_recommendation: str | None = None
    status: str
    simulated_exit_price: float | None = None
    simulated_pnl: float | None = None
    simulated_pnl_pct: float | None = None
    exit_reason: str | None = None
    created_at: datetime
    closed_at: datetime | None = None

    model_config = {"from_attributes": True}


class DecisionDivergenceSchema(BaseModel):
    id: str
    signal_id: str
    bot: str
    coin: str
    v1_action: str
    v2_action: str
    divergence_type: str
    reason: str
    detected_at: datetime
    v1_pnl: float | None = None
    v2_simulated_pnl: float | None = None

    model_config = {"from_attributes": True}


class DivergenceSummarySchema(BaseModel):
    total_divergences: int
    divergences_by_type: dict[str, int] = Field(default_factory=dict)
    total_shadow_trades: int
    closed_shadow_trades: int
    winning_shadow_trades: int
    simulated_win_rate_pct: float
    total_simulated_pnl: float


# ── Dashboard & Monitoring (Phase 7 & 8) ────────────────────────────────────


class PipelineStageSchema(BaseModel):
    id: str
    number: int
    name: str
    description: str
    status: str
    category: str
    icon: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    last_event: dict[str, Any] | None = None


class PipelineStageDetailSchema(BaseModel):
    id: str
    number: int
    name: str
    description: str
    status: str
    category: str
    icon: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    input_contract: dict[str, Any] = Field(default_factory=dict)
    output_contract: dict[str, Any] = Field(default_factory=dict)
    last_event: dict[str, Any] | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)


# ── Bot Pipeline Status (4 Production Bots) ───────────────────────────────────


class BotStatusSchema(BaseModel):
    bot_name: str = Field(default="", description="Bot identifier (STE, HDA, VCP, BBS)")
    bot: str | None = None
    strategy: str
    subaccount_id: str | None = None
    description: str | None = None
    icon: str = "🤖"
    color: str = "#94a3b8"
    current_stage: str
    stage_label: str | None = None
    current_stage_label: str | None = None
    stage_index: int = 0
    current_stage_index: int | None = None
    total_stages: int = 14
    stage_status: str
    signals_generated: int = 0
    ai_evaluations: int = 0
    ai_approval_rate_pct: float = 0.0
    trades_executed: int = 0
    open_positions: int = 0
    win_rate_pct: float = 0.0
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    capital_deployed: float = 0.0
    capital_limit: float = 0.0
    last_action: str | None = None
    last_action_time: str | None = None
    last_coin: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if not self.bot and self.bot_name:
            self.bot = self.bot_name
        if not self.bot_name and self.bot:
            self.bot_name = self.bot
        if not self.stage_label and self.current_stage_label:
            self.stage_label = self.current_stage_label
        if not self.current_stage_label and self.stage_label:
            self.current_stage_label = self.stage_label
        if self.current_stage_index is None:
            self.current_stage_index = self.stage_index


class BotDetailSchema(BotStatusSchema):
    stage_order: list[str] = Field(default_factory=list)
    stage_labels: dict[str, str] = Field(default_factory=dict)
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    stop_loss_tightened_pct: float | None = None
    default_trade_amount: float | None = None
    scan_pairs: list[str] = Field(default_factory=list)
    counters: dict[str, Any] = Field(default_factory=dict)
    telemetry: dict[str, Any] = Field(default_factory=dict)


class DashboardOverviewSchema(BaseModel):
    status: str = "ok"
    system_status: str | None = "OPERATIONAL"
    active_ws_clients: int = 0
    portfolio: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    shadow: dict[str, Any] | None = None
    subsystems: dict[str, Any] = Field(default_factory=dict)
    pipeline_stages: list[dict[str, Any]] | None = None
    bots: list[dict[str, Any]] | None = None
    execution_fleet: dict[str, Any] | None = None
    open_positions: list[dict[str, Any]] | None = Field(default_factory=list)
    open_positions_count: int = 0
    active_positions: list[dict[str, Any]] | None = Field(default_factory=list)
    scanned_coins: list[dict[str, Any]] | None = Field(default_factory=list)
    watchlist_summary: dict[str, Any] | None = Field(default_factory=dict)
    scanner_funnel: dict[str, Any] | None = None
    performance_summary: dict[str, Any] | None = None
    feedback_state: dict[str, Any] | None = None
    telemetry: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class MonitoringMetricsSchema(BaseModel):
    uptime_seconds: float
    counters: dict[str, int] = Field(default_factory=dict)
    latencies: dict[str, Any] = Field(default_factory=dict)


class MonitoringHealthSchema(BaseModel):
    status: str
    unhealthy_services: list[str] = Field(default_factory=list)
    services: dict[str, Any] = Field(default_factory=dict)
    checked_at: str


class TestNotificationRequestSchema(BaseModel):
    message: str = "Test notification from PROJECT-ALPHA V2"


# ── Generic success ───────────────────────────────────────────────────────────


class OkSchema(BaseModel):
    ok: bool = True
    detail: str | None = None


# ── Analytics schemas (Phase 4) ──────────────────────────────────────────────


class AnalyticsWinRatesSchema(BaseModel):
    time_horizons: dict[str, Any] = Field(default_factory=dict)
    tier_accuracy: dict[str, Any] = Field(default_factory=dict)
    overall_win_rate: float = 0.0


class AnalyticsCoinsSchema(BaseModel):
    total_coins: int = 0
    coins: list[dict[str, Any]] = Field(default_factory=list)
    best_performing: list[dict[str, Any]] = Field(default_factory=list)
    worst_performing: list[dict[str, Any]] = Field(default_factory=list)


class AnalyticsFunnelSchema(BaseModel):
    layers: list[dict[str, Any]] = Field(default_factory=list)
    dispatched_signals_count: int = 0
    final_conversion_pct: float = 0.0


# ── Scanned Coins & Latest Evaluation Snapshot schemas ────────────────────────


class ScannedCoinLayerDetailSchema(BaseModel):
    score: int = 0
    passed: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class ScannedCoinSchema(BaseModel):
    symbol: str
    coin: str
    pair: str
    price: float
    price_change_pct: float = Field(default=0.0)
    volume_24h: float = 0.0
    volume_ratio: float = 1.0
    ema_trend: str = "SIDEWAYS"
    rsi: float = 50.0
    mtf_alignment: str = "none"
    is_mtf_aligned: bool = False
    confluence_score: int = 0
    status: str = "REJECTED"
    accepted: bool = False
    rejection_reason: str | None = None
    evaluated_at: str


class ScannedCoinDetailSchema(ScannedCoinSchema):
    eval_breakdown: dict[str, Any] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)


class WatchlistSummarySchema(BaseModel):
    total_evaluated: int = 0
    passed_confluence_count: int = 0
    top_candidates: list[ScannedCoinSchema] = Field(default_factory=list)
    last_scan_at: str | None = None


# ── Simulation & Learning Schemas ─────────────────────────────────────────────


class SimulateSignalRequestSchema(BaseModel):
    pair: str | None = "SOL/INR"
    coin: str | None = None
    bot_name: str | None = "STE"
    score: int | None = 89
    price: float | None = 10140.0
    suggested_allocation_inr: float | None = 200.0
    stop_loss: float | None = 9980.0
    take_profit: float | None = 10450.0
    regime: str | None = "RISK_ON"
    eval_breakdown: dict[str, Any] | None = None


class SimulateSignalResponseSchema(BaseModel):
    ok: bool = True
    signal_id: str
    pair: str
    bot_name: str
    confluence_score: int
    ai_recommendation: str
    confidence_score: int
    setup_quality: str
    supporting_factors: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    model_name: str
    event_published: bool = True


# ── Production Mode Controller Schemas ────────────────────────────────────────


class SetModeRequestSchema(BaseModel):
    mode: str = Field(description="'LIVE_MICROCASH', 'PAPER', or 'SHADOW'")
    password: str | None = Field(
        default=None,
        description="Configured operator password for LIVE mode authorization",
    )


class SetModeResponseSchema(BaseModel):
    ok: bool = True
    success: bool = True
    mode: str
    deployment_mode: str | None = None
    trading_enabled: bool
    shadow_mode: bool
    message: str

    def model_post_init(self, __context: Any) -> None:
        if not self.deployment_mode and self.mode:
            self.deployment_mode = self.mode


class KillSwitchResponseSchema(BaseModel):
    ok: bool = True
    circuit_breaker: str
    trading_enabled: bool
    status: str
    message: str
    ok: bool = True
    circuit_breaker: str = "TRIPPED"
    trading_enabled: bool = False
    status: str = "KILL_SWITCH_TRIPPED"
    is_kill_switch_tripped: bool = True
    message: str = "Circuit breaker tripped. All orders blocked."


class ResumeResponseSchema(BaseModel):
    ok: bool = True
    circuit_breaker: str
    mode: str
    trading_enabled: bool
    message: str
    ok: bool = True
    circuit_breaker: str = "NORMAL"
    mode: str = "PAPER"
    deployment_mode: str | None = None
    trading_enabled: bool = True
    status: str = "ACTIVE"
    is_kill_switch_tripped: bool = False
    message: str = "Trading resumed successfully."

    def model_post_init(self, __context: Any) -> None:
        if not self.deployment_mode and self.mode:
            self.deployment_mode = self.mode


class ProductionStatusSchema(BaseModel):
    mode: str
    deployment_mode: str | None = None
    is_kill_switch_tripped: bool = False
    trading_enabled: bool
    shadow_mode: bool
    capital_pool_limit: float | None = None
    capital_pool_deployed: float
    capital_pool_available: float | None = None
    open_positions_count: int
    circuit_breaker_status: str
    # Retained as response fields for backwards compatibility; no artificial
    # per-bot capital ceilings or microcash caps are advertised here.
    wallet_limits_inr: dict[str, float] = Field(default_factory=dict)
    micro_order_caps_inr: dict[str, float] = Field(default_factory=dict)
    minimum_notional_inr: float = 200.0
    watchdog_status: str | None = None
    subsystems_healthy: bool | None = None
    last_inspection: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if not self.deployment_mode and self.mode:
            self.deployment_mode = self.mode


# ── Execution & Error Center Schemas ──────────────────────────────────────────


class UnifiedOrderSchema(BaseModel):
    id: str
    exchange_order_id: str | None = None
    coin: str
    pair: str
    side: str = "BUY"
    qty: float
    price: float
    executed_price: float | None = None
    mode: str = "SHADOW"
    status: str = "FILLED"
    created_at: str | None = None
    filled_at: str | None = None
    bot: str | None = None
    signal_id: str | None = None
    error_reason: str | None = None


class OrderLifecycleSchema(BaseModel):
    entity_id: str
    coin: str
    pair: str
    status: str
    current_stage: str
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    subaccount_id: str | None = None
    requested_qty: float = 0.0
    filled_qty: float = 0.0
    requested_price: float = 0.0
    executed_price: float | None = None
    slippage_pct: float | None = None
    mode: str = "SHADOW"
    timestamps: dict[str, Any] = Field(default_factory=dict)
    stages: list[dict[str, Any]] = Field(default_factory=list)
    rejection_reason: str | None = None


class ErrorLogItemSchema(BaseModel):
    id: str
    timestamp: str
    service: str
    severity: str = "ERROR"
    message: str
    status: str = "ACTIVE"
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Coin Research & Intelligence (Research Hub) ───────────────────────────────


class ResearchPairSchema(BaseModel):
    """One entry in the supported-pairs list."""

    pair: str
    base: str
    quote: str


class ResolvedPairsSchema(BaseModel):
    """Multi-quote resolution response for a coin symbol."""

    base_asset: str
    primary_pair: str
    available_pairs: list[str]
    preferred_quote: str
    usdt_inr_rate: float
    has_inr: bool
    has_usdt: bool


class TickerStreamSchema(BaseModel):
    """High-frequency 1-second price ticker stream response."""

    symbol: str
    pair: str
    quote: str
    price: float
    price_inr_equiv: float
    change_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float
    bid: float
    ask: float
    timestamp: int
    ltp: float | None = None
    quote_currency: str | None = None
    change_24h_pct: float | None = None
    usdt_inr_rate: float | None = None
    inr_equivalent_ltp: float | None = None
    usdt_equivalent_ltp: float | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.ltp is None:
            self.ltp = self.price
        if self.quote_currency is None:
            self.quote_currency = self.quote
        if self.change_24h_pct is None:
            self.change_24h_pct = self.change_24h
        if self.inr_equivalent_ltp is None:
            self.inr_equivalent_ltp = self.price_inr_equiv
        if self.usdt_equivalent_ltp is None:
            rate = self.usdt_inr_rate or 91.50
            self.usdt_equivalent_ltp = (
                self.price
                if self.quote == "USDT"
                else (self.price / rate if rate > 0 else self.price)
            )


class VCPStageSchema(BaseModel):
    stage: str
    high: float
    low: float
    range: float
    contraction_pct: float


class VCPSetupSchema(BaseModel):
    detected: bool
    stages: list[VCPStageSchema] = Field(default_factory=list)
    pivot_buy_point: float | None = None
    hard_stop_loss: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    contraction_count: int = 0
    setup_quality: str = "NO_SETUP"


class ScorecardSchema(BaseModel):
    total_score: float
    pillar_technical_structure: float
    pillar_relative_strength: float
    pillar_volume_delivery: float
    pillar_risk_reward: float
    rating: str


class TickerSnapshotSchema(BaseModel):
    ltp: float
    change_24h_pct: float
    high_24h: float
    low_24h: float
    volume_24h: float
    bid: float
    ask: float


class Week52Schema(BaseModel):
    high_52w: float | None = None
    low_52w: float | None = None
    pct_from_52w_high: float | None = None


class CoinProfileSchema(BaseModel):
    pair: str
    fetched_at: str
    ticker: TickerSnapshotSchema
    week52: Week52Schema
    indicators: dict[str, Any]
    vcp_setup: VCPSetupSchema
    scorecard: ScorecardSchema


class BacktestRequestSchema(BaseModel):
    symbol: str
    strategy: str = "STE"
    days: int = Field(default=30, ge=7, le=90)


class BacktestResultSchema(BaseModel):
    pair: str
    strategy: str
    days: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    net_pnl_pct: float
    net_realized_pnl_inr: float
    gross_profit_factor: float
    net_profit_factor: float
    max_drawdown_pct: float
    avg_net_rr: float
    expectancy_per_trade: float
    survives_friction: bool
    statutory_drag_pct: float
    initial_capital: float
    ran_at: str


class PredictRequestSchema(BaseModel):
    symbol: str


class HorizonForecastSchema(BaseModel):
    direction: str
    confidence: int
    description: str


class PredictResultSchema(BaseModel):
    pair: str
    predicted_at: str
    method: str
    horizons: dict[str, HorizonForecastSchema]
    key_support_levels: list[float] = Field(default_factory=list)
    key_resistance_levels: list[float] = Field(default_factory=list)
    bullish_catalysts: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    summary: str
