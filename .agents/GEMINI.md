# PROJECT-ALPHA Trading Philosophy & Rules

## 1. Strategy & Timeframes
- **Core Strategy**: PROJECT-ALPHA is a trend-following **Swing Trader**, NOT a micro-scalper.
- **Timeframes**: Scanner relies on higher timeframes (`1h`, `4h`, `1d`) for Multi-Timeframe (MTF) alignment. Do not optimize for `1m` or `5m` noise.
- **Holding Period**: Trades are designed to be held for 1 day up to 1 week.

## 2. Risk Management & Profit Targets
- **Take Profit (TP)**: Set aggressively high (`20.0%` to `25.0%`). We aim for big, decent profits.
- **Stop Loss (SL)**: Set wide enough (`5.0%` to `8.0%`) to survive multi-day volatility. Do not use extremely tight (`< 2%`) stops unless dynamically triggered by a crash.

## 3. Position Scaling (Pyramiding)
- **Adding Capital**: The system is allowed to "double down" and add capital to an actively winning position if the coin continues to show strong positive momentum and new scanner signals fire.
- **Single-Coin Limits**: When adding capital, we bypass strict single-coin locks, provided the position is already in profit (e.g. `unrealized_pnl > 3.0%`), up to a maximum cap of 3 entries per coin.

