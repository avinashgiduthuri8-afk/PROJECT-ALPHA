# BRIEFING — 2026-09-11T09:05:42Z

## Mission
Implement Milestone 1: Backend Startup Hydration & Active Positions Routing (Features 1, 2, 3, 4, 5).

## 🔒 My Identity
- Archetype: implementer
- Roles: implementer, qa, specialist
- Working directory: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\worker_m1
- Original parent: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Milestone: M1 (Backend Startup Hydration & Active Positions Routing)

## 🔒 Key Constraints
- Preserve Paper Trading: Do NOT enable live execution. Maintain BotMode.PAPER across all services.
- Data Preservation: Do NOT mutate, delete, or drop historical trades or positions in SQLite.
- Capital Rule: Enforce the unified shared capital pool and ₹200 minimum notional per order across all bots.
- Integrity: No cheats, dummy implementations, or hardcoded test values.
- Scope bounds: Exclusive ownership of specified backend files. DO NOT touch frontend templates or test files.

## Current Parent
- Conversation ID: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Updated: 2026-09-11T09:05:42Z

## Task Summary
- **What to build**:
  1. `BotPipelineTracker.sync_from_repository()` in `v2/services/dashboard_service/bot_pipeline.py` and hook into `v2/app_v2.py` startup lifespan.
  2. Mount `dashboard_router` in `v2/api/router.py` and initialize via `init_dashboard_routes()` in `init_router()`. Unify `/dashboard/overview` schemas.
  3. Update `/positions/open`, `/trading/positions?status=OPEN`, and `/production/status` to use `get_active_positions()` (`status != 'CLOSED'`).
  4. Include `open_positions` and `open_positions_count` in `DashboardService.get_overview()`, `DashboardAggregator`, and `DashboardOverviewSchema`.
  5. Dynamic total equity calculation in `PortfolioAggregator` / `PortfolioService` using `get_active_positions()`.
- **Success criteria**:
  - `py -m pytest tests/test_v2_phase7_dashboard.py tests/test_v2_mark_to_market.py tests/test_v2_portfolio_service.py tests/test_v2_price_precision_and_order_integrity.py --basetemp=.pytest_tmp_m1 -v` passes 100%.
  - Correct hydration on restart with active SQLite positions.
  - Handoff report in `.agents/worker_m1/handoff.md`.
- **Interface contracts**: PROJECT.md § Interface Contracts
- **Code layout**: PROJECT.md § Code Layout

## Key Decisions Made
- Follow Survey Report 2 architecture recommendations for `sync_from_repository`, router mounting, active position queries, and equity calculation.

## Artifact Index
- `.agents/worker_m1/DISPATCH.md` — Assignment instructions
- `.agents/worker_m1/BRIEFING.md` — Working memory and status
- `.agents/worker_m1/progress.md` — Liveness heartbeat and step tracking
- `.agents/worker_m1/handoff.md` — Final handoff report

## Change Tracker
- **Files modified**:
  - `v2/services/dashboard_service/bot_pipeline.py`: Added `sync_from_repository()` to hydrate bot active positions and capital from SQLite.
  - `v2/services/dashboard_service/service.py`: Added `position_repo` argument to `__init__`, hooked `sync_from_repository()` in `start()`, enhanced `get_overview()` with `open_positions`, `open_positions_count`, `active_positions`, `execution_fleet`, and `system_status`.
  - `v2/services/dashboard_service/aggregator.py`: Included `open_positions` and `open_positions_count` in `get_overview_snapshot()` and tracked per-bot active position counts.
  - `v2/api/router.py`: Mounted `dashboard_router`, initialized `init_dashboard_routes()` in `init_router()`, updated `/trading/positions` and `/positions/open` to query `get_active_positions()`.
  - `v2/api/dashboard_routes.py`: Updated `init_dashboard_routes()` to bind `aggregator`, `dashboard_service`, and `bot_tracker`, delegated `get_dashboard_overview()` to `DashboardService.get_overview()`.
  - `v2/api/schemas.py`: Updated `DashboardOverviewSchema` with `open_positions`, `open_positions_count`, `execution_fleet`, `system_status`, and `active_positions`.
  - `v2/api/production_routes.py`: Updated `/production/status` to query `get_active_positions()` for accurate open position count and capital deployment.
  - `v2/services/portfolio_service/service.py`: Updated `get_snapshot()` to query `get_active_positions()`.
  - `v2/services/portfolio_service/aggregator.py`: Implemented dynamic total equity combining cash balance with live mark-to-market valuations and fallback unrealized PnL.
  - `v2/services/trading_service/service.py`: Added bare-coin fallback for INR positions in mark-to-market pricing check (authorized by parent).
  - `v2/app_v2.py`: Passed `position_repo` to `DashboardService`, wired `init_dashboard_routes()`, hooked startup hydration in lifespan.
- **Build status**: 35 passed in 4.63s (100% pass)
- **Pending issues**: None

## Quality Status
- **Build/test result**: PASS (35/35 passing: test_v2_phase7_dashboard, test_v2_mark_to_market, test_v2_portfolio_service, test_v2_price_precision_and_order_integrity)
- **Lint status**: Clean
- **Tests added/modified**: Verified all 35 tests in target suites and verified endpoint responses via FastAPI TestClient

## Loaded Skills
- None
