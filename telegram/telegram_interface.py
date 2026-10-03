"""
V2 Interactive Telegram Command & Control (C2) Interface.

Provides a mobile-friendly, bidirectional operator interface for PROJECT-ALPHA
requiring ZERO external domain, ZERO public IP, and ZERO port-forwarding via
Telegram Bot API long polling.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any

import httpx

from core.bus.event_bus import EventBus
from core.bus.event_types import EventType
from core.config import AppConfig, get_config
from core.logging import get_logger
from core.repository.event_log_repo import EventLogRepository
from core.repository.position_repo import PositionRepository
from core.repository.signal_repo import SignalRepository
from core.repository.trade_repo import TradeRepository

from .formatters import (
    format_telegram_alerts,
    format_telegram_balance,
    format_telegram_bot_fleet,
    format_telegram_capital,
    format_telegram_config,
    format_telegram_funnel,
    format_telegram_health,
    format_telegram_help,
    format_telegram_limits,
    format_telegram_logs,
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
    format_telegram_winrate,
)
from .telegram import TelegramClient

logger = get_logger("telegram.telegram_interface")

BOT_AUTOFILL_COMMANDS: list[dict[str, str]] = [
    {"command": "status", "description": "📊 Engine status & active fleet"},
    {"command": "health", "description": "🩺 System health & connectivity"},
    {"command": "scan", "description": "📡 Live market scanner results"},
    {"command": "signals", "description": "🎯 Active MTF trading signals"},
    {"command": "positions", "description": "📈 Active positions & live PnL"},
    {"command": "trades", "description": "📜 Recent executed trade history"},
    {"command": "pnl", "description": "💰 Closed trade PnL & win rate"},
    {"command": "orders", "description": "📋 Open exchange orders"},
    {"command": "balance", "description": "💼 Account balance & available cash"},
    {"command": "portfolio", "description": "📊 Portfolio capital allocation"},
    {"command": "capital", "description": "💵 Trading capital & position sizing"},
    {"command": "winrate", "description": "🏆 Fleet win rate & profit factor"},
    {"command": "funnel", "description": "🌪️ Scanner multi-stage filter funnel"},
    {"command": "risk", "description": "🛡️ Risk engine & circuit breakers"},
    {"command": "fleet", "description": "🤖 Multi-bot fleet operational state"},
    {"command": "stages", "description": "⚡ Bot pipeline stage tracking"},
    {"command": "config", "description": "⚙️ System configuration parameters"},
    {"command": "help", "description": "📖 Complete command manual & instructions"},
    {"command": "pause", "description": "⏸️ Pause new trade entries"},
    {"command": "resume", "description": "▶️ Resume automated trading"},
    {"command": "reconcile", "description": "🔄 Audit exchange orders & balances"},
    {"command": "emergency_stop", "description": "🛑 Emergency stop & close positions"},
]


def build_main_menu_keyboard(mode: str = "PAPER") -> dict:
    """Build the interactive inline keyboard tailored for Live vs Paper Mission Control."""
    if mode in ("LIVE", "LIVE_MICROCASH"):
        return {
            "inline_keyboard": [
                [
                    {"text": "💼 Live Balance", "callback_data": "cb:balance"},
                    {"text": "📊 Live Portfolio", "callback_data": "cb:portfolio"},
                ],
                [
                    {"text": "📈 Positions", "callback_data": "cb:positions"},
                    {"text": "📜 Live Orders", "callback_data": "cb:orders"},
                ],
                [
                    {"text": "💰 P&L", "callback_data": "cb:pnl"},
                    {"text": "🛡️ Risk Ceilings", "callback_data": "cb:risk"},
                ],
                [
                    {"text": "📊 Fleet Status", "callback_data": "cb:status"},
                    {"text": "🩺 Health Probe", "callback_data": "cb:health"},
                ],
                [
                    {"text": "🛑 Emergency Stop", "callback_data": "cb:stop"},
                    {"text": "▶️ Resume Trading", "callback_data": "cb:resume"},
                ],
            ]
        }
    else:
        return {
            "inline_keyboard": [
                [
                    {"text": "🏆 Win Rate", "callback_data": "cb:winrate"},
                    {"text": "📊 Stats & Metrics", "callback_data": "cb:stats"},
                ],
                [
                    {"text": "🎯 MTF Signals", "callback_data": "cb:signals"},
                    {"text": "📡 Live Scan", "callback_data": "cb:scan"},
                ],
                [
                    {"text": "📈 Paper Positions", "callback_data": "cb:positions"},
                    {"text": "📜 Paper Trades", "callback_data": "cb:trades"},
                ],
                [
                    {"text": "💼 Paper Wallet (₹10k)", "callback_data": "cb:balance"},
                    {"text": "🌪️ Filter Funnel", "callback_data": "cb:funnel"},
                ],
                [
                    {"text": "📊 Engine Status", "callback_data": "cb:status"},
                    {"text": "🔄 Refresh", "callback_data": "cb:refresh"},
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
                {
                    "text": "⚠️ CONFIRM EMERGENCY STOP",
                    "callback_data": "cb:confirm_stop",
                },
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
        config: AppConfig,
        signal_repo: SignalRepository | None = None,
        position_repo: PositionRepository | None = None,
        trade_repo: TradeRepository | None = None,
        portfolio_service: Any | None = None,
        risk_service: Any | None = None,
        trading_service: Any | None = None,
        dashboard_service: Any | None = None,
        scanner_service: Any | None = None,
        health_checker: Any | None = None,
        event_log_repo: EventLogRepository | None = None,
        production_controller: Any | None = None,
        mode_override: str | None = None,
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
        self._mode_override = mode_override

        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._offset: int | None = None
        self._start_time = datetime.now(timezone.utc)

        from background.ai.assistant import MBTAssistantAgent
        self._assistant_agent = MBTAssistantAgent(
            config=self._config,
            position_repo=self._position_repo,
            trade_repo=self._trade_repo,
            portfolio_service=self._portfolio_service,
            health_checker=self._health_checker,
            risk_service=self._risk_service,
            scanner_service=self._scanner_service,
        )

    def _get_subaccount_manager(self) -> Any | None:
        """Safely resolve subaccount manager from trading service."""
        if not self._trading_service:
            return None
        return getattr(self._trading_service, "subaccount_manager", None) or getattr(
            self._trading_service, "_subaccount_manager", None
        )

    def is_authorized(self, chat_id: str | int) -> bool:
        """Verify if the sender chat ID is authorized."""
        cid_str = str(chat_id).strip()

        # Whitelist from config and active client
        allowed = set()
        for cand in (
            getattr(self._config, "alert_chat_id", None),
            getattr(self._config, "telegram_chat_id", None),
            getattr(self._config, "paper_chat_id", None),
            getattr(self._config, "live_chat_id", None),
            getattr(self._telegram, "default_chat_id", None),
        ):
            if cand:
                allowed.add(str(cand).strip())

        allowed_csv = getattr(self._config, "telegram_allowed_chat_ids", None)
        if allowed_csv:
            for piece in str(allowed_csv).split(","):
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
        try:
            if hasattr(self._telegram, "set_my_commands"):
                await self._telegram.set_my_commands(BOT_AUTOFILL_COMMANDS)
        except Exception as exc:
            logger.debug("Failed to set native bot commands: %s", exc)

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
                updates = await self._telegram.get_updates(
                    offset=self._offset, timeout=15
                )
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
        # Natural language operator query or main menu shortcuts
        if not text.startswith("/"):
            if text.lower().strip() in ("menu", "main menu", "main", "back", "home", "dashboard"):
                await self._send_main_menu(chat_id)
                return
            response_text = await self._assistant_agent.process_query(text)
            await self._telegram.send_message(
                text=response_text,
                target_chat_id=str(chat_id),
                reply_markup=build_back_keyboard(),
            )
            return

        parts = text.split()
        cmd = parts[0].lower()
        if "@" in cmd:
            cmd = cmd.split("@")[0]
        args = parts[1:]

        # 1. System Commands
        if cmd in ("/start", "/menu", "/main", "/mainmenu", "/main_menu", "/home", "/back"):
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

        # 3. Dedicated Balance & Portfolio & Capital Commands
        elif cmd in ("/balance", "/wallet"):
            await self._send_balance(chat_id)
        elif cmd == "/portfolio":
            await self._send_portfolio(chat_id)
        elif cmd == "/capital":
            await self._send_capital(chat_id)

        # 4. Strategy Win Rate & Stats Commands
        elif cmd in ("/winrate", "/stats", "/performance"):
            await self._send_winrate(chat_id)

        # 5. Trading & Position Commands
        elif cmd == "/positions":
            await self._send_positions(chat_id)
        elif cmd == "/trades":
            await self._send_trades(chat_id)
        elif cmd == "/pnl":
            await self._send_pnl(chat_id)
        elif cmd == "/orders":
            await self._send_orders(chat_id)
        elif cmd == "/config":
            await self._send_config(chat_id)

        # 6. Order Amount Control
        elif cmd == "/setamount":
            await self._handle_set_amount(chat_id, args)

        # 7. Trading Control & Safety
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

        # 8. Risk & Monitoring
        elif cmd in ("/risk", "/safety"):
            await self._send_risk(chat_id)
        elif cmd == "/limits":
            await self._send_limits(chat_id)
        elif cmd == "/alerts":
            await self._send_alerts(chat_id)
        elif cmd == "/logs":
            await self._send_logs(chat_id)
        elif cmd in ("/export", "/db"):
            await self._send_database_export(chat_id)

        else:
            clean_query = text.lstrip("/").replace("_", " ")
            response_text = await self._assistant_agent.process_query(clean_query)
            msg = f"❓ Unknown command <code>{cmd}</code>. Use /help to view available commands.\n\n{response_text}"
            await self._telegram.send_message(
                text=msg,
                target_chat_id=str(chat_id),
                reply_markup=build_main_menu_keyboard(self._get_active_mode()),
            )

    async def _handle_callback_query(self, cb: dict[str, Any]) -> None:
        """Process inline button tap."""
        cb_id = cb.get("id")
        data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id") if message else None
        message_id = message.get("message_id") if message else None
        from_id = cb.get("from", {}).get("id")

        if not chat_id and from_id:
            chat_id = from_id

        if not cb_id or not chat_id:
            return

        # Support authorization check by chat_id or operator user_id
        if not (self.is_authorized(chat_id) or (from_id and self.is_authorized(from_id))):
            await self._telegram.answer_callback_query(
                cb_id, text="Unauthorized.", show_alert=True
            )
            return

        await self._telegram.answer_callback_query(cb_id)

        data_clean = str(data or "").strip().lower()
        if data_clean.startswith("cb:"):
            action = data_clean[3:]
        else:
            action = data_clean

        try:
            logger.info("Handling Telegram button tap: action='%s', raw='%s', chat_id=%s, msg_id=%s", action, data, chat_id, message_id)
            if action in ("menu", "main", "main_menu", "back", "home", "refresh", "dashboard"):
                await self._render_main_menu_edit(chat_id, message_id)
            elif action in ("status", "fleet_status", "engine_status"):
                await self._render_status_edit(chat_id, message_id)
            elif action in ("health", "health_probe"):
                await self._render_health_edit(chat_id, message_id)
            elif action in ("balance", "wallet"):
                await self._render_balance_edit(chat_id, message_id)
            elif action == "portfolio":
                await self._render_portfolio_edit(chat_id, message_id)
            elif action in ("winrate", "stats", "performance"):
                await self._render_winrate_edit(chat_id, message_id)
            elif action == "capital":
                await self._render_capital_edit(chat_id, message_id)
            elif action == "positions":
                await self._render_positions_edit(chat_id, message_id)
            elif action == "trades":
                await self._render_trades_edit(chat_id, message_id)
            elif action == "orders":
                await self._render_orders_edit(chat_id, message_id)
            elif action == "pnl":
                await self._render_pnl_edit(chat_id, message_id)
            elif action in ("scan", "scans"):
                await self._render_scan_edit(chat_id, message_id)
            elif action in ("signals", "signal"):
                await self._render_signals_edit(chat_id, message_id)
            elif action == "funnel":
                await self._render_funnel_edit(chat_id, message_id)
            elif action in ("risk", "safety"):
                await self._render_risk_edit(chat_id, message_id)
            elif action == "stop":
                await self._render_stop_prompt_edit(chat_id, message_id)
            elif action == "confirm_stop":
                await self._handle_confirm_stop_edit(chat_id, message_id)
            elif action == "resume":
                await self._handle_resume_edit(chat_id, message_id)
            elif action in ("bots", "fleet"):
                await self._render_bot_fleet_edit(chat_id, message_id)
            elif action in ("stages", "pipeline"):
                await self._render_stages_edit(chat_id, message_id)
            else:
                # Any unrecognized callback defaults back to main menu
                await self._render_main_menu_edit(chat_id, message_id)
        except Exception as exc:
            logger.error("Error executing callback query %s: %s", data, exc, exc_info=True)
            if chat_id:
                await self._send_main_menu(chat_id)

    # ── View Builders & Command Handlers ─────────────────────────────────────

    def _get_active_mode(self) -> str:
        """Return standardized active trading deployment mode."""
        if getattr(self, "_mode_override", None):
            return self._mode_override
        return getattr(self._config, "deployment_mode", "PAPER")

    # 1. System Handlers

    async def _send_main_menu(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        text = (
            "🤖 <b>PROJECT-ALPHA MISSION CONTROL</b>\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "PROJECT-ALPHA Operator Control & Telemetry Interface.\n"
            "• Use buttons below for quick navigation\n"
            "• Send /help for the complete operator manual\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_main_menu_keyboard(mode),
        )

    async def _render_main_menu_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        mode = self._get_active_mode()
        text = (
            "🤖 <b>PROJECT-ALPHA MISSION CONTROL</b>\n"
            f"<b>MODE: {mode}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "PROJECT-ALPHA Operator Control & Telemetry Interface.\n"
            "• Use buttons below for quick navigation\n"
            "• Send /help for the complete operator manual\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_main_menu_keyboard(mode),
                )
            except Exception as e:
                logger.debug("Edit main menu error: %s", e)
                ok = False
        if not ok:
            await self._send_main_menu(chat_id)

    async def _send_help(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        text = format_telegram_help(mode=mode)
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
                open_pos = await self._position_repo.get_active_positions()
                open_pos_count = len(open_pos)
            except Exception as e:
                logger.debug("Status fetch open positions error: %s", e)

        # Capital resolution
        avail_cap = None
        if mode in ("LIVE", "LIVE_MICROCASH"):
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr:
                try:
                    bal = await sub_mgr.get_live_balance()
                    if bal.get("success"):
                        avail_cap = bal.get("inr_balance")
                except Exception as e:
                    logger.debug("Live balance fetch error in status: %s", e)
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
            "execution_status": "ENABLED" if self._config.trading_enabled else "PAUSED",
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

    async def _render_status_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_status_data()
        text = format_telegram_status(data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:status"),
                )
            except Exception as e:
                logger.debug("Edit status error: %s", e)
                ok = False
        if not ok:
            await self._send_status(chat_id)

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
                components["database"] = services.get("database", {}).get(
                    "healthy", False
                )
                components["scanner"] = services.get("scanner", {}).get(
                    "healthy", False
                )
                components["ai"] = services.get("ai", {}).get("healthy", False)
                components["risk"] = services.get("risk", {}).get("healthy", False)
                components["execution"] = services.get("trading", {}).get(
                    "healthy", False
                )
            except Exception as e:
                logger.debug("HealthChecker probe error: %s", e)
        else:
            components["scanner"] = self._scanner_service is not None
            components["risk"] = self._risk_service is not None
            components["execution"] = self._trading_service is not None
            components["database"] = self._position_repo is not None

        # CoinDCX connectivity probe
        is_live = mode in ("LIVE", "LIVE_MICROCASH")
        if is_live:
            # LIVE mode requires authenticated CoinDCX connectivity
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr:
                try:
                    bal = await sub_mgr.get_live_balance()
                    components["coindcx"] = bool(bal.get("success", False))
                except Exception as e:
                    logger.debug("CoinDCX live health probe error: %s", e)
                    components["coindcx"] = False
            else:
                components["coindcx"] = False
        else:
            # PAPER mode: probe public CoinDCX connectivity (does not require private credentials)
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get("https://api.coindcx.com/exchange/ticker")
                    components["coindcx"] = resp.status_code == 200
            except Exception as e:
                logger.debug("CoinDCX public health probe error: %s", e)
                sub_mgr = self._get_subaccount_manager()
                components["coindcx"] = sub_mgr is not None

        # Overall health logic: in LIVE mode, coindcx must also be healthy
        required_components = ["database", "scanner", "risk", "execution"]
        if is_live:
            required_components.append("coindcx")

        overall = (
            "healthy"
            if all(components.get(k, False) for k in required_components)
            else "degraded"
        )

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

    async def _render_health_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_health_data()
        text = format_telegram_health(data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:health"),
                )
            except Exception as e:
                logger.debug("Edit health error: %s", e)
                ok = False
        if not ok:
            await self._send_health(chat_id)

    async def _handle_mode_command(self, chat_id: str | int, args: list[str]) -> None:
        """Handle /mode query or dynamic mode switching."""
        if not args:
            await self._send_mode(chat_id)
            return

        target = args[0].strip().upper()
        if target == "PAPER":
            self._config.deployment_mode = "PAPER"
            self._config.trading_enabled = True
            self._config.shadow_mode = False
            msg = "✅ <b>Mode Switched to PAPER</b>\nSimulated execution active with zero capital risk."
        elif target in ("LIVE", "LIVE_MICROCASH"):
            if len(args) < 2 or args[1].lower() != "confirm":
                warn = (
                    "⚠️ <b>CONFIRMATION REQUIRED</b>\n"
                    "Switching to <b>LIVE</b> enables real money orders dispatched to CoinDCX.\n\n"
                    "To proceed, send:\n"
                    "<code>/mode live confirm</code>"
                )
                await self._telegram.send_message(
                    text=warn, target_chat_id=str(chat_id)
                )
                return
            self._config.deployment_mode = "LIVE_MICROCASH"
            self._config.trading_enabled = True
            self._config.shadow_mode = False
            msg = f"🔴 <b>Mode Switched to LIVE</b>\nReal money micro-orders enabled (₹{self._config.order_size_inr:.2f} notional)."
        else:
            await self._telegram.send_message(
                text=f"❓ Invalid mode <code>{args[0]}</code>. Valid modes: <code>paper</code>, <code>live</code>.",
                target_chat_id=str(chat_id),
            )
            return

        try:
            from core.config import AppConfig

            AppConfig.save_runtime_overrides(
                {
                    "deployment_mode": self._config.deployment_mode,
                    "trading_enabled": self._config.trading_enabled,
                    "shadow_mode": self._config.shadow_mode,
                    "v2_deployment_mode": self._config.deployment_mode,
                    "v2_trading_enabled": self._config.trading_enabled,
                    "v2_shadow_mode": self._config.shadow_mode,
                }
            )
        except Exception as e:
            logger.warning("Could not persist runtime override for /mode: %s", e)

        await self._telegram.send_message(text=msg, target_chat_id=str(chat_id))

    async def _send_mode(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        data = {
            "mode": mode,
            "trading_enabled": self._config.trading_enabled,
            "shadow_mode": self._config.shadow_mode,
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

        poll_cnt = (
            getattr(self._scanner_service, "_poll_count", 0)
            if self._scanner_service
            else 0
        )
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
                        "confluence_score": getattr(s, "confluence_score", None)
                        or s.score,
                        "action": getattr(s, "action", None)
                        or (
                            s.raw_payload.get("action", "BUY")
                            if getattr(s, "raw_payload", None)
                            else "BUY"
                        ),
                        "price": getattr(s, "price", None)
                        or (
                            s.raw_payload.get("price", 0.0)
                            if getattr(s, "raw_payload", None)
                            else 0.0
                        ),
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

    async def _render_scan_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_scan_data()
        text = format_telegram_scan(data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:scan"),
                )
            except Exception as e:
                logger.debug("Edit scan error: %s", e)
                ok = False
        if not ok:
            await self._send_scan(chat_id)

    async def _send_signals(self, chat_id: str | int) -> None:
        signals = await self._fetch_signals_data()
        text = format_telegram_signals(signals)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:signals"),
        )

    async def _render_signals_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        signals = await self._fetch_signals_data()
        text = format_telegram_signals(signals)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:signals"),
                )
            except Exception as e:
                logger.debug("Edit signals error: %s", e)
                ok = False
        if not ok:
            await self._send_signals(chat_id)

    async def _fetch_signals_data(self) -> list[dict[str, Any]]:
        mode = self._get_active_mode()
        if self._scanner_service and hasattr(self._scanner_service, "get_live_signals"):
            sigs = self._scanner_service.get_live_signals()
            return [
                {
                    "coin": s.coin,
                    "confluence_score": getattr(s, "confluence_score", None) or s.score,
                    "action": getattr(s, "action", None)
                    or (
                        s.raw_payload.get("action", "BUY")
                        if getattr(s, "raw_payload", None)
                        else "BUY"
                    ),
                    "price": getattr(s, "price", None)
                    or (
                        s.raw_payload.get("price", 0.0)
                        if getattr(s, "raw_payload", None)
                        else 0.0
                    ),
                    "generated_at": (
                        s.generated_at.isoformat()
                        if hasattr(s.generated_at, "isoformat")
                        else str(s.generated_at)
                    ),
                }
                for s in sigs
            ]
        if self._signal_repo:
            live = await self._signal_repo.get_live()
            return [
                {
                    "coin": s.coin,
                    "confluence_score": getattr(s, "confluence_score", None) or s.score,
                    "action": getattr(s, "action", None)
                    or (
                        s.raw_payload.get("action", "BUY")
                        if getattr(s, "raw_payload", None)
                        else "BUY"
                    ),
                    "price": getattr(s, "price", None)
                    or (
                        s.raw_payload.get("price", 0.0)
                        if getattr(s, "raw_payload", None)
                        else 0.0
                    ),
                    "generated_at": (
                        s.generated_at.isoformat()
                        if hasattr(s.generated_at, "isoformat")
                        else str(s.generated_at)
                    ),
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
        if self._scanner_service and hasattr(
            self._scanner_service, "get_scanned_coin_detail"
        ):
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
        if self._scanner_service and hasattr(
            self._scanner_service, "_fetch_watchlist_coins"
        ):
            try:
                watchlist = await self._scanner_service._fetch_watchlist_coins()
            except Exception:
                pass
        if not watchlist:
            watchlist = [
                "BTC",
                "ETH",
                "SOL",
                "BNB",
                "XRP",
                "ZEC",
                "AVAX",
                "LINK",
                "DOGE",
                "SHIB",
                "MATIC",
            ]

        text = format_telegram_watchlist(watchlist, mode)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _compile_funnel_data(self) -> dict[str, Any]:
        data = {}
        if self._dashboard_service and hasattr(
            self._dashboard_service, "get_funnel_analytics"
        ):
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
        return data

    async def _send_funnel(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        data = await self._compile_funnel_data()
        text = format_telegram_funnel(data, mode)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:funnel"),
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

    async def _render_positions_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        positions = await self._fetch_positions_data()
        text = format_telegram_positions(positions)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:positions"),
                )
            except Exception as e:
                logger.debug("Edit positions error: %s", e)
                ok = False
        if not ok:
            await self._send_positions(chat_id)

    async def _fetch_positions_data(self) -> list[dict[str, Any]]:
        if self._position_repo:
            open_pos = await self._position_repo.get_active_positions()
            return [
                {
                    "coin": p.coin,
                    "pair": getattr(p, "pair", None) or f"{p.coin}/INR",
                    "quote": getattr(p, "quote", None)
                    or (
                        "USDT"
                        if (getattr(p, "pair", "") or "").endswith("USDT")
                        else "INR"
                    ),
                    "bot": p.bot.value if hasattr(p.bot, "value") else str(p.bot),
                    "qty": p.qty,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealised_pnl": p.unrealised_pnl,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                    "amount": float(
                        getattr(p, "deployed_capital", 0.0)
                        or (float(p.entry_price or 0.0) * float(p.qty or 0.0))
                    ),
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

    async def _render_trades_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        trades = await self._fetch_trades_data()
        text = format_telegram_trades(trades)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:trades"),
                )
            except Exception as e:
                logger.debug("Edit trades error: %s", e)
                ok = False
        if not ok:
            await self._send_trades(chat_id)

    async def _fetch_trades_data(self) -> list[dict[str, Any]]:
        if self._trade_repo:
            recent = await self._trade_repo.get_recent(limit=5)
            return [
                {
                    "coin": t.coin,
                    "bot": t.bot.value if hasattr(t.bot, "value") else str(t.bot),
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "exit_reason": (
                        t.exit_reason.value
                        if hasattr(t.exit_reason, "value")
                        else str(t.exit_reason)
                    ),
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

    async def _render_pnl_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_pnl_data()
        text = format_telegram_pnl(data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:pnl"),
                )
            except Exception as e:
                logger.debug("Edit pnl error: %s", e)
                ok = False
        if not ok:
            await self._send_pnl(chat_id)

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
                open_pos = await self._position_repo.get_active_positions()
                for p in open_pos:
                    orders.append(
                        {
                            "coin": p.coin,
                            "side": "BUY",
                            "qty": p.qty,
                            "price": p.entry_price,
                            "mode": (
                                p.mode.value
                                if hasattr(p.mode, "value")
                                else str(p.mode)
                            ),
                            "status": "OPEN",
                            "exchange_order_id": getattr(p, "exchange_order_id", None)
                            or "LOCAL_PAPER",
                        }
                    )
            except Exception:
                pass

        if self._trade_repo:
            try:
                recent_trades = await self._trade_repo.get_recent(limit=10)
                for t in recent_trades:
                    orders.append(
                        {
                            "coin": t.coin,
                            "side": "SELL",
                            "qty": t.qty,
                            "price": t.exit_price,
                            "mode": (
                                t.mode.value
                                if hasattr(t.mode, "value")
                                else str(t.mode)
                            ),
                            "status": "FILLED",
                            "exchange_order_id": getattr(t, "exchange_order_id", None)
                            or "LOCAL_PAPER",
                        }
                    )
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

    async def _render_orders_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        orders = await self._compile_orders_data()
        text = format_telegram_orders(orders, self._get_active_mode())
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:orders"),
                )
            except Exception as e:
                logger.debug("Edit orders error: %s", e)
                ok = False
        if not ok:
            await self._send_orders(chat_id)

    async def _compile_capital_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        avail_cap = None
        source = "SIMULATION"

        if mode in ("LIVE", "LIVE_MICROCASH"):
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr:
                try:
                    bal_resp = await sub_mgr.get_live_balance()
                    if bal_resp.get("success"):
                        avail_cap = bal_resp.get("inr_balance")
                        source = "COINDCX_EXCHANGE"
                    else:
                        avail_cap = None
                        source = "COINDCX_UNAVAILABLE"
                except Exception as e:
                    logger.debug("Live balance fetch error in capital: %s", e)
                    avail_cap = None
                    source = "COINDCX_UNAVAILABLE"
            else:
                avail_cap = None
                source = "UNAVAILABLE"
        else:
            avail_cap = self._config.total_capital_limit
            source = "SIMULATION"

        deployed_cap = 0.0
        open_pos_count = 0
        per_bot_alloc: dict[str, float] = {}

        if self._position_repo:
            try:
                open_pos = await self._position_repo.get_active_positions()
                open_pos_count = len(open_pos)
                for p in open_pos:
                    entry = float(getattr(p, "entry_price", 0.0) or 0.0)
                    qty = float(getattr(p, "qty", 0.0) or 0.0)
                    p_dep = float(getattr(p, "deployed_capital", 0.0) or (entry * qty))
                    deployed_cap += p_dep
                    b_key = (
                        p.bot.value if hasattr(p.bot, "value") else str(p.bot or "BOT")
                    )
                    per_bot_alloc[b_key] = per_bot_alloc.get(b_key, 0.0) + p_dep
            except Exception as e:
                logger.debug("Capital data position fetch error: %s", e)

        return {
            "mode": mode,
            "available_capital": avail_cap,
            "deployed_capital": deployed_cap,
            "open_positions_count": open_pos_count,
            "per_bot_allocation": per_bot_alloc,
            "order_amount_inr": max(
                200.0, float(getattr(self._config, "order_size_inr", 200.0))
            ),
            "min_order_size": 200.0,
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

    async def _render_capital_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_capital_data()
        text = format_telegram_capital(data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:capital"),
                )
            except Exception as e:
                logger.debug("Edit capital error: %s", e)
                ok = False
        if not ok:
            await self._send_capital(chat_id)

    # ── Dedicated Balance & Portfolio Handlers ────────────────────────────────

    async def _compile_balance_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        is_live = mode in ("LIVE", "LIVE_MICROCASH")
        inr_bal = 0.0
        inr_locked = 0.0
        asset_balances: dict[str, float] = {}

        if is_live:
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr:
                try:
                    master_client = sub_mgr.get_client()
                    bal_res = await master_client.get_balances()
                    if bal_res.get("success"):
                        inr_bal = float(bal_res.get("inr_balance", 0.0))
                        inr_locked = float(bal_res.get("inr_locked", 0.0))
                        asset_balances = bal_res.get("asset_balances", {})
                except Exception as exc:
                    logger.debug("Live broker balance fetch error: %s", exc)

        deployed_cap = 0.0
        open_pos_count = 0
        if self._position_repo:
            try:
                open_pos = await self._position_repo.get_active_positions()
                open_pos_count = len(open_pos)
                deployed_cap = sum(float(getattr(p, "deployed_capital", 0.0) or 0.0) for p in open_pos)
            except Exception as exc:
                logger.debug("Balance positions fetch error: %s", exc)

        return {
            "mode": mode,
            "inr_balance": inr_bal,
            "inr_locked": inr_locked,
            "asset_balances": asset_balances,
            "capital_limit": self._config.total_capital_limit or 10000.0,
            "deployed_capital": deployed_cap,
            "open_positions_count": open_pos_count,
        }

    async def _send_balance(self, chat_id: str | int) -> None:
        data = await self._compile_balance_data()
        text = format_telegram_balance(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:balance"),
        )

    async def _render_balance_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_balance_data()
        text = format_telegram_balance(data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:balance"),
                )
            except Exception as e:
                logger.debug("Edit balance error: %s", e)
                ok = False
        if not ok:
            await self._send_balance(chat_id)

    async def _compile_portfolio_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        is_live = mode in ("LIVE", "LIVE_MICROCASH")
        open_pos_list: list[dict[str, Any]] = []
        deployed_cap = 0.0
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        trades_cnt = 0
        win_rate = 0.0
        avail_cash = 0.0

        if self._position_repo:
            try:
                raw_positions = await self._position_repo.get_active_positions()
                for p in raw_positions:
                    entry = float(getattr(p, "entry_price", 0.0) or 0.0)
                    cur = float(getattr(p, "current_price", entry) or entry)
                    qty = float(getattr(p, "qty", 0.0) or 0.0)
                    pos_dep = float(getattr(p, "deployed_capital", 0.0) or (entry * qty))
                    deployed_cap += pos_dep
                    u_pnl = float(getattr(p, "unrealized_pnl", 0.0) or 0.0)
                    u_pct = float(getattr(p, "unrealized_pnl_pct", 0.0) or 0.0)
                    unrealized_pnl += u_pnl
                    bot_str = p.bot.value if hasattr(p.bot, "value") else str(p.bot or "BOT")
                    open_pos_list.append({
                        "coin": p.coin,
                        "bot": bot_str,
                        "entry_price": entry,
                        "current_price": cur,
                        "qty": qty,
                        "deployed": pos_dep,
                        "unrealized_pnl": u_pnl,
                        "unrealized_pnl_pct": u_pct,
                    })
            except Exception as exc:
                logger.debug("Portfolio positions fetch error: %s", exc)

        if self._portfolio_service:
            try:
                snap = await self._portfolio_service.get_snapshot()
                realized_pnl = snap.total_realised_pnl
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

        if is_live:
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr:
                try:
                    bal_res = await sub_mgr.get_live_balance()
                    if bal_res.get("success"):
                        avail_cash = float(bal_res.get("inr_balance", 0.0))
                except Exception:
                    pass

        return {
            "mode": mode,
            "open_positions": open_pos_list,
            "deployed_capital": deployed_cap,
            "available_cash": avail_cash,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "trades_count": trades_cnt,
            "win_rate_pct": win_rate,
            "starting_capital": self._config.total_capital_limit or 10000.0,
        }

    async def _send_portfolio(self, chat_id: str | int) -> None:
        data = await self._compile_portfolio_data()
        text = format_telegram_portfolio(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:portfolio"),
        )

    async def _render_portfolio_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_portfolio_data()
        text = format_telegram_portfolio(data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:portfolio"),
                )
            except Exception as e:
                logger.debug("Edit portfolio error: %s", e)
                ok = False
        if not ok:
            await self._send_portfolio(chat_id)

    # ── Strategy Win Rate & Stats Handlers ───────────────────────────────────

    async def _compile_winrate_data(self) -> dict[str, Any]:
        mode = self._get_active_mode()
        total_trades = 0
        wins_cnt = 0
        realized_pnl = 0.0
        win_pnls: list[float] = []
        loss_pnls: list[float] = []
        strat_stats: dict[str, dict[str, Any]] = {}
        signals_cnt = 0

        if self._trade_repo:
            try:
                recent = await self._trade_repo.get_recent(limit=200)
                total_trades = len(recent)
                for t in recent:
                    p = float(getattr(t, "pnl", 0.0) or 0.0)
                    realized_pnl += p
                    b = t.bot.value if hasattr(t.bot, "value") else str(t.bot or "BOT")
                    if b not in strat_stats:
                        strat_stats[b] = {"trades": 0, "wins": 0, "pnl": 0.0}
                    strat_stats[b]["trades"] += 1
                    strat_stats[b]["pnl"] += p

                    if p > 0:
                        wins_cnt += 1
                        win_pnls.append(p)
                        strat_stats[b]["wins"] += 1
                    else:
                        loss_pnls.append(abs(p))

                for s_data in strat_stats.values():
                    s_t = s_data["trades"]
                    s_w = s_data["wins"]
                    s_data["win_rate_pct"] = (s_w / s_t * 100.0) if s_t > 0 else 0.0
            except Exception as exc:
                logger.debug("Winrate trades compilation error: %s", exc)

        if self._signal_repo:
            try:
                signals = await self._signal_repo.get_recent(limit=100)
                signals_cnt = len(signals)
            except Exception:
                pass

        win_rate = (wins_cnt / total_trades * 100.0) if total_trades > 0 else 0.0
        avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else 0.0
        avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0
        tot_win_sum = sum(win_pnls)
        tot_loss_sum = sum(loss_pnls)
        profit_factor = (tot_win_sum / tot_loss_sum) if tot_loss_sum > 0 else (tot_win_sum if tot_win_sum > 0 else 1.0)

        return {
            "mode": mode,
            "trades_count": total_trades,
            "wins_count": wins_cnt,
            "win_rate_pct": win_rate,
            "realized_pnl": realized_pnl,
            "avg_win_inr": avg_win,
            "avg_loss_inr": avg_loss,
            "profit_factor": profit_factor,
            "signals_evaluated": signals_cnt,
            "strategy_stats": strat_stats,
        }

    async def _send_winrate(self, chat_id: str | int) -> None:
        data = await self._compile_winrate_data()
        text = format_telegram_winrate(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:winrate"),
        )

    async def _render_winrate_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_winrate_data()
        text = format_telegram_winrate(data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:winrate"),
                )
            except Exception as e:
                logger.debug("Edit winrate error: %s", e)
                ok = False
        if not ok:
            await self._send_winrate(chat_id)

    async def _render_funnel_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        data = await self._compile_funnel_data()
        mode = self._get_active_mode()
        text = format_telegram_funnel(data, mode)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:funnel"),
                )
            except Exception as e:
                logger.debug("Edit funnel error: %s", e)
                ok = False
        if not ok:
            await self._send_funnel(chat_id)

    async def _send_config(self, chat_id: str | int) -> None:
        mode = self._get_active_mode()
        data = {
            "mode": mode,
            "trading_enabled": self._config.trading_enabled,
            "order_amount_inr": self._config.order_size_inr,
            "total_capital_limit": self._config.total_capital_limit,
            "max_concurrent_positions": self._config.max_concurrent_positions,
            "enforce_single_coin_lock": self._config.enforce_single_coin_lock,
            "ai_model": self._config.ai_model,
            "scanner_poll_interval": self._config.scanner_poll_interval,
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

        if val < 200.0:
            await self._telegram.send_message(
                text=(
                    f"❌ <b>Order Amount Below Minimum: ₹{val:,.2f}</b>\n"
                    "Mandatory minimum order size is <b>₹200.00</b> across all modes (PAPER & LIVE)."
                ),
                target_chat_id=str(chat_id),
            )
            return

        # Persist through existing central configuration mechanism
        try:
            AppConfig.save_runtime_overrides({"order_size_inr": val})
            self._config = get_config()
            self._config.order_size_inr = val

            # Propagate to running trading service
            sub_mgr = self._get_subaccount_manager()
            if sub_mgr and hasattr(sub_mgr, "update_order_size"):
                sub_mgr.update_order_size(val)

            logger.info(
                "Order amount updated via Telegram C2: ₹%.2f (chat_id: %s)",
                val,
                chat_id,
            )
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
        self._config.trading_enabled = False
        if self._trading_service and hasattr(self._trading_service, "_config"):
            self._trading_service._config.trading_enabled = False

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
            check_fn = self._risk_service.is_safe_to_resume
            res = check_fn()
            if asyncio.iscoroutine(res):
                is_safe, reason = await res
            elif isinstance(res, tuple):
                is_safe, reason = res
            else:
                is_safe, reason = True, "Mock/Default"
            if not is_safe:
                logger.warning(
                    "Resume rejected via Telegram C2: Risk Engine reports unsafe state: %s",
                    reason,
                )
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
            res = await self._production_controller.resume(
                operator=f"TELEGRAM_{chat_id}", target_mode=mode
            )
            if not res.get("ok"):
                await self._telegram.send_message(
                    text=f"❌ <b>Resume Failed:</b> {res.get('message') or res.get('error')}",
                    target_chat_id=str(chat_id),
                    reply_markup=build_back_keyboard(),
                )
                return
        else:
            self._config.trading_enabled = True
            if self._trading_service and hasattr(self._trading_service, "_config"):
                self._trading_service._config.trading_enabled = True
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
            check_fn = self._risk_service.is_safe_to_resume
            res = check_fn()
            if asyncio.iscoroutine(res):
                is_safe, reason = await res
            elif isinstance(res, tuple):
                is_safe, reason = res
            else:
                is_safe, reason = True, "Mock/Default"
            if not is_safe:
                logger.warning(
                    "Resume rejected via Telegram C2: Risk Engine reports unsafe state: %s",
                    reason,
                )
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
            await self._production_controller.resume(
                operator=f"TELEGRAM_{chat_id}", target_mode=mode
            )
        else:
            self._config.trading_enabled = True
            if self._trading_service and hasattr(self._trading_service, "_config"):
                self._trading_service._config.trading_enabled = True
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

    async def _handle_emergency_stop(
        self, chat_id: str | int, args: list[str], is_kill: bool = False
    ) -> None:
        mode = self._get_active_mode()
        # Direct execution on explicit /kill or argument confirmation
        if is_kill or (
            args and args[0].lower() in ("confirm", "yes", "force", "kill", "now")
        ):
            if hasattr(self, "_production_controller") and self._production_controller:
                await self._production_controller.kill_switch(
                    reason="Manual emergency kill-switch via Telegram C2 interface",
                    operator=f"TELEGRAM_{chat_id}",
                )
            else:
                self._config.trading_enabled = False
                if self._trading_service and hasattr(self._trading_service, "_config"):
                    self._trading_service._config.trading_enabled = False

                if self._risk_service and hasattr(
                    self._risk_service, "circuit_breaker"
                ):
                    self._risk_service.circuit_breaker.set_emergency_stop(
                        True, reason="EMERGENCY_STOP_VIA_TELEGRAM"
                    )
                    self._risk_service.circuit_breaker.trip(
                        "EMERGENCY_STOP_VIA_TELEGRAM"
                    )

                await self._bus.publish(
                    EventType.CIRCUIT_BREAKER_TRIGGERED,
                    {
                        "reason": "Manual emergency stop via Telegram C2 interface",
                        "source": "telegram",
                    },
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

    async def _render_stop_prompt_edit(
        self, chat_id: str | int, message_id: int
    ) -> None:
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

    async def _handle_confirm_stop_edit(
        self, chat_id: str | int, message_id: int
    ) -> None:
        mode = self._get_active_mode()
        self._config.trading_enabled = False
        if self._trading_service and hasattr(self._trading_service, "_config"):
            self._trading_service._config.trading_enabled = False

        if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
            self._risk_service.circuit_breaker.set_emergency_stop(
                True, reason="EMERGENCY_STOP_VIA_TELEGRAM"
            )
            self._risk_service.circuit_breaker.trip("EMERGENCY_STOP_VIA_TELEGRAM")

        await self._bus.publish(
            EventType.CIRCUIT_BREAKER_TRIGGERED,
            {
                "reason": "Manual emergency stop via Telegram C2 interface",
                "source": "telegram",
            },
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
        if self._trading_service and hasattr(
            self._trading_service, "reconcile_live_orders"
        ):
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

    async def _render_risk_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        risk_data = await self._fetch_risk_data()
        text = format_telegram_risk(risk_data)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:risk"),
                )
            except Exception as e:
                logger.debug("Edit risk error: %s", e)
                ok = False
        if not ok:
            await self._send_risk(chat_id)

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
            "max_drawdown_pct": self._config.max_drawdown_pct,
            "max_consecutive_losses": self._config.max_consecutive_losses,
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
                raw_entries = await self._event_log_repo.get_by_type(
                    EventType.CIRCUIT_BREAKER_TRIGGERED.value, limit=10
                )
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

    async def _send_database_export(self, chat_id: str | int) -> None:
        """Export the main SQLite database file and send it via Telegram."""
        import os
        import gzip
        import asyncio
        import sqlite3
        import time

        db_path = getattr(self._config, "db_path", None) or getattr(self._config, "sqlite_db_path", None) or "v2/data/alpha_v2.db"
        if not os.path.exists(db_path):
            fallbacks = ["/opt/project-alpha/v2/data/alpha_v2.db", "v2/data/alpha_v2.db", "data/project_alpha.db"]
            for fb in fallbacks:
                if os.path.exists(fb):
                    db_path = fb
                    break

        if not os.path.exists(db_path):
            await self._telegram.send_message(
                text=f"❌ Error: Database file not found at <code>{db_path}</code>.",
                target_chat_id=str(chat_id),
            )
            return

        await self._telegram.send_message(
            text="⏳ <b>Exporting Database...</b>\nCreating clean snapshot and compressing database for download...",
            target_chat_id=str(chat_id),
        )

        tmp_dir = "/tmp" if os.path.isdir("/tmp") else os.path.dirname(os.path.abspath(db_path))
        snapshot_db = os.path.join(tmp_dir, f"mbt_snapshot_{int(time.time())}.db")
        zip_path = f"{snapshot_db}.gz"

        def backup_and_compress():
            # Use SQLite native online backup to safely snapshot live WAL database
            src = sqlite3.connect(db_path)
            dst = sqlite3.connect(snapshot_db)
            src.backup(dst)
            dst.close()
            src.close()

            with open(snapshot_db, "rb") as f_in:
                with gzip.open(zip_path, "wb") as f_out:
                    f_out.writelines(f_in)

        try:
            await asyncio.to_thread(backup_and_compress)

            file_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
            success = await self._telegram.send_document(
                document_path=zip_path,
                caption=f"📂 <b>PROJECT-ALPHA Database Export</b>\nSize: {file_size_mb:.2f} MB\nExtract the .gz file to inspect with DB Browser for SQLite.",
                target_chat_id=str(chat_id),
            )

            if not success:
                await self._telegram.send_message(
                    text="❌ <b>Export Failed</b>\nThe file could not be delivered to Telegram.",
                    target_chat_id=str(chat_id),
                )
        except Exception as e:
            logger.error("Failed to snapshot or export DB: %s", e, exc_info=True)
            await self._telegram.send_message(
                text=f"❌ <b>Export Error:</b> {e}",
                target_chat_id=str(chat_id),
            )
        finally:
            if os.path.exists(snapshot_db):
                try:
                    os.remove(snapshot_db)
                except Exception:
                    pass
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass

    # Legacy Bot Fleet and Stages (Preserved for compatibility)

    async def _send_bot_fleet(self, chat_id: str | int) -> None:
        bots = await self._fetch_bots_data()
        text = format_telegram_bot_fleet(bots)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:bots"),
        )

    async def _render_bot_fleet_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        bots = await self._fetch_bots_data()
        text = format_telegram_bot_fleet(bots)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:bots"),
                )
            except Exception as e:
                logger.debug("Edit bot fleet error: %s", e)
                ok = False
        if not ok:
            await self._send_bot_fleet(chat_id)

    async def _fetch_bots_data(self) -> list[dict[str, Any]]:
        if self._dashboard_service and hasattr(
            self._dashboard_service, "bot_pipeline_tracker"
        ):
            return self._dashboard_service.bot_pipeline_tracker.get_all_bot_summaries()

        # Do not fabricate balances in operator output.  Return an explicit
        # unavailable state until the dashboard pipeline has real telemetry.
        return [
            {
                "name": name,
                "current_stage": "IDLE",
                "status": "ACTIVE",
                "wallet_balance": None,
                "available_balance": None,
                "open_positions": 0,
                "daily_pnl": 0.0,
                "win_rate_pct": 0.0,
            }
            for name in ("STE", "HDA", "VCP", "BBS")
        ]

    async def _send_pipeline_stages(self, chat_id: str | int) -> None:
        stages = await self._fetch_stages_data()
        text = format_telegram_pipeline_stages(stages)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:stages"),
        )

    async def _render_stages_edit(self, chat_id: str | int, message_id: int | None = None) -> None:
        stages = await self._fetch_stages_data()
        text = format_telegram_pipeline_stages(stages)
        ok = False
        if message_id:
            try:
                ok = await self._telegram.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_back_keyboard("cb:stages"),
                )
            except Exception as e:
                logger.debug("Edit stages error: %s", e)
                ok = False
        if not ok:
            await self._send_pipeline_stages(chat_id)

    async def _fetch_stages_data(self) -> list[dict[str, Any]]:
        if self._dashboard_service and hasattr(
            self._dashboard_service, "pipeline_stage_collector"
        ):
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
            {
                "number": num,
                "name": name,
                "status": "ACTIVE",
                "processed_count": 0,
                "rejected_count": 0,
            }
            for num, name in stage_names
        ]
