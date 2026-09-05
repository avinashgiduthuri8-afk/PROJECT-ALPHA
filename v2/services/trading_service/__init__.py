"""
V2 Trading Service Package (Execution Engine Edition).
"""

from .auto_trader import AutoTradeRouter
from .position_manager import PositionManager
from .reconciliation import ReconciliationService
from .recovery import RestartRecoveryService
from .service import TradingService
from .adapters import (
    BaseBotAdapter,
    STEAdapter,
    HDAAdapter,
    VCPAdapter,
    BBSAdapter,
    StrategyAdapterFactory,
)

__all__ = [
    "TradingService",
    "AutoTradeRouter",
    "PositionManager",
    "RestartRecoveryService",
    "ReconciliationService",
    "BaseBotAdapter",
    "STEAdapter",
    "HDAAdapter",
    "VCPAdapter",
    "BBSAdapter",
    "StrategyAdapterFactory",
]
