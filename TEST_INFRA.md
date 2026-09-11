# E2E Test Infra: PROJECT-ALPHA V2 Platform & UI Fixes

## Test Philosophy
- Opaque-box, requirement-driven. Derives from `ORIGINAL_REQUEST.md` and user-facing contracts.
- Independent of internal class details: tests exercise FastAPI endpoints, SQLite database state hydration across restarts, and HTML template DOM integrity.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing.

## Feature Inventory & Test Coverage Map
| # | Feature | Source (Requirement) | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Workload) |
|---|---------|----------------------|:-----------------:|:-----------------:|:-----------------:|:-----------------:|
| 1 | SQLite Active Position Hydration | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ |
| 2 | Main Router Dashboard Routes Mount | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ |
| 3 | `/positions/open` Non-Closed Status Filter | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ |
| 4 | Dashboard Overview Positions & Counts | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ |
| 5 | Dynamic Equity & Capital Calculation | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ |
| 6 | Frontend Script & Modal Syntax | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ |
| 7 | Dashboard Telemetry DOM Synchronization | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ |
| 8 | Fleet Bot Capacity & Count Alignment | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ |
| 9 | Watchlist Live Scanner Feed Wiring | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ | ✓ |
| 10 | AI Intelligence Telemetry Binding | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ | ✓ |
| 11 | OHLCV Candlestick API Feed | ORIGINAL_REQUEST R4 | 5 | 5 | ✓ | ✓ |
| 12 | Interactive Trade Chart Widget | ORIGINAL_REQUEST R4 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Runner**: Pytest invocation: `py -m pytest tests/e2e/ tests/test_v2_dashboard_ui.py tests/test_v2_price_precision_and_order_integrity.py --basetemp=.pytest_tmp -v`.
- **E2E Test Directory**: `tests/e2e/test_v2_e2e_platform.py`
- **Pass/Fail Semantics**: 100% pass, zero errors, exit code 0.
- **Fixture Support**: Isolated temporary SQLite test databases and FastAPI `TestClient` / `AsyncClient`.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Server Cold Restart with Active Positions | F1, F3, F4, F7, F8 (SQLite hydration, API reflection, bot cards capacity) | High |
| 2 | Multi-Stage Position Transition Lifecycle | F1, F3, F4, F5 (PENDING_ENTRY → OPEN → CLOSING → CLOSED) | High |
| 3 | Dynamic Portfolio Mark-to-Market & Friction Adjustment | F4, F5 (Cash, deployed capital, MTM valuation, dynamic equity calculation) | High |
| 4 | Live Scanner to Watchlist Feed Ingestion | F9, F10 (Scanner feeds, price change pct, confluence score, DOM table) | Medium |
| 5 | Research Hub Candlestick & Marker Charting | F11, F12 (Candle API, Canvas/TradingView container, Entry/SL/TP levels) | Medium |

## Coverage Thresholds
- Tier 1: ≥60 tests (5 × 12 features)
- Tier 2: ≥60 boundary & edge condition tests
- Tier 3: Pairwise cross-feature interactions
- Tier 4: ≥5 realistic end-to-end workload workflows
- Acceptance Target: 100% tests passing on automated run.

