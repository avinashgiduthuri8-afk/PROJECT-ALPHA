# Handoff Report: Worker M1 (Backend Startup Hydration & Active Positions Routing)

## 1. Observation

1. **BotPipelineTracker Unhydrated on Startup**:
   - In `v2/services/dashboard_service/bot_pipeline.py:131-143`, each bot initialized with `open_positions = 0`, `capital_deployed = 0.0`, `current_stage = "scanner"`, and `stage_status = "IDLE"`. State transitions were only triggered by live EventBus events, meaning server restart discarded in-memory active position states even if SQLite contained active positions.
   - `v2/app_v2.py:254` instantiated `DashboardService` without passing `position_repo` or calling hydration during startup lifespan.

2. **Dashboard Router Missing from Main Router**:
   - In `v2/api/router.py:20`, `from .dashboard_routes import router as dashboard_router, init_dashboard_routes` was imported, but lines 44–46 only mounted `research_router` and `production_router`. `dashboard_router` was never mounted on `router`.
   - `init_dashboard_routes` was never invoked in `v2/api/router.py:init_router()`.

3. **Active Positions Filtering Gap in API Endpoints**:
   - In `v2/api/router.py:653-654`, `/trading/positions` with `status="OPEN"` called `_position_repo.get_open()`, which filtered with `WHERE status='OPEN'`. This excluded valid non-closed active positions in transitional states (e.g. `PENDING_ENTRY`, `CLOSING`).
   - In `v2/api/production_routes.py:77`, `/production/status` queried `_position_repo.get_open()`, resulting in incomplete deployed capital and position count metrics.

4. **Missing Open Positions in Dashboard Overview**:
   - `DashboardService.get_overview()` in `v2/services/dashboard_service/service.py:401-432` and `DashboardAggregator.get_overview_snapshot()` in `v2/services/dashboard_service/aggregator.py:169-178` did not return `open_positions` or `open_positions_count`.
   - `DashboardOverviewSchema` in `v2/api/schemas.py:338-350` did not declare `open_positions`, `open_positions_count`, `execution_fleet`, or `system_status`.

5. **Portfolio Aggregation Omitting Transitional Active Positions**:
   - In `v2/services/portfolio_service/service.py:82`, `get_snapshot()` called `self._position_repo.get_open()`, omitting transitional active positions from MTM valuation and deployed capital.
   - In `v2/services/portfolio_service/aggregator.py:39-43`, if `pos.unrealised_pnl` was None, fallback MTM calculation was missing.
   - In `v2/services/trading_service/service.py:434-440`, mark-to-market pricing check lacked fallback to bare coin keys (`current_prices.get(clean_coin)` / `current_prices.get(pos.coin)`), causing 8 test failures in `test_v2_mark_to_market.py` when test feeds passed bare symbols. Parent authorized adding this safe fallback.

---

## 2. Logic Chain

1. **Hydration Implementation (Feature 1)**:
   - Added `async def sync_from_repository(self, repository_or_positions: Any) -> None` to `BotPipelineTracker` in `v2/services/dashboard_service/bot_pipeline.py`. It queries `get_active_positions()` (`status != 'CLOSED'`), resets counters, accumulates `open_positions` and `capital_deployed`, and transitions stage to `position_manager` with status `IN_POSITION`.
   - Updated `DashboardService.__init__` in `v2/services/dashboard_service/service.py` to accept `position_repo` and invoke `sync_from_repository` in `start()`.
   - In `v2/app_v2.py`, passed `position_repo` to `DashboardService` and added explicit startup hydration call in the lifespan context before serving requests.

2. **Router Mounting & Schema Reconciliation (Feature 2)**:
   - In `v2/api/router.py`, mounted `dashboard_router` via `router.include_router(dashboard_router)`.
   - In `init_router()`, initialized `init_dashboard_routes(aggregator=dash_agg, dashboard_service=dashboard_service, bot_tracker=dash_bot_tracker)`.
   - In `v2/api/dashboard_routes.py`, made `init_dashboard_routes` flexible to accept `(aggregator, dashboard_service, bot_tracker)` or `(bot_tracker, aggregator)` and updated `get_dashboard_overview()` to delegate to `DashboardService.get_overview()`.

