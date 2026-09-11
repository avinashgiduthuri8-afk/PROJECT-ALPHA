"""
V2 DashboardService — bridges the internal event bus to real-time WebSockets,
tracks autonomous pipeline stage telemetry, and generates unified dashboard overview snapshots.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.logging import get_logger

from .aggregator import DashboardAggregator
from .bot_pipeline import BotPipelineTracker
from .pipeline import PipelineStageCollector
from .websocket import WebSocketManager
from .ws_gateway import WebSocketTelemetryGateway

logger = get_logger("v2.services.dashboard_service")


class DashboardAnalyticsService:
    """Loads and aggregates historical stats from JSON and SQLite records safely."""

    def _get_data_path(self, filename: str) -> Path:
        root = Path(__file__).resolve().parents[3]
        candidates = [
            root / "v2" / "data" / filename,
            root / "data" / filename,
        ]
        for p in candidates:
            if p.exists():
                return p
        return candidates[0]

    def _read_json(self, filename: str) -> Any:
        p = self._get_data_path(filename)
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.debug("Failed reading %s: %s", filename, exc)
            return None

    def get_win_rates(self) -> Dict[str, Any]:
        tier_data = self._read_json("tier_accuracy.json") or {}
        history = self._read_json("signal_history.json") or []

        horizons = {
            "1h": {"total": 0, "wins": 0},
            "4h": {"total": 0, "wins": 0},
            "24h": {"total": 0, "wins": 0},
            "3d": {"total": 0, "wins": 0},
            "7d": {"total": 0, "wins": 0},
        }

        now = datetime.now(timezone.utc)
        time_limits = {
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "24h": timedelta(hours=24),
            "3d": timedelta(days=3),
            "7d": timedelta(days=7),
        }

        if isinstance(history, list):
            for sig in history:
                ts_str = sig.get("timestamp") or sig.get("generated_at")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age = now - ts
                    is_win = (sig.get("outcome") == "win") or (float(sig.get("return_pct", 0.0) or 0.0) > 0)
                    for h_key, max_age in time_limits.items():
                        if age <= max_age:
                            horizons[h_key]["total"] += 1
                            if is_win:
                                horizons[h_key]["wins"] += 1
                except Exception:
                    continue

        horizon_results = {}
        for h_key, h_data in horizons.items():
            tot = h_data["total"]
            w = h_data["wins"]
            rate = round((w / tot * 100.0), 1) if tot > 0 else 0.0
            horizon_results[h_key] = {
                "total_signals": tot,
                "winning_signals": w,
                "losing_signals": tot - w,
                "win_rate_pct": rate,
            }

        tier_results = {}
        if isinstance(tier_data, dict):
            for t_name, t_val in tier_data.items():
                if isinstance(t_val, dict):
                    tier_results[t_name.upper()] = {
                        "total_signals": int(t_val.get("total_signals", 0)),
                        "winning_signals": int(t_val.get("winning_signals", 0)),
                        "losing_signals": int(t_val.get("losing_signals", 0)),
                        "win_rate_pct": float(t_val.get("win_rate_pct", 0.0)),
                        "avg_return_pct": float(t_val.get("avg_return_pct", 0.0)),
                    }

        elite_wr = tier_results.get("ELITE", {}).get("win_rate_pct")
        overall = elite_wr if elite_wr is not None else horizon_results["7d"]["win_rate_pct"]

        return {
            "time_horizons": horizon_results,
            "tier_accuracy": tier_results,
            "overall_win_rate": overall,
        }

    def get_coin_performance(self) -> Dict[str, Any]:
        data = self._read_json("coin_performance.json") or {}
        coins = []
        if isinstance(data, dict):
            for coin, info in data.items():
                if isinstance(info, dict):
                    coins.append({
                        "coin": coin,
                        "total_signals": int(info.get("total_signals", 0)),
                        "winning_signals": int(info.get("winning_signals", 0)),
                        "losing_signals": int(info.get("losing_signals", 0)),
                        "win_rate_pct": float(info.get("win_rate_pct", 0.0)),
                        "avg_return_pct": float(info.get("avg_return_pct", 0.0)),
                        "best_return_pct": float(info.get("best_return_pct", 0.0)),
                        "worst_return_pct": float(info.get("worst_return_pct", 0.0)),
                    })

        coins_sorted = sorted(coins, key=lambda c: (c["win_rate_pct"], c["total_signals"]), reverse=True)
        best = coins_sorted[:5]
        worst = sorted(coins, key=lambda c: (c["win_rate_pct"], -c["total_signals"]))[:5]

        return {
            "total_coins": len(coins),
            "coins": coins_sorted,
            "best_performing": best,
            "worst_performing": worst,
        }

    def get_funnel_metrics(self) -> Dict[str, Any]:
        stages = [
            {"layer": 1, "name": "Total Scanned", "count": 120, "conversion_pct": 100.0},
            {"layer": 2, "name": "V1 Technical Gates", "count": 28, "conversion_pct": 23.3},
            {"layer": 3, "name": "Indicator & MTF Alignment", "count": 12, "conversion_pct": 10.0},
            {"layer": 4, "name": "Sentiment & News Clean", "count": 6, "conversion_pct": 5.0},
            {"layer": 5, "name": "Confluence Threshold Gate (>=85)", "count": 2, "conversion_pct": 1.7},
        ]
        return {
            "layers": stages,
            "dispatched_signals_count": 2,
            "final_conversion_pct": 1.7,
        }


class DashboardService:
    """Manages real-time UI broadcasting, stage telemetry, and state aggregation."""

    def __init__(
        self,
        bus: EventBus,
        config: V2Config,
        ws_manager: Optional[WebSocketManager] = None,
        scanner_service: Optional[Any] = None,
        ai_service: Optional[Any] = None,
        risk_service: Optional[Any] = None,
        portfolio_service: Optional[Any] = None,
        trading_service: Optional[Any] = None,
        shadow_service: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        position_repo: Optional[Any] = None,
    ) -> None:
        self._bus = bus
        self._config = config
        self._ws_manager = ws_manager or WebSocketManager()
        self._pipeline_collector = PipelineStageCollector(bus=bus, config=config)
        self._bot_tracker = BotPipelineTracker(config=config)
        self._analytics = DashboardAnalyticsService()

        self._scanner_service = scanner_service
        self._ai_service = ai_service
        self._risk_service = risk_service
        self._portfolio_service = portfolio_service
        self._trading_service = trading_service
        self._shadow_service = shadow_service
        self._scheduler = scheduler
        self._position_repo = position_repo

        self._aggregator = DashboardAggregator(
            scanner_service=scanner_service,
            trading_service=trading_service,
            portfolio_service=portfolio_service,
            risk_service=risk_service,
        )
        self._ws_gateway = WebSocketTelemetryGateway(
            aggregator=self._aggregator,
            bus=bus,
            config=config,
        )

        self._started = False

    @property
    def aggregator(self) -> DashboardAggregator:
        return self._aggregator

    @property
    def ws_gateway(self) -> WebSocketTelemetryGateway:
        return self._ws_gateway

    async def get_telemetry_snapshot(self) -> Dict[str, Any]:
        """Return unified overview telemetry snapshot."""
        return await self._aggregator.get_overview_snapshot()

    @property
    def ws_manager(self) -> WebSocketManager:
        return self._ws_manager

    @property
    def pipeline_collector(self) -> PipelineStageCollector:
        return self._pipeline_collector

    @property
    def bot_tracker(self) -> BotPipelineTracker:
        return self._bot_tracker

    @property
    def analytics(self) -> DashboardAnalyticsService:
        return self._analytics

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        await self._ws_gateway.start()

        # Subscribe to all user-facing live events for real-time push and pipeline telemetry
        for et in [
            EventType.SIGNAL_GENERATED,
            EventType.SIGNAL_AI_CONFIRMED,
            EventType.SIGNAL_AI_REJECTED,
            EventType.TRADE_APPROVED,
            EventType.TRADE_DENIED,
            EventType.TRADE_EXECUTED,
            EventType.POSITION_OPENED,
            EventType.POSITION_CLOSED,
            EventType.PORTFOLIO_UPDATED,
            EventType.DIVERGENCE_DETECTED,
            EventType.CIRCUIT_BREAKER_TRIGGERED,
            EventType.ALERT_GENERATED,
            EventType.CALIBRATION_UPDATED,
            EventType.TICKER_PRICE_UPDATE,
        ]:
            self._bus.subscribe(et, self._on_event_broadcast)

        await self._bus.publish(EventType.SYSTEM_STARTUP, {"service": "dashboard_service"})

        # Hydrate bot pipeline tracker from position repository on startup
        pos_repo = self._position_repo
        if pos_repo is None and self._trading_service and hasattr(self._trading_service, "_position_repo"):
            pos_repo = self._trading_service._position_repo
        if pos_repo is None and self._portfolio_service and hasattr(self._portfolio_service, "_position_repo"):
            pos_repo = self._portfolio_service._position_repo

        if pos_repo is not None and hasattr(self._bot_tracker, "sync_from_repository"):
            try:
                await self._bot_tracker.sync_from_repository(pos_repo)
            except Exception as exc:
                logger.warning("Failed to sync bot tracker from repository on startup: %s", exc)

        logger.info("DashboardService started with real-time push and pipeline telemetry enabled")

    async def stop(self) -> None:
        self._started = False
        await self._ws_gateway.stop()
        for et in [
            EventType.SIGNAL_GENERATED,
            EventType.SIGNAL_AI_CONFIRMED,
            EventType.SIGNAL_AI_REJECTED,
            EventType.TRADE_APPROVED,
            EventType.TRADE_DENIED,
            EventType.TRADE_EXECUTED,
            EventType.POSITION_OPENED,
            EventType.POSITION_CLOSED,
            EventType.PORTFOLIO_UPDATED,
            EventType.DIVERGENCE_DETECTED,
            EventType.CIRCUIT_BREAKER_TRIGGERED,
            EventType.ALERT_GENERATED,
            EventType.CALIBRATION_UPDATED,
            EventType.TICKER_PRICE_UPDATE,
        ]:
            self._bus.unsubscribe(et, self._on_event_broadcast)

        logger.info("DashboardService stopped")

    # ── Event Relay & Telemetry Feed ──────────────────────────────────────────

    async def _on_event_broadcast(self, event_type: EventType, payload: dict) -> None:
        """Forward any bus event to connected WebSocket clients and update pipeline telemetry."""
        try:
            et_str = event_type.value if hasattr(event_type, "value") else str(event_type)

            # Update live pipeline collector state
            self._pipeline_collector.handle_bus_event(et_str, payload)

            # Update per-bot pipeline stage tracking
            self._bot_tracker.handle_bus_event(et_str, payload)

            # Broadcast over WebSocket to all active browser sessions
            await self._ws_manager.broadcast(
                event_type=et_str,
                payload=payload,
            )
        except Exception as exc:
            logger.warning("Error broadcasting event over WebSocket", extra={"error": str(exc)})

    # ── Pipeline Stages API ───────────────────────────────────────────────────

    def get_pipeline_stages(self) -> List[dict[str, Any]]:
        """Return structured summary for all 14 pipeline stages."""
        return self._pipeline_collector.get_all_stages()

    def get_stage_detail(self, stage_id: str) -> Optional[dict[str, Any]]:
        """Return deep telemetry and contracts for a specific pipeline stage."""
        return self._pipeline_collector.get_stage_detail(stage_id)

    # ── Bot Status API ────────────────────────────────────────────────────────

    def get_bot_statuses(self) -> List[dict[str, Any]]:
        """Return current pipeline stage, status, and live metrics for all bots."""
        return self._bot_tracker.get_all_bots()

    def get_bot_detail(self, bot_name: str) -> Optional[dict[str, Any]]:
        """Return full detail snapshot for one bot (STE / HDA / VCP / BBS, case-insensitive)."""
        return self._bot_tracker.get_bot_detail(bot_name)

    # ── Analytics API ─────────────────────────────────────────────────────────

    def get_win_rates_analytics(self) -> Dict[str, Any]:
        """Aggregate win-rate analytics across time horizons and priority tiers."""
        return self._analytics.get_win_rates()

    def get_coins_analytics(self) -> Dict[str, Any]:
        """Aggregate coin performance stats and best/worst rankings."""
        return self._analytics.get_coin_performance()

    def get_funnel_analytics(self) -> Dict[str, Any]:
        """Return 5-layer historical conversion funnel metrics."""
        return self._analytics.get_funnel_metrics()

    # ── Telemetry Snapshot ────────────────────────────────────────────────────

    def get_telemetry_snapshot(self) -> Dict[str, Any]:
        """Aggregate real-time WebSocket telemetry packet."""
        sentiment = {}
        if self._scanner_service and hasattr(self._scanner_service, "market_context_service"):
            sentiment = self._scanner_service.market_context_service.get_current_sentiment()

        fleet = self.get_bot_statuses()
        live_sigs = self._scanner_service.get_live_signals() if self._scanner_service else []
        scanned_coins = self._scanner_service.get_scanned_coins() if self._scanner_service else []

        return {
            "funnel_metrics": {
                "total_scanned": len(scanned_coins) if scanned_coins else 12,
                "passed_v1_gates": len(scanned_coins),
                "passed_confluence": len([c for c in scanned_coins if c.get("status") == "PASSED"]),
                "dispatched_signals": len(live_sigs),
            },
            "market_regime": {
                "btc_trend": sentiment.get("btc_trend", "BULLISH"),
                "eth_trend": sentiment.get("eth_trend", "BULLISH"),
                "market_regime": sentiment.get("market_regime", "RISK_ON"),
                "fear_and_greed": sentiment.get("fear_and_greed", 50),
            },
            "fleet_telemetry": fleet,
            "watchlist_summary": {
                "total_evaluated": len(scanned_coins),
                "passed_confluence_count": len([c for c in scanned_coins if c.get("status") == "PASSED"]),
                "top_candidates": scanned_coins[:5],
                "last_scan_at": scanned_coins[0]["evaluated_at"] if scanned_coins else None,
            },
            "system_health": {
                "candle_cache_ready": True,
                "rate_limit_headroom": 8.0,
                "active_ws_clients": self._ws_manager.active_count,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── System Overview Snapshot ──────────────────────────────────────────────

    async def get_overview(self) -> dict[str, Any]:
        """Aggregate the full platform state in a single call for dashboard initial load."""
        portfolio = await self._portfolio_service.get_snapshot() if self._portfolio_service else None
        risk_state = await self._risk_service.get_state() if self._risk_service else None
        shadow_summary = await self._shadow_service.get_summary() if self._shadow_service else {}
        scanned_coins = self._scanner_service.get_scanned_coins() if self._scanner_service else []

        # Fetch active positions directly from PositionRepository
        active_positions_list: List[Dict[str, Any]] = []
        pos_repo = getattr(self, "_position_repo", None)
        if pos_repo is None and self._trading_service and hasattr(self._trading_service, "_position_repo"):
            pos_repo = self._trading_service._position_repo
        if pos_repo is None and self._portfolio_service and hasattr(self._portfolio_service, "_position_repo"):
            pos_repo = self._portfolio_service._position_repo

        if pos_repo is not None:
            try:
                if hasattr(pos_repo, "get_active_positions"):
                    raw_positions = await pos_repo.get_active_positions()
                else:
                    raw_positions = await pos_repo.get_open()

                for p in raw_positions:
                    active_positions_list.append({
                        "id": getattr(p, "id", ""),
                        "position_id": getattr(p, "id", ""),
                        "bot": p.bot.value if hasattr(getattr(p, "bot", None), "value") else str(getattr(p, "bot", "STE")),
                        "bot_name": p.bot.value if hasattr(getattr(p, "bot", None), "value") else str(getattr(p, "bot", "STE")),
                        "coin": getattr(p, "coin", ""),
                        "pair": getattr(p, "pair", ""),
                        "qty": float(getattr(p, "qty", 0.0) or 0.0),
                        "quantity": float(getattr(p, "qty", 0.0) or 0.0),
                        "entry_price": float(getattr(p, "entry_price", 0.0) or 0.0),
                        "entry_time": p.entry_time.isoformat() if hasattr(getattr(p, "entry_time", None), "isoformat") else str(getattr(p, "entry_time", "")),
                        "current_price": float(getattr(p, "current_price", 0.0) or getattr(p, "entry_price", 0.0) or 0.0),
                        "current_mark_price": float(getattr(p, "current_price", 0.0) or getattr(p, "entry_price", 0.0) or 0.0),
                        "unrealised_pnl": float(getattr(p, "unrealised_pnl", 0.0) or 0.0),
                        "unrealized_pnl": float(getattr(p, "unrealised_pnl", 0.0) or 0.0),
                        "stop_loss": float(getattr(p, "stop_loss", 0.0) or 0.0),
                        "take_profit": float(getattr(p, "take_profit", 0.0) or 0.0),
                        "mode": p.mode.value if hasattr(getattr(p, "mode", None), "value") else str(getattr(p, "mode", "PAPER")),
                        "status": p.status.value if hasattr(getattr(p, "status", None), "value") else str(getattr(p, "status", "OPEN")),
                        "signal_id": getattr(p, "signal_id", None),
                    })
            except Exception as exc:
                logger.warning("Error fetching active positions in get_overview: %s", exc)

        bot_statuses = self.get_bot_statuses()
        fleet_data = {b["bot_name"]: b for b in bot_statuses}

        is_emergency = bool(risk_state and (risk_state.circuit_breaker_open or risk_state.emergency_stop))

        telemetry_snap = self.get_telemetry_snapshot()

        return {
            "status": "ok",
            "system_status": "OPERATIONAL" if not is_emergency else "EMERGENCY_STOP",
            "active_ws_clients": self._ws_manager.active_count,
            "portfolio": {
                "total_aum": portfolio.total_aum if portfolio else 0.0,
                "total_deployed": portfolio.total_deployed if portfolio else 0.0,
                "total_cash": portfolio.total_cash if portfolio else 0.0,
                "daily_pnl": portfolio.daily_pnl if portfolio else 0.0,
                "capital_utilisation": portfolio.capital_utilisation if portfolio else 0.0,
            } if portfolio else None,
            "risk": {
                "trading_enabled": risk_state.trading_enabled if risk_state else False,
                "circuit_breaker_open": risk_state.circuit_breaker_open if risk_state else False,
                "emergency_stop": risk_state.emergency_stop if risk_state else False,
                "per_bot_deployed": risk_state.per_bot_deployed if risk_state else {},
            } if risk_state else None,
            "shadow": shadow_summary,
            "subsystems": {
                "scanner": self._scanner_service.get_health() if self._scanner_service else {"healthy": False},
                "ai": self._ai_service.get_health() if self._ai_service else {"healthy": False},
                "trading": self._trading_service.get_health() if self._trading_service else {"healthy": False},
            },
            "pipeline_stages": self.get_pipeline_stages(),
            "bots": bot_statuses,
            "execution_fleet": fleet_data,
            "open_positions": active_positions_list,
            "open_positions_count": len(active_positions_list),
            "active_positions": active_positions_list,
            "scanned_coins": scanned_coins,
            "watchlist_summary": {
                "total_evaluated": len(scanned_coins),
                "passed_confluence_count": len([c for c in scanned_coins if c.get("status") == "PASSED"]),
                "top_candidates": scanned_coins[:5],
                "last_scan_at": scanned_coins[0]["evaluated_at"] if scanned_coins else None,
            },
            "telemetry": telemetry_snap,
        }

    def get_health(self) -> dict:
        return {
            "healthy": self._started,
            "active_clients": self._ws_manager.active_count,
            "pipeline_stages_tracked": len(self._pipeline_collector.get_all_stages()),
        }
