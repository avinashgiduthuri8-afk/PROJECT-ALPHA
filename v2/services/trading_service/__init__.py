"""
V2 Trading Service Package (Production Fleet Edition).
"""

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
    "BaseBotAdapter",
    "STEAdapter",
    "HDAAdapter",
    "VCPAdapter",
    "BBSAdapter",
    "StrategyAdapterFactory",
]
