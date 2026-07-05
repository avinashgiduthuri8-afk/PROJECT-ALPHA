"""
conftest.py — PROJECT-ALPHA test bootstrap.

Sets safe defaults for every environment variable the application reads at
import time so tests never fail due to missing env vars.  Uses setdefault so
real environment values are never overwritten.
"""
from __future__ import annotations

import os

# ── Core application secrets ──────────────────────────────────────────────────
os.environ.setdefault("SESSION_SECRET",   "test-session-secret")
os.environ.setdefault("DASHBOARD_API_KEY", "test-api-key")

# ── Trading kill-switches (off by default in tests) ───────────────────────────
os.environ.setdefault("TRADING_ENABLED",  "false")
os.environ.setdefault("EMERGENCY_STOP",   "false")

# ── Bot modes (paper so risk engine is exercisable) ───────────────────────────
os.environ.setdefault("VGX_BOT_MODE", "PAPER")
os.environ.setdefault("PMB_BOT_MODE", "PAPER")
os.environ.setdefault("MTB_BOT_MODE", "PAPER")

# ── Capital / position limits ─────────────────────────────────────────────────
os.environ.setdefault("VGX_TRADE_AMOUNT",  "500")
os.environ.setdefault("PMB_TRADE_AMOUNT",  "100")
os.environ.setdefault("MTB_TRADE_AMOUNT",  "200")
os.environ.setdefault("VGX_CAPITAL_LIMIT", "5000")
os.environ.setdefault("PMB_CAPITAL_LIMIT", "3000")
os.environ.setdefault("MTB_CAPITAL_LIMIT", "2000")
os.environ.setdefault("TOTAL_CAPITAL_LIMIT", "10000")
os.environ.setdefault("VGX_MAX_POSITIONS", "5")
os.environ.setdefault("PMB_MAX_POSITIONS", "5")
os.environ.setdefault("MTB_MAX_POSITIONS", "3")
