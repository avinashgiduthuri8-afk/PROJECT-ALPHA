"""
V2 NotificationService — central event listener and alert coordinator.
"""

from __future__ import annotations

from typing import Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.logging import get_logger

from .formatters import (
    format_circuit_breaker_alert,
    format_divergence_alert,
    format_generic_alert,
    format_position_closed_alert,
    format_position_opened_alert,
    format_signal_ai_alert,
    format_trade_approved_alert,
    format_trade_denied_alert,
)
from .telegram import TelegramClient
from .telegram_interface import TelegramInteractiveInterface

logger = get_logger("v2.services.notification_service")


class NotificationService:
    """Subscribes to significant trading events and routes formatted notifications."""

    def __init__(
        self,
        bus: EventBus,
        config: V2Config,
        telegram_client: Optional[TelegramClient] = None,
        signal_repo: Optional[Any] = None,
        position_repo: Optional[Any] = None,
        trade_repo: Optional[Any] = None,
        portfolio_service: Optional[Any] = None,
        risk_service: Optional[Any] = None,
        trading_service: Optional[Any] = None,
        dashboard_service: Optional[Any] = None,
        scanner_service: Optional[Any] = None,
        health_checker: Optional[Any] = None,
        event_log_repo: Optional[Any] = None,
        production_controller: Optional[Any] = None,
    ) -> None:
        self._bus = bus
        self._config = config
        self._telegram = telegram_client or TelegramClient(
            bot_token=config.alert_bot_token,
            chat_id=config.alert_chat_id,
        )
        self._interactive_interface = TelegramInteractiveInterface(
            telegram_client=self._telegram,
            bus=self._bus,
            config=self._config,
            signal_repo=signal_repo,
            position_repo=position_repo,
            trade_repo=trade_repo,
            portfolio_service=portfolio_service,
            risk_service=risk_service,
            trading_service=trading_service,
            dashboard_service=dashboard_service,
            scanner_service=scanner_service,
            health_checker=health_checker,
            event_log_repo=event_log_repo,
            production_controller=production_controller,
        )
        self._total_dispatched = 0
        self._started = False

    @property
    def telegram_client(self) -> TelegramClient:
        return self._telegram

    @property
    def interactive_interface(self) -> TelegramInteractiveInterface:
        return self._interactive_interface

    def wire_dependencies(
        self,
        signal_repo: Optional[Any] = None,
        position_repo: Optional[Any] = None,
        trade_repo: Optional[Any] = None,
        portfolio_service: Optional[Any] = None,
        risk_service: Optional[Any] = None,
        trading_service: Optional[Any] = None,
        dashboard_service: Optional[Any] = None,
        scanner_service: Optional[Any] = None,
        health_checker: Optional[Any] = None,
        event_log_repo: Optional[Any] = None,
        production_controller: Optional[Any] = None,
    ) -> None:
        """Dynamically wire late-bound subsystem references into the interactive interface."""
        if signal_repo is not None:
            self._interactive_interface._signal_repo = signal_repo
        if position_repo is not None:
            self._interactive_interface._position_repo = position_repo
        if trade_repo is not None:
            self._interactive_interface._trade_repo = trade_repo
        if portfolio_service is not None:
            self._interactive_interface._portfolio_service = portfolio_service
        if risk_service is not None:
            self._interactive_interface._risk_service = risk_service
        if trading_service is not None:
            self._interactive_interface._trading_service = trading_service
        if dashboard_service is not None:
            self._interactive_interface._dashboard_service = dashboard_service
        if scanner_service is not None:
            self._interactive_interface._scanner_service = scanner_service
        if health_checker is not None:
            self._interactive_interface._health_checker = health_checker
        if event_log_repo is not None:
            self._interactive_interface._event_log_repo = event_log_repo
        if production_controller is not None:
            self._interactive_interface._production_controller = production_controller

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._bus.subscribe(EventType.SIGNAL_AI_CONFIRMED, self._on_signal_ai_confirmed)
        self._bus.subscribe(EventType.TRADE_APPROVED, self._on_trade_approved)
        self._bus.subscribe(EventType.TRADE_DENIED, self._on_trade_denied)
        self._bus.subscribe(EventType.POSITION_OPENED, self._on_position_opened)
        self._bus.subscribe(EventType.POSITION_CLOSED, self._on_position_closed)
        self._bus.subscribe(EventType.CIRCUIT_BREAKER_TRIGGERED, self._on_circuit_breaker)
        self._bus.subscribe(EventType.DIVERGENCE_DETECTED, self._on_divergence)
        self._bus.subscribe(EventType.ALERT_GENERATED, self._on_alert_generated)
        await self._bus.publish(EventType.SYSTEM_STARTUP, {"service": "notification_service"})
        await self._interactive_interface.start()
        logger.info("NotificationService started", extra={"telegram_configured": self._telegram.is_configured})

    async def stop(self) -> None:
        self._started = False
        await self._interactive_interface.stop()
        self._bus.unsubscribe(EventType.SIGNAL_AI_CONFIRMED, self._on_signal_ai_confirmed)
        self._bus.unsubscribe(EventType.TRADE_APPROVED, self._on_trade_approved)
        self._bus.unsubscribe(EventType.TRADE_DENIED, self._on_trade_denied)
        self._bus.unsubscribe(EventType.POSITION_OPENED, self._on_position_opened)
        self._bus.unsubscribe(EventType.POSITION_CLOSED, self._on_position_closed)
        self._bus.unsubscribe(EventType.CIRCUIT_BREAKER_TRIGGERED, self._on_circuit_breaker)
        self._bus.unsubscribe(EventType.DIVERGENCE_DETECTED, self._on_divergence)
        self._bus.unsubscribe(EventType.ALERT_GENERATED, self._on_alert_generated)
        logger.info("NotificationService stopped")

    # ── Dispatch Handlers ─────────────────────────────────────────────────────

    async def send_custom_alert(self, text: str) -> bool:
        """Manually dispatch a custom alert through the pipeline."""
        sent = await self._telegram.send_message(text)
        if sent:
            self._total_dispatched += 1
        return sent

    async def _on_signal_ai_confirmed(self, event_type: EventType, payload: dict) -> None:
        try:
            msg = format_signal_ai_alert(payload)
            if await self._telegram.send_message(msg):
                self._total_dispatched += 1
        except Exception as exc:
            logger.warning("Error dispatching AI alert", extra={"error": str(exc)})

    async def _on_trade_approved(self, event_type: EventType, payload: dict) -> None:
        try:
            msg = format_trade_approved_alert(payload)
            if await self._telegram.send_message(msg):
                self._total_dispatched += 1
        except Exception as exc:
            logger.warning("Error dispatching Trade Approved alert", extra={"error": str(exc)})

    async def _on_trade_denied(self, event_type: EventType, payload: dict) -> None:
        try:
            msg = format_trade_denied_alert(payload)
            if await self._telegram.send_message(msg):
                self._total_dispatched += 1
        except Exception as exc:
            logger.warning("Error dispatching Trade Denied alert", extra={"error": str(exc)})

    async def _on_position_opened(self, event_type: EventType, payload: dict) -> None:
        try:
            msg = format_position_opened_alert(payload)
            if await self._telegram.send_message(msg):
                self._total_dispatched += 1
        except Exception as exc:
            logger.warning("Error dispatching Position Opened alert", extra={"error": str(exc)})

    async def _on_position_closed(self, event_type: EventType, payload: dict) -> None:
        try:
            msg = format_position_closed_alert(payload)
            if await self._telegram.send_message(msg):
                self._total_dispatched += 1
        except Exception as exc:
            logger.warning("Error dispatching Position Closed alert", extra={"error": str(exc)})

    async def _on_circuit_breaker(self, event_type: EventType, payload: dict) -> None:
        try:
            msg = format_circuit_breaker_alert(payload)
            if await self._telegram.send_message(msg):
                self._total_dispatched += 1
        except Exception as exc:
            logger.warning("Error dispatching Circuit Breaker alert", extra={"error": str(exc)})

    async def _on_divergence(self, event_type: EventType, payload: dict) -> None:
        try:
            msg = format_divergence_alert(payload)
            if await self._telegram.send_message(msg):
                self._total_dispatched += 1
        except Exception as exc:
            logger.warning("Error dispatching Divergence alert", extra={"error": str(exc)})

    async def _on_alert_generated(self, event_type: EventType, payload: dict) -> None:
        try:
            msg = format_generic_alert(payload)
            if await self._telegram.send_message(msg):
                self._total_dispatched += 1
        except Exception as exc:
            logger.warning("Error dispatching Generic alert", extra={"error": str(exc)})

    def get_health(self) -> dict:
        return {
            "healthy": self._started,
            "telegram_configured": self._telegram.is_configured,
            "total_dispatched": self._total_dispatched,
        }
