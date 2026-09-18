"""
conftest.py — PROJECT-ALPHA test bootstrap.

Sets safe defaults for every environment variable the application reads at
import time so tests never fail due to missing env vars.  Uses setdefault so
real environment values are never overwritten.
"""

from __future__ import annotations

import os

# ── Core application secrets ──────────────────────────────────────────────────
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("DASHBOARD_API_KEY", "test-api-key")

# ── Trading kill-switches (off by default in tests) ───────────────────────────
os.environ.setdefault("TRADING_ENABLED", "false")
os.environ.setdefault("EMERGENCY_STOP", "false")

# ── Bot modes (paper so risk engine is exercisable) ───────────────────────────
os.environ.setdefault("MTB_BOT_MODE", "PAPER")

# ── Capital / position limits ─────────────────────────────────────────────────
os.environ.setdefault("MTB_TRADE_AMOUNT", "200")
os.environ.setdefault("MTB_CAPITAL_LIMIT", "2000")
os.environ.setdefault("MTB_MAX_POSITIONS", "3")

# ── Shared test helpers ───────────────────────────────────────────────────────
from datetime import datetime, timedelta, timezone  # noqa: E402


def generate_synthetic_candles(count: int = 50, start_price: float = 100.0) -> list[dict]:
    """Generate a synthetic candle series for backtest / feedback testing."""
    candles = []
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    price = start_price
    for i in range(count):
        t_str = (base_time + timedelta(minutes=5 * i)).isoformat()
        change = 1.5 if i % 2 == 0 else -0.8
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + 0.5
        low_p = min(open_p, close_p) - 0.5
        price = close_p
        candles.append({
            "timestamp": t_str,
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": 100.0 + i * 2,
        })
    return candles

