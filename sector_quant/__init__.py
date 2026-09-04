"""
sector_quant — Institutional Event-Driven Multi-Asset & Cross-Sector Framework.

Features:
- Relational Securities Master schema for multi-sector equities.
- Zero look-ahead event-driven DataHandler.
- Statistical arbitrage / pairs trading strategy with rolling OLS and z-score signals.
- Sector-level RiskEngine (30% sector cap, 15% stock cap).
- Simulated execution engine with linear slippage and commissions.
"""

from .events import Event, EventType, MarketEvent, SignalEvent, OrderEvent, FillEvent

__all__ = [
    "Event",
    "EventType",
    "MarketEvent",
    "SignalEvent",
    "OrderEvent",
    "FillEvent",
]
