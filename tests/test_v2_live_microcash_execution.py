"""
Unit and Integration Tests for Shadow-to-Live Execution Switch,
Position Lifecycle Reconciliation, and 1.572% Statutory Friction Accounting.
"""

from __future__ import annotations

import asyncio
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from v2.app_v2 import app
from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config, get_config, invalidate_config
from v2.core.types import BotMode, BotName, ExitReason, MarketState, OppType, Position, PositionStatus, Priority, RiskLevel, Signal
from v2.repository.db import Database
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.repository.signal_repo import SignalRepository
from v2.repository.ai_repo import AIAnalysisRepository
from v2.services.risk_service.service import RiskService
from v2.services.trading_service.service import TradingService
from v2.trading.subaccount_manager import CoinDCXSubAccountManager
from v2.backtest.friction import CoinDCXFrictionModel


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    test_db = str(tmp_path / f"test_exec_{uuid.uuid4().hex[:6]}.db")
    monkeypatch.setenv("V2_DB_PATH", test_db)
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-exec-key")
    monkeypatch.setenv("V2_DEPLOYMENT_MODE", "SHADOW")
    monkeypatch.setenv("V2_TRADING_ENABLED", "false")
    monkeypatch.setenv("TOTAL_CAPITAL_LIMIT", "10000.0")
    monkeypatch.setenv("ORDER_SIZE_INR", "200.0")
    invalidate_config()
    yield
    invalidate_config()


@pytest.mark.anyio
async def test_shadow_mode_isolation_and_single_coin_lock(tmp_path):
    """Verify that in SHADOW mode, approved trades create paper positions, update headroom, and enforce single-coin lock."""
    db_path = str(tmp_path / "test_shadow_exec.db")
    db = Database(db_path)
    await db.open()

    bus = EventBus()
    pos_repo = PositionRepository(db.connection)
    trade_repo = TradeRepository(db.connection)
    event_repo = EventLogRepository(db.connection)
    cfg = V2Config(v2_deployment_mode="SHADOW", v2_trading_enabled=False, total_capital_limit=10000.0, order_size_inr=200.0, enforce_single_coin_lock=True)

    risk_service = RiskService(bus=bus, position_repo=pos_repo, trade_repo=trade_repo, event_log_repo=event_repo, config=cfg)
    subaccount_mgr = CoinDCXSubAccountManager()
    trading_service = TradingService(bus=bus, position_repo=pos_repo, trade_repo=trade_repo, event_log_repo=event_repo, config=cfg, subaccount_manager=subaccount_mgr)

    await risk_service.start()
    await trading_service.start()

    # 1. Emit trade approval for SOL
    payload_sol = {
        "signal_id": "SIG-SOL-001",
        "coin": "SOL",
        "pair": "SOL/INR",
        "bot": "STE",
        "price": 10000.0,
        "approved_amount": 200.0,
    }
    await trading_service.on_trade_approved(EventType.TRADE_APPROVED, payload_sol)

    # Verify open position created in SHADOW (PAPER) mode
    open_pos = await pos_repo.get_open()
    assert len(open_pos) == 1
    assert open_pos[0].coin == "SOL"
    assert open_pos[0].mode == BotMode.PAPER
    assert open_pos[0].qty > 0

    # 2. Test Single-Coin Lock: Subsequent HDA signal on SOL must be blocked
    dec = await risk_service.check_trade_allowed(BotName.HDA, 200.0, coin="SOL", pair="SOL/INR")
    assert dec.allowed is False
    assert dec.code == "OPPORTUNITY_LOCKED_ACTIVE_PAIR"
    assert "already has an active open position" in dec.reason

    # 3. Non-conflicting coin (ETH) is allowed
    dec_eth = await risk_service.check_trade_allowed(BotName.HDA, 200.0, coin="ETH", pair="ETH/INR")
    assert dec_eth.allowed is True

    await risk_service.stop()
    await trading_service.stop()
    await db.close()


