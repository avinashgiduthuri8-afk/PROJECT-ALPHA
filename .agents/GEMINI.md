# PROJECT-ALPHA Trading Philosophy & Rules

## 1. Strategy & Timeframes
- **Core Strategy**: PROJECT-ALPHA is a trend-following **Swing & Momentum Trader**.
- **Timeframes**: Scanner relies on higher timeframes (`1h`, `4h`, `1d`) for Multi-Timeframe (MTF) alignment, while monitoring intraday momentum.
- **Holding Period**: Trades are designed to be held from intraday up to 1 week.

## 2. Dynamic Take Profit (TP) & Risk Management
- **Standard Score Signals (80 - 89 Score)**: Target **Standard Profits (4.6% - 6.0%)**.
- **High-Conviction / Elite Signals (90+ Score)**: Extend Target to **Big Profits (20.0% - 25.0%)**.
- **Stop Loss (SL)**: Set appropriately (`3.5%` to `5.0%`) to survive market noise.

## 3. Active Trade Momentum & Market Shift (The SOL Scenario)
- **In-Trade Scaling**: If a position is in strong profit (e.g. +9%) and the market turns strongly BULLISH:
  1. **Add Capital (Pyramiding)**: The system bypasses single-coin locks to add a second tranche (up to 3 max) to ride the bull wave.
  2. **Strict Micro-Tranche Sizing**: Every added tranche is strictly capped at the standard order amount (e.g. ₹200 / `ORDER_SIZE_INR`). It **NEVER** increases to a large amount, ensuring ample capital remains available for other trades across the fleet.
  3. **Profit Protection**: The trailing stop automatically ratchets up (e.g. locking in +6% minimum profit) to protect gains while letting the remaining target run up to 20%+.

## 4. Execution Workflow & Roadmap Invariants
- **Linear Module Progression**: Work must proceed sequentially through the module roadmap:
  `N (Naming) → S (Scanner) → E (Execution) → C (Core) → T (Telegram) → D (Dashboard) → B (Background) → I (Integration)`
- **One Fix Per Prompt**: NEVER combine multiple module tasks into a single turn. Each prompt must focus on a single micro-task (e.g., N1, N2, N3, S1, S2).
- **Scanner Signal Philosophy**: The scanner engine prioritizes **few, high-quality signals with measurable success rates** over signal volume.

## 5. Currency Pairs
- **INR Pairs Only**: The bot and scanner must strictly operate on **INR pairs** (e.g., `BTC/INR`, `SOL/INR`). USDT pairs must be ignored or explicitly filtered out from market scans and execution logic.
- **Multi-Currency Pairs**: The bot and scanner evaluate and trade **both INR and USDT pairs**. The system natively fetches both from the exchange and ranks them cohesively based on liquidity and turnover. Do not restrict logic to a single quote currency unless explicitly requested.
