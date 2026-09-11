# Handoff Report: Backend Startup Hydration & Active Positions Routing (R2)

**Agent**: Survey Explorer 2 (Backend Startup Hydration & Routing)  
**Date**: 2026-09-11  
**Working Directory**: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_backend`  
**Parent Conversation ID**: `23cd86ea-b363-4f96-89b2-56b04249c4b8`  

---

## 1. Observation

1. **`BotPipelineTracker` Initialization**:
   - In `v2/services/dashboard_service/bot_pipeline.py:246-254`, `BotPipelineTracker.__init__` instantiates `BotState` for `STE`, `HDA`, `VCP`, `BBS`.
   - In `v2/services/dashboard_service/bot_pipeline.py:128-143`, each `BotState` defaults to:
     ```python
     self.current_stage = "scanner"
     self.stage_status = "IDLE"
     self.open_positions = 0
     self.capital_deployed = 0.0
     ```
   - Counters are only incremented/decremented when `POSITION_OPENED` or `POSITION_CLOSED` bus events occur while running (`bot_pipeline.py:355-390`). There is no startup routine to read positions from SQLite.
2. **`v2/api/router.py` Router Mounting**:
   - In `v2/api/router.py:20`:
     `from .dashboard_routes import router as dashboard_router, init_dashboard_routes`
   - In `v2/api/router.py:44-46`:
     ```python
     router = APIRouter()
     router.include_router(research_router, prefix="/research", tags=["research"])
     router.include_router(production_router, prefix="/production", tags=["production"])
     ```
     `dashboard_router` is NOT mounted to `router`.
   - In `v2/api/router.py:78-154`: `init_router()` does not call `init_dashboard_routes()`.
   - In `v2/api/dashboard_routes.py:16-134`: `router = APIRouter(prefix="/dashboard", tags=["dashboard"])` defines `/overview`, `/fleet`, `/signals`, `/fleet/{bot_name}/pause`, `/fleet/{bot_name}/resume`, and `/emergency-stop`.
3. **`/positions/open` Query Logic**:
   - In `v2/api/router.py:688-690`:
     ```python
     async def get_open_positions_alias() -> list[PositionSchema]:
         """Convenience alias for /trading/positions?status=OPEN."""
         return await get_positions(status="OPEN")
     ```
   - In `v2/api/router.py:653-654`:
     ```python
     if status and status.upper() == "OPEN":
         positions = await _position_repo.get_open()
     ```
   - In `v2/repository/position_repo.py:147-158`:
     `get_open()` executes `SELECT * FROM positions WHERE status='OPEN' ORDER BY entry_time DESC`.
   - In `v2/services/trading_service/position_manager.py:38-43`:
     `PositionState` has states `PENDING_ENTRY`, `OPEN`, `PENDING_EXIT`, `CLOSED`.
   - In `v2/repository/position_repo.py:177-189`:
     `get_active_positions()` executes `SELECT * FROM positions WHERE status != 'CLOSED' ORDER BY entry_time DESC`.
   - In `v2/api/production_routes.py:77`: `open_pos = await _position_repo.get_open()` also uses `get_open()`.
4. **`DashboardService.get_overview()` Payload**:
   - In `v2/services/dashboard_service/service.py:392-432`: `get_overview()` returns a dict with `status`, `active_ws_clients`, `portfolio`, `risk`, `shadow`, `subsystems`, `pipeline_stages`, `bots`, `scanned_coins`, `watchlist_summary`, `telemetry`. It does NOT return `open_positions` or `open_positions_count`.
   - In `v2/api/schemas.py:338-350`: `DashboardOverviewSchema` does not have `open_positions` or `open_positions_count`.
5. **Portfolio Aggregation & Equity Calculation**:
   - In `v2/services/portfolio_service/service.py:82`: `open_positions = await self._position_repo.get_open()`.
   - In `v2/services/portfolio_service/aggregator.py:39-48`:
     ```python
     deployed = pos.deployed_capital
     total_deployed += deployed
     ...
     total_cash = max(0.0, base_cash + total_realised - total_deployed)
     total_aum = total_cash + total_deployed + total_unrealised
     ```

---

## 2. Logic Chain

1. From Observation 1, because `BotPipelineTracker` initializes in-memory counters to 0 and only updates them via runtime `POSITION_OPENED` / `POSITION_CLOSED` bus events, any server restart wipes the in-memory state. Active positions in SQLite are not reflected in the bot cards (`0 / 3`) or KPI metrics until a new trade is placed. Adding an asynchronous `sync_from_repository(position_repo)` routine on `BotPipelineTracker` that queries `get_active_positions()` resolves this state loss.
2. From Observation 2, `dashboard_router` was imported at the top of `v2/api/router.py` but never registered via `router.include_router(dashboard_router)`. As a result, `/api/v2/dashboard/fleet`, `/api/v2/dashboard/signals`, pause/resume, and `/emergency-stop` endpoints were unreachable in the main application. Mounting `dashboard_router` and initializing its aggregator dependencies in `init_router()` will restore full command-and-control functionality.
3. From Observation 3, when `/positions/open` and `/trading/positions?status=OPEN` query `_position_repo.get_open()`, they filter exclusively for `status='OPEN'`. Any position transitioning through `PENDING_ENTRY` or `CLOSING` is dropped from API responses, UI tables, and `/production/status`. Switching these queries to `_position_repo.get_active_positions()` ensures all non-`CLOSED` positions (`status != 'CLOSED'`) are consistently returned.
4. From Observation 4, `DashboardService.get_overview()` omits `open_positions` and `open_positions_count`, causing frontend dashboards to lack direct position data in their initial overview payload. Querying active positions from `PositionRepository` and including them in `get_overview()` and `DashboardOverviewSchema` directly satisfies requirement R2 and acceptance criterion #56.
5. From Observation 5, dynamic total equity combining cash balances, live mark-to-market valuations, and statutory friction costs is calculated as $\text{Total Equity} = \text{Total Cash} + \text{Total MTM} - \text{Total Friction}$. `PortfolioService.get_snapshot()` must query `get_active_positions()` so that non-`OPEN` active positions are incorporated into AUM, cash, and deployed capital.

---

## 3. Caveats

- In `tests/test_v2_dashboard_ui.py:95-97`, there is a known contradictory assertion (`assert "110299" in resp.text` and `assert "110299" not in resp.text`), which is part of the frontend survey/fix scope.
- In `v2/api/dashboard_routes.py` vs `v2/api/router.py`, both define `GET /dashboard/overview`. When `dashboard_router` is mounted, `DashboardAggregator.get_overview_snapshot()` and `DashboardService.get_overview()` must return unified superset fields (`status: "ok"`, `system_status: "OPERATIONAL"`, `execution_fleet`, `pipeline_stages`, `open_positions`, `open_positions_count`) to satisfy both `test_v2_phase7_dashboard.py` and `test_v2_pipeline_dashboard.py`.
- No database migrations are required; the `positions` SQLite table already possesses `status`, `current_price`, `unrealised_pnl`, `qty`, and `entry_price`.

---

## 4. Conclusion

All 5 areas of Requirement R2 have been surveyed and their technical solutions fully designed:
1. Implement `BotPipelineTracker.sync_from_repository(position_repo)` and invoke it during `app_v2.py` lifespan startup.
2. Mount `dashboard_router` in `v2/api/router.py` and wire `init_dashboard_routes` into `init_router()`.
3. Update `/positions/open`, `/trading/positions?status=OPEN`, and `/production/status` to query `PositionRepository.get_active_positions()` (`status != 'CLOSED'`).
4. Add `open_positions` and `open_positions_count` to `DashboardService.get_overview()`, `DashboardAggregator.get_overview_snapshot()`, and `DashboardOverviewSchema`.
5. Update `PortfolioService.get_snapshot()` to use `get_active_positions()` and enforce dynamic total equity calculation in `PortfolioAggregator`.

Detailed code blocks, signatures, and diff proposals are documented in `.agents/explorer_survey_backend/survey_report.md`.

---

## 5. Verification Method

To verify the proposed implementation once applied:
1. **Automated Unit Tests**:
   - `py -m pytest tests/test_v2_phase7_dashboard.py --basetemp=.pytest_tmp_dash -v`
   - `py -m pytest tests/test_v2_mark_to_market.py --basetemp=.pytest_tmp_mtm -v`
   - `py -m pytest tests/test_v2_portfolio_service.py --basetemp=.pytest_tmp_port -v`
   - `py -m pytest tests/test_v2_pipeline_dashboard.py --basetemp=.pytest_tmp_pipe -v`
2. **API Endpoint Verification**:
   - `GET /api/v2/positions/open` with `X-API-Key`: verify HTTP 200 and presence of positions with `status = 'PENDING_ENTRY'`.
   - `GET /api/v2/dashboard/overview`: verify HTTP 200, `"open_positions_count": N`, and `"open_positions"` contains active positions list.
   - `GET /api/v2/dashboard/fleet`: verify HTTP 200 and execution fleet states.
   - `POST /api/v2/dashboard/emergency-stop`: verify HTTP 200 and system status trips to `EMERGENCY_STOP`.
3. **Invalidation Condition**:
   - If restarting the server with open positions in SQLite results in `kpi-openpos` showing `0` or `/api/v2/positions/open` dropping a `PENDING_ENTRY` position, the verification has failed.
