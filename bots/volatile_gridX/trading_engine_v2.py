"""
PROJECT-ALPHA Trading Engine v2.0
Production-grade trading engine with:
- Thread-safe mutex locks (BUG-001 FIX)
- Circuit breaker integration
- Duplicate order prevention
- Safe storage integration

Original issues fixed:
- BUG-001: Race condition in position creation
- Concurrent order execution vulnerability
- Balance corruption risk

NOTE (SP2.5): This module is NOT wired into the live trading path. The live path
uses trading_engine.py (v1). This file is kept for reference / potential future use.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any

from . import config
from . import storage
from .market_data import get_cached_price_safe
from .thread_safety import (
    position_lock,
    order_lock,
    order_guard,
    thread_safe_order,
    get_lock_status
)
from .circuit_breaker import (
    check_can_trade,
    record_pnl,
    get_breaker_status,
    TradingState
)
from .safe_storage import (
    get_positions,
    get_trade_history,
    get_analytics,
    create_backup
)

logger = logging.getLogger("vgx.trading_engine")

# ============================================================
# POSITION CREATION
# ============================================================

def open_position(
    coin: str,
    price: float,
    amount: float,
    source: str = "SCANNER"
) -> dict:
    """Create a new position object."""
    qty = amount / price
    
    return {
        "coin": coin,
        "buy_price": price,
        "qty": qty,
        "amount": amount,
        "time": time.time(),
        "time_iso": datetime.now(timezone.utc).isoformat(),
        "peak": price,
        "trailing_active": False,
        "trade_source": source,
        "status": "OPEN"
    }


# ============================================================
# THREAD-SAFE BUY POSITION (BUG-001 FIX)
# ============================================================

@thread_safe_order
def buy_position(
    coin: str,
    price: float,
    amount: float,
    source: str = "SCANNER"
) -> Tuple[bool, str]:
    """
    Thread-safe buy position with circuit breaker integration.
    
    BUG-001 FIX: Uses @thread_safe_order decorator to ensure atomic execution.
    Prevents race conditions and duplicate orders.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    pos_key = f"{coin}_{source}"
    
    # FIX: Emergency Stop Verification - V1
    # Check global emergency stop FIRST before any other checks
    try:
        from bots.risk_engine.config import EMERGENCY_STOP
        if EMERGENCY_STOP:
            logger.warning("EMERGENCY_STOP: Trade blocked for %s", coin)
            return False, "EMERGENCY_STOP is active - all new trades blocked"
    except ImportError:
        pass
    
    # ── Input validation ──
    if amount <= 100:
        return False, "Trade amount must be above 100"
    
    if price <= 0:
        return False, "Invalid price (<=0)"
    
    # ── Circuit breaker check ──
    can_trade, reason = check_can_trade()
    if not can_trade:
        logger.warning("CIRCUIT_BREAKER: Trade blocked - %s", reason)
        return False, f"Circuit breaker: {reason}"
    
    # ── Duplicate check (inside lock) ──
    if pos_key in storage.positions:
        logger.info("Duplicate position blocked: %s", pos_key)
        return False, f"Position {pos_key} already exists"
    
    # ── Balance check ──
    if storage.virtual_balance < amount:
        return False, f"Insufficient balance: {storage.virtual_balance:.2f} < {amount:.2f}"
    
    # ── Execute position ──
    try:
        # Deduct balance
        storage.virtual_balance -= amount
        
        # Create position
        position = open_position(coin, price, amount, source)
        storage.positions[pos_key] = position
        
        # Persist to safe storage
        safe_positions = get_positions()
        safe_positions.add(pos_key, position)
        
        logger.info(
            "BUY EXECUTED: %s @ %.6f, Amount: %.2f, Source: %s",
            coin, price, amount, source
        )
        
        return True, f"{coin} bought successfully"
        
    except Exception as e:
        # Rollback on failure
        storage.virtual_balance += amount
        if pos_key in storage.positions:
            del storage.positions[pos_key]
        
        logger.error("Buy position failed: %s", e)
        return False, f"Execution error: {str(e)}"