3. **Active Positions API Routing (Feature 3)**:
   - In `v2/api/router.py`, updated `get_positions()` for `status in ("OPEN", "ACTIVE")` and `get_open_positions_alias()` (`/positions/open`) to query `_position_repo.get_active_positions()` (`WHERE status != 'CLOSED'`).
   - In `v2/api/production_routes.py:77`, updated `/production/status` to query `_position_repo.get_active_positions()` for accurate open position count and capital deployment calculations.

4. **Overview Schema & Payload Enrichment (Feature 4)**:
   - In `v2/services/dashboard_service/service.py:get_overview()`, fetched active positions from `PositionRepository`, formatting full active position details and returning `open_positions`, `open_positions_count`, `active_positions`, `execution_fleet`, and `system_status`.
   - In `v2/services/dashboard_service/aggregator.py:get_overview_snapshot()`, included `open_positions`, `open_positions_count`, and updated per-bot `active_positions_count` in `fleet_data`.
   - In `v2/api/schemas.py`, updated `DashboardOverviewSchema` to declare `open_positions: list[dict]`, `open_positions_count: int`, `execution_fleet: dict`, `system_status: str`, and `active_positions: list[dict]`.

5. **Dynamic Total Equity & Live Mark-to-Market (Feature 5)**:
   - In `v2/services/portfolio_service/service.py:get_snapshot()`, queried `_position_repo.get_active_positions()` so all active positions contribute to deployed capital and MTM valuation.
   - In `v2/services/portfolio_service/aggregator.py`, calculated `total_mtm`, fallback unrealized PnL (`(mark_price - entry_price) * qty`), null-safe `exit_time` check, and dynamic total AUM/equity ($\text{Cash} + \text{Deployed} + \text{Unrealised} = \text{Cash} + \text{MTM}$).
   - In `v2/services/trading_service/service.py:439`, added bare-coin fallback (`current_prices.get(clean_coin)` / `current_prices.get(pos.coin)`) for INR quote currency lookup.

---

## 3. Caveats

- `v2/templates/dashboard.html` and UI test assertions in `tests/test_v2_dashboard_ui.py` are scoped to Milestones 2 and 4 and were not modified per dispatch constraints.
- Real CoinDCX ticker pricing in live environments will provide full pair symbols (e.g. `BTC/INR` or `B-BTC_INR`); bare-coin key fallback ensures seamless mock testing and resilient mark-to-market updating under all ticker format variations.

---

## 4. Conclusion

All 5 features of Milestone 1 have been successfully implemented, verified, and integrated into PROJECT-ALPHA V2:
1. SQLite active positions hydrate cleanly into `BotPipelineTracker` on startup.
2. `dashboard_router` is mounted into the main FastAPI router with initialized dependencies and unified overview schemas.
3. `/positions/open`, `/trading/positions?status=OPEN`, and `/production/status` consistently route via `get_active_positions()`.
4. `DashboardService.get_overview()` and `DashboardAggregator.get_overview_snapshot()` return complete `open_positions` lists and counts conforming to `DashboardOverviewSchema`.
5. Dynamic total equity and live mark-to-market calculations incorporate all non-closed active positions.

All 35 automated tests across the required verification suites pass 100% with zero failures.

---

## 5. Verification Method

### Automated Test Execution
Run the following test command:
```bash
py -m pytest tests/test_v2_phase7_dashboard.py tests/test_v2_mark_to_market.py tests/test_v2_portfolio_service.py tests/test_v2_price_precision_and_order_integrity.py --basetemp=.pytest_tmp_m1 -v
```

