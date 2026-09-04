"""
sector_quant.data — Market data handlers for event-driven simulation.
"""

from .base import DataHandler
from .historic_sector import HistoricSectorDataHandler

__all__ = [
    "DataHandler",
    "HistoricSectorDataHandler",
]