def buy_position_with_guard(
    coin: str,
    price: float,
    amount: float,
    source: str = "SCANNER"
) -> Tuple[bool, str]:
    """
    Buy position with additional duplicate order guard.
    Use this for signal-triggered buys to prevent duplicate processing.
    """
    pos_key = f"{coin}_{source}"
    
    try:
        with order_guard(pos_key):
            return buy_position(coin, price, amount, source)
    except ValueError as e:
        # Duplicate order detected by guard
        return False, str(e)


# ============================================================
# THREAD-SAFE CLOSE POSITION
# ============================================================

@thread_safe_order
def close_position(
    pos_key: str,
    current_price: float,
    reason: str = "MANUAL"
) -> Tuple[float, float, Optional[str], str]:
    """
    Thread-safe close position with circuit breaker PnL recording.
    
    Returns:
        Tuple of (receive_amount, pnl, source, message)
    """
    if pos_key not in storage.positions:
        return 0, 0, None, f"Position {pos_key} not found"
    
    pos = storage.positions[pos_key]
    qty = pos["qty"]
    receive_amount = qty * current_price
    pnl = receive_amount - pos["amount"]
    source = pos["trade_source"]
    
    try:
        # Update balance
        storage.virtual_balance += receive_amount
        
        # Remove from storage
        del storage.positions[pos_key]
        
        # Update safe storage
        safe_positions = get_positions()
        safe_positions.remove(pos_key)
        
        # Record PnL to circuit breaker
        trading_state = record_pnl(pnl)
        
        # Log trade to history
        trade_entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "coin": pos["coin"],
            "action": f"SELL [{reason}]",
            "buy_price": pos["buy_price"],
            "sell_price": current_price,
            "qty": qty,
            "amount": pos["amount"],
            "receive": round(receive_amount, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / pos["amount"]) * 100, 2),
            "hold_time_sec": time.time() - pos["time"],
            "trade_source": source,
            "close_reason": reason
        }
        
        get_trade_history().add(trade_entry)
        storage.trade_log.append(trade_entry)
        storage.save_data()
        
        # Check if circuit breaker triggered
        state_msg = ""
        if trading_state != TradingState.ACTIVE:
            state_msg = f" [CIRCUIT BREAKER: {trading_state.value}]"
        
        logger.info(
            "SELL EXECUTED: %s @ %.6f, PnL: %.2f (%.1f%%), Reason: %s%s",
            pos["coin"], current_price, pnl, 
            (pnl / pos["amount"]) * 100, reason, state_msg
        )
        
        return receive_amount, pnl, source, f"Closed with PnL: {pnl:.2f}"
        
    except Exception as e:
        logger.error("Close position failed: %s", e)
        return 0, 0, None, f"Execution error: {str(e)}"


# ============================================================
# THREAD-SAFE UPDATE POSITION
# ============================================================

@thread_safe_order
def update_position(pos_key: str, updates: dict) -> bool:
    """Thread-safe position update."""
    if pos_key not in storage.positions:
        return False
    
    storage.positions[pos_key].update(updates)
    
    # Sync to safe storage
    safe_positions = get_positions()
    safe_positions.update(pos_key, updates)
    
    return True


# ============================================================
# PAPER EXECUTION (PRODUCTION-GRADE)
# ============================================================

