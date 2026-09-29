from datetime import datetime, timezone
import pytest
from core.config import AppConfig
from core.types import BotMode, BotName, Position, PositionStatus
from execution.risk.capital_guard import CapitalGuard


def test_position_deployed_capital_inr_pair():
    pos = Position(
        id="pos-inr-1",
        bot=BotName.VCP,
        coin="BTC",
        pair="BTC/INR",
        qty=0.0001,
        entry_price=5000000.0,
        entry_time=datetime.now(timezone.utc),
        mode=BotMode.PAPER,
    )
    # 5,000,000 * 0.0001 = 500 INR
    assert pos.deployed_capital == 500.0


def test_position_deployed_capital_usdt_pair():
    pos = Position(
        id="pos-usdt-1",
        bot=BotName.STE,
        coin="SOL",
        pair="SOL/USDT",
        qty=0.01,           # 0.01 SOL
        entry_price=150.0,  # 150 USDT => 1.50 USDT notional
        entry_time=datetime.now(timezone.utc),
        mode=BotMode.PAPER,
    )
    # 1.50 USDT * 91.50 INR/USDT = 137.25 INR
    assert pos.deployed_capital == pytest.approx(137.25, rel=1e-3)


def test_capital_guard_enforces_inr_master_budget():
    """Verify CapitalGuard prevents orders that would exceed master INR capital budget."""
    cfg = AppConfig()
    cfg.total_capital_limit = 10000.0  # ₹10,000 INR
    guard = CapitalGuard(config=cfg)

    # 1. First order: ₹200 INR (allowed)
    dec1 = guard.check_trade(
        bot=BotName.STE,
        requested_amount=200.0,
        current_bot_deployed=0.0,
        total_deployed=9800.0,  # ₹9,800 already deployed
        current_bot_positions=0,
    )
    assert dec1.allowed is True

    # 2. Next order: ₹250 INR (exceeds ₹10,000 ceiling -> rejected)
    dec2 = guard.check_trade(
        bot=BotName.STE,
        requested_amount=250.0,
        current_bot_deployed=200.0,
        total_deployed=9800.0,
        current_bot_positions=1,
    )
    assert dec2.allowed is False
    assert dec2.code == "BLOCKED_TOTAL_CAPITAL"
