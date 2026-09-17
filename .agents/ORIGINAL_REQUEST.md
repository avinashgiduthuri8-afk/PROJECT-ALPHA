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

## 2026-09-11T12:30:03Z

The server restarted. Please resume work on the teamwork specification in prompt_draft.md and complete all remaining tasks (#6 Dashboard Sync, #7 SQLite Positions Hydration, #8 Portfolio Telemetry, #9 Capital Inconsistency, #10 Equity Calculation, #11 Position Count Inconsistency, #13 Analytics Telemetry, #15 Watchlist Widget, #16 Trade Chart Plotting). Proceed with implementation and verification.

## 2026-09-13T10:35:11Z

This is a single self-contained fix; keep it small and focused. Permanently remove the legacy v2/ directory from PROJECT-ALPHA and update any remaining test suite imports to canonical modules so the entire system and test suite run cleanly and independently.

Working directory: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA
Integrity mode: development

## Requirements

### R1. Remove Legacy `v2/` Directory
Permanently delete the legacy `v2/` directory tree. No active application service, script, or configuration may depend on the existence of `v2/`.

### R2. Test Suite Import Migration
Migrate any remaining test files in `tests/` that import from `v2.*` so they import directly from the six canonical packages: `core`, `scanner`, `execution`, `telegram`, `background`, and `dashboard`.

### R3. Route & Schema Invariants Preservation
Maintain all backward-compatibility API and WebSocket endpoints (`/api/v2/*`, `/v2/dashboard`, `/v2-static/*`, `/ws/v2/feed`) defined in `app.py` and `dashboard/` so existing external clients remain fully supported. Do not alter database migrations or table schemas.

## Acceptance Criteria

### Clean Removal
- [ ] The `v2/` directory no longer exists in the repository.
- [ ] No active file in `core`, `scanner`, `execution`, `telegram`, `background`, `dashboard`, `app.py`, or `scripts` contains imports from `v2`.

### Compilation & Static Health
- [ ] `python -m compileall core scanner execution telegram dashboard background app.py scripts` exits with code 0.

### Automated Test Verification
- [ ] `python -m pytest tests/test_canonical_config.py tests/test_canonical_app.py tests/test_v2_dashboard_ui.py tests/test_v2_pipeline_dashboard.py tests/test_v2_phase7_dashboard.py tests/test_v2_safety_invariants.py --basetemp=.pytest_temp -v` exits with code 0 (0 failed).
- [ ] Full pytest discovery (`python -m pytest --collect-only`) collects all tests without any `ModuleNotFoundError` for `v2`.

## 2026-09-17T08:22:34Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: Small, focused team

Perform a read-only audit of the scanner's indicator calculations on the VPS to validate correctness, no look-ahead bias, proper warm-up, and live integration. Do NOT modify any indicator logic, thresholds, or scoring.

Working directory: `C:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA`
Integrity mode: development

## Requirements

### R1. Phase 1: Code Inspection
Inspect `scanner/indicators.py` and `scanner/research/indicators.py` on the VPS to report line counts, list active indicator function signatures (RSI, MACD, EMA, Bollinger, ATR, Volume), and scan for any forward-looking/look-ahead data leakage patterns.

### R2. Phase 2: Unit Test Coverage
Locate and execute the indicator test suite (`tests/test_v2_indicators.py`) on the VPS. Summarize the test results and report any failures.

### R3. Phase 3 & 4 & 5: Manual Reference Validation
Create and execute temporary Python scripts on the VPS to validate that:
- RSI correctly identifies overbought (>70) on an uptrend and oversold (<30) on a downtrend.
- MACD returns a valid multi-column DataFrame with non-null final values.
- EMA50 correctly handles insufficient data (<50 candles) by returning None/NaN, and returns valid values with sufficient data.

### R4. Phase 6: Live Scanner Integration
Query the live SQLite database (`data/project_alpha.db`) on the VPS to verify that signals have been generated in the last 5 minutes and that the `indicators` JSON blob is correctly populated.

### R5. Controlled Infrastructure (VPS Access)
All commands and scripts must be executed on the remote Linux VPS. Because your local environment is Windows, you must write and execute local Python scripts using the `paramiko` library to run commands over SSH (`root@148.113.9.103`, port `20069`, password `SMT6SiQU2nIUMj0V`).

## Acceptance Criteria

### Execution & Reporting
- [ ] All 7 phases from the user's audit script are executed exactly as requested.
- [ ] The final output is a strictly formatted Summary Report (Phase 7) detailing the status of RSI, MACD, EMA, and Live Scanner Integration.
- [ ] No indicator logic, thresholds, or scoring mechanisms are modified in the codebase.
- [ ] Large tests or execution scripts are broken down into smaller, manageable chunks.

