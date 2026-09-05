"""
V2 Feedback Repository.

Asynchronous SQLite interface for persisting feedback audit trail events,
pre-deployment backtest validation outcomes, and active strategy calibrations cache.
"""

from __future__ import annotations

import sqlite3, aiosqlite
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from v2.core.logging import get_logger

logger = get_logger("v2.repository.feedback_repo")


class FeedbackRepository:
    """Repository for managing autonomous feedback audit trails and calibrations cache in SQLite."""

    def __init__(self, conn: sqlite3.Connection | aiosqlite.Connection) -> None:
        self._conn = conn

    def _is_async(self) -> bool:
        return isinstance(self._conn, aiosqlite.Connection)

    async def _execute(self, query: str, params: tuple = ()) -> Any:
        if self._is_async():
            return await self._conn.execute(query, params)
        else:
            return self._conn.execute(query, params)

    async def _fetchall(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        if self._is_async():
            async with self._conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                cols = [description[0] for description in cursor.description]
                return [dict(zip(cols, r)) for r in rows]
        else:
            cur = self._conn.execute(query, params)
            rows = cur.fetchall()
            cols = [description[0] for description in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    async def _fetchone(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        rows = await self._fetchall(query, params)
        return rows[0] if rows else None

    # ── Feedback Audit Trail ──────────────────────────────────────────────────

    async def record_audit_event(self, event: Dict[str, Any]) -> str:
        """Insert a feedback audit event into SQLite."""
        event_id = str(event.get("id") or uuid.uuid4())
        cycle_id = str(event.get("cycle_id") or uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()

        query = """
        INSERT INTO feedback_audit_trail (
            id, cycle_id, bot_name, pair, action_taken, previous_multiplier, new_multiplier,
            previous_threshold, new_threshold, validation_backtest_id, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            event_id,
            cycle_id,
            str(event["bot_name"]).upper(),
            event.get("pair"),
            str(event["action_taken"]).upper(),
            float(event.get("previous_multiplier", 1.0)),
            float(event.get("new_multiplier", 1.0)),
            float(event.get("previous_threshold", 85.0)),
            float(event.get("new_threshold", 85.0)),
            event.get("validation_backtest_id"),
            str(event.get("status", "PROMOTED")).upper(),
            str(event.get("created_at") or now_str),
        )

        await self._execute(query, params)
        if not self._is_async():
            self._conn.commit()

        logger.info(
            "Recorded feedback audit event %s [%s] for bot %s: status=%s",
            event_id, event["action_taken"], event["bot_name"], event.get("status", "PROMOTED"),
        )
        return event_id

    async def get_audit_history(
        self, bot_name: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Fetch chronological audit trail records."""
        if bot_name:
            query = "SELECT * FROM feedback_audit_trail WHERE bot_name = ? ORDER BY created_at DESC LIMIT ?"
            return await self._fetchall(query, (bot_name.upper(), limit))
        else:
            query = "SELECT * FROM feedback_audit_trail ORDER BY created_at DESC LIMIT ?"
            return await self._fetchall(query, (limit,))

    # ── Active Calibrations Cache ─────────────────────────────────────────────

    async def upsert_active_calibration(
        self, bot_name: str, weight_multiplier: float, strict_threshold: float
    ) -> None:
        """Upsert active promoted calibration configuration into cache."""
        bot_str = bot_name.upper()
        now_str = datetime.now(timezone.utc).isoformat()

        query = """
        INSERT INTO active_calibrations_cache (
            bot_name, weight_multiplier, strict_threshold, updated_at
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(bot_name) DO UPDATE SET
            weight_multiplier = excluded.weight_multiplier,
            strict_threshold = excluded.strict_threshold,
            updated_at = excluded.updated_at
        """
        params = (bot_str, float(weight_multiplier), float(strict_threshold), now_str)

        await self._execute(query, params)
        if not self._is_async():
            self._conn.commit()

        logger.info("Updated active calibration cache for bot %s -> Mult: %.2fx, Thresh: %.1f", bot_str, weight_multiplier, strict_threshold)

    async def get_active_calibration(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """Fetch cached active calibration for a bot strategy."""
        query = "SELECT * FROM active_calibrations_cache WHERE bot_name = ?"
        return await self._fetchone(query, (bot_name.upper(),))

    async def get_all_active_calibrations(self) -> List[Dict[str, Any]]:
        """Fetch all cached active calibrations."""
        query = "SELECT * FROM active_calibrations_cache ORDER BY bot_name ASC"
        return await self._fetchall(query)
