# BRIEFING — 2026-09-11T09:02:00Z

## Mission
Survey the backend codebase for R2: Backend Startup Hydration & Active Positions Routing (Issues #6, #7, #9, #10).

## 🔒 My Identity
- Archetype: explorer
- Roles: Backend Startup Hydration & Routing Explorer
- Working directory: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_backend
- Original parent: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Milestone: Survey & Investigation

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Preserve Paper Trading: Do NOT enable live execution. Maintain BotMode.PAPER across all services.
- Data Preservation: Do NOT mutate, delete, or drop historical trades or positions in SQLite.
- Capital Rule: Enforce unified shared capital pool and ₹200 minimum notional per order across all bots.

## Current Parent
- Conversation ID: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `v2/services/dashboard_service/bot_pipeline.py`: `BotPipelineTracker`, `BotState`
  - `v2/services/dashboard_service/service.py`: `DashboardService`, `get_overview()`
  - `v2/services/dashboard_service/aggregator.py`: `DashboardAggregator`, `get_overview_snapshot()`
  - `v2/repository/position_repo.py`: `PositionRepository`, `get_active_positions()`
  - `v2/services/trading_service/position_manager.py`: `PositionManager`, `PositionState`
  - `v2/services/trading_service/recovery.py`: `RestartRecoveryService`
  - `v2/api/router.py`: Router mounting, `get_positions()`, `get_open_positions_alias()`
  - `v2/api/dashboard_routes.py`: `dashboard_router`, `init_dashboard_routes`
  - `v2/api/production_routes.py`: `/production/status`, `get_production_status()`
  - `v2/api/schemas.py`: `DashboardOverviewSchema`, `PositionSchema`
  - `v2/services/portfolio_service/service.py` & `aggregator.py`: `PortfolioService`, `PortfolioAggregator`
  - `v2/app_v2.py`: Lifespan startup sequence
- **Key findings**:
  - `BotPipelineTracker` initializes with 0s and is never hydrated on server restart; requires `sync_from_repository()` querying `PositionRepository.get_active_positions()`.
  - `dashboard_routes.py` (which has `/fleet`, `/signals`, `/emergency-stop`, etc.) is imported in `v2/api/router.py` but never mounted via `router.include_router(dashboard_router)`.
  - `/positions/open` calls `get_positions(status="OPEN")` which uses `_position_repo.get_open()` (`status='OPEN'`), omitting transitional active states like `PENDING_ENTRY` and `CLOSING`.
  - `DashboardService.get_overview()` omits `open_positions` and `open_positions_count`, and `DashboardOverviewSchema` lacks these fields.
  - Dynamic total equity calculation: Total Equity = Cash Balance + Active Positions MTM Valuations - Statutory Drag (Friction). `PortfolioAggregator` must be aligned with active positions.
- **Unexplored areas**: None for R2 scope.

## Key Decisions Made
- Fully documented all 5 investigation points with exact file paths, line numbers, and proposed implementation code blocks.

## Artifact Index
- DISPATCH.md — Dispatch instructions and mission description
- BRIEFING.md — Persistent working memory and state
- progress.md — Liveness heartbeat and progress log
- survey_report.md — Comprehensive technical investigation report for R2
- handoff.md — Standard 5-component handoff report
