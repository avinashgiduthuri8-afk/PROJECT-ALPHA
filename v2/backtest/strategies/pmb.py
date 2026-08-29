"""
5. PMB (Pullback Momentum Bot) Strategy.
Vectorized implementation.
"""

from __future__ import annotations

from typing import List
import numpy as np
import pandas as pd

from .base import BacktestTradeSignal, BaseStrategy


class PMBStrategy(BaseStrategy):

    def __init__(self) -> None:
        super().__init__("PMB (Pullback Momentum Bot)")

    def generate_signals(
        self,
        df: pd.DataFrame,
        pair: str = "BTC/USDT",
        timeframe: str = "1H",
    ) -> List[BacktestTradeSignal]:
        signals: List[BacktestTradeSignal] = []
        n = len(df)
        if n < 50:
            return signals

        closes = df["close"].values
        lows = df["low"].values
        ema_21 = df["ema_21"].values
        ema_50 = df["ema_50"].values
        vwap = df["vwap"].values
        rsi = df["rsi_14"].values

        rsi_shift = np.roll(rsi, 1)
        rsi_shift[0] = 50.0

        mask = (ema_21 > ema_50) & ((lows <= ema_21 * 1.002) | (lows <= vwap * 1.002)) & (rsi_shift < 40) & (rsi > rsi_shift)
        cand_indices = np.where(mask)[0]

        for i in cand_indices:
            if i < 25 or i >= n - 1:
                continue

            entry = closes[i]
            stop_loss = entry * 0.975  # 2.5% SL
            take_profit = entry * 1.035  # 3.5% TP

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
                    metadata={"rsi": float(rsi[i]), "ema_21": float(ema_21[i])},
                )
            )

        return signals
