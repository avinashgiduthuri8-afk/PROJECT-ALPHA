"""
Unit and Integration Tests for Mandatory Minimum INR 200.00 Order Size Invariant.
Ensures no order is placed or sized below INR 200.00 in either PAPER or LIVE modes.
"""

from __future__ import annotations

import pytest
from v2.core.config import V2Config
from v2.core.types import BotName
from v2.services.risk_service.capital_guard import CapitalGuard
from v2.services.trading_service.adapters import StrategyAdapterFactory
from v2.trading.precision_rules import PRECISION_TABLE, validate_order_notional


def test_precision_table_min_notional_is_200():
    """Verify all 12 CoinDCX INR pairs have min_notional_inr >= 200.0."""
    for pair, spec in PRECISION_TABLE.items():
        if pair.endswith("/INR"):
            assert spec.min_notional_inr >= 200.0, f"Pair {pair} has min_notional_inr {spec.min_notional_inr} < 200"


def test_validate_order_notional_rejects_below_200():
    """Verify validate_order_notional returns False for notionals < 200 INR."""
    assert not validate_order_notional("BTC/INR", price=8200000.0, qty=0.000018)
    assert validate_order_notional("BTC/INR", price=8200000.0, qty=0.000025)
    assert not validate_order_notional("DOGE/INR", price=16.5, qty=6.0)
    assert validate_order_notional("DOGE/INR", price=16.5, qty=13.0)


def test_all_adapters_enforce_200_minimum():
    """Verify STE, HDA, VCP, BBS adapters round up lot size to ensure amount >= 200.0 even if passed 50.0."""
    for bot in [BotName.STE, BotName.HDA, BotName.VCP, BotName.BBS]:
        adapter = StrategyAdapterFactory.get_adapter(bot)
        order = adapter.calculate_order(
            coin="ETH",
            pair="ETH/INR",
            approved_amount=50.0,
            current_price=260000.0,
            ai_adjustments={},
        )
        assert order["amount"] >= 200.0, f"Adapter {bot.value} produced order amount {order['amount']} < 200.0"
        assert order["qty"] * order["entry_price"] >= 200.0


def test_capital_guard_blocks_order_below_200():
    """Verify CapitalGuard denies any trade where requested_amount < 200.0."""
    cfg = V2Config()
    guard = CapitalGuard(cfg)

    dec_blocked = guard.check_trade(
        bot=BotName.STE,
        requested_amount=50.0,
        current_bot_deployed=0.0,
        total_deployed=0.0,
        current_bot_positions=0,
    )
    assert not dec_blocked.allowed
    assert dec_blocked.code == "BLOCKED_MIN_ORDER_SIZE"
    assert "200.00" in dec_blocked.reason

    dec_allowed = guard.check_trade(
        bot=BotName.STE,
        requested_amount=200.0,
        current_bot_deployed=0.0,
        total_deployed=0.0,
        current_bot_positions=0,
    )
    assert dec_allowed.allowed


def test_v2_config_clamps_order_size_to_200(tmp_path):
    """Verify V2Config validator and runtime overrides enforce order_size_inr >= 200.0."""
    cfg = V2Config(order_size_inr=50.0)
    assert cfg.order_size_inr == 200.0

    override_file = str(tmp_path / "test_override.json")
    saved = V2Config.save_runtime_overrides({"order_size_inr": 75.0}, override_path=override_file)
    assert saved.order_size_inr == 200.0
