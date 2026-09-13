"""
V2 Repository Layer — all persistence goes through repositories.
Services never write SQL directly.
"""

from .db import Database
from .signal_repo import SignalRepository
from .ai_repo import AIAnalysisRepository
from .position_repo import PositionRepository
from .trade_repo import TradeRepository
from .shadow_repo import ShadowRepository
from .metrics_repo import MetricsRepository
from .event_log_repo import EventLogRepository
from .candle_repo import CandleRepository
from .production_state_repo import ProductionStateRepository

__all__ = [
    "Database",
    "SignalRepository",
    "AIAnalysisRepository",
    "PositionRepository",
    "TradeRepository",
    "ShadowRepository",
    "MetricsRepository",
    "EventLogRepository",
    "CandleRepository",
    "ProductionStateRepository",
]
