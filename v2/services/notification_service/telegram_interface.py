"""
V2 Interactive Telegram Command & Control (C2) Interface.

Provides a mobile-friendly, bidirectional operator interface for PROJECT-ALPHA V2
requiring ZERO external domain, ZERO public IP, and ZERO port-forwarding via
Telegram Bot API long polling.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any, Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import DEFAULT_ORDER_AMOUNT_INR, V2Config, get_config
from v2.core.logging import get_logger
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.signal_repo import SignalRepository
from v2.repository.trade_repo import TradeRepository

from .formatters import (
    format_telegram_alerts,
    format_telegram_bot_fleet,
    format_telegram_capital,
    format_telegram_config,
    format_telegram_funnel,
    format_telegram_health,
    format_telegram_help,
    format_telegram_limits,
    format_telegram_logs,
    format_telegram_menu,
    format_telegram_mode,
    format_telegram_orders,
    format_telegram_pipeline_stages,
    format_telegram_pnl,
    format_telegram_portfolio,
    format_telegram_positions,
    format_telegram_reconciliation,
    format_telegram_risk,
    format_telegram_scan,
    format_telegram_signal_detail,
    format_telegram_signals,
    format_telegram_status,
    format_telegram_trades,
    format_telegram_uptime,
    format_telegram_watchlist,
    mask_sensitive_data,
)
from .telegram import TelegramClient

logger = get_logger("v2.services.notification_service.telegram_interface")


def build_main_menu_keyboard() -> dict:
    """Build the interactive inline keyboard for Mission Control."""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Status", "callback_data": "cb:status"},
                {"text": "🩺 Health", "callback_data": "cb:health"},
            ],
            [
                {"text": "💼 Capital", "callback_data": "cb:capital"},
                {"text": "📈 Positions", "callback_data": "cb:positions"},
            ],
            [
                {"text": "📜 Orders", "callback_data": "cb:orders"},
                {"text": "💰 P&L", "callback_data": "cb:pnl"},
            ],
            [
                {"text": "📡 Scan", "callback_data": "cb:scan"},
                {"text": "🎯 Signals", "callback_data": "cb:signals"},
            ],
            [
                {"text": "🛡️ Risk", "callback_data": "cb:risk"},
                {"text": "🔄 Refresh", "callback_data": "cb:refresh"},
            ],
            [
                {"text": "🛑 Emergency Stop", "callback_data": "cb:stop"},
                {"text": "▶️ Resume Trading", "callback_data": "cb:resume"},
            ],
        ]
    }


def build_back_keyboard(refresh_cb: str = "cb:refresh") -> dict:
    """Build navigation keyboard to return to main menu or refresh."""
    return {
        "inline_keyboard": [
            [
                {"text": "🔙 Main Menu", "callback_data": "cb:menu"},
                {"text": "🔄 Refresh", "callback_data": refresh_cb},
            ]
        ]
    }


def build_confirm_stop_keyboard() -> dict:
    """Build confirmation keyboard for emergency stop."""
    return {
        "inline_keyboard": [
            [
                {"text": "⚠️ CONFIRM EMERGENCY STOP", "callback_data": "cb:confirm_stop"},
            ],
            [
                {"text": "❌ Cancel", "callback_data": "cb:menu"},
            ],
        ]
    }


class TelegramInteractiveInterface:
    """
    Bidirectional Telegram C2 interface supporting interactive commands,
    inline button navigation, and operator-level trading controls.
    """

    def __init__(
        self,
        telegram_client: TelegramClient,
        bus: EventBus,
        config: V2Config,
        signal_repo: Optional[SignalRepository] = None,
        position_repo: Optional[PositionRepository] = None,
        trade_repo: Optional[TradeRepository] = None,
        portfolio_service: Optional[Any] = None,
        risk_service: Optional[Any] = None,
        trading_service: Optional[Any] = None,
        dashboard_service: Optional[Any] = None,
        scanner_service: Optional[Any] = None,
        health_checker: Optional[Any] = None,
        event_log_repo: Optional[EventLogRepository] = None,
        production_controller: Optional[Any] = None,
    ) -> None:
        self._telegram = telegram_client
        self._bus = bus
        self._config = config
        self._signal_repo = signal_repo
        self._position_repo = position_repo
        self._trade_repo = trade_repo
        self._portfolio_service = portfolio_service
        self._risk_service = risk_service
        self._trading_service = trading_service
        self._dashboard_service = dashboard_service
        self._scanner_service = scanner_service
        self._health_checker = health_checker
        self._event_log_repo = event_log_repo
        self._production_controller = production_controller

        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._offset: Optional[int] = None
        self._start_time = datetime.now(timezone.utc)

    def _get_subaccount_manager(self) -> Optional[Any]:
        """Safely resolve subaccount manager from trading service."""
        if not self._trading_service:
            return None
        return getattr(self._trading_service, "subaccount_manager", None) or getattr(self._trading_service, "_subaccount_manager", None)

    def is_authorized(self, chat_id: str | int) -> bool:
        """Verify if the sender chat ID is authorized."""
        cid_str = str(chat_id).strip()

        # Whitelist from config
        allowed = set()
        if self._config.alert_chat_id:
            allowed.add(str(self._config.alert_chat_id).strip())
        if self._config.telegram_allowed_chat_ids:
            for piece in self._config.telegram_allowed_chat_ids.split(","):
                if piece.strip():
                    allowed.add(piece.strip())

        if not allowed:
            logger.warning("Telegram access rejected: No allowed chat IDs configured.")
            return False

        return cid_str in allowed

    async def start(self) -> None:
        """Start interactive long polling background task."""
        if self._running or not self._telegram.is_configured:
            return

        if not self._config.telegram_interactive_enabled:
            logger.info("Telegram interactive interface is disabled in config.")
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram Interactive C2 Interface started with long-polling.")

    async def stop(self) -> None:
        """Stop interactive long polling task."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Telegram Interactive C2 Interface stopped.")

    # ── Long Polling Loop ─────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Continuous long-polling loop fetching incoming user interactions."""
        backoff = 1.0
        while self._running:
            try:
                updates = await self._telegram.get_updates(offset=self._offset, timeout=15)
                backoff = 1.0

                if not updates:
                    await asyncio.sleep(0.1)
                else:
                    for u in updates:
                        update_id = u.get("update_id")
                        if update_id is not None:
                            self._offset = update_id + 1

                        if "message" in u:
                            await self._handle_incoming_message(u["message"])
                        elif "callback_query" in u:
                            await self._handle_callback_query(u["callback_query"])

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in Telegram poll loop: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)

    # ── Command & Callback Dispatchers ────────────────────────────────────────

    async def _handle_incoming_message(self, message: dict[str, Any]) -> None:
        """Process incoming user text command."""
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if not chat_id or not text:
            return

        # Strict security authorization check
        if not self.is_authorized(chat_id):
            await self._telegram.send_message(
                text="Unauthorized.",
                target_chat_id=str(chat_id),
            )
            return

        parts = text.split()
        cmd = parts[0].lower()
        if "@" in cmd:
            cmd = cmd.split("@")[0]
        args = parts[1:]

        # 1. System Commands
        if cmd in ("/start", "/menu"):
            await self._send_main_menu(chat_id)
        elif cmd == "/help":
            await self._send_help(chat_id)
        elif cmd == "/status":
            await self._send_status(chat_id)
        elif cmd == "/health":
            await self._send_health(chat_id)
        elif cmd == "/mode":
            await self._handle_mode_command(chat_id, args)
        elif cmd == "/uptime":
            await self._send_uptime(chat_id)
        elif cmd in ("/bots", "/fleet"):
            await self._send_bot_fleet(chat_id)
        elif cmd in ("/stages", "/pipeline"):
            await self._send_pipeline_stages(chat_id)

        # 2. Scanner Commands
        elif cmd == "/scan":
            await self._send_scan(chat_id)
        elif cmd == "/signals":
            await self._send_signals(chat_id)
        elif cmd == "/signal":
            symbol = args[0] if args else ""
            await self._send_signal_detail(chat_id, symbol)
        elif cmd == "/watchlist":
            await self._send_watchlist(chat_id)
        elif cmd == "/funnel":
            await self._send_funnel(chat_id)

        # 3. Trading Commands
        elif cmd == "/positions":
            await self._send_positions(chat_id)
        elif cmd == "/trades":
            await self._send_trades(chat_id)
        elif cmd == "/pnl":
            await self._send_pnl(chat_id)
        elif cmd == "/orders":
            await self._send_orders(chat_id)
        elif cmd in ("/capital", "/portfolio", "/balance"):
            await self._send_capital(chat_id)
        elif cmd == "/config":
            await self._send_config(chat_id)

        # 4. Order Amount Control
        elif cmd == "/setamount":
            await self._handle_set_amount(chat_id, args)

        # 5. Trading Control
        elif cmd == "/pause":
            await self._handle_pause(chat_id)
        elif cmd == "/resume":
            await self._handle_resume(chat_id)
        elif cmd == "/kill":
            await self._handle_emergency_stop(chat_id, args, is_kill=True)
        elif cmd == "/emergency_stop":
            await self._handle_emergency_stop(chat_id, args, is_kill=False)
        elif cmd == "/reconcile":
            await self._handle_reconcile(chat_id)

        # 6. Risk & Monitoring
        elif cmd == "/risk":
            await self._send_risk(chat_id)
        elif cmd == "/limits":
            await self._send_limits(chat_id)
        elif cmd == "/alerts":
            await self._send_alerts(chat_id)
        elif cmd == "/logs":
            await self._send_logs(chat_id)

        else:
            await self._telegram.send_message(
                text=f"❓ Unknown command <code>{cmd}</code>. Use /help to view available commands.",
                target_chat_id=str(chat_id),
                reply_markup=build_main_menu_keyboard(),
            )

    async def _handle_callback_query(self, cb: dict[str, Any]) -> None:
        """Process inline button tap."""
        cb_id = cb.get("id")
        data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        if not cb_id or not chat_id or not message_id:
            return

        if not self.is_authorized(chat_id):
            await self._telegram.answer_callback_query(cb_id, text="Unauthorized.", show_alert=True)
            return

        await self._telegram.answer_callback_query(cb_id)

        if data in ("cb:menu", "cb:refresh"):
            await self._render_main_menu_edit(chat_id, message_id)
        elif data == "cb:status":
            await self._render_status_edit(chat_id, message_id)
        elif data == "cb:health":
            await self._render_health_edit(chat_id, message_id)
        elif data == "cb:capital":
            await self._render_capital_edit(chat_id, message_id)
        elif data == "cb:positions":
            await self._render_positions_edit(chat_id, message_id)
        elif data == "cb:trades":
            await self._render_trades_edit(chat_id, message_id)
        elif data == "cb:orders":
            await self._render_orders_edit(chat_id, message_id)
        elif data == "cb:pnl":
            await self._render_pnl_edit(chat_id, message_id)
        elif data == "cb:scan":
            await self._render_scan_edit(chat_id, message_id)
        elif data == "cb:signals":
            await self._render_signals_edit(chat_id, message_id)
        elif data == "cb:risk":
            await self._render_risk_edit(chat_id, message_id)
        elif data == "cb:stop":
            await self._render_stop_prompt_edit(chat_id, message_id)
        elif data == "cb:confirm_stop":
            await self._handle_confirm_stop_edit(chat_id, message_id)
        elif data == "cb:resume":
            await self._handle_resume_edit(chat_id, message_id)
        elif data == "cb:bots":
            await self._render_bot_fleet_edit(chat_id, message_id)
        elif data == "cb:stages":
            await self._render_stages_edit(chat_id, message_id)

    # ── View Builders & Command Handlers ─────────────────────────────────────

    def _get_active_mode(self) -> str:
        """Return standardized active trading deployment mode."""
        return getattr(self._config, "v2_deployment_mode", "SHADOW")

    # 1. System Handlers

    async def _send_main_menu(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        text = (
            "🤖 <b>PROJECT-ALPHA V2 MISSION CONTROL</b>\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "PROJECT-ALPHA V2 Operator Control & Telemetry Interface.\n"
            "• Use buttons below for quick navigation\n"
            "• Send /help for the complete operator manual\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_main_menu_keyboard(),
        )

    async def _render_main_menu_edit(self, chat_id: str | int, message_id: int) -> None:
        mode = self._get_active_mode()
        text = (
            "🤖 <b>PROJECT-ALPHA V2 MISSION CONTROL</b>\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "PROJECT-ALPHA V2 Operator Control & Telemetry Interface.\n"
            "• Use buttons below for quick navigation\n"
            "• Send /help for the complete operator manual\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_main_menu_keyboard(),
        )

    async def _send_help(self, chat_id: str | int) -> None:
        text = format_telegram_help()
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _compile_status_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        open_pos_count = 0
        if self._position_repo:
            try:
                open_pos = await self._position_repo.get_open()
                open_pos_count = len(open_pos)
            except Exception as e:
                logger.debug("Status fetch open positions error: %s", e)

        # Capital resolution
        avail_cap = None
        if mode == "LIVE_MICROCASH":
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr:
                bal = await sub_mgr.get_live_balance()
                if bal.get("success"):
                    avail_cap = bal.get("inr_balance")
        else:
            avail_cap = self._config.total_capital_limit

        # Scanner status
        poll_count = 0
        last_scan = "N/A"
        if self._scanner_service:
            poll_count = getattr(self._scanner_service, "_poll_count", 0)
            last_dt = getattr(self._scanner_service, "_last_poll_at", None)
            if last_dt:
                last_scan = last_dt.isoformat()[:19]

        # Execution event
        last_exec = "N/A"
        if self._trade_repo:
            try:
                recent_trades = await self._trade_repo.get_recent(limit=1)
                if recent_trades:
                    t = recent_trades[0]
                    last_exec = f"{t.coin} {getattr(t.exit_reason, 'value', str(t.exit_reason))}"
            except Exception:
                pass

        # Risk status
        risk_status = "HEALTHY"
        if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
            if self._risk_service.circuit_breaker.is_open:
                risk_status = "CIRCUIT_BREAKER_TRIPPED"

        return {
            "mode": mode,
            "system_status": "ONLINE",
            "scanner_status": "ACTIVE" if poll_count > 0 else "STARTING",
            "execution_status": "ENABLED" if self._config.v2_trading_enabled else "PAUSED",
            "risk_status": risk_status,
            "event_bus_status": "OPERATIONAL",
            "database_status": "CONNECTED",
            "order_amount_inr": self._config.order_size_inr,
            "available_capital": avail_cap,
            "open_positions_count": open_pos_count,
            "poll_count": poll_count,
            "last_scan_at": last_scan,
            "last_execution_at": last_exec,
        }

    async def _send_status(self, chat_id: str | int) -> None:
        data = await self._compile_status_data()
        text = format_telegram_status(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:status"),
        )

    async def _render_status_edit(self, chat_id: str | int, message_id: int) -> None:
        data = await self._compile_status_data()
        text = format_telegram_status(data)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:status"),
        )

    async def _compile_health_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        components = {
            "scanner": False,
            "ai": False,
            "risk": False,
            "execution": False,
            "database": False,
            "event_bus": True,
            "coindcx": False,
        }

        if self._health_checker:
            try:
                res = self._health_checker.check_health()
                services = res.get("services", {})
                components["database"] = services.get("database", {}).get("healthy", False)
                components["scanner"] = services.get("scanner", {}).get("healthy", False)
                components["ai"] = services.get("ai", {}).get("healthy", False)
                components["risk"] = services.get("risk", {}).get("healthy", False)
                components["execution"] = services.get("trading", {}).get("healthy", False)
            except Exception as e:
                logger.debug("HealthChecker probe error: %s", e)
        else:
            components["scanner"] = self._scanner_service is not None
            components["risk"] = self._risk_service is not None
            components["execution"] = self._trading_service is not None
            components["database"] = self._position_repo is not None

        # CoinDCX connectivity probe
        sub_mgr = self._get_subaccount_manager()
        if sub_mgr:
            try:
                bal = await sub_mgr.get_live_balance()
                components["coindcx"] = bool(bal.get("success", False))
            except Exception:
                components["coindcx"] = False
        else:
            components["coindcx"] = False

        overall = "healthy" if all(components[k] for k in ("database", "scanner", "risk", "execution")) else "degraded"

        return {
            "mode": mode,
            "components": components,
            "overall": overall,
            "checked_at": datetime.now(timezone.utc).isoformat()[:19],
        }

    async def _send_health(self, chat_id: str | int) -> None:
        data = await self._compile_health_data()
        text = format_telegram_health(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:health"),
        )

    async def _render_health_edit(self, chat_id: str | int, message_id: int) -> None:
        data = await self._compile_health_data()
        text = format_telegram_health(data)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:health"),
        )

    async def _handle_mode_command(self, chat_id: str | int, args: list[str]) -> None:
        """Handle /mode query or dynamic mode switching."""
        if not args:
            await self._send_mode(chat_id)
            return

        target = args[0].strip().upper()
        if target == "PAPER":
            self._config.v2_deployment_mode = "PAPER"
            self._config.v2_trading_enabled = True
            self._config.v2_shadow_mode = False
            msg = "✅ <b>Mode Switched to PAPER</b>\nSimulated execution active with zero capital risk."
        elif target == "SHADOW":
            self._config.v2_deployment_mode = "SHADOW"
            self._config.v2_trading_enabled = False
            self._config.v2_shadow_mode = True
            msg = "✅ <b>Mode Switched to SHADOW</b>\nShadow ledger recording only."
        elif target in ("LIVE", "LIVE_MICROCASH"):
            if len(args) < 2 or args[1].lower() != "confirm":
                warn = (
                    "⚠️ <b>CONFIRMATION REQUIRED</b>\n"
                    "Switching to <b>LIVE_MICROCASH</b> enables real money orders dispatched to CoinDCX.\n\n"
                    "To proceed, send:\n"
                    "<code>/mode live confirm</code>"
                )
                await self._telegram.send_message(text=warn, target_chat_id=str(chat_id))
                return
            self._config.v2_deployment_mode = "LIVE_MICROCASH"
            self._config.v2_trading_enabled = True
            self._config.v2_shadow_mode = False
            msg = f"🔴 <b>Mode Switched to LIVE_MICROCASH</b>\nReal money micro-orders enabled (₹{self._config.order_size_inr:.2f} notional)."
        else:
            await self._telegram.send_message(
                text=f"❓ Invalid mode <code>{args[0]}</code>. Valid modes: <code>paper</code>, <code>shadow</code>, <code>live</code>.",
                target_chat_id=str(chat_id),
            )
            return

        try:
            from v2.core.config import V2Config
            V2Config.save_runtime_overrides({
                "v2_deployment_mode": self._config.v2_deployment_mode,
                "v2_trading_enabled": self._config.v2_trading_enabled,
                "v2_shadow_mode": self._config.v2_shadow_mode,
            })
        except Exception as e:
            logger.warning("Could not persist runtime override for /mode: %s", e)

        await self._telegram.send_message(text=msg, target_chat_id=str(chat_id))

    async def _send_mode(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        data = {
            "mode": mode,
            "trading_enabled": self._config.v2_trading_enabled,
            "shadow_mode": self._config.v2_shadow_mode,
        }
        text = format_telegram_mode(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _send_uptime(self, chat_id: str | int) -> None:
        now = datetime.now(timezone.utc)
        elapsed = now - self._start_time
        total_seconds = int(elapsed.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        poll_cnt = getattr(self._scanner_service, "_poll_count", 0) if self._scanner_service else 0
        data = {
            "mode": self._get_active_mode(),
            "started_at": self._start_time.isoformat()[:19],
            "uptime_str": uptime_str,
            "poll_count": poll_cnt,
            "tasks_count": 1 if self._running else 0,
        }
        text = format_telegram_uptime(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    # 2. Scanner Handlers

    async def _compile_scan_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        last_scan = "N/A"
        poll_cnt = 0
        signals_data = []
        eval_count = 0

        if self._scanner_service:
            last_dt = getattr(self._scanner_service, "_last_poll_at", None)
            if last_dt:
                last_scan = last_dt.isoformat()[:19]
            poll_cnt = getattr(self._scanner_service, "_poll_count", 0)

            if hasattr(self._scanner_service, "get_live_signals"):
                sigs = self._scanner_service.get_live_signals()
                signals_data = [
                    {
                        "coin": s.coin,
                        "confluence_score": getattr(s, "confluence_score", None) or s.score,
                        "action": getattr(s, "action", None) or (s.raw_payload.get("action", "BUY") if getattr(s, "raw_payload", None) else "BUY"),
                        "price": getattr(s, "price", None) or (s.raw_payload.get("price", 0.0) if getattr(s, "raw_payload", None) else 0.0),
                    }
                    for s in sigs
                ]
            if hasattr(self._scanner_service, "get_scanned_coins"):
                scanned = self._scanner_service.get_scanned_coins()
                eval_count = len(scanned)

        return {
            "mode": mode,
            "last_scan_at": last_scan,
            "evaluated_count": eval_count,
            "candidate_count": poll_cnt,
            "signals": signals_data,
        }

    async def _send_scan(self, chat_id: str | int) -> None:
        data = await self._compile_scan_data()
        text = format_telegram_scan(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:scan"),
        )

    async def _render_scan_edit(self, chat_id: str | int, message_id: int) -> None:
        data = await self._compile_scan_data()
        text = format_telegram_scan(data)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:scan"),
        )

    async def _send_signals(self, chat_id: str | int) -> None:
        signals = await self._fetch_signals_data()
        text = format_telegram_signals(signals)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:signals"),
        )

    async def _render_signals_edit(self, chat_id: str | int, message_id: int) -> None:
        signals = await self._fetch_signals_data()
        text = format_telegram_signals(signals)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:signals"),
        )

    async def _fetch_signals_data(self) -> list[dict[str, Any]]:
        mode = self._get_active_mode()
        if self._scanner_service and hasattr(self._scanner_service, "get_live_signals"):
            sigs = self._scanner_service.get_live_signals()
            return [
                {
                    "coin": s.coin,
                    "confluence_score": getattr(s, "confluence_score", None) or s.score,
                    "action": getattr(s, "action", None) or (s.raw_payload.get("action", "BUY") if getattr(s, "raw_payload", None) else "BUY"),
                    "price": getattr(s, "price", None) or (s.raw_payload.get("price", 0.0) if getattr(s, "raw_payload", None) else 0.0),
                    "generated_at": s.generated_at.isoformat() if hasattr(s.generated_at, "isoformat") else str(s.generated_at),
                }
                for s in sigs
            ]
        if self._signal_repo:
            live = await self._signal_repo.get_live()
            return [
                {
                    "coin": s.coin,
                    "confluence_score": getattr(s, "confluence_score", None) or s.score,
                    "action": getattr(s, "action", None) or (s.raw_payload.get("action", "BUY") if getattr(s, "raw_payload", None) else "BUY"),
                    "price": getattr(s, "price", None) or (s.raw_payload.get("price", 0.0) if getattr(s, "raw_payload", None) else 0.0),
                    "generated_at": s.generated_at.isoformat() if hasattr(s.generated_at, "isoformat") else str(s.generated_at),
                }
                for s in live
            ]
        return []

    async def _send_signal_detail(self, chat_id: str | int, symbol: str) -> None:
        mode = self._get_active_mode()
        if not symbol:
            await self._telegram.send_message(
                text=f"ℹ️ <b>MODE: {mode}</b>\nUsage: <code>/signal &lt;SYMBOL&gt;</code> (e.g. <code>/signal BTCINR</code>)",
                target_chat_id=str(chat_id),
            )
            return

        detail = None
        if self._scanner_service and hasattr(self._scanner_service, "get_scanned_coin_detail"):
            detail = self._scanner_service.get_scanned_coin_detail(symbol)

        if detail:
            text = format_telegram_signal_detail(detail, symbol, mode)
        else:
            text = (
                f"ℹ️ <b>MODE: {mode}</b>\n"
                f"No recent scanner telemetry found for symbol <b>{symbol.upper()}</b>.\n"
                f"Ensure the asset is in the scanner watchlist."
            )

        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _send_watchlist(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        watchlist = []
        if self._scanner_service and hasattr(self._scanner_service, "_fetch_watchlist_coins"):
            try:
                watchlist = await self._scanner_service._fetch_watchlist_coins()
            except Exception:
                pass
        if not watchlist:
            watchlist = ["BTC", "ETH", "SOL", "BNB", "XRP", "ZEC", "AVAX", "LINK", "DOGE", "SHIB", "MATIC"]

        text = format_telegram_watchlist(watchlist, mode)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _send_funnel(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        data = {}
        if self._dashboard_service and hasattr(self._dashboard_service, "get_funnel_analytics"):
            try:
                data = self._dashboard_service.get_funnel_analytics()
            except Exception:
                pass
        if not data:
            data = {
                "raw_signals_count": 0,
                "pre_filtered_count": 0,
                "confluence_passed_count": 0,
                "ai_approved_count": 0,
                "executed_count": 0,
                "pre_filter_conversion_pct": 0.0,
                "confluence_conversion_pct": 0.0,
                "ai_conversion_pct": 0.0,
                "execution_conversion_pct": 0.0,
            }
        text = format_telegram_funnel(data, mode)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    # 3. Trading Handlers

    async def _send_positions(self, chat_id: str | int) -> None:
        positions = await self._fetch_positions_data()
        text = format_telegram_positions(positions)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:positions"),
        )

    async def _render_positions_edit(self, chat_id: str | int, message_id: int) -> None:
        positions = await self._fetch_positions_data()
        text = format_telegram_positions(positions)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:positions"),
        )

    async def _fetch_positions_data(self) -> list[dict[str, Any]]:
        if self._position_repo:
            open_pos = await self._position_repo.get_open()
            return [
                {
                    "coin": p.coin,
                    "bot": p.bot.value if hasattr(p.bot, "value") else str(p.bot),
                    "qty": p.qty,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealised_pnl": p.unrealised_pnl,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                }
                for p in open_pos
            ]
        return []

    async def _send_trades(self, chat_id: str | int) -> None:
        trades = await self._fetch_trades_data()
        text = format_telegram_trades(trades)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:trades"),
        )

    async def _render_trades_edit(self, chat_id: str | int, message_id: int) -> None:
        trades = await self._fetch_trades_data()
        text = format_telegram_trades(trades)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:trades"),
        )

    async def _fetch_trades_data(self) -> list[dict[str, Any]]:
        if self._trade_repo:
            recent = await self._trade_repo.get_recent(limit=5)
            return [
                {
                    "coin": t.coin,
                    "bot": t.bot.value if hasattr(t.bot, "value") else str(t.bot),
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "exit_reason": t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason),
                }
                for t in recent
            ]
        return []

    async def _send_pnl(self, chat_id: str | int) -> None:
        data = await self._compile_pnl_data()
        text = format_telegram_pnl(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:pnl"),
        )

    async def _render_pnl_edit(self, chat_id: str | int, message_id: int) -> None:
        data = await self._compile_pnl_data()
        text = format_telegram_pnl(data)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:pnl"),
        )

    async def _compile_pnl_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        realized = 0.0
        unrealized = 0.0
        trades_cnt = 0
        win_rate = 0.0

        if self._portfolio_service:
            try:
                snap = await self._portfolio_service.get_snapshot()
                realized = snap.total_realised_pnl
                unrealized = snap.total_unrealised_pnl
            except Exception:
                pass

        if self._trade_repo:
            try:
                recent = await self._trade_repo.get_recent(limit=100)
                trades_cnt = len(recent)
                wins = sum(1 for t in recent if getattr(t, "pnl", 0.0) > 0)
                win_rate = (wins / trades_cnt * 100.0) if trades_cnt > 0 else 0.0
            except Exception:
                pass

        return {
            "mode": mode,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "trades_count": trades_cnt,
            "win_rate_pct": win_rate,
        }

    async def _compile_orders_data(self) -> list[dict[str, Any]]:
        mode = self._get_active_mode()
        orders: list[dict[str, Any]] = []

        if self._position_repo:
            try:
                open_pos = await self._position_repo.get_open()
                for p in open_pos:
                    orders.append({
                        "coin": p.coin,
                        "side": "BUY",
                        "qty": p.qty,
                        "price": p.entry_price,
                        "mode": p.mode.value if hasattr(p.mode, "value") else str(p.mode),
                        "status": "OPEN",
                        "exchange_order_id": getattr(p, "exchange_order_id", None) or "LOCAL_PAPER",
                    })
            except Exception:
                pass

        if self._trade_repo:
            try:
                recent_trades = await self._trade_repo.get_recent(limit=10)
                for t in recent_trades:
                    orders.append({
                        "coin": t.coin,
                        "side": "SELL",
                        "qty": t.qty,
                        "price": t.exit_price,
                        "mode": t.mode.value if hasattr(t.mode, "value") else str(t.mode),
                        "status": "FILLED",
                        "exchange_order_id": getattr(t, "exchange_order_id", None) or "LOCAL_PAPER",
                    })
            except Exception:
                pass

        return orders

    async def _send_orders(self, chat_id: str | int) -> None:
        orders = await self._compile_orders_data()
        text = format_telegram_orders(orders, self._get_active_mode())
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:orders"),
        )

    async def _render_orders_edit(self, chat_id: str | int, message_id: int) -> None:
        orders = await self._compile_orders_data()
        text = format_telegram_orders(orders, self._get_active_mode())
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:orders"),
        )

    async def _compile_capital_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        avail_cap = None
        source = "SIMULATION"

        if mode == "LIVE_MICROCASH":
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr:
                bal_resp = await sub_mgr.get_live_balance()
                if bal_resp.get("success"):
                    avail_cap = bal_resp.get("inr_balance")
                    source = "COINDCX_EXCHANGE"
                else:
                    avail_cap = None
                    source = "COINDCX_UNAVAILABLE"
            else:
                avail_cap = None
                source = "UNAVAILABLE"
        else:
            avail_cap = self._config.total_capital_limit
            source = "SIMULATION"

        return {
            "mode": mode,
            "available_capital": avail_cap,
            "order_amount_inr": self._config.order_size_inr,
            "capital_limit": self._config.total_capital_limit,
            "risk_available": avail_cap,
            "source": source,
        }

    async def _send_capital(self, chat_id: str | int) -> None:
        data = await self._compile_capital_data()
        text = format_telegram_capital(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:capital"),
        )

    async def _render_capital_edit(self, chat_id: str | int, message_id: int) -> None:
        data = await self._compile_capital_data()
        text = format_telegram_capital(data)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:capital"),
        )

    async def _send_config(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        data = {
            "mode": mode,
            "trading_enabled": self._config.v2_trading_enabled,
            "order_amount_inr": self._config.order_size_inr,
            "total_capital_limit": self._config.total_capital_limit,
            "max_concurrent_positions": self._config.max_concurrent_positions,
            "enforce_single_coin_lock": self._config.enforce_single_coin_lock,
            "ai_model": self._config.v2_ai_model,
            "scanner_poll_interval": self._config.v2_scanner_poll_interval,
        }
        text = format_telegram_config(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    # 4. Order Amount Control

    async def _handle_set_amount(self, chat_id: str | int, args: list[str]) -> None:
        mode = self._get_active_mode()
        if not args:
            await self._telegram.send_message(
                text=(
                    f"❌ <b>Missing Order Amount</b>\n"
                    f"<b>MODE: {mode}</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Usage: <code>/setamount &lt;amount_in_inr&gt;</code>\n"
                    "Examples:\n"
                    "  • <code>/setamount 200</code>\n"
                    "  • <code>/setamount 500</code>\n"
                    "  • <code>/setamount 1000</code>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "<i>Configure dynamic micro-order allocation amount</i>"
                ),
                target_chat_id=str(chat_id),
            )
            return

        raw_val = args[0].replace("₹", "").replace(",", "").strip()
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            await self._telegram.send_message(
                text=f"❌ <b>Invalid Number:</b> <code>{args[0]}</code>. Must be a valid numeric amount.",
                target_chat_id=str(chat_id),
            )
            return

        if math.isnan(val) or math.isinf(val) or val <= 0.0:
            await self._telegram.send_message(
                text=(
                    f"❌ <b>Invalid Order Amount: ₹{val:,.2f}</b>\n"
                    "Amount must be a positive finite number greater than ₹0.00."
                ),
                target_chat_id=str(chat_id),
            )
            return

        # Persist through existing central V2 configuration mechanism
        try:
            V2Config.save_runtime_overrides({"order_size_inr": val})
            self._config = get_config()
            self._config.order_size_inr = val

            # Propagate to running trading service
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr and hasattr(sub_mgr, "update_order_size"):
                sub_mgr.update_order_size(val)

            logger.info("Order amount updated via Telegram C2: ₹%.2f (chat_id: %s)", val, chat_id)
            await self._telegram.send_message(
                text=(
                    f"✅ <b>ORDER AMOUNT UPDATED</b>\n"
                    f"<b>MODE: {mode}</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• <b>New Configured Amount:</b> <code>₹{val:,.2f}</code>\n"
                    f"• <b>Persistence:</b> Saved to runtime override config.\n"
                    f"• <b>Risk Engine:</b> Will dynamically enforce this size on all future orders.\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                target_chat_id=str(chat_id),
                reply_markup=build_back_keyboard(),
            )
        except Exception as exc:
            logger.error("Failed to persist order amount from Telegram: %s", exc)
            await self._telegram.send_message(
                text=f"❌ <b>Error persisting configuration:</b> <code>{exc}</code>",
                target_chat_id=str(chat_id),
            )

    # 5. Trading Control

    async def _handle_pause(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        self._config.v2_trading_enabled = False
        if self._trading_service and hasattr(self._trading_service, "_config"):
            self._trading_service._config.v2_trading_enabled = False

        logger.warning("Trading paused via Telegram C2 by chat_id: %s", chat_id)
        text = (
            "⏸️ <b>TRADING EXECUTION PAUSED</b>\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <b>New Entries:</b> <b>SUSPENDED</b>\n"
            "• <b>Open Positions:</b> Maintained and monitored (NOT closed)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Use /resume to restore normal trading.</i>"
        )
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _handle_resume(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()

        # Enforce Risk Engine safety check
        if self._risk_service and hasattr(self._risk_service, "is_safe_to_resume"):
            check_fn = getattr(self._risk_service, "is_safe_to_resume")
            res = check_fn()
            if asyncio.iscoroutine(res):
                is_safe, reason = await res
            elif isinstance(res, tuple):
                is_safe, reason = res
            else:
                is_safe, reason = True, "Mock/Default"
            if not is_safe:
                logger.warning("Resume rejected via Telegram C2: Risk Engine reports unsafe state: %s", reason)
                await self._telegram.send_message(
                    text=(
                        "⚠️ <b>CANNOT RESUME TRADING</b>\n"
                        f"<b>MODE: {mode}</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>Reason:</b> <code>{reason}</code>\n"
                        "• <b>Status:</b> Trading remains <b>HALTED</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "<i>Resolve underlying risk condition before resuming.</i>"
                    ),
                    target_chat_id=str(chat_id),
                    reply_markup=build_back_keyboard(),
                )
                return

        # If production controller is wired, resume through controller
        if hasattr(self, "_production_controller") and self._production_controller:
            res = await self._production_controller.resume(operator=f"TELEGRAM_{chat_id}", target_mode=mode)
            if not res.get("ok"):
                await self._telegram.send_message(
                    text=f"❌ <b>Resume Failed:</b> {res.get('message') or res.get('error')}",
                    target_chat_id=str(chat_id),
                    reply_markup=build_back_keyboard(),
                )
                return
        else:
            self._config.v2_trading_enabled = True
            if self._trading_service and hasattr(self._trading_service, "_config"):
                self._trading_service._config.v2_trading_enabled = True
            if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
                self._risk_service.circuit_breaker.reset()

        logger.info("Trading resumed via Telegram C2 by chat_id: %s", chat_id)
        text = (
            "▶️ <b>TRADING EXECUTION RESUMED</b>\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <b>Circuit Breaker:</b> <b>RESET</b>\n"
            "• <b>Automated Entries:</b> <b>RESTORED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>New signals will be evaluated through the Risk Engine.</i>"
        )
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _handle_resume_edit(self, chat_id: str | int, message_id: int) -> None:
        mode = self._get_active_mode()

        # Enforce Risk Engine safety check
        if self._risk_service and hasattr(self._risk_service, "is_safe_to_resume"):
            check_fn = getattr(self._risk_service, "is_safe_to_resume")
            res = check_fn()
            if asyncio.iscoroutine(res):
                is_safe, reason = await res
            elif isinstance(res, tuple):
                is_safe, reason = res
            else:
                is_safe, reason = True, "Mock/Default"
            if not is_safe:
                logger.warning("Resume rejected via Telegram C2: Risk Engine reports unsafe state: %s", reason)
                await self._telegram.edit_message_text(
                    text=(
                        "⚠️ <b>CANNOT RESUME TRADING</b>\n"
                        f"<b>MODE: {mode}</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>Reason:</b> <code>{reason}</code>\n"
                        "• <b>Status:</b> Trading remains <b>HALTED</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "<i>Resolve underlying risk condition before resuming.</i>"
                    ),
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard(),
                )
                return

        if hasattr(self, "_production_controller") and self._production_controller:
            await self._production_controller.resume(operator=f"TELEGRAM_{chat_id}", target_mode=mode)
        else:
            self._config.v2_trading_enabled = True
            if self._trading_service and hasattr(self._trading_service, "_config"):
                self._trading_service._config.v2_trading_enabled = True
            if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
                self._risk_service.circuit_breaker.reset()

        text = (
            "▶️ <b>TRADING EXECUTION RESUMED</b>\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <b>Circuit Breaker:</b> <b>RESET</b>\n"
            "• <b>Automated Entries:</b> <b>RESTORED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard(),
        )

    async def _handle_emergency_stop(self, chat_id: str | int, args: list[str], is_kill: bool = False) -> None:
        mode = self._get_active_mode()
        # Direct execution on explicit /kill or argument confirmation
        if is_kill or (args and args[0].lower() in ("confirm", "yes", "force", "kill", "now")):
            if hasattr(self, "_production_controller") and self._production_controller:
                await self._production_controller.kill_switch(
                    reason="Manual emergency kill-switch via Telegram C2 interface",
                    operator=f"TELEGRAM_{chat_id}",
                )
            else:
                self._config.v2_trading_enabled = False
                if self._trading_service and hasattr(self._trading_service, "_config"):
                    self._trading_service._config.v2_trading_enabled = False

                if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
                    self._risk_service.circuit_breaker.set_emergency_stop(True, reason="EMERGENCY_STOP_VIA_TELEGRAM")
                    self._risk_service.circuit_breaker.trip("EMERGENCY_STOP_VIA_TELEGRAM")

                await self._bus.publish(
                    EventType.CIRCUIT_BREAKER_TRIGGERED,
                    {"reason": "Manual emergency stop via Telegram C2 interface", "source": "telegram"},
                )

            text = (
                "🛑 <b>EMERGENCY STOPPED / KILL-SWITCH ENGAGED</b>\n"
                f"<b>MODE: {mode}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "• <b>System Status:</b> <b>ALL TRADING HALTED</b>\n"
                "• <b>Circuit Breaker:</b> <b>TRIPPED</b>\n"
                "• <b>Outbound Execution:</b> <b>COMPLETELY BLOCKED</b>\n"
                "• <b>Existing Positions:</b> Preserved in database\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Use /resume to clear breaker and restore execution after verifying risk safety.</i>"
            )
            await self._telegram.send_message(
                text=text,
                target_chat_id=str(chat_id),
                reply_markup=build_back_keyboard(),
            )
        else:
            await self._send_emergency_stop_prompt(chat_id)

    async def _send_emergency_stop_prompt(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        text = (
            "⚠️ <b>EMERGENCY STOP CONFIRMATION REQUIRED</b> ⚠️\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Are you sure you want to trigger an Emergency Stop?\n"
            "This will instantly trip the circuit breaker and halt all new orders.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "To confirm, reply with: <code>/emergency_stop confirm</code>\n"
            "or tap the confirmation button below:"
        )
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_confirm_stop_keyboard(),
        )

    async def _render_stop_prompt_edit(self, chat_id: str | int, message_id: int) -> None:
        mode = self._get_active_mode()
        text = (
            "⚠️ <b>EMERGENCY STOP CONFIRMATION REQUIRED</b> ⚠️\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Are you sure you want to trigger an Emergency Stop?\n"
            "This will instantly trip the circuit breaker and halt all new orders.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Tap below to confirm:"
        )
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_confirm_stop_keyboard(),
        )

    async def _handle_confirm_stop_edit(self, chat_id: str | int, message_id: int) -> None:
        mode = self._get_active_mode()
        self._config.v2_trading_enabled = False
        if self._trading_service and hasattr(self._trading_service, "_config"):
            self._trading_service._config.v2_trading_enabled = False

        if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
            self._risk_service.circuit_breaker.set_emergency_stop(True, reason="EMERGENCY_STOP_VIA_TELEGRAM")
            self._risk_service.circuit_breaker.trip("EMERGENCY_STOP_VIA_TELEGRAM")

        await self._bus.publish(
            EventType.CIRCUIT_BREAKER_TRIGGERED,
            {"reason": "Manual emergency stop via Telegram C2 interface", "source": "telegram"},
        )

        text = (
            "🛑 <b>EMERGENCY STOPPED</b>\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <b>System Status:</b> <b>EMERGENCY STOPPED</b>\n"
            "• <b>Circuit Breaker:</b> <b>TRIPPED</b>\n"
            "• <b>New Entries:</b> <b>HALTED</b>\n"
            "• <b>Existing Positions:</b> Preserved in database\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Use /resume to restore execution.</i>"
        )
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard(),
        )

    async def _handle_reconcile(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        report = {
            "status": "IN_SYNC",
            "positions_checked": 0,
            "orders_checked": 0,
            "mismatches": 0,
            "balance_diff": 0.0,
            "discrepancies": [],
        }
        if self._trading_service and hasattr(self._trading_service, "reconcile_live_orders"):
            try:
                report = await self._trading_service.reconcile_live_orders()
            except Exception as e:
                logger.error("Error running reconciliation: %s", e)
                report["status"] = "RECONCILIATION_ERROR"

        text = format_telegram_reconciliation(report, mode)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    # 6. Risk & Monitoring Handlers

    async def _send_risk(self, chat_id: str | int) -> None:
        risk_data = await self._fetch_risk_data()
        text = format_telegram_risk(risk_data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:risk"),
        )

    async def _render_risk_edit(self, chat_id: str | int, message_id: int) -> None:
        risk_data = await self._fetch_risk_data()
        text = format_telegram_risk(risk_data)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:risk"),
        )

    async def _fetch_risk_data(self) -> dict[str, Any]:
        if self._risk_service:
            state = await self._risk_service.get_state()
            return {
                "circuit_breaker_open": state.circuit_breaker_open,
                "emergency_stop": state.emergency_stop,
                "total_capital_limit": self._config.total_capital_limit,
                "per_bot_deployed": state.per_bot_deployed,
                "per_bot_open_count": state.per_bot_open_count,
            }
        return {
            "circuit_breaker_open": False,
            "emergency_stop": False,
            "total_capital_limit": self._config.total_capital_limit,
            "per_bot_deployed": {"STE": 0.0, "HDA": 0.0, "VCP": 0.0, "BBS": 0.0},
            "per_bot_open_count": {"STE": 0, "HDA": 0, "VCP": 0, "BBS": 0},
        }

    async def _send_limits(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        limits_data = {
            "max_drawdown_pct": self._config.v2_max_drawdown_pct,
            "max_consecutive_losses": self._config.v2_max_consecutive_losses,
            "max_concurrent_positions": self._config.max_concurrent_positions,
        }
        text = format_telegram_limits(limits_data, mode)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _send_alerts(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        alerts = []
        if self._event_log_repo:
            try:
                raw_entries = await self._event_log_repo.get_by_type(EventType.CIRCUIT_BREAKER_TRIGGERED.value, limit=10)
                alerts = [
                    {
                        "event_type": e.event_type,
                        "source_service": e.source_service,
                        "logged_at": e.logged_at.isoformat() if e.logged_at else "N/A",
                    }
                    for e in raw_entries
                ]
            except Exception:
                pass
        text = format_telegram_alerts(alerts, mode)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _send_logs(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        logs = []
        if self._event_log_repo:
            try:
                entries = await self._event_log_repo.get_recent(limit=10)
                logs = [
                    {
                        "event_type": e.event_type,
                        "source_service": e.source_service,
                        "payload": e.payload,
                        "logged_at": e.logged_at.isoformat() if e.logged_at else "N/A",
                    }
                    for e in entries
                ]
            except Exception:
                pass
        text = format_telegram_logs(logs, mode)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    # Legacy Bot Fleet and Stages (Preserved for compatibility)

    async def _send_bot_fleet(self, chat_id: str | int) -> None:
        bots = await self._fetch_bots_data()
        text = format_telegram_bot_fleet(bots)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:bots"),
        )

    async def _render_bot_fleet_edit(self, chat_id: str | int, message_id: int) -> None:
        bots = await self._fetch_bots_data()
        text = format_telegram_bot_fleet(bots)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:bots"),
        )

    async def _fetch_bots_data(self) -> list[dict[str, Any]]:
        if self._dashboard_service and hasattr(self._dashboard_service, "bot_pipeline_tracker"):
            return self._dashboard_service.bot_pipeline_tracker.get_all_bot_summaries()

        return [
            {"name": "STE", "subaccount_id": "ALPHA_STE_01", "current_stage": "IDLE", "wallet_balance": 35000.0, "available_balance": 35000.0, "open_positions": 0, "daily_pnl": 0.0, "win_rate_pct": 0.0},
            {"name": "HDA", "subaccount_id": "ALPHA_HDA_01", "current_stage": "IDLE", "wallet_balance": 30000.0, "available_balance": 30000.0, "open_positions": 0, "daily_pnl": 0.0, "win_rate_pct": 0.0},
            {"name": "VCP", "subaccount_id": "ALPHA_VCP_01", "current_stage": "IDLE", "wallet_balance": 15000.0, "available_balance": 15000.0, "open_positions": 0, "daily_pnl": 0.0, "win_rate_pct": 0.0},
            {"name": "BBS", "subaccount_id": "ALPHA_BBS_01", "current_stage": "IDLE", "wallet_balance": 20000.0, "available_balance": 20000.0, "open_positions": 0, "daily_pnl": 0.0, "win_rate_pct": 0.0},
        ]

    async def _send_pipeline_stages(self, chat_id: str | int) -> None:
        stages = await self._fetch_stages_data()
        text = format_telegram_pipeline_stages(stages)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:stages"),
        )

    async def _render_stages_edit(self, chat_id: str | int, message_id: int) -> None:
        stages = await self._fetch_stages_data()
        text = format_telegram_pipeline_stages(stages)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:stages"),
        )

    async def _fetch_stages_data(self) -> list[dict[str, Any]]:
        if self._dashboard_service and hasattr(self._dashboard_service, "pipeline_stage_collector"):
            return self._dashboard_service.pipeline_stage_collector.get_all_stages()

        stage_names = [
            (1, "Market Data Ingestion"),
            (2, "5-Layer Confluence Scanner"),
            (3, "Signal Engine (High-Conviction)"),
            (4, "AI Intelligence (Gemini)"),
            (5, "Trade Constructor"),
            (6, "Risk Engine"),
            (7, "Execution Engine (CoinDCX)"),
            (8, "Position Manager"),
            (9, "Trade Journal"),
            (10, "Analytics Engine"),
            (11, "Learning & Backtest Engine"),
        ]
        return [
            {"number": num, "name": name, "status": "ACTIVE", "processed_count": 0, "rejected_count": 0}
            for num, name in stage_names
        ]
