# Project: PROJECT-ALPHA V2 Platform, Telemetry & UI Fixes

## Architecture
PROJECT-ALPHA V2 is an automated crypto algorithmic trading system operating strictly under `BotMode.PAPER` with a unified shared capital pool (minimum ₹200 notional per order).
Data flow and module boundaries:
1. **Repository Layer (`v2/repository/`)**:
   - `PositionRepository`: SQLite database interface for `positions` and `trades`. Tracks lifecycle (`PENDING_ENTRY`, `OPEN`, `PENDING_EXIT`, `CLOSING`, `CLOSED`). Provides `get_active_positions()` (`status != 'CLOSED'`).
2. **Service Layer (`v2/services/`)**:
   - `BotPipelineTracker` (`dashboard_service/bot_pipeline.py`): Tracks 4 execution bots (`STE`, `HDA`, `VCP`, `BBS`) with configured capacities `(3, 3, 2, 4)`. Must hydrate active positions and deployed capital from `PositionRepository` on startup.
   - `DashboardService` (`dashboard_service/service.py`) & `DashboardAggregator`: Aggregates overview metrics, fleet state, risk metrics, and active positions for API and WebSocket delivery.
   - `PortfolioService` & `PortfolioAggregator`: Computes cash balance, total MTM valuation, statutory friction, and dynamic total equity ($\text{Cash} + \text{MTM} - \text{Friction}$).
   - `ScannerService` (`scanner_service/`): Generates universe scan candidates, EMA trend, RSI, MTF alignment, and B3/B4 confluence scores.
   - `AIIntelligenceService` (`ai_intelligence_service/`): Gating decisions and market regime intelligence.
3. **API Routing Layer (`v2/api/`)**:
   - `v2/api/router.py`: Main FastAPI router. Mounts `research_router`, `production_router`, `dashboard_router`.
   - `/positions/open` convenience endpoint: Must query non-closed positions via `get_active_positions()`.
   - `/scanner/watchlist` & `/scanner/coins`: Feed universe coins with price changes and confluence scores.
   - `/research/candles/{symbol}`: Returns recent OHLCV candlestick data for chart plotting.
4. **Presentation Layer (`v2/templates/dashboard.html`)**:
   - Institutional single-page trading dashboard with live telemetry polling (`refreshLiveTelemetry()`) and WebSocket streaming.
   - KPI metrics (`kpi-openpos`), active positions tables (`home-positions-tbody`, `open-positions-tbody`), bot fleet cards with configured capacities.
   - Interactive Watchlist Center table.
   - Interactive Canvas OHLCV trade chart widget (`#trade-chart-container`) with Entry/SL/TP overlay markers.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | SQLite Active Position Startup Hydration | `BotPipelineTracker.sync_from_repository()` populates bot active position counts and deployed capital on server initialization from SQLite. | M1 | ORIGINAL_REQUEST R2 |
