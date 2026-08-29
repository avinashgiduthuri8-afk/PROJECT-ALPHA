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
