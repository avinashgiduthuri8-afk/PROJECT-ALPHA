"""
V2 CandleRepository — persistence for historical market candles.
"""

from __future__ import annotations

import aiosqlite
from typing import Any, Optional

from v2.core.exceptions import StorageError
from v2.core.logging import get_logger
from .base import BaseRepository

logger = get_logger("v2.repository.candle_repo")


class CandleRepository(BaseRepository):
    """Manages SQLite storage for historical market candles."""

    async def get_recent_candles(self, pair: str, timeframe: str, limit: int = 120) -> list[dict[str, Any]]:
        """
        Get the most recent candles for a pair and timeframe.
        Returns a list of dicts ordered chronologically (ascending timestamp).
        """
        query = """
            SELECT pair, timeframe, timestamp, open, high, low, close, volume
            FROM market_candles
            WHERE pair = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        try:
            async with self._conn.execute(query, (pair.upper(), timeframe, limit)) as cursor:
                rows = await cursor.fetchall()
            
            # Convert sqlite rows to list of dicts, and reverse to be ascending (chronological)
            candles = []
            for r in reversed(rows):
                candles.append({
                    "pair": r["pair"],
                    "timeframe": r["timeframe"],
                    "timestamp": r["timestamp"],
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "volume": r["volume"],
                })
            return candles
        except Exception as exc:
            raise StorageError(f"Failed to fetch candles: {exc}") from exc

    async def get_candles_range(
        self,
        pair: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        """
        Get candles for a pair and timeframe within an optional timestamp range.
        Returns a list of dicts ordered chronologically (ascending timestamp).
        """
        clauses = ["pair = ?", "timeframe = ?"]
        params: list[Any] = [pair.upper(), timeframe]

        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time)

        where_clause = " AND ".join(clauses)
        query = f"""
            SELECT pair, timeframe, timestamp, open, high, low, close, volume
            FROM market_candles
            WHERE {where_clause}
            ORDER BY timestamp ASC
            LIMIT ?
        """
        params.append(limit)

        try:
            async with self._conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
            
            candles = []
            for r in rows:
                candles.append({
                    "pair": r["pair"],
                    "timeframe": r["timeframe"],
                    "timestamp": r["timestamp"],
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "volume": r["volume"],
                })
            return candles
        except Exception as exc:
            raise StorageError(f"Failed to fetch candles range: {exc}") from exc

    async def upsert_candles(self, candles_list: list[dict[str, Any]]) -> None:
        """
        Insert or replace a list of candles in the database.
        Idempotent bulk write.
        """
        if not candles_list:
            return
            
        query = """
            INSERT OR REPLACE INTO market_candles (pair, timeframe, timestamp, open, high, low, close, volume)
            VALUES (:pair, :timeframe, :timestamp, :open, :high, :low, :close, :volume)
        """
        
        # Ensure correct types and capitalization
        formatted = []
        for c in candles_list:
            formatted.append({
                "pair": str(c["pair"]).upper(),
                "timeframe": str(c["timeframe"]),
                "timestamp": int(c["timestamp"]),
                "open": float(c.get("open", c.get("o", 0.0))),
                "high": float(c.get("high", c.get("h", 0.0))),
                "low": float(c.get("low", c.get("l", 0.0))),
                "close": float(c.get("close", c.get("c", 0.0))),
                "volume": float(c.get("volume", c.get("v", 0.0))),
            })
            
        try:
            await self._conn.executemany(query, formatted)
            await self._conn.commit()
        except Exception as exc:
            raise StorageError(f"Failed to upsert candles: {exc}") from exc
