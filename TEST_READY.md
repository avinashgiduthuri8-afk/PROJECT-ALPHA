# TEST READY: PROJECT-ALPHA V2 E2E Test Suite (Milestone M0)

**Status**: READY  
**Generated Date**: 2026-09-11  
**Author**: E2E Test Writer (Milestone M0)  
**Primary Suite Target**: `tests/e2e/test_v2_e2e_platform.py`  
**Execution Verification**: 137 / 137 PASSED (100% pass rate, 0 failures, 0 errors)

---

## 1. Test Suite Overview & Execution

The End-to-End (E2E) test suite for PROJECT-ALPHA V2 has been designed, implemented, and verified in `tests/e2e/test_v2_e2e_platform.py`. The suite adheres to the specifications defined in `ORIGINAL_REQUEST.md`, `PROJECT.md`, and `TEST_INFRA.md`.

### Pytest Execution Command
```bash
py -m pytest tests/e2e/test_v2_e2e_platform.py --basetemp=.pytest_tmp_e2e -v
```

### Execution Results
- **Total Tests Executed**: 137
- **Passed**: 137
- **Failed**: 0
- **Duration**: ~9.7 seconds
- **Exit Code**: 0

---

## 2. Feature Inventory & Coverage Mapping (Tiers 1–4)

All 12 core features from `TEST_INFRA.md` are comprehensively tested across all four tiers:

| Feature # | Feature Description | Requirement Source | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Workload) |
|---|---|---|:---:|:---:|:---:|:---:|
| **F1** | SQLite Active Position Hydration | ORIGINAL_REQUEST R2 | 5 (`t1_1`–`t1_5`) | 5 (`t2_1`–`t2_5`) | ✓ (`t3_1`, `t3_2`, `t3_3`, `t3_4`) | ✓ (Scenario 1, 2) |
| **F2** | Main Router Dashboard Routes Mount | ORIGINAL_REQUEST R2 | 5 (`t1_6`–`t1_10`) | 5 (`t2_6`–`t2_10`) | ✓ (`t3_1`, `t3_7`) | ✓ (Scenario 1) |
| **F3** | `/positions/open` Non-Closed Filter | ORIGINAL_REQUEST R2 | 5 (`t1_11`–`t1_15`) | 5 (`t2_11`–`t2_15`) | ✓ (`t3_1`, `t3_5`) | ✓ (Scenario 1, 2) |
| **F4** | Dashboard Overview Counts & Positions | ORIGINAL_REQUEST R2 | 5 (`t1_16`–`t1_20`) | 5 (`t2_16`–`t2_20`) | ✓ (`t3_2`, `t3_7`) | ✓ (Scenario 1, 2, 3) |
| **F5** | Dynamic Equity & Capital Calculation | ORIGINAL_REQUEST R2 | 5 (`t1_21`–`t1_25`) | 5 (`t2_21`–`t2_25`) | ✓ (`t3_3`, `t3_5`, `t3_11`) | ✓ (Scenario 2, 3) |
| **F6** | Frontend Script & Modal Syntax | ORIGINAL_REQUEST R1 | 5 (`t1_26`–`t1_30`) | 5 (`t2_26`–`t2_30`) | ✓ (`t3_8`) | ✓ (Scenario 1) |
| **F7** | Dashboard Telemetry DOM Sync | ORIGINAL_REQUEST R1 | 5 (`t1_31`–`t1_35`) | 5 (`t2_31`–`t2_35`) | ✓ (`t3_7`) | ✓ (Scenario 1) |
| **F8** | Fleet Bot Capacity & Count Alignment | ORIGINAL_REQUEST R1 | 5 (`t1_36`–`t1_40`) | 5 (`t2_36`–`t2_40`) | ✓ (`t3_4`, `t3_6`, `t3_8`) | ✓ (Scenario 1) |
| **F9** | Watchlist Live Scanner Feed Wiring | ORIGINAL_REQUEST R3 | 5 (`t1_41`–`t1_45`) | 5 (`t2_41`–`t2_45`) | ✓ (`t3_9`) | ✓ (Scenario 4) |
| **F10** | AI Intelligence Telemetry Binding | ORIGINAL_REQUEST R3 | 5 (`t1_46`–`t1_50`) | 5 (`t2_46`–`t2_50`) | ✓ (`t3_9`) | ✓ (Scenario 4) |
| **F11** | OHLCV Candlestick API Feed | ORIGINAL_REQUEST R4 | 5 (`t1_51`–`t1_55`) | 5 (`t2_51`–`t2_55`) | ✓ (`t3_10`) | ✓ (Scenario 5) |
| **F12** | Interactive Trade Chart Widget | ORIGINAL_REQUEST R4 | 5 (`t1_56`–`t1_60`) | 5 (`t2_56`–`t2_60`) | ✓ (`t3_10`) | ✓ (Scenario 5) |

