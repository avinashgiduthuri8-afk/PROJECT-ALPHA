"""
sector_quant.data.base — Abstract DataHandler class for event-driven bar feeds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from queue import Queue
from typing import Any, Dict, List, Optional


class DataHandler(ABC):
    """
    Abstract base class providing an interface for both live and historical data handlers.
    Strictly forbids look-ahead bias by drip-feeding bars tick-by-tick.
    """

    def __init__(self, events_queue: Queue) -> None:
        self.events = events_queue
        self.continue_backtest = True

    @abstractmethod
    def get_latest_bar(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return the most recent single bar."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_bars(self, symbol: str, N: int = 1) -> List[Dict[str, Any]]:
        """Return the latest N bars, or fewer if not available."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_bar_datetime(self, symbol: str) -> Optional[datetime]:
        """Return datetime of the most recent bar."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_bar_value(self, symbol: str, val_type: str) -> Optional[float]:
        """Return one of Open, High, Low, Close, Volume from latest bar."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_bars_values(self, symbol: str, val_type: str, N: int = 1) -> List[float]:
        """Return list of float values for given attribute from latest N bars."""
        raise NotImplementedError

    @abstractmethod
    def update_bars(self) -> None:
        """Push the next synchronized bar to latest_symbol_data and emit MarketEvent."""
        raise NotImplementedError
