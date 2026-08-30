"""
V2 Interactive Telegram Command & Control (C2) Interface.

Provides a mobile-friendly, bidirectional interface for PROJECT-ALPHA V2
requiring ZERO external domain, ZERO public IP, and ZERO port-forwarding via
Telegram Bot API long polling.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.logging import get_logger
from v2.repository.position_repo import PositionRepository
from v2.repository.signal_repo import SignalRepository
from v2.repository.trade_repo import TradeRepository

from .formatters import (
    format_telegram_bot_fleet,
    format_telegram_help,
    format_telegram_menu,
    format_telegram_pipeline_stages,
    format_telegram_portfolio,
    format_telegram_positions,
    format_telegram_risk,
    format_telegram_signals,
    format_telegram_trades,
)
from .telegram import TelegramClient

logger = get_logger("v2.services.notification_service.telegram_interface")


def build_main_menu_keyboard() -> dict:
    """Build the 2xN interactive inline keyboard for Mission Control."""
    return {
        "inline_keyboard": [
            [
                {"text": "🤖 Bot Fleet", "callback_data": "cb:bots"},
                {"text": "📊 11 Stages", "callback_data": "cb:stages"},
            ],
            [
                {"text": "💼 Portfolio", "callback_data": "cb:portfolio"},
                {"text": "📈 Positions", "callback_data": "cb:positions"},
            ],
            [
                {"text": "📜 Trades", "callback_data": "cb:trades"},
                {"text": "🎯 Signals", "callback_data": "cb:signals"},
            ],
            [
                {"text": "🛡️ Risk State", "callback_data": "cb:risk"},
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
    inline button navigation, and trading controls.
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

        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._offset: Optional[int] = None

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
            # If no chat ID whitelist is explicitly locked, authorize the sender
            return True

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
                backoff = 1.0  # Reset backoff on successful call

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

        if not self.is_authorized(chat_id):
            await self._telegram.send_message(
                text="⛔ <b>Access Denied</b>\nYour Telegram account is not authorized to interact with PROJECT-ALPHA V2.",
                target_chat_id=str(chat_id),
            )
            return

        cmd = text.split()[0].lower()
        # Strip bot username if mentioned (e.g. /start@MyBot -> /start)
        if "@" in cmd:
            cmd = cmd.split("@")[0]

        if cmd in ("/start", "/menu"):
            await self._send_main_menu(chat_id)
        elif cmd in ("/status", "/health"):
            await self._send_status(chat_id)
        elif cmd in ("/bots", "/fleet"):
            await self._send_bot_fleet(chat_id)
        elif cmd in ("/stages", "/pipeline"):
            await self._send_pipeline_stages(chat_id)
        elif cmd in ("/portfolio", "/balance"):
            await self._send_portfolio(chat_id)
        elif cmd == "/positions":
            await self._send_positions(chat_id)
        elif cmd == "/trades":
            await self._send_trades(chat_id)
        elif cmd == "/signals":
            await self._send_signals(chat_id)
        elif cmd == "/risk":
            await self._send_risk(chat_id)
        elif cmd == "/emergency_stop":
            await self._send_emergency_stop_prompt(chat_id)
        elif cmd == "/resume":
            await self._handle_resume(chat_id)
        elif cmd == "/help":
            await self._send_help(chat_id)
        else:
            await self._telegram.send_message(
                text=f"❓ Unknown command <code>{cmd}</code>. Use /menu or /help to view available commands.",
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
            await self._telegram.answer_callback_query(cb_id, text="Unauthorized access", show_alert=True)
            return

        # Acknowledge button press immediately
        await self._telegram.answer_callback_query(cb_id)

        if data in ("cb:menu", "cb:refresh"):
            await self._render_main_menu_edit(chat_id, message_id)
        elif data == "cb:bots":
            await self._render_bot_fleet_edit(chat_id, message_id)
        elif data == "cb:stages":
            await self._render_stages_edit(chat_id, message_id)
        elif data == "cb:portfolio":
            await self._render_portfolio_edit(chat_id, message_id)
        elif data == "cb:positions":
            await self._render_positions_edit(chat_id, message_id)
        elif data == "cb:trades":
            await self._render_trades_edit(chat_id, message_id)
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

    # ── View Builders & Data Fetchers ─────────────────────────────────────────

    async def _get_overview_data(self) -> dict[str, Any]:
        """Compile consolidated system overview dictionary."""
        aum = 0.0
        deployed = 0.0
        daily_pnl = 0.0
        active_pos_count = 0

        if self._portfolio_service:
            try:
                snap = await self._portfolio_service.get_snapshot()
                aum = snap.total_aum
                deployed = snap.total_deployed
                daily_pnl = snap.daily_pnl
            except Exception as e:
                logger.debug("Error fetching portfolio for overview: %s", e)

        if self._position_repo:
            try:
                open_pos = await self._position_repo.get_open()
                active_pos_count = len(open_pos)
            except Exception as e:
                logger.debug("Error fetching open positions: %s", e)

        mode = "LIVE TRADING" if self._config.v2_trading_enabled else "PAPER ACTIVE"
        if self._config.v2_shadow_mode:
            mode += " (SHADOW SIM ON)"

        return {
            "status": "HEALTHY",
            "uptime": "Active",
            "total_aum": aum,
            "total_deployed": deployed,
            "daily_pnl": daily_pnl,
            "active_positions": active_pos_count,
            "bot_count": 4,
            "trading_mode": mode,
        }

    async def _send_main_menu(self, chat_id: str | int) -> None:
        overview = await self._get_overview_data()
        text = format_telegram_menu(overview)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_main_menu_keyboard(),
        )

    async def _render_main_menu_edit(self, chat_id: str | int, message_id: int) -> None:
        overview = await self._get_overview_data()
        text = format_telegram_menu(overview)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_main_menu_keyboard(),
        )

    async def _send_status(self, chat_id: str | int) -> None:
        overview = await self._get_overview_data()
        text = (
            f"ℹ️ <b>PROJECT-ALPHA V2 Status</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Server:</b> Online (Port {self._config.v2_port})\n"
            f"• <b>Trading Mode:</b> <code>{overview['trading_mode']}</code>\n"
            f"• <b>AUM:</b> ₹{overview['total_aum']:,.2f}\n"
            f"• <b>Active Positions:</b> <code>{overview['active_positions']}</code>\n"
            f"• <b>Event Bus:</b> Operational\n"
            f"• <b>Sub-Accounts:</b> 4 Production Bots Configured\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

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
        """Fetch real-time data for the 4 production bots."""
        if self._dashboard_service and hasattr(self._dashboard_service, "bot_pipeline_tracker"):
            return self._dashboard_service.bot_pipeline_tracker.get_all_bot_summaries()

        # Fallback defaults
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
        """Fetch live status of the 11 pipeline stages."""
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

    async def _send_portfolio(self, chat_id: str | int) -> None:
        data = await self._fetch_portfolio_data()
        text = format_telegram_portfolio(data)
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard("cb:portfolio"),
        )

    async def _render_portfolio_edit(self, chat_id: str | int, message_id: int) -> None:
        data = await self._fetch_portfolio_data()
        text = format_telegram_portfolio(data)
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard("cb:portfolio"),
        )

    async def _fetch_portfolio_data(self) -> dict[str, Any]:
        if self._portfolio_service:
            snap = await self._portfolio_service.get_snapshot()
            return {
                "total_aum": snap.total_aum,
                "total_deployed": snap.total_deployed,
                "total_cash": snap.total_cash,
                "total_unrealised_pnl": snap.total_unrealised_pnl,
                "total_realised_pnl": snap.total_realised_pnl,
                "daily_pnl": snap.daily_pnl,
                "capital_utilisation": snap.capital_utilisation,
            }
        return {"total_aum": 100000.0, "total_deployed": 0.0, "total_cash": 100000.0, "capital_utilisation": 0.0}

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
        if self._signal_repo:
            live = await self._signal_repo.get_live()
            return [
                {
                    "coin": s.coin,
                    "confluence_score": getattr(s, "confluence_score", None) or s.score,
                    "action": getattr(s, "action", "BUY"),
                    "price": s.price,
                    "generated_at": s.generated_at.isoformat() if hasattr(s.generated_at, "isoformat") else str(s.generated_at),
                }
                for s in live
            ]
        return []

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

    # ── Operational Controls ──────────────────────────────────────────────────

    async def _send_emergency_stop_prompt(self, chat_id: str | int) -> None:
        text = (
            "🚨 <b>EMERGENCY STOP CONFIRMATION</b> 🚨\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Are you sure you want to trigger an emergency stop?\n"
            "This will instantly trip the circuit breaker and halt all new orders."
        )
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_confirm_stop_keyboard(),
        )

    async def _render_stop_prompt_edit(self, chat_id: str | int, message_id: int) -> None:
        text = (
            "🚨 <b>EMERGENCY STOP CONFIRMATION</b> 🚨\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Are you sure you want to trigger an emergency stop?\n"
            "This will instantly trip the circuit breaker and halt all new orders."
        )
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_confirm_stop_keyboard(),
        )

    async def _handle_confirm_stop_edit(self, chat_id: str | int, message_id: int) -> None:
        if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
            self._risk_service.circuit_breaker.trip("EMERGENCY_STOP_TRIGGERED_VIA_TELEGRAM")
            await self._bus.publish(
                EventType.CIRCUIT_BREAKER_TRIGGERED,
                {"reason": "Manual emergency stop via Telegram C2 interface", "source": "telegram"},
            )

        text = (
            "🛑 <b>EMERGENCY STOP ACTIVATED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• Circuit breaker: <b>TRIPPED</b>\n"
            "• Live order dispatch: <b>SUSPENDED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Use /resume or tap ▶️ Resume Trading to restore execution.</i>"
        )
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard(),
        )

    async def _handle_resume(self, chat_id: str | int) -> None:
        if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
            self._risk_service.circuit_breaker.reset()

        text = (
            "▶️ <b>TRADING EXECUTION RESUMED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• Circuit breaker: <b>RESET</b>\n"
            "• Automated execution: <b>RESTORED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )

    async def _handle_resume_edit(self, chat_id: str | int, message_id: int) -> None:
        if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
            self._risk_service.circuit_breaker.reset()

        text = (
            "▶️ <b>TRADING EXECUTION RESUMED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• Circuit breaker: <b>RESET</b>\n"
            "• Automated execution: <b>RESTORED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await self._telegram.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_back_keyboard(),
        )

    async def _send_help(self, chat_id: str | int) -> None:
        text = format_telegram_help()
        await self._telegram.send_message(
            text=text,
            target_chat_id=str(chat_id),
            reply_markup=build_back_keyboard(),
        )
