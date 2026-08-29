"""
V2 PortfolioAggregator — computes cross-bot capital allocation, PnL, and AUM.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from v2.core.types import BotName, Position, PortfolioSnapshot, Trade


class PortfolioAggregator:
    """Pure mathematical aggregator for multi-bot portfolio state."""

    @staticmethod
    def aggregate(
        positions: list[Position],
        closed_trades: list[Trade],
        base_cash: float = 100000.0,
    ) -> PortfolioSnapshot:
        """Calculate live AUM, deployed capital, cash, and PnL breakdown."""
        positions_by_bot: dict[str, list[Position]] = {
            BotName.STE.value: [],
            BotName.HDA.value: [],
            BotName.VCP.value: [],
            BotName.BBS.value: [],
        }

        total_deployed = 0.0
        total_unrealised = 0.0

        for pos in positions:
            b_key = pos.bot.value if isinstance(pos.bot, BotName) else str(pos.bot)
            if b_key not in positions_by_bot:
                positions_by_bot[b_key] = []
            positions_by_bot[b_key].append(pos)

            deployed = pos.deployed_capital
            total_deployed += deployed
            if pos.unrealised_pnl is not None:
                total_unrealised += pos.unrealised_pnl

        total_realised = sum(t.pnl for t in closed_trades)
        
        # Cash = Initial Cash + Realised PnL - Currently Deployed Capital
        total_cash = max(0.0, base_cash + total_realised - total_deployed)
        total_aum = total_cash + total_deployed + total_unrealised

        capital_util = round((total_deployed / total_aum * 100.0), 2) if total_aum > 0 else 0.0

        # Calculate daily realised PnL (from today UTC)
        today_utc = datetime.now(timezone.utc).date()
        daily_pnl = sum(
            t.pnl for t in closed_trades
            if t.exit_time.date() == today_utc
        ) + total_unrealised

        return PortfolioSnapshot(
            total_aum=round(total_aum, 2),
            total_deployed=round(total_deployed, 2),
            total_cash=round(total_cash, 2),
            total_unrealised_pnl=round(total_unrealised, 2),
            total_realised_pnl=round(total_realised, 2),
            daily_pnl=round(daily_pnl, 2),
            capital_utilisation=capital_util,
            positions_by_bot=positions_by_bot,
            captured_at=datetime.now(timezone.utc),
        )
