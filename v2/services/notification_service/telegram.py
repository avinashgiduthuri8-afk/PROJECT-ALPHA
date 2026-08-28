"""
V2 Async Telegram Dispatcher.

Dispatches formatted alerts to a configured Telegram chat with rate-limiting,
exponential backoff, and graceful fallback when credentials are unconfigured.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import httpx

from v2.core.logging import get_logger

logger = get_logger("v2.services.notification_service.telegram")


class TelegramClient:
    """Asynchronous Telegram Bot API messaging client."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = 8.0,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout
        self._last_send_time = 0.0
        self._min_interval = 0.05  # Min interval between dispatches to avoid Telegram flood limits

    @property
    def is_configured(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        max_retries: int = 2,
    ) -> bool:
        """Send an HTML/Markdown formatted message to the configured Telegram chat."""
        if not self.is_configured:
            logger.info("Telegram not configured; alert recorded locally", extra={"preview": text[:100]})
            return False

        # Simple rate limiter pacing
        elapsed = time.monotonic() - self._last_send_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload)
                    self._last_send_time = time.monotonic()
                    if resp.status_code == 200:
                        return True
                    logger.warning("Telegram API error response", extra={"status": resp.status_code, "body": resp.text[:200]})
            except Exception as exc:
                if attempt == max_retries:
                    logger.error("Failed to dispatch Telegram message after retries", extra={"error": str(exc)})
                    return False
                await asyncio.sleep(0.5 * (attempt + 1))

        return False
