# Original User Request

## 2026-09-11T08:50:39Z

Resolve all remaining platform, dashboard, telemetry, and UI issues (#6 Dashboard Sync, #7 SQLite State Hydration, #8 Portfolio Telemetry, #9 Capital Inconsistency, #10 Equity Calculation, #11 Position Count Inconsistency, #13 Intelligence Analytics, #15 Watchlist Widget, #16 Trade Chart Plotting) in PROJECT-ALPHA V2.

Working directory: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA
Integrity mode: development

## Core Constraints
- **Preserve Paper Trading**: Do NOT enable live execution. Maintain `BotMode.PAPER` across all services.
- **Data Preservation**: Do NOT mutate, delete, or drop historical trades or positions in SQLite.
- **Capital Rule**: Enforce the unified shared capital pool and ₹200 minimum notional per order across all bots.

## Requirements

### R1. Frontend Script Execution & Dashboard DOM Synchronization (Issues #6, #8, #11)
Resolve the compile-time JavaScript SyntaxError in `v2/templates/dashboard.html` caused by duplicate variable declarations (`homeTbody` and `openTbody` around line 2043). Ensure `refreshLiveTelemetry()` executes smoothly on `DOMContentLoaded`, continuously polling telemetry and updating:
- Header KPI `kpi-openpos` reflecting actual `openPositions.length`.
- Open positions tables (`home-positions-tbody` and `open-positions-tbody`) populated from live API data rather than static fallback rows.
- Fleet bot cards displaying accurate position counts and configured capacities (`STE: 3, HDA: 3, VCP: 2, BBS: 4`) instead of hardcoded `0 / 1 (None)`.

### R2. Backend Startup Hydration & Active Positions Routing (Issues #6, #7, #9, #10)
Ensure that existing database positions in SQLite are properly hydrated on server startup and reflected across all services:
- Add a startup hydration routine in `BotPipelineTracker` (e.g. `sync_from_repository`) to populate bot active position counts and deployed capital from SQLite (`PositionRepository.get_active_positions()`) when the server initializes.
- Mount and register `dashboard_routes` into the main FastAPI router (`v2/api/router.py`) and initialize its aggregator dependencies.
- Update `/positions/open` endpoint to query non-closed positions (`status != 'CLOSED'`) via `get_active_positions()` so transitional active positions (like `PENDING_ENTRY`) are never dropped.
- Include `open_positions` and `open_positions_count` in `DashboardService.get_overview()`.
- Dynamically calculate total equity and deployed capital by combining cash balances with active positions' live mark-to-market valuations and friction costs.

### R3. Watchlist Widget & Intelligence Analytics Telemetry (Issues #13, #15)
- Wire the dashboard watchlist container to live scanner feeds (`/scanner/coins` / `/scanner/watchlist`), populating active universe coins, price change, volume ratios, and confluence scores.
- Connect the AI Intelligence service telemetry (market regime, B3/B4 scores, and risk assessment) to the dashboard analytics cards and status indicators.

### R4. Trade Chart Plotting Integration (Issue #16)
- Integrate an interactive lightweight financial charting widget (e.g., TradingView Lightweight Charts or Canvas-based OHLCV chart) into the dashboard chart panel (`#tradingview_widget` or `#trade-chart-container`).
- Render live/recent candlestick data for the selected symbol with overlay markers for Entry Price, Stop-Loss (SL), and Take-Profit (TP).

## Verification Resources
Existing automated test suites and diagnostic endpoints:
- `tests/test_v2_price_precision_and_order_integrity.py`
- `tests/test_v2_min_trading_value.py`
- `tests/test_v2_c2_scanner.py`
- `tests/test_v2_dashboard_ui.py`
- Server health endpoint `/health` and telemetry endpoints `/dashboard/overview`, `/positions/open`, `/production/status`.

## Acceptance Criteria

### Automated Verification
- [ ] Pytest test suites run and pass 100%: `py -m pytest tests/test_v2_dashboard_ui.py tests/test_v2_price_precision_and_order_integrity.py --basetemp=.pytest_tmp -v`.
- [ ] No JavaScript syntax errors or unhandled exceptions in `v2/templates/dashboard.html`.

### Functional & API Verification
- [ ] Restarting the application with active SQLite positions immediately displays all active positions across the dashboard KPI, positions table, and bot fleet cards without requiring new trade events.
- [ ] GET `/api/v2/positions/open` returns all non-closed positions (`status != 'CLOSED'`).
- [ ] GET `/api/v2/dashboard/overview` contains valid `open_positions_count` matching SQLite active positions.
- [ ] Watchlist widget displays scanned candidate coins with prices, volume, and confluence scores.
- [ ] Trade chart panel renders candlesticks and TP/SL levels for active pairs without console errors.