| 2 | Main API Router Mounting | Mount `dashboard_routes` into `v2/api/router.py` and initialize aggregator dependencies in `init_router()`. | M1 | ORIGINAL_REQUEST R2 |
| 3 | Non-Closed Positions API Routing | Update `/positions/open`, `/trading/positions?status=OPEN`, and `/production/status` to query `get_active_positions()` (`status != 'CLOSED'`). | M1 | ORIGINAL_REQUEST R2 |
| 4 | Dashboard Overview Positions Payload | Include `open_positions` and `open_positions_count` in `DashboardService.get_overview()` and `DashboardOverviewSchema`. | M1 | ORIGINAL_REQUEST R2 |
| 5 | Dynamic Equity & Capital Calculation | Calculate dynamic Total Equity ($\text{Cash} + \text{MTM} - \text{Friction}$) and deployed capital incorporating active positions. | M1 | ORIGINAL_REQUEST R2 |
| 6 | Frontend HTML & Modal Syntax Fixes | Fix unclosed/mismatched tags in `#liveTradeConfirmModal`, fix `#positionActionModal` onsubmit handler, fix security PIN check bypass. | M2 | ORIGINAL_REQUEST R1 |
| 7 | Dashboard Telemetry DOM Synchronization | Ensure `refreshLiveTelemetry()` populates `#kpi-openpos`, `#home-positions-tbody`, `#open-positions-tbody` from live API data. | M2 | ORIGINAL_REQUEST R1 |
| 8 | Fleet Bot Capacity & Count Alignment | Set bot cards and tab views to configured capacities `STE: 3, HDA: 3, VCP: 2, BBS: 4` instead of hardcoded `0 / 1 (None)`. | M2 | ORIGINAL_REQUEST R1 |
| 9 | Watchlist Widget Live Feed | Wire `#watchlist-center` to `/scanner/coins` or `/scanner/watchlist` with price changes, volume ratios, and confluence scores. | M2 | ORIGINAL_REQUEST R3 |
| 10 | AI Intelligence Telemetry Binding | Bind market regime, B3/B4 scores, and AI risk assessment telemetry to dashboard cards. | M2 | ORIGINAL_REQUEST R3 |
| 11 | OHLCV Candlestick API Feed | Add `/research/candles/{symbol}` endpoint in `v2/api/research_routes.py` returning recent OHLCV bars. | M3 | ORIGINAL_REQUEST R4 |
| 12 | Interactive Trade Chart Plotting Widget | Embed `#trade-chart-container` with Canvas OHLCV candlestick plotter and TP/SL/Entry price overlay markers in Research Hub. | M3 | ORIGINAL_REQUEST R4 |
| 13 | Comprehensive E2E Test Suite | Build opaque-box 4-tier E2E test suite covering all features, boundaries, and acceptance criteria. | M0 | ORIGINAL_REQUEST Verification |
| 14 | 100% Automated Acceptance Verification | Fix stale assertions in `test_v2_dashboard_ui.py` and verify all tests pass 100% under pytest with `--basetemp`. | M4 | ORIGINAL_REQUEST Acceptance |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M0 | E2E Testing Suite (Tiers 1-4) | Design test harness and test cases in `tests/e2e/`, publish `TEST_INFRA.md` & `TEST_READY.md`. | none | IN_PROGRESS |
| M1 | Backend Startup Hydration & Active Positions Routing | Implement features 1, 2, 3, 4, 5 in `v2/services/`, `v2/api/`, `v2/repository/`. | none | PLANNED |
| M2 | Frontend Script, DOM Sync, Capacities & Watchlist | Implement features 6, 7, 8, 9, 10 in `v2/templates/dashboard.html` and schemas. | M1 | PLANNED |
| M3 | Trade Chart Plotting Integration | Implement features 11, 12 in `v2/api/research_routes.py` and `v2/templates/dashboard.html`. | M2 | PLANNED |
| M4 | Final Acceptance & Adversarial Hardening | Implement feature 14, run full pytest suite (100% pass), adversarial coverage audit. | M0, M1, M2, M3 | PLANNED |

---

## Interface Contracts
### `PositionRepository` ↔ `BotPipelineTracker`
- Method: `await position_repo.get_active_positions() -> list[PositionModel]`
- Hydration Signature: `async def sync_from_repository(self, position_repo: PositionRepository) -> None`
- Behavior: Counts active positions grouped by `bot_name` (`STE`, `HDA`, `VCP`, `BBS`), sets `open_positions`, accumulates `capital_deployed`, and sets `current_stage = "position_manager"` with `stage_status = "IN_POSITION"`.

### Main Router ↔ Dashboard Router
- Module: `v2/api/dashboard_routes.py`
- Mount: `router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])`
- Initialization: `init_dashboard_routes(bot_tracker, aggregator)` called within `init_router(...)`.

### `/positions/open` API Endpoint
- Route: `GET /api/v2/positions/open`
- Header: `X-API-Key`
- Response: `list[PositionSchema]` where `status != 'CLOSED'`. Includes `PENDING_ENTRY`, `OPEN`, `PENDING_EXIT`, `CLOSING`.

### Dashboard Overview API Endpoint
- Route: `GET /api/v2/dashboard/overview`
- Response Schema: `DashboardOverviewSchema` containing:
  - `open_positions_count: int`
  - `open_positions: list[dict]`
  - `system_status: str`
  - `execution_fleet: dict`
  - `portfolio: dict`

### Research Candles API Endpoint
- Route: `GET /api/v2/research/candles/{symbol}?interval=1h&limit=50`
- Response: `list[dict]` with fields `[time, open, high, low, close, volume]`.

---

## Code Layout
- `v2/services/dashboard_service/bot_pipeline.py`: Bot pipeline and hydration tracking.
- `v2/services/dashboard_service/service.py`: Dashboard overview aggregation.
- `v2/api/router.py`: FastAPI root router and `/positions/open` handler.
- `v2/api/dashboard_routes.py`: Dashboard fleet, signals, overview routes.
- `v2/api/research_routes.py`: Research candle feed for charting.
- `v2/api/schemas.py`: Schema definitions (`DashboardOverviewSchema`, `ScannedCoinSchema`, etc.).
- `v2/services/portfolio_service/`: Dynamic total equity calculation.
- `v2/templates/dashboard.html`: Single-page application HTML/JS/CSS.
- `tests/test_v2_dashboard_ui.py`: UI and API endpoint unit tests.
- `tests/e2e/`: Opaque-box E2E test suite.

