"""
V2 API Pydantic response schemas.

These are the wire types returned by /api/v2/* endpoints.
They are intentionally a superset of V1 /api/v1/* schemas so
clients can migrate incrementally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Signal ────────────────────────────────────────────────────────────────────

class SignalSchema(BaseModel):
    id:               str
    coin:             str
    pair:             str
    market_state:     str
    opportunity_type: str
    priority:         str
    risk_level:       str
    score:            int
    confidence:       int
    coin_class:       Optional[str]
    mtf_alignment:    bool
    generated_at:     datetime
    expires_at:       datetime
    source_bot:       str = "scanner_v1"

    model_config = {"from_attributes": True}


# ── Scanner health ────────────────────────────────────────────────────────────

class ScannerHealthSchema(BaseModel):
    healthy:        bool
    poll_count:     int
    live_signals:   int
    last_poll_at:   Optional[str]
    last_error:     Optional[str]


# ── Scheduler job status ──────────────────────────────────────────────────────

class JobStatusSchema(BaseModel):
    name:               str
    enabled:            bool
    interval_s:         int
    run_count:          int
    error_count:        int
    consecutive_errors: int
    last_run_at:        Optional[str]
    last_duration_ms:   Optional[int]
    last_error:         Optional[str]


# ── AI Intelligence (Phase 4) ─────────────────────────────────────────────

class AIAnalysisSchema(BaseModel):
    id:                     str
    signal_id:              str
    coin:                   str
    pair:                   str
    recommendation:         str
    confidence_score:       int
    trend_evaluation:       str
    momentum_evaluation:    str
    volume_evaluation:      str
    setup_quality:          str
    market_regime:          str
    risk_reward_assessment: str
    supporting_factors:     list[str] = Field(default_factory=list)
    conflicts:              list[str] = Field(default_factory=list)
    risk_factors:           list[str] = Field(default_factory=list)
    suggested_adjustments:  dict[str, Any] = Field(default_factory=dict)
    model_name:             str
    execution_latency_ms:   float
    analyzed_at:            datetime

    model_config = {"from_attributes": True}


class AIHealthSchema(BaseModel):
    healthy:              bool
    ai_enabled:           bool
    model:                str
    has_api_key:          bool
    min_priority:         str
    confidence_threshold: int
    total_evaluations:    int
    confirmed_count:      int
    rejected_count:       int
    fallback_count:       int
    avg_latency_ms:       float
    last_error:           Optional[str] = None


# ── System status ─────────────────────────────────────────────────────────────

class V2StatusSchema(BaseModel):
    version:         str = "2.1.0"
    status:          str = "ok"
    scanner_health:  ScannerHealthSchema
    ai_health:       Optional[AIHealthSchema] = None
    scheduler_jobs:  list[JobStatusSchema]
    db_path:         str
    uptime_polls:    int
    live_signals:    int


# ── Risk & Portfolio (Phase 5) ─────────────────────────────────────────────

class RiskStateSchema(BaseModel):
    trading_enabled:      bool
    emergency_stop:       bool
    circuit_breaker_open: bool
    per_bot_deployed:     dict[str, float] = Field(default_factory=dict)
    per_bot_open_count:   dict[str, int] = Field(default_factory=dict)
    total_capital_limit:  float = 0.0
    last_checked_at:      Optional[str] = None


class PositionSchema(BaseModel):
    id:             str
    bot:            str
    coin:           str
    pair:           str
    qty:            float
    entry_price:    float
    entry_time:     datetime
    current_price:  Optional[float] = None
    unrealised_pnl: Optional[float] = None
    stop_loss:      Optional[float] = None
    take_profit:    Optional[float] = None
    mode:           str
    status:         str
    signal_id:      Optional[str] = None
    exit_price:     Optional[float] = None
    exit_reason:    Optional[str] = None
    closed_at:      Optional[datetime] = None

    model_config = {"from_attributes": True}


class TradeSchema(BaseModel):
    id:          str
    position_id: str
    bot:         str
    coin:        str
    pair:        str
    entry_price: float
    exit_price:  float
    qty:         float
    pnl:         float
    pnl_pct:     float
    entry_time:  datetime
    exit_time:   datetime
    exit_reason: str
    mode:        str
    signal_id:   Optional[str] = None

    model_config = {"from_attributes": True}


class PortfolioSnapshotSchema(BaseModel):
    total_aum:           float
    total_deployed:      float
    total_cash:          float
    total_unrealised_pnl: float
    total_realised_pnl:  float
    daily_pnl:           float
    capital_utilisation: float
    positions_by_bot:    dict[str, Any] = Field(default_factory=dict)
    captured_at:         datetime


# ── Shadow Mode & Divergence (Phase 6) ───────────────────────────────────────

class ShadowTradeSchema(BaseModel):
    id:                   str
    signal_id:            str
    bot:                  str
    coin:                 str
    pair:                 str
    entry_price:          float
    qty:                  float
    amount:               float
    stop_loss:            Optional[float] = None
    take_profit:          Optional[float] = None
    ai_recommendation:    Optional[str] = None
    status:               str
    simulated_exit_price: Optional[float] = None
    simulated_pnl:        Optional[float] = None
    simulated_pnl_pct:    Optional[float] = None
    exit_reason:          Optional[str] = None
    created_at:           datetime
    closed_at:            Optional[datetime] = None

    model_config = {"from_attributes": True}


class DecisionDivergenceSchema(BaseModel):
    id:               str
    signal_id:        str
    bot:              str
    coin:             str
    v1_action:        str
    v2_action:        str
    divergence_type:  str
    reason:           str
    detected_at:      datetime
    v1_pnl:           Optional[float] = None
    v2_simulated_pnl: Optional[float] = None

    model_config = {"from_attributes": True}


class DivergenceSummarySchema(BaseModel):
    total_divergences:      int
    divergences_by_type:    dict[str, int] = Field(default_factory=dict)
    total_shadow_trades:    int
    closed_shadow_trades:   int
    winning_shadow_trades:  int
    simulated_win_rate_pct: float
    total_simulated_pnl:    float


# ── Dashboard & Monitoring (Phase 7 & 8) ────────────────────────────────────

class PipelineStageSchema(BaseModel):
    id:          str
    number:      int
    name:        str
    description: str
    status:      str
    category:    str
    icon:        str
    metrics:     dict[str, Any] = Field(default_factory=dict)
    last_event:  Optional[dict[str, Any]] = None


class PipelineStageDetailSchema(BaseModel):
    id:             str
    number:         int
    name:           str
    description:    str
    status:         str
    category:       str
    icon:           str
    metrics:        dict[str, Any] = Field(default_factory=dict)
    input_contract: dict[str, Any] = Field(default_factory=dict)
    output_contract: dict[str, Any] = Field(default_factory=dict)
    last_event:     Optional[dict[str, Any]] = None
    telemetry:      dict[str, Any] = Field(default_factory=dict)


# ── Bot Pipeline Status (4 Production Bots) ───────────────────────────────────

class BotStatusSchema(BaseModel):
    bot_name:             str = Field(default="", description="Bot identifier (STE, HDA, VCP, BBS)")
    bot:                  Optional[str] = None
    strategy:             str
    subaccount_id:        Optional[str] = None
    description:          Optional[str] = None
    icon:                 str = "🤖"
    color:                str = "#94a3b8"
    current_stage:        str
    stage_label:          Optional[str] = None
    current_stage_label:  Optional[str] = None
    stage_index:          int = 0
    current_stage_index:  Optional[int] = None
    total_stages:         int = 14
    stage_status:         str
    signals_generated:    int = 0
    ai_evaluations:       int = 0
    ai_approval_rate_pct: float = 0.0
    trades_executed:      int = 0
    open_positions:       int = 0
    win_rate_pct:         float = 0.0
    daily_pnl:            float = 0.0
    total_pnl:            float = 0.0
    capital_deployed:     float = 0.0
    capital_limit:        float = 0.0
    last_action:          Optional[str] = None
    last_action_time:     Optional[str] = None
    last_coin:            Optional[str] = None

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
    stage_order:               list[str] = Field(default_factory=list)
    stage_labels:              dict[str, str] = Field(default_factory=dict)
    strategy_params:           dict[str, Any] = Field(default_factory=dict)
    stop_loss_pct:             Optional[float] = None
    take_profit_pct:           Optional[float] = None
    stop_loss_tightened_pct:   Optional[float] = None
    default_trade_amount:      Optional[float] = None
    scan_pairs:                list[str] = Field(default_factory=list)
    counters:                  dict[str, Any] = Field(default_factory=dict)
    telemetry:                 dict[str, Any] = Field(default_factory=dict)


class DashboardOverviewSchema(BaseModel):
    status:             str = "ok"
    active_ws_clients:  int = 0
    portfolio:          Optional[dict[str, Any]] = None
    risk:               Optional[dict[str, Any]] = None
    shadow:             Optional[dict[str, Any]] = None
    subsystems:         dict[str, Any] = Field(default_factory=dict)
    pipeline_stages:    Optional[list[dict[str, Any]]] = None
    bots:               Optional[list[dict[str, Any]]] = None
    scanned_coins:      Optional[list[dict[str, Any]]] = Field(default_factory=list)
    watchlist_summary:  Optional[dict[str, Any]] = Field(default_factory=dict)
    telemetry:          Optional[dict[str, Any]] = None


class MonitoringMetricsSchema(BaseModel):
    uptime_seconds: float
    counters:       dict[str, int] = Field(default_factory=dict)
    latencies:      dict[str, Any] = Field(default_factory=dict)


class MonitoringHealthSchema(BaseModel):
    status:             str
    unhealthy_services: list[str] = Field(default_factory=list)
    services:           dict[str, Any] = Field(default_factory=dict)
    checked_at:         str


class TestNotificationRequestSchema(BaseModel):
    message: str = "Test notification from PROJECT-ALPHA V2"


# ── Generic success ───────────────────────────────────────────────────────────

class OkSchema(BaseModel):
    ok: bool = True
    detail: Optional[str] = None


# ── Analytics schemas (Phase 4) ──────────────────────────────────────────────

class AnalyticsWinRatesSchema(BaseModel):
    time_horizons:    dict[str, Any] = Field(default_factory=dict)
    tier_accuracy:    dict[str, Any] = Field(default_factory=dict)
    overall_win_rate: float = 0.0


class AnalyticsCoinsSchema(BaseModel):
    total_coins:      int = 0
    coins:            list[dict[str, Any]] = Field(default_factory=list)
    best_performing:  list[dict[str, Any]] = Field(default_factory=list)
    worst_performing: list[dict[str, Any]] = Field(default_factory=list)


class AnalyticsFunnelSchema(BaseModel):
    layers:                   list[dict[str, Any]] = Field(default_factory=list)
    dispatched_signals_count: int = 0
    final_conversion_pct:     float = 0.0


# ── Scanned Coins & Latest Evaluation Snapshot schemas ────────────────────────

class ScannedCoinLayerDetailSchema(BaseModel):
    score:   int = 0
    passed:  bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class ScannedCoinSchema(BaseModel):
    symbol:           str
    coin:             str
    pair:             str
    price:            float
    volume_24h:       float = 0.0
    volume_ratio:     float = 1.0
    ema_trend:        str = "SIDEWAYS"
    rsi:              float = 50.0
    mtf_alignment:    str = "none"
    is_mtf_aligned:   bool = False
    confluence_score: int = 0
    status:           str = "REJECTED"
    accepted:         bool = False
    rejection_reason: Optional[str] = None
    evaluated_at:     str


class ScannedCoinDetailSchema(ScannedCoinSchema):
    eval_breakdown:    dict[str, Any] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)


class WatchlistSummarySchema(BaseModel):
    total_evaluated:         int = 0
    passed_confluence_count: int = 0
    top_candidates:          list[ScannedCoinSchema] = Field(default_factory=list)
    last_scan_at:            Optional[str] = None


# ── Simulation & Learning Schemas ─────────────────────────────────────────────

class SimulateSignalRequestSchema(BaseModel):
    pair:                     Optional[str] = "SOL/INR"
    coin:                     Optional[str] = None
    bot_name:                 Optional[str] = "STE"
    score:                    Optional[int] = 89
    price:                    Optional[float] = 10140.0
    suggested_allocation_inr: Optional[float] = 200.0
    stop_loss:                Optional[float] = 9980.0
    take_profit:              Optional[float] = 10450.0
    regime:                   Optional[str] = "RISK_ON"
    eval_breakdown:           Optional[dict[str, Any]] = None


class SimulateSignalResponseSchema(BaseModel):
    ok:                       bool = True
    signal_id:                str
    pair:                     str
    bot_name:                 str
    confluence_score:         int
    ai_recommendation:        str
    confidence_score:         int
    setup_quality:            str
    supporting_factors:       list[str] = Field(default_factory=list)
    risk_factors:             list[str] = Field(default_factory=list)
    model_name:               str
    event_published:          bool = True


# ── Production Mode Controller Schemas ────────────────────────────────────────

class SetModeRequestSchema(BaseModel):
    mode: str = Field(description="'LIVE_MICROCASH' or 'SHADOW'")


class SetModeResponseSchema(BaseModel):
    ok:              bool = True
    mode:            str
    trading_enabled: bool
    shadow_mode:     bool
    message:         str


class KillSwitchResponseSchema(BaseModel):
    ok:              bool = True
    circuit_breaker: str
    trading_enabled: bool
    status:          str
    message:         str


class ResumeResponseSchema(BaseModel):
    ok:              bool = True
    circuit_breaker: str
    mode:            str
    trading_enabled: bool
    message:         str


class ProductionStatusSchema(BaseModel):
    mode:                   str
    trading_enabled:        bool
    shadow_mode:            bool
    capital_pool_limit:     Optional[float] = None
    capital_pool_deployed:  float
    capital_pool_available: Optional[float] = None
    open_positions_count:   int
    circuit_breaker_status: str
    watchdog_status:        Optional[str] = None
    subsystems_healthy:     Optional[bool] = None
    last_inspection:        Optional[str] = None


# ── Execution & Error Center Schemas ──────────────────────────────────────────

class UnifiedOrderSchema(BaseModel):
    id:                str
    exchange_order_id: Optional[str] = None
    coin:              str
    pair:              str
    side:              str = "BUY"
    qty:               float
    price:             float
    executed_price:    Optional[float] = None
    mode:              str = "SHADOW"
    status:            str = "FILLED"
    created_at:        Optional[str] = None
    filled_at:         Optional[str] = None
    bot:               Optional[str] = None
    signal_id:         Optional[str] = None
    error_reason:      Optional[str] = None


class OrderLifecycleSchema(BaseModel):
    entity_id:         str
    coin:              str
    pair:              str
    status:            str
    current_stage:     str
    client_order_id:   Optional[str] = None
    exchange_order_id: Optional[str] = None
    subaccount_id:     Optional[str] = None
    requested_qty:     float = 0.0
    filled_qty:        float = 0.0
    requested_price:   float = 0.0
    executed_price:    Optional[float] = None
    slippage_pct:      Optional[float] = None
    mode:              str = "SHADOW"
    timestamps:        dict[str, Any] = Field(default_factory=dict)
    stages:            list[dict[str, Any]] = Field(default_factory=list)
    rejection_reason:  Optional[str] = None


class ErrorLogItemSchema(BaseModel):
    id:        str
    timestamp: str
    service:   str
    severity:  str = "ERROR"
    message:   str
    status:    str = "ACTIVE"
    payload:   dict[str, Any] = Field(default_factory=dict)


# ── Coin Research & Intelligence (Research Hub) ───────────────────────────────

class ResearchPairSchema(BaseModel):
    """One entry in the supported-pairs list."""
    pair:  str
    base:  str
    quote: str


class VCPStageSchema(BaseModel):
    stage:            str
    high:             float
    low:              float
    range:            float
    contraction_pct:  float


class VCPSetupSchema(BaseModel):
    detected:          bool
    stages:            list[VCPStageSchema] = Field(default_factory=list)
    pivot_buy_point:   Optional[float] = None
    hard_stop_loss:    Optional[float] = None
    target_1:          Optional[float] = None
    target_2:          Optional[float] = None
    contraction_count: int = 0
    setup_quality:     str = "NO_SETUP"


class ScorecardSchema(BaseModel):
    total_score:                float
    pillar_technical_structure: float
    pillar_relative_strength:   float
    pillar_volume_delivery:     float
    pillar_risk_reward:         float
    rating:                     str


class TickerSnapshotSchema(BaseModel):
    ltp:            float
    change_24h_pct: float
    high_24h:       float
    low_24h:        float
    volume_24h:     float
    bid:            float
    ask:            float


class Week52Schema(BaseModel):
    high_52w:          Optional[float] = None
    low_52w:           Optional[float] = None
    pct_from_52w_high: Optional[float] = None


class CoinProfileSchema(BaseModel):
    pair:       str
    fetched_at: str
    ticker:     TickerSnapshotSchema
    week52:     Week52Schema
    indicators: dict[str, Any]
    vcp_setup:  VCPSetupSchema
    scorecard:  ScorecardSchema


class BacktestRequestSchema(BaseModel):
    symbol:   str
    strategy: str = "STE"
    days:     int = Field(default=30, ge=7, le=90)


class BacktestResultSchema(BaseModel):
    pair:                   str
    strategy:               str
    days:                   int
    total_trades:           int
    winning_trades:         int
    losing_trades:          int
    win_rate_pct:           float
    net_pnl_pct:            float
    net_realized_pnl_inr:   float
    gross_profit_factor:    float
    net_profit_factor:      float
    max_drawdown_pct:       float
    avg_net_rr:             float
    expectancy_per_trade:   float
    survives_friction:      bool
    statutory_drag_pct:     float
    initial_capital:        float
    ran_at:                 str


class PredictRequestSchema(BaseModel):
    symbol: str


class HorizonForecastSchema(BaseModel):
    direction:   str
    confidence:  int
    description: str


class PredictResultSchema(BaseModel):
    pair:                  str
    predicted_at:          str
    method:                str
    horizons:              dict[str, HorizonForecastSchema]
    key_support_levels:    list[float] = Field(default_factory=list)
    key_resistance_levels: list[float] = Field(default_factory=list)
    bullish_catalysts:     list[str]   = Field(default_factory=list)
    risk_factors:          list[str]   = Field(default_factory=list)
    summary:               str