### Tier Breakdown
- **Tier 1 (Feature Coverage)**: 60 tests (`TestTier1*`, 5 tests per feature) verifying happy path API responses, contracts, and HTML structural requirements.
- **Tier 2 (Boundary & Corner Cases)**: 60 tests (`TestTier2*`, 5 tests per feature) stress-testing zero/negative balances, unknown pairs, malformed query params, extreme price movements, and DOM fallback states.
- **Tier 3 (Pairwise Interactions)**: 12 tests (`TestTier3PairwiseInteractions`) verifying cross-module invariants (e.g. SQLite hydration aligning with overview API counts, bot pause states reflecting across telemetry, mode switching security pin isolation, scanner confluence feeding AI gating).
- **Tier 4 (Real-World Workloads)**: 5 end-to-end scenario workflows (`TestTier4RealWorldScenarios`):
  1. *Scenario 1*: Cold server restart with active positions restoring SQLite state into `BotPipelineTracker`, API reflection, and UI DOM fleet cards.
  2. *Scenario 2*: Multi-stage position transition lifecycle (`PENDING_ENTRY` → `OPEN` → `CLOSING` → `CLOSED`), ensuring non-closed filtering and realized equity updates.
  3. *Scenario 3*: Dynamic portfolio mark-to-market valuation with friction calculations under fluctuating coin prices.
  4. *Scenario 4*: Live scanner ingestion to watchlist UI rendering with confluence scoring and AI gating.
  5. *Scenario 5*: Research candlestick data hydration and technical charting markers (Entry, Stop-Loss, Take-Profit).

---

## 3. Discovered Implementation Defects (Escalations)

During test design and execution against the existing codebase, the following implementation issue was identified and is escalated to the implementing agent:

### Defect 1: Missing Column `realized_pnl` in `positions` Table After Migrations
- **Location**: `v2/repository/migrations/007_execution_positions.sql` vs `v2/repository/migrations/001_core_tables.sql`
- **Component**: `v2.repository.position_repository.PositionRepository.update_status()`
- **Symptom**: When closing a position via `update_status(..., status="CLOSED", realized_pnl=...)`, SQLite raises:
  `sqlite3.OperationalError: no such column: realized_pnl`
- **Root Cause**: `001_core_tables.sql` creates the `positions` table without a `realized_pnl` column. `007_execution_positions.sql` includes `CREATE TABLE IF NOT EXISTS positions (... realized_pnl REAL DEFAULT 0.0 ...)`. In SQLite, `CREATE TABLE IF NOT EXISTS` is a no-op if the table already exists, so the `realized_pnl` column is never added to the schema.
- **Recommended Fix**: Add a schema migration or alter statement:
  ```sql
  ALTER TABLE positions ADD COLUMN realized_pnl REAL DEFAULT 0.0;
  ```
  or include `realized_pnl` in the initial `CREATE TABLE positions` in `001_core_tables.sql`.

---

## 4. Test Infrastructure Compliance

- **Opaque-Box Testing**: All tests interact strictly via FastAPI route handlers (`TestClient`), standard SQLite schema queries, and DOM/JS template parsing (`dashboard.html`).
- **Data Safety**: All tests run against isolated temporary SQLite files generated per test/module (`tmp_path / "v2_test.db"`), leaving real SQLite databases untouched.
- **Paper Trading Safety**: All tests enforce `BotMode.PAPER` or shadow execution to prevent accidental live exchange operations.
