# Context: PROJECT-ALPHA Platform & UI Fixes

## Background
PROJECT-ALPHA is an algorithmic trading platform running in PAPER mode.
Issues identified in V2:
1. Issue #6: Dashboard Sync - compile-time JavaScript SyntaxError (`homeTbody` & `openTbody`), failing DOM updates on DOMContentLoaded.
2. Issue #7: SQLite State Hydration - on server startup, existing active positions from SQLite are not hydrated into `BotPipelineTracker`, causing bot cards to show 0 positions and dropped tracking.
3. Issue #8: Portfolio Telemetry - open positions tables and KPIs not reflecting live telemetry.
4. Issue #9: Capital Inconsistency - deployed capital and cash balances not properly accounting for SQLite positions and live mark-to-market.
5. Issue #10: Equity Calculation - dynamic equity calculation needed (cash + mark-to-market valuations - friction costs).
6. Issue #11: Position Count Inconsistency - transitional active positions (`PENDING_ENTRY`, etc.) dropped or mismatched between SQLite and API endpoints (`/positions/open` vs overview).
7. Issue #13: Intelligence Analytics - telemetry for market regime, B3/B4 scores, and risk assessment not bound to dashboard cards.
8. Issue #15: Watchlist Widget - scanner feeds not wired to the dashboard watchlist container.
9. Issue #16: Trade Chart Plotting - no interactive lightweight charting widget rendering candlesticks with TP/SL/Entry markers.

## Constraints & Requirements
- BotMode.PAPER must be maintained everywhere.
- Existing historical positions and trades in SQLite database must NOT be deleted, mutated, or dropped.
- Minimum ₹200 notional per order and shared capital pool rules apply.
- Automated pytest tests must pass 100%.
- Dashboard JavaScript must have zero syntax errors.

