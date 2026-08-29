"""
V2 Bot Pipeline Tracker (Production Fleet Edition).

Tracks which pipeline stage each of the 4 production trading bots (STE, HDA, VCP, BBS)
is currently operating at, along with per-bot live metrics and last action.

Stage transitions are driven by EventBus events. No business logic —
pure observation and telemetry aggregation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.logging import get_logger
from v2.core.types import BotName

logger = get_logger("v2.services.dashboard_service.bot_pipeline")


# Pipeline stage ordering for progress-bar display
STAGE_ORDER = [
    "market_data",
    "scanner",
    "signal_engine",
    "ai_intelligence",
    "trade_constructor",
    "risk_engine",
    "auto_trade",
    "position_manager",
    "trade_journal",
    "analytics",
    "learning_engine",
    "backtest_test",
    "improved_strategy",
    "autonomous_loop",
]

STAGE_LABELS: Dict[str, str] = {
    "market_data":       "Market Data",
    "scanner":           "Scanner",
    "signal_engine":     "Signal Engine",
    "ai_intelligence":   "AI Intelligence",
    "trade_constructor": "Trade Constructor",
    "risk_engine":       "Risk Engine",
    "auto_trade":        "Auto Trade",
    "position_manager":  "Position Manager",
    "trade_journal":     "Trade Journal",
    "analytics":         "Analytics",
    "learning_engine":   "Learning Engine",
    "backtest_test":     "Backtest / Test",
    "improved_strategy": "Improved Strategy",
    "autonomous_loop":   "Recursive Loop ↺",
}


class BotState:
    """Live state snapshot for a single trading bot."""

    # Strategy parameters per bot (static, from production adapters)
    _STRATEGY_PARAMS: Dict[str, Dict[str, Any]] = {
        "STE": {
            "strategy":               "SuperTrend ATR Range Expansion",
            "description":            "Captures ATR explosive expansion moves with SuperTrend flip & 50 EMA trend alignment.",
            "subaccount_id":          "ALPHA_STE_01",
            "stop_loss_pct":          2.0,
            "take_profit_pct":        4.6,
            "stop_loss_tightened_pct": 1.2,
            "max_positions":          3,
            "default_trade_amount":   500.0,
            "allocated_wallet_inr":   35000.0,
            "icon":                   "📈",
            "color":                  "#4ade80",  # green
            "scan_pairs":             ["BTC/INR", "ETH/INR", "SOL/INR", "AVAX/INR", "LINK/INR", "BNB/INR"],
        },
        "HDA": {
            "strategy":               "High Delivery & CVD Absorption",
            "description":            "Institutional CVD volume accumulation and local breakout absorption trades.",
            "subaccount_id":          "ALPHA_HDA_01",
            "stop_loss_pct":          2.2,
            "take_profit_pct":        5.28,
            "stop_loss_tightened_pct": 1.4,
            "max_positions":          3,
            "default_trade_amount":   500.0,
            "allocated_wallet_inr":   30000.0,
            "icon":                   "💧",
            "color":                  "#06b6d4",  # cyan
            "scan_pairs":             ["BTC/INR", "ETH/INR", "SOL/INR", "MATIC/INR", "XRP/INR", "ADA/INR"],
        },
        "VCP": {
            "strategy":               "Volatility Contraction Pattern",
            "description":            "Minervini 3-wave progressive volatility contraction (T1 >= T2 >= T3) pivot breakouts.",
            "subaccount_id":          "ALPHA_VCP_01",
            "stop_loss_pct":          2.0,
            "take_profit_pct":        5.0,
            "stop_loss_tightened_pct": 1.2,
            "max_positions":          2,
            "default_trade_amount":   500.0,
            "allocated_wallet_inr":   15000.0,
            "icon":                   "🎯",
            "color":                  "#a855f7",  # purple
            "scan_pairs":             ["SOL/INR", "AVAX/INR", "LINK/INR", "ADA/INR", "MATIC/INR"],
        },
        "BBS": {
            "strategy":               "Bollinger Band Squeeze Breakout",
            "description":            "Explosive volatility expansion upon Bollinger Bands compression inside Keltner Channels.",
            "subaccount_id":          "ALPHA_BBS_01",
            "stop_loss_pct":          2.5,
            "take_profit_pct":        6.0,
            "stop_loss_tightened_pct": 1.5,
            "max_positions":          4,
            "default_trade_amount":   400.0,
            "allocated_wallet_inr":   20000.0,
            "icon":                   "⚡",
            "color":                  "#f59e0b",  # amber
            "scan_pairs":             ["BTC/INR", "ETH/INR", "SOL/INR", "DOGE/INR", "TRX/INR", "SHIB/INR"],
        },
    }

    def __init__(self, bot_name: str, config: Optional[V2Config] = None) -> None:
        self.bot_name = bot_name
        self._config = config

        # Current pipeline stage
        self.current_stage = "scanner"
        self.stage_status = "IDLE"  # IDLE / SCANNING / AI_EVALUATING / RISK_CHECK / EXECUTING / IN_POSITION / JOURNALING

        # Live counters
        self.signals_generated = 0
        self.ai_evaluations = 0
        self.ai_approved = 0
        self.ai_rejected = 0
        self.trades_executed = 0
        self.trades_closed = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.daily_pnl = 0.0
        self.open_positions = 0
        self.capital_deployed = 0.0
        self.last_action: Optional[str] = None
        self.last_action_time: Optional[str] = None
        self.last_coin: Optional[str] = None

        # Strategy params (static)
        self._params = self._STRATEGY_PARAMS.get(bot_name, self._STRATEGY_PARAMS["STE"])

        # Capital limit from config
        if config:
            limit_map = {
                "STE": config.ste_capital_limit,
                "HDA": config.hda_capital_limit,
                "VCP": config.vcp_capital_limit,
                "BBS": config.bbs_capital_limit,
            }
            self.capital_limit = limit_map.get(bot_name, 25000.0)
        else:
            default_map = {"STE": 35000.0, "HDA": 30000.0, "VCP": 15000.0, "BBS": 20000.0}
            self.capital_limit = default_map.get(bot_name, 25000.0)

    @property
    def win_rate_pct(self) -> float:
        if self.trades_closed == 0:
            return 0.0
        return round((self.wins / self.trades_closed) * 100.0, 1)

    @property
    def stage_index(self) -> int:
        try:
            return STAGE_ORDER.index(self.current_stage)
        except ValueError:
            return 0

    def to_summary(self) -> Dict[str, Any]:
        """Compact dict for multi-bot comparison view."""
        return {
            "bot_name":            self.bot_name,
            "strategy":            self._params.get("strategy", self.bot_name),
            "subaccount_id":       self._params.get("subaccount_id", f"ALPHA_{self.bot_name}_01"),
            "icon":                self._params.get("icon", "🤖"),
            "color":               self._params.get("color", "#94a3b8"),
            "current_stage":       self.current_stage,
            "stage_label":         STAGE_LABELS.get(self.current_stage, self.current_stage),
            "stage_index":         self.stage_index,
            "total_stages":        len(STAGE_ORDER),
            "stage_status":        self.stage_status,
            "open_positions":      self.open_positions,
            "max_positions":       self._params.get("max_positions", 3),
            "capital_deployed":    round(self.capital_deployed, 2),
            "capital_limit":       self.capital_limit,
            "daily_pnl":           round(self.daily_pnl, 2),
            "total_pnl":           round(self.total_pnl, 2),
            "win_rate_pct":        self.win_rate_pct,
            "trades_executed":     self.trades_executed,
            "last_action":         self.last_action or "Awaiting signals...",
            "last_action_time":    self.last_action_time,
            "last_coin":           self.last_coin,
        }

    def to_detail(self) -> Dict[str, Any]:
        """Full dict with strategy params and detailed telemetry."""
        summary = self.to_summary()
        summary.update({
            "description":             self._params.get("description", ""),
            "stop_loss_pct":           self._params.get("stop_loss_pct", 2.0),
            "take_profit_pct":         self._params.get("take_profit_pct", 4.0),
            "stop_loss_tightened_pct": self._params.get("stop_loss_tightened_pct", 1.2),
            "default_trade_amount":    self._params.get("default_trade_amount", 500.0),
            "scan_pairs":              self._params.get("scan_pairs", []),
            "stage_order":             STAGE_ORDER,
            "stage_labels":            STAGE_LABELS,
            "telemetry": {
                "signals_generated":   self.signals_generated,
                "ai_evaluations":      self.ai_evaluations,
                "ai_approved":         self.ai_approved,
                "ai_rejected":         self.ai_rejected,
                "trades_closed":       self.trades_closed,
                "wins":                self.wins,
                "losses":              self.losses,
            },
        })
        return summary


class BotPipelineTracker:
    """
    Tracks the current pipeline stage, status, and live telemetry
    for all 4 production trading bots (STE, HDA, VCP, BBS) in real time.
    """

    def __init__(self, config: Optional[V2Config] = None) -> None:
        self._config = config
        self._bots: Dict[str, BotState] = {
            BotName.STE.value: BotState("STE", config),
            BotName.HDA.value: BotState("HDA", config),
            BotName.VCP.value: BotState("VCP", config),
            BotName.BBS.value: BotState("BBS", config),
        }

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_all_bots(self) -> List[Dict[str, Any]]:
        """Return summary snapshots for all 4 production bots."""
        return [state.to_summary() for state in self._bots.values()]

    def get_bot_detail(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """Return full detail for one bot (case-insensitive). Returns None if unknown."""
        state = self._bots.get(bot_name.upper())
        return state.to_detail() if state else None

    # ── EventBus Handler ──────────────────────────────────────────────────────

    def handle_bus_event(self, event_type: str, payload: dict) -> None:
        """
        Route incoming EventBus events to the relevant bot state(s) and
        advance that bot's pipeline stage accordingly.
        """
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        bot_raw = payload.get("bot", "")
        coin = payload.get("coin", "")

        # ── SIGNAL_GENERATED ───────────────────────────────────────────────
        if event_type == EventType.SIGNAL_GENERATED.value:
            targets = [bot_raw.upper()] if bot_raw.upper() in self._bots else list(self._bots.keys())
            for bn in targets:
                s = self._bots[bn]
                s.signals_generated += 1
                s.current_stage = "signal_engine"
                s.stage_status = "SCANNING"
                s.last_action = f"Signal generated: {coin}" if coin else "Signal generated"
                s.last_action_time = now_str
                s.last_coin = coin or s.last_coin

        # ── SIGNAL_AI_CONFIRMED ────────────────────────────────────────────
        elif event_type == EventType.SIGNAL_AI_CONFIRMED.value:
            targets = [bot_raw.upper()] if bot_raw.upper() in self._bots else list(self._bots.keys())
            for bn in targets:
                s = self._bots[bn]
                s.ai_evaluations += 1
                s.ai_approved += 1
                s.current_stage = "ai_intelligence"
                s.stage_status = "AI_EVALUATING"
                conf = payload.get("confidence_score", "?")
                s.last_action = f"AI confirmed {coin} (confidence: {conf}%)"
                s.last_action_time = now_str
                s.last_coin = coin or s.last_coin

        # ── SIGNAL_AI_REJECTED ─────────────────────────────────────────────
        elif event_type == EventType.SIGNAL_AI_REJECTED.value:
            targets = [bot_raw.upper()] if bot_raw.upper() in self._bots else list(self._bots.keys())
            for bn in targets:
                s = self._bots[bn]
                s.ai_evaluations += 1
                s.ai_rejected += 1
                s.current_stage = "ai_intelligence"
                s.stage_status = "AI_EVALUATING"
                s.last_action = f"AI rejected {coin}"
                s.last_action_time = now_str

        # ── TRADE_APPROVED (Risk Engine gate passed) ───────────────────────
        elif event_type == EventType.TRADE_APPROVED.value:
            bn = bot_raw.upper()
            if bn in self._bots:
                s = self._bots[bn]
                s.current_stage = "risk_engine"
                s.stage_status = "RISK_CHECK"
                amt = payload.get("approved_amount", 0.0)
                s.last_action = f"Risk APPROVED {coin} — ₹{amt:.0f}"
                s.last_action_time = now_str
                s.last_coin = coin or s.last_coin

        # ── TRADE_DENIED (Risk Engine gate blocked) ────────────────────────
        elif event_type == EventType.TRADE_DENIED.value:
            bn = bot_raw.upper()
            if bn in self._bots:
                s = self._bots[bn]
                code = payload.get("code", "DENIED")
                s.current_stage = "risk_engine"
                s.stage_status = "RISK_CHECK"
                s.last_action = f"Risk DENIED {coin} ({code})"
                s.last_action_time = now_str

        # ── TRADE_EXECUTED (Auto Trade fired) ─────────────────────────────
        elif event_type == EventType.TRADE_EXECUTED.value:
            bn = bot_raw.upper()
            if bn in self._bots:
                s = self._bots[bn]
                s.trades_executed += 1
                price = payload.get("entry_price", 0.0)
                qty = payload.get("qty", 0.0)
                s.capital_deployed += price * qty
                s.current_stage = "auto_trade"
                s.stage_status = "EXECUTING"
                s.last_action = f"Executed {coin} @ ₹{price:.2f}"
                s.last_action_time = now_str
                s.last_coin = coin or s.last_coin

        # ── POSITION_OPENED (Position Manager now tracking) ───────────────
        elif event_type == EventType.POSITION_OPENED.value:
            bn = bot_raw.upper()
            if bn in self._bots:
                s = self._bots[bn]
                s.open_positions += 1
                s.current_stage = "position_manager"
                s.stage_status = "IN_POSITION"
                s.last_action = f"Position opened: {coin}"
                s.last_action_time = now_str

        # ── POSITION_CLOSED (Trade journaled) ─────────────────────────────
        elif event_type == EventType.POSITION_CLOSED.value:
            bn = bot_raw.upper()
            if bn in self._bots:
                s = self._bots[bn]
                s.open_positions = max(0, s.open_positions - 1)
                s.trades_closed += 1
                pnl = float(payload.get("pnl", 0.0))
                entry_price = float(payload.get("entry_price", 0.0))
                qty = float(payload.get("qty", 0.0))
                s.capital_deployed = max(0.0, s.capital_deployed - (entry_price * qty))
                s.daily_pnl += pnl
                s.total_pnl += pnl
                if pnl >= 0:
                    s.wins += 1
                else:
                    s.losses += 1
                reason = payload.get("exit_reason", "EXIT")
                sign = "+" if pnl >= 0 else ""
                s.current_stage = "trade_journal"
                s.stage_status = "JOURNALING"
                s.last_action = f"Closed {coin} {sign}₹{pnl:.2f} ({reason})"
                s.last_action_time = now_str
                s.last_coin = coin or s.last_coin
                s.stage_status = "IDLE"

        # ── PORTFOLIO_UPDATED ──────────────────────────────────────────────
        elif event_type == EventType.PORTFOLIO_UPDATED.value:
            for s in self._bots.values():
                if s.stage_status == "IDLE":
                    s.current_stage = "analytics"

    def get_health(self) -> Dict[str, Any]:
        return {
            "healthy": True,
            "bots_tracked": len(self._bots),
            "bot_names": list(self._bots.keys()),
        }
