"""
10. VGX (Volatile Grid Execution) Strategy.
Vectorized implementation.
"""

from __future__ import annotations

from typing import List
import numpy as np
import pandas as pd

from .base import BacktestTradeSignal, BaseStrategy


class VGXStrategy(BaseStrategy):

    def __init__(self) -> None:
        super().__init__("VGX (Volatile Grid Execution)")

    def generate_signals(
        self,
        df: pd.DataFrame,
        pair: str = "BTC/USDT",
        timeframe: str = "1H",
    ) -> List[BacktestTradeSignal]:
        signals: List[BacktestTradeSignal] = []
        n = len(df)
        if n < 40:
            return signals

        closes = df["close"].values
        lows = df["low"].values
        kc_lower = df["kc_lower"].values
        rsi = df["rsi_14"].values
        atr = df["atr_14"].values

        mask = (lows <= kc_lower) | (rsi < 38)
        cand_indices = np.where(mask)[0]

        for i in cand_indices:
            if i < 25 or i >= n - 1:
                continue

            entry = closes[i]
            stop_loss = entry * 0.960  # Boundary SL: 4.0%
            take_profit = entry * 1.020  # Step Grid TP: 2.0%

            signals.append(
                BacktestTradeSignal(
                    strategy_name=self.name,
                    pair=pair,
                    timeframe=timeframe,
                    bar_index=int(i),
                    entry_price=float(entry),
                    stop_loss_price=float(stop_loss),
                    take_profit_price=float(take_profit),
                    direction="LONG",
                    metadata={"kc_lower": float(kc_lower[i]), "atr": float(atr[i])},
                )
            )

        return signals
