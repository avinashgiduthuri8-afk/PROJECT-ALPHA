"""
Vectorized & Event-Driven Backtesting Simulation Engine Manager.

Mandates:
  1. Execution Simulation: Avoid lookahead bias. Orders execute at next bar Open after signal bar Close.
  2. Risk & Sizing Gate: Applies Stage 06 dynamic risk allocation with pair-specific lot precision.
  3. Statutory Friction Model: Deducts CoinDCX fees (0.20% + 18% GST), 1% Sec 194S TDS, and 0.05% slippage per side.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from .data_feeder import DataFeeder, COINDCX_INR_PAIRS, round_price, round_qty
from .friction import CoinDCXFrictionModel, FrictionConfig
from .metrics import PerformanceMetrics, calculate_trade_metrics
from .risk_gate import Stage06RiskGate
from .strategies import ALL_CANDIDATE_STRATEGIES, BaseStrategy, BacktestTradeSignal


class BacktestEngine:
    """Manages full execution backtests across all 10 candidate strategies for INR crypto pairs."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        friction_config: Optional[FrictionConfig] = None,
        data_feeder: Optional[DataFeeder] = None,
    ) -> None:
        self.initial_capital = initial_capital
        self.friction_config = friction_config or FrictionConfig()
        self.friction_model = CoinDCXFrictionModel(self.friction_config)
        self.risk_gate = Stage06RiskGate(max_risk_pct_per_trade=1.0, friction_config=self.friction_config)
        self.feeder = data_feeder or DataFeeder()

    def run_strategy_backtest(
        self,
        strategy: BaseStrategy,
        pairs: List[str] = None,
        timeframes: List[str] = None,
        sessions: int = 250,
    ) -> PerformanceMetrics:
        """
        Runs backtest for a single strategy across specified INR pairs and timeframes.
        """
        pairs = pairs or list(COINDCX_INR_PAIRS.keys())
        timeframes = timeframes or ["15M", "1H", "4H"]

        all_trades: List[Dict[str, Any]] = []

        for pair in pairs:
            for tf in timeframes:
                df = self.feeder.generate_ohlcv_dataframe(pair=pair, timeframe=tf, sessions=sessions)
                signals = strategy.generate_signals(df, pair=pair, timeframe=tf)

                trades = self._simulate_trade_executions(df, signals, pair=pair, timeframe=tf)
                all_trades.extend(trades)

        # Calculate performance metrics over all executed trades
        return calculate_trade_metrics(
            strategy_name=strategy.name,
            trades=all_trades,
            initial_capital=self.initial_capital,
        )

    def run_all_candidate_strategies(
        self,
        pairs: List[str] = None,
        timeframes: List[str] = None,
        sessions: int = 250,
    ) -> List[PerformanceMetrics]:
        """
        Runs backtest for all 10 candidate strategies.
        """
        results: List[PerformanceMetrics] = []
        for strat in ALL_CANDIDATE_STRATEGIES:
            m = self.run_strategy_backtest(strat, pairs=pairs, timeframes=timeframes, sessions=sessions)
            results.append(m)
        return results

    def _simulate_trade_executions(
        self,
        df: pd.DataFrame,
        signals: List[BacktestTradeSignal],
        pair: str,
        timeframe: str,
    ) -> List[Dict[str, Any]]:
        """
        Simulates Realistic Execution at next bar Open price with Stage 06 Risk Sizing and Statutory Friction.
        """
        trades: List[Dict[str, Any]] = []
        n = len(df)
        if not signals or n == 0:
            return trades

        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        timestamps = df["timestamp"].values

        current_equity = self.initial_capital

        for sig in signals:
            trigger_bar = sig.bar_index
            exec_bar = trigger_bar + 1

            # Avoid lookahead: Execution occurs at next bar's Open price
            if exec_bar >= n:
                continue

            raw_entry_price = round_price(pair, opens[exec_bar])
            raw_sl_price = round_price(pair, sig.stop_loss_price)
            raw_tp_price = round_price(pair, sig.take_profit_price)

            # Calculate position sizing via Stage 06 Risk Gate with discrete lot rounding
            sizing = self.risk_gate.calculate_position_size(
                account_equity=current_equity,
                entry_price=raw_entry_price,
                stop_loss_price=raw_sl_price,
                pair=pair,
            )

            qty = sizing["qty"]
            if qty <= 0:
                continue

            # Simulate exit price by tracking subsequent price action (vectorized lookahead)
            raw_exit_price = raw_tp_price
            exit_bar = exec_bar + 1

            max_b = min(exec_bar + 40, n)
            sub_lows = lows[exec_bar + 1 : max_b]
            sub_highs = highs[exec_bar + 1 : max_b]

            sl_hits = np.where(sub_lows <= raw_sl_price)[0]
            tp_hits = np.where(sub_highs >= raw_tp_price)[0]

            first_sl = sl_hits[0] if len(sl_hits) > 0 else 9999
            first_tp = tp_hits[0] if len(tp_hits) > 0 else 9999

            if first_sl < first_tp:
                raw_exit_price = raw_sl_price
                exit_bar = exec_bar + 1 + first_sl
            elif first_tp < 9999:
                raw_exit_price = raw_tp_price
                exit_bar = exec_bar + 1 + first_tp

            raw_exit_price = round_price(pair, raw_exit_price)

            # Calculate realized PnL after Indian statutory TDS, GST, fees, and slippage
            pnl_data = self.friction_model.calculate_trade_net_pnl(
                entry_price=raw_entry_price,
                exit_price=raw_exit_price,
                position_size_qty=qty,
            )

            current_equity += pnl_data["net_pnl"]

            trade_record = {
                "strategy_name": sig.strategy_name,
                "pair": pair,
                "timeframe": timeframe,
                "trigger_time": str(timestamps[trigger_bar]),
                "exec_time": str(timestamps[exec_bar]),
                "entry_price": raw_entry_price,
                "exit_price": raw_exit_price,
                "qty": qty,
                "position_amount": sizing["amount"],
                "gross_pnl": pnl_data["gross_pnl"],
                "gross_pnl_pct": pnl_data["gross_pnl_pct"],
                "net_pnl": pnl_data["net_pnl"],
                "net_pnl_pct": pnl_data["net_pnl_pct"],
                "friction_cost": pnl_data["total_friction_cost"],
            }
            trades.append(trade_record)

        return trades
