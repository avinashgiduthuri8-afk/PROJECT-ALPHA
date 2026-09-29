from datetime import datetime, timezone
import pytest
from core.config import AppConfig
from core.types import BotMode, BotName, Position, PositionStatus
from execution.adapters.ste_adapter import STEAdapter
from execution.adapters.vcp_adapter import VCPAdapter
from execution.adapters.hda_adapter import HDAAdapter
from execution.adapters.bbs_adapter import BBSAdapter
from execution.risk.capital_guard import CapitalGuard


def test_position_deployed_capital_currency_conversion():
    """Verify Position.deployed_capital computes correctly for INR vs USDT pairs."""
    now = datetime.now(timezone.utc)
    # 1. INR pair: deployed_capital = qty * entry_price
    pos_inr = Position(
        id="pos-inr-1",
        bot=BotName.STE,
        coin="BTC",
        pair="BTC/INR",
        qty=0.0001,
        entry_price=6000000.0,
        entry_time=now,
        mode=BotMode.PAPER,
        status=PositionStatus.OPEN,
    )
    assert pos_inr.deployed_capital == pytest.approx(600.0, abs=0.01)

    # 2. USDT pair: deployed_capital = qty * entry_price * 91.50
    pos_usdt = Position(
        id="pos-usdt-1",
        bot=BotName.STE,
        coin="SOL",
        pair="SOL/USDT",
        qty=0.1,
        entry_price=150.0,  # $15.00 USDT value
        entry_time=now,
        mode=BotMode.PAPER,
        status=PositionStatus.OPEN,
    )
    # 0.1 * 150 * 91.50 = 1372.50 INR
    assert pos_usdt.deployed_capital == pytest.approx(1372.50, abs=0.01)


def test_strategy_adapters_convert_inr_to_usdt():
    """Verify strategy adapters calculate order quantity using INR converted to USDT."""
    ste = STEAdapter()
    vcp = VCPAdapter()
    hda = HDAAdapter()
    bbs = BBSAdapter()

    # Given ₹250 INR allocation on a USDT pair with SOL @ $150 USDT and rate = 91.50
    # $250 / 91.50 = 2.7322 USDT target
    # qty = 2.7322 / 150 = ~0.0182 SOL
    for adapter in (ste, vcp, hda, bbs):
        order = adapter.calculate_order(
            coin="SOL",
            pair="SOL/USDT",
            approved_amount=250.0,  # ₹250 INR
            current_price=150.0,   # $150 USDT
            ai_adjustments={"usdt_inr_rate": 91.50},
        )
        assert order["entry_price"] == 150.0
        # Notional in USDT must be around 2.73 USDT, NOT 250 USDT
        assert order["amount"] < 10.0  # Around $2.73 USDT
        assert order["amount"] > 1.0


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
