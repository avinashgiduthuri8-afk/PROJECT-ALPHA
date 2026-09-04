"""
V2 ProductionStateRepository — Persistent operational state and circuit breaker tracking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiosqlite

from v2.core.logging import get_logger
from .base import BaseRepository

logger = get_logger("v2.repository.production_state_repo")


class ProductionStateRepository(BaseRepository):
    """
    Manages persistent runtime operational state for PROJECT-ALPHA V2 in SQLite.
    Survives server restarts and crashes.
    """

    async def get(self, key: str) -> Optional[str]:
        """Fetch value for a specific runtime key."""
        async with self._conn.execute(
            "SELECT value FROM production_runtime_state WHERE key = ?",
            (key,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    async def set(self, key: str, value: Any, updated_by: str = "SYSTEM") -> None:
        """Insert or update a runtime key-value pair."""
        now_str = datetime.now(timezone.utc).isoformat()
        val_str = str(value)
        await self._conn.execute(
            """
            INSERT INTO production_runtime_state (key, value, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (key, val_str, now_str, updated_by),
        )
        await self._conn.commit()

    async def set_many(self, items: Dict[str, Any], updated_by: str = "SYSTEM") -> None:
        """Atomically insert or update multiple runtime keys."""
        now_str = datetime.now(timezone.utc).isoformat()
        params = [
            (k, str(v), now_str, updated_by)
            for k, v in items.items()
        ]
        await self._conn.executemany(
            """
            INSERT INTO production_runtime_state (key, value, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            params,
        )
        await self._conn.commit()

    async def get_all(self) -> Dict[str, str]:
        """Retrieve all persisted runtime state keys and values."""
        async with self._conn.execute(
            "SELECT key, value FROM production_runtime_state"
        ) as cur:
            rows = await cur.fetchall()
            return {row[0]: row[1] for row in rows}

    async def verify_integrity(self) -> bool:
        """Run SQLite integrity check to verify database health."""
        try:
            async with self._conn.execute("PRAGMA integrity_check") as cur:
                rows = await cur.fetchall()
                if rows and rows[0][0].lower() == "ok":
                    return True
                logger.error("Database integrity check failed: %s", rows)
                return False
        except Exception as exc:
            logger.error("Failed to run PRAGMA integrity_check: %s", exc)
            return False

