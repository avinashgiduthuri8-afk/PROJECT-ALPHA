# DISPATCH: Worker M1 (Backend Startup Hydration & Active Positions Routing)

**Working Directory**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\worker_m1
**Original Request**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md
**Project Plan**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\PROJECT.md
**Backend Survey Report**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_backend\survey_report.md
**Project Workspace**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA

## Mission
Implement Milestone 1 (Features 1, 2, 3, 4, 5) per `PROJECT.md` and `ORIGINAL_REQUEST.md § R2`:
1. `BotPipelineTracker` (`v2/services/dashboard_service/bot_pipeline.py`):
   - Add `async def sync_from_repository(self, position_repo: PositionRepository) -> None` to hydrate active positions count and deployed capital from SQLite (`get_active_positions()`). Group by bot (`STE`, `HDA`, `VCP`, `BBS`), set `open_positions`, `capital_deployed`, and transition stage to `position_manager` with status `IN_POSITION` if positions exist.
   - Hook `sync_from_repository` in `v2/app_v2.py` during startup lifespan.
2. Main Router Mounting (`v2/api/router.py` & `v2/api/dashboard_routes.py`):
   - Mount `dashboard_router` via `router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])`.
   - In `init_router()`, call `init_dashboard_routes(bot_tracker, aggregator)` to bind dependencies.
   - Ensure `/dashboard/overview` in `dashboard_routes.py` returns unified schema with `DashboardService.get_overview()`.
3. `/positions/open` endpoint (`v2/api/router.py`):
   - In `get_open_positions_alias()` and `/trading/positions` when `status="OPEN"`, query `_position_repo.get_active_positions()` (`WHERE status != 'CLOSED'`) so transitional states like `PENDING_ENTRY` and `CLOSING` are never dropped. Also check `v2/api/production_routes.py`.
4. Dashboard Overview Payload (`v2/services/dashboard_service/service.py` & `v2/api/schemas.py`):
   - Update `DashboardService.get_overview()` and `DashboardAggregator.get_overview_snapshot()` to include `open_positions` and `open_positions_count`.
   - Update `DashboardOverviewSchema` in `v2/api/schemas.py` to declare `open_positions: list[dict] = Field(default_factory=list)` and `open_positions_count: int = 0`.
5. Dynamic Total Equity Calculation (`v2/services/portfolio_service/`):
   - Ensure dynamic Total Equity = Total Cash + Total MTM - Total Friction.
   - In `PortfolioService.get_snapshot()`, query `get_active_positions()` so all active positions contribute to deployed capital, MTM, and equity.

You own the following files exclusively:
- `v2/services/dashboard_service/bot_pipeline.py`
- `v2/services/dashboard_service/service.py`
- `v2/services/portfolio_service/service.py`
- `v2/services/portfolio_service/aggregator.py`
- `v2/api/router.py`
- `v2/api/dashboard_routes.py`
- `v2/api/schemas.py`
- `v2/app_v2.py`
- `v2/api/production_routes.py`

DO NOT touch any frontend templates or test files.
Run the existing test suites (`tests/test_v2_phase7_dashboard.py`, `tests/test_v2_mark_to_market.py`, `tests/test_v2_portfolio_service.py`, `tests/test_v2_price_precision_and_order_integrity.py` with `--basetemp=.pytest_tmp_m1 -v`) to verify your implementation.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

