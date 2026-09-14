"""
sector_quant.data.historic_sector — Synchronized multi-symbol historic data handler.
"""

from __future__ import annotations

from datetime import datetime
from queue import Queue
from typing import Any

from sector_quant.data.base import DataHandler
from sector_quant.events import MarketEvent


class HistoricSectorDataHandler(DataHandler):
    """
    Simulates real-time multi-asset data delivery from historic OHLCV bars.
    Synchronizes iterators across sectors and drip-feeds bars to guarantee zero look-ahead bias.
    """

    def __init__(
        self,
        events_queue: Queue,
        symbol_list: list[str],
        data_feed: dict[str, list[dict[str, Any]]],
    ) -> None:
        super().__init__(events_queue)
        self.symbol_list = [s.upper() for s in symbol_list]
        self._raw_data: dict[str, list[dict[str, Any]]] = {
            s.upper(): sorted(data_feed.get(s, []), key=lambda b: b["price_date"])
            for s in self.symbol_list
        }
        self.latest_symbol_data: dict[str, list[dict[str, Any]]] = {
            s: [] for s in self.symbol_list
        }

        # Build chronological timeline across all symbols
        all_timestamps = set()
        for sym_bars in self._raw_data.values():
            for b in sym_bars:
                all_timestamps.add(b["price_date"])

        self._timeline: list[str] = sorted(list(all_timestamps))
        self._timeline_idx: int = 0
        self._symbol_indices: dict[str, int] = {s: 0 for s in self.symbol_list}

    def get_latest_bar(self, symbol: str) -> dict[str, Any] | None:
        sym = symbol.upper()
        bars = self.latest_symbol_data.get(sym, [])
        return bars[-1] if bars else None

    def get_latest_bars(self, symbol: str, N: int = 1) -> list[dict[str, Any]]:
        sym = symbol.upper()
        bars = self.latest_symbol_data.get(sym, [])
        return bars[-N:] if bars else []

    def get_latest_bar_datetime(self, symbol: str) -> datetime | None:
        bar = self.get_latest_bar(symbol)
        if not bar:
            return None
        dt_str = bar.get("price_date", "")
        try:
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None

    def get_latest_bar_value(self, symbol: str, val_type: str) -> float | None:
        bar = self.get_latest_bar(symbol)
        if not bar:
            return None
        return float(bar.get(val_type.lower(), 0.0))

    def get_latest_bars_values(
        self, symbol: str, val_type: str, N: int = 1
    ) -> list[float]:
        bars = self.get_latest_bars(symbol, N)
        return [float(b.get(val_type.lower(), 0.0)) for b in bars]

    def update_bars(self) -> None:
        """Advance one step in the synchronized timeline and emit MarketEvent."""
        if self._timeline_idx >= len(self._timeline):
            self.continue_backtest = False
            return

        current_time = self._timeline[self._timeline_idx]
        has_new_bar = False

        for sym in self.symbol_list:
            idx = self._symbol_indices[sym]
            sym_bars = self._raw_data[sym]
            if idx < len(sym_bars) and sym_bars[idx]["price_date"] == current_time:
                self.latest_symbol_data[sym].append(sym_bars[idx])
                self._symbol_indices[sym] += 1
                has_new_bar = True

        self._timeline_idx += 1

        if has_new_bar:
            self.events.put(MarketEvent())
        else:
            # If no symbol had data at this timestamp, continue to next
            if self._timeline_idx >= len(self._timeline):
                self.continue_backtest = False