**Verbatim Test Output**:
```
tests/test_v2_phase7_dashboard.py::TestDashboardAggregator::test_aggregator_snapshot_assembly[asyncio] PASSED [  2%]
tests/test_v2_phase7_dashboard.py::TestWebSocketTelemetryGateway::test_ws_gateway_lifecycle_and_delta_broadcast[asyncio] PASSED [  5%]
tests/test_v2_phase7_dashboard.py::TestDashboardAPIEndpoints::test_dashboard_overview_fleet_and_signals_endpoints PASSED [  8%]
tests/test_v2_phase7_dashboard.py::TestDashboardAPIEndpoints::test_fleet_bot_pause_resume_and_emergency_stop PASSED [ 11%]
tests/test_v2_mark_to_market.py::test_a_current_price_updates_on_fresh_ticker[asyncio] PASSED [ 14%]
tests/test_v2_mark_to_market.py::test_b_positive_unrealized_pnl[asyncio] PASSED [ 17%]
tests/test_v2_mark_to_market.py::test_c_negative_unrealized_pnl[asyncio] PASSED [ 20%]
tests/test_v2_mark_to_market.py::test_d_multiple_positions_independent_prices[asyncio] PASSED [ 22%]
tests/test_v2_mark_to_market.py::test_e_trailing_stop_ratchets_and_triggers_exit[asyncio] PASSED [ 25%]
tests/test_v2_mark_to_market.py::test_f_missing_or_zero_ticker_preserves_last_mark[asyncio] PASSED [ 28%]
tests/test_v2_mark_to_market.py::test_g_closed_positions_not_updated[asyncio] PASSED [ 31%]
tests/test_v2_mark_to_market.py::test_h_loop_continues_when_coin_lacks_ticker[asyncio] PASSED [ 34%]
tests/test_v2_mark_to_market.py::test_i_get_open_returns_updated_mark_prices[asyncio] PASSED [ 37%]
tests/test_v2_mark_to_market.py::test_j_portfolio_service_snapshot_aggregates_unrealized[asyncio] PASSED [ 40%]
tests/test_v2_mark_to_market.py::test_k_l_m_core_fields_remain_immutable[asyncio] PASSED [ 42%]
tests/test_v2_portfolio_service.py::test_portfolio_service_initialization[asyncio] PASSED [ 45%]
tests/test_v2_portfolio_service.py::test_portfolio_service_startup[asyncio] PASSED [ 48%]
tests/test_v2_portfolio_service.py::test_portfolio_service_shutdown[asyncio] PASSED [ 51%]
tests/test_v2_portfolio_service.py::test_portfolio_service_lifecycle_idempotency[asyncio] PASSED [ 54%]
tests/test_v2_portfolio_service.py::test_portfolio_service_event_handling[asyncio] PASSED [ 57%]
tests/test_v2_portfolio_service.py::test_portfolio_service_subscriber_registry[asyncio] PASSED [ 60%]
tests/test_v2_price_precision_and_order_integrity.py::test_canonical_price_normalization PASSED [ 62%]
tests/test_v2_price_precision_and_order_integrity.py::test_canonical_quantity_normalization PASSED [ 65%]
tests/test_v2_price_precision_and_order_integrity.py::test_dynamic_precision_inference PASSED [ 68%]
tests/test_v2_price_precision_and_order_integrity.py::test_positive_prices_never_round_to_zero PASSED [ 71%]
tests/test_v2_price_precision_and_order_integrity.py::test_bonk_sub_1_rupee_regression PASSED [ 74%]
tests/test_v2_price_precision_and_order_integrity.py::test_shib_sub_1_rupee_regression PASSED [ 77%]
tests/test_v2_price_precision_and_order_integrity.py::test_pepe_sub_1_rupee_regression PASSED [ 80%]
tests/test_v2_price_precision_and_order_integrity.py::test_validate_trade_parameters PASSED [ 82%]
tests/test_v2_price_precision_and_order_integrity.py::test_ena_inr_vs_ena_usdt_quote_isolation PASSED [ 85%]
tests/test_v2_price_precision_and_order_integrity.py::test_sui_inr_vs_sui_usdt_quote_isolation PASSED [ 88%]
tests/test_v2_price_precision_and_order_integrity.py::test_runtime_price_jump_guard PASSED [ 91%]
tests/test_v2_price_precision_and_order_integrity.py::test_order_rejection_before_dispatch_in_auto_trader PASSED [ 94%]
tests/test_v2_price_precision_and_order_integrity.py::test_subaccount_manager_order_layer_normalization PASSED [ 97%]
tests/test_v2_price_precision_and_order_integrity.py::test_historical_contamination_diagnostic_read_only PASSED [100%]
======================== 35 passed, 1 warning in 4.63s ========================
```

### Direct Endpoint Integration Verification
1. Insert active position into SQLite.
2. Initialize `app_v2.py` / `init_router()`.
3. Query `GET /api/v2/positions/open` -> HTTP 200, active positions returned.
4. Query `GET /api/v2/dashboard/overview` -> HTTP 200, `open_positions_count` matches active positions, `execution_fleet` and `system_status` populated.
5. Query `GET /api/v2/production/status` -> HTTP 200, `open_positions_count` and `capital_pool_deployed` reflect active positions.
