# Orchestration Plan: PROJECT-ALPHA Remaining Platform & UI Issues

## Objective
Fully resolve issues #6, #7, #8, #9, #10, #11, #13, #15, #16 in accordance with `ORIGINAL_REQUEST.md`, preserving paper trading mode, database state, and capital rules.

## Step 0: Survey & Scoping
1. Dispatch 3 Explorers:
   - Explorer 1 (Frontend & UI): Inspect `v2/templates/dashboard.html`, DOM synchronization, variable conflicts, chart panel, watchlist widget, telemetry UI bindings.
   - Explorer 2 (Backend Startup Hydration & Routing): Inspect `BotPipelineTracker`, `PositionRepository`, `v2/api/router.py`, `dashboard_routes`, `/positions/open`, `DashboardService.get_overview()`, capital calculation.
   - Explorer 3 (Test Suite & Intelligence/Scanner Telemetry): Inspect existing tests (`test_v2_dashboard_ui.py`, `test_v2_price_precision_and_order_integrity.py`, `test_v2_min_trading_value.py`, `test_v2_c2_scanner.py`), scanner/intelligence routes and models.
2. Aggregate Explorer findings into `PROJECT.md` with full architecture, feature inventory, code layout, interface contracts, and milestone plan.

## Step 1: Decomposition & Dual Track Setup
- Track 1 (Implementation): Decompose into modular milestones (e.g., M1: Frontend Syntax & Telemetry DOM Sync, M2: Backend Startup Hydration & Positions API Routing, M3: Intelligence & Watchlist Live Feeds, M4: Trade Chart Plotting Widget, M5: E2E Integration & Final Verification).
- Track 2 (E2E Testing): Design comprehensive test coverage (Tiers 1-4) published in `TEST_READY.md`.

## Step 2: Milestone Iteration Loops
For each milestone:
- Spawn Explorers (recommend strategy)
- Spawn Worker (implement + verify unit tests, enforce anti-cheat)
- Spawn Reviewers x2 (independent verification)
- Spawn Challengers x2 (stress test / property check)
- Spawn Forensic Auditor (integrity verification, binary veto)
- Gate Check (`GATE_STATUS.md`)

## Step 3: Final Acceptance & Reporting
- Run full pytest test suites (100% pass)
- Verify functional acceptance criteria
- Report completion to Sentinel

