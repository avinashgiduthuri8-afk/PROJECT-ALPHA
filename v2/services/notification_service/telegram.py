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
    """Asynchronous Telegram Bot API messaging and polling client."""

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
        return bool(self._bot_token)

    @property
    def bot_token(self) -> Optional[str]:
        return self._bot_token

    @property
    def default_chat_id(self) -> Optional[str]:
        return self._chat_id

    async def send_message(
        self,
        text: str,
        target_chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
        max_retries: int = 2,
    ) -> bool:
        """Send an HTML/Markdown formatted message to a target or default Telegram chat."""
        cid = target_chat_id or self._chat_id
        if not self._bot_token or not cid:
            logger.info("Telegram not configured; message logged locally", extra={"preview": text[:100]})
            return False

        # Rate limiter pacing
        elapsed = time.monotonic() - self._last_send_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload: dict = {
            "chat_id": cid,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

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

    async def edit_message_text(
        self,
        text: str,
        chat_id: str | int,
        message_id: int,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
        max_retries: int = 2,
    ) -> bool:
        """Edit an existing Telegram message in-place (used for dynamic inline keyboard navigation)."""
        if not self._bot_token:
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/editMessageText"
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        return True
                    # 400 Bad Request if message text is unchanged — ignore harmless edit errors
                    if resp.status_code == 400 and "message is not modified" in resp.text.lower():
                        return True
                    logger.warning("Telegram editMessageText error", extra={"status": resp.status_code, "body": resp.text[:200]})
            except Exception as exc:
                if attempt == max_retries:
                    logger.error("Failed to edit Telegram message after retries", extra={"error": str(exc)})
                    return False
                await asyncio.sleep(0.3 * (attempt + 1))

        return False

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledge an incoming inline keyboard button tap."""
        if not self._bot_token:
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/answerCallbackQuery"
        payload: dict = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("Failed to answer callback query: %s", exc)
            return False

    async def get_updates(
        self,
        offset: Optional[int] = None,
        timeout: int = 20,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch incoming user messages and button callbacks using long-polling."""
        if not self._bot_token:
            return []

        url = f"https://api.telegram.org/bot{self._bot_token}/getUpdates"
        params: dict = {"timeout": timeout, "limit": limit}
        if offset is not None:
            params["offset"] = offset

        try:
            # Client timeout should be greater than long-poll timeout
            async with httpx.AsyncClient(timeout=timeout + 5.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        return data.get("result", [])
                logger.warning("Telegram getUpdates returned status %s: %s", resp.status_code, resp.text[:200])
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            # Normal long-polling timeout when no updates occurred
            return []
        except Exception as exc:
            logger.error("Error fetching Telegram updates: %s", exc)

        return []