def paper_execute_signal(signal: dict) -> Tuple[bool, str]:
    """
    Execute a trading signal in paper mode with full safety checks.
    
    This is the main entry point for signal-triggered trades.
    """
    if signal.get("action") != "BUY":
        return False, "BUY only supported"
    
    coin = signal.get("coin", "").upper()
    source = signal.get("source", "SCANNER")
    
    if not coin:
        return False, "Missing coin symbol"
    
    # Get current price
    price = get_cached_price_safe(coin)
    if price <= 0:
        return False, f"Invalid price for {coin}"
    
    amount = config.TRADE_AMOUNT
    if amount <= 100:
        return False, "Trade amount must be > 100"
    
    # Execute with full protection
    success, message = buy_position_with_guard(coin, price, amount, source)
    
    if success:
        # Log trade entry
        trade_entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "coin": coin,
            "action": f"BUY [{source}]",
            "price": round(price, 6),
            "amount": round(amount, 2),
            "pnl": 0,
            "trade_source": source,
            "signal_score": signal.get("score", 0),
            "signal_tier": signal.get("tier", "UNKNOWN")
        }
        
        storage.trade_log.append(trade_entry)
        storage.save_data()
        
        return True, f"{coin} BUY executed @ {price:.6f}"
    
    return False, message


# ============================================================
# POSITION QUERIES (THREAD-SAFE)
# ============================================================

def get_all_positions() -> Dict[str, dict]:
    """Get all open positions (thread-safe)."""
    with position_lock():
        return dict(storage.positions)


def get_position(pos_key: str) -> Optional[dict]:
    """Get a specific position."""
    with position_lock():
        return storage.positions.get(pos_key)


def position_exists(coin: str, source: str = "SCANNER") -> bool:
    """Check if position exists for coin/source."""
    pos_key = f"{coin}_{source}"
    with position_lock():
        return pos_key in storage.positions


def get_position_count() -> int:
    """Get count of open positions."""
    with position_lock():
        return len(storage.positions)


# ============================================================
# TRADING ENGINE STATUS
# ============================================================

def get_engine_status() -> dict:
    """Get complete trading engine status."""
    breaker = get_breaker_status()
    locks = get_lock_status()
    
    with position_lock():
        positions = dict(storage.positions)
        balance = storage.virtual_balance
    
    # Calculate unrealized PnL
    unrealized_pnl = 0
    for pos_key, pos in positions.items():
        current_price = get_cached_price_safe(pos["coin"])
        if current_price > 0:
            current_value = pos["qty"] * current_price
            unrealized_pnl += current_value - pos["amount"]
    
    return {
        "trading_enabled": breaker.get("can_trade", False),
        "circuit_breaker": breaker,
        "lock_status": locks,
        "positions": {
            "count": len(positions),
            "total_invested": sum(p["amount"] for p in positions.values()),
            "unrealized_pnl": round(unrealized_pnl, 2)
        },
        "balance": round(balance, 2),
        "trade_amount": config.TRADE_AMOUNT,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================
# EMERGENCY FUNCTIONS
# ============================================================

def emergency_close_all(reason: str = "EMERGENCY") -> dict:
    """
    Emergency close all positions.
    Use during emergency stop or critical situations.
    """
    logger.warning("EMERGENCY CLOSE ALL INITIATED: %s", reason)
    
    # Create backup before emergency close
    create_backup("emergency_close")
    
    results = {
        "closed": 0,
        "failed": 0,
        "total_pnl": 0,
        "details": []
    }
    
    with position_lock():
        positions_to_close = list(storage.positions.keys())
    
    for pos_key in positions_to_close:
        pos = storage.positions.get(pos_key)
        if not pos:
            continue
        
        current_price = get_cached_price_safe(pos["coin"])
        if current_price <= 0:
            current_price = pos["buy_price"] * 0.95  # Assume 5% loss if no price
        
        _, pnl, _, msg = close_position(pos_key, current_price, reason)
        
        if "error" not in msg.lower():
            results["closed"] += 1
            results["total_pnl"] += pnl
            results["details"].append({
                "position": pos_key,
                "pnl": round(pnl, 2),
                "status": "closed"
            })
        else:
            results["failed"] += 1
            results["details"].append({
                "position": pos_key,
                "error": msg,
                "status": "failed"
            })
    
    logger.warning(
        "EMERGENCY CLOSE COMPLETE: Closed %d, Failed %d, Total PnL: %.2f",
        results["closed"], results["failed"], results["total_pnl"]
    )
    
    return results