@pytest.mark.anyio
async def test_bracket_exit_and_statutory_friction(tmp_path):
    """Verify position exit applies the exact 1.572% round-trip statutory friction and releases asset lock."""
    db_path = str(tmp_path / "test_friction_exec.db")
    db = Database(db_path)
    await db.open()

    bus = EventBus()
    pos_repo = PositionRepository(db.connection)
    trade_repo = TradeRepository(db.connection)
    event_repo = EventLogRepository(db.connection)
    cfg = V2Config(v2_deployment_mode="SHADOW", v2_trading_enabled=False, total_capital_limit=10000.0, order_size_inr=200.0)

    subaccount_mgr = CoinDCXSubAccountManager()
    trading_service = TradingService(bus=bus, position_repo=pos_repo, trade_repo=trade_repo, event_log_repo=event_repo, config=cfg, subaccount_manager=subaccount_mgr)
    await trading_service.start()

    # Create position with entry=10000.0, SL=9500.0, TP=11000.0, qty=0.02 (₹200 notional)
    now = datetime.now(timezone.utc)
    pos = Position(
        id="POS-SOL-TEST",
        bot=BotName.STE,
        coin="SOL",
        pair="SOL/INR",
        qty=0.02,
        entry_price=10000.0,
        entry_time=now,
        mode=BotMode.PAPER,
        status=PositionStatus.OPEN,
        current_price=10000.0,
        stop_loss=9500.0,
        take_profit=11000.0,
    )
    await pos_repo.insert(pos)

    # 1. Price hits Take Profit (11050.0)
    closed = await trading_service.check_open_position_exits({"SOL": 11050.0})
    assert len(closed) == 1
    t = closed[0]
    assert t.exit_reason == ExitReason.TAKE_PROFIT
    assert t.exit_price == 11050.0

    # Verify 1.572% friction deduction in net P&L
    friction = CoinDCXFrictionModel()
    expected = friction.calculate_trade_net_pnl(10000.0, 11050.0, 0.02)
    assert t.pnl == expected["net_pnl"]
    assert expected["total_friction_cost"] > 0

    # Verify position is closed and asset lock is released
    open_now = await pos_repo.get_open()
    assert len(open_now) == 0

    await trading_service.stop()
    await db.close()


def test_production_mode_controller_api():
    """Verify REST endpoints for dynamic mode switching, kill switch, active positions, and status."""
    with TestClient(app) as client:
        headers = {"X-API-Key": "test-exec-key"}

        # 1. Initial status query
        r_status = client.get("/api/v2/production/status", headers=headers)
        assert r_status.status_code == 200
        data_status = r_status.json()
        assert "mode" in data_status
        assert "capital_pool_limit" in data_status
        assert "open_positions_count" in data_status

        # 2. Switch to LIVE_MICROCASH
        r_mode = client.post("/api/v2/production/set-mode", json={"mode": "LIVE_MICROCASH"}, headers=headers)
        assert r_mode.status_code == 200
        assert r_mode.json()["mode"] == "LIVE_MICROCASH"
        assert r_mode.json()["trading_enabled"] is True

        # Verify status reflected
        r_status2 = client.get("/api/v2/production/status", headers=headers)
        assert r_status2.json()["mode"] == "LIVE_MICROCASH"
        assert r_status2.json()["trading_enabled"] is True

        # 3. Emergency Kill-Switch
        r_kill = client.post("/api/v2/production/kill-switch", headers=headers)
        assert r_kill.status_code == 200
        assert r_kill.json()["circuit_breaker"] == "TRIPPED"
        assert r_kill.json()["trading_enabled"] is False

        # 4. Switch back to SHADOW
        r_shadow = client.post("/api/v2/production/set-mode", json={"mode": "SHADOW"}, headers=headers)
        assert r_shadow.status_code == 200
        assert r_shadow.json()["mode"] == "SHADOW"
        assert r_shadow.json()["trading_enabled"] is False

        # 5. Query active positions list
        r_pos = client.get("/api/v2/trading/positions", headers=headers)
        assert r_pos.status_code == 200
        assert isinstance(r_pos.json(), list)
