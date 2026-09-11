# SURVEY REPORT: Test Suite, Intelligence & Scanner Telemetry

**Agent**: Survey Explorer 3  
**Working Directory**: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_tests`  
**Target Date**: 2026-09-11  
**Integrity Mode**: Development (Preserve Paper Trading, Data Preservation, ₹200 Minimum Capital Pool)  

---

## Executive Summary

This investigation conducted a comprehensive survey of:
1. The automated test suite with a focus on `tests/test_v2_dashboard_ui.py`, `tests/test_v2_price_precision_and_order_integrity.py`, `tests/test_v2_min_trading_value.py`, `tests/test_v2_c2_scanner.py`, and related test modules.
2. Scanner feeds and API routes (`/scanner/coins`, `/scanner/signals`, `/scanner/watchlist`).
3. AI Intelligence service telemetry (Gemini gating, FallbackEvaluator, circuit breaker, market regime, B3 regime adjustment, B4 dynamic threshold, and risk assessment).
4. Concrete gaps between existing test coverage/system behavior and the acceptance criteria in `ORIGINAL_REQUEST.md`.

---

## 1. Existing Test Suite Analysis

### 1.1 Test Suite Inventory & Execution Results

| Test File | Tests Run | Result | Key Observations & Root Causes |
|---|---|---|---|
| `tests/test_v2_dashboard_ui.py` | 6 | **2 FAILED**, 4 PASSED | **Failure 1**: `test_dashboard_security_elements_rendered` contains contradictory assertions: line 95 `assert "110299" in resp.text` followed by line 97 `assert "110299" not in resp.text`. Line 95 is an obsolete assertion left over from Phase 2 auth hardening.<br>**Failure 2**: `test_set_mode_security_password_protection` line 139 asserts `"Security password required" in resp_live_fail.json()["detail"]`, but actual server response is `"Configured security password required to switch to LIVE mode."` (case mismatch). |
| `tests/test_v2_price_precision_and_order_integrity.py` | 14 | **14 PASSED** (100%) | Robust unit tests covering price/qty normalization, dynamic precision inference, sub-₹1 protections (SHIB, BONK, PEPE), quote-currency isolation (INR vs USDT), runtime price-jump guards, and AutoTradeRouter pre-dispatch rejection. |
| `tests/test_v2_min_trading_value.py` | 4 | **4 PASSED** (100%) | Validates discrete lot steps, boundary checks for the ₹200.00 notional threshold, and quantity round-up logic (`round_qty_up`) in `AutoTradeRouter`. |
| `tests/test_v2_c2_scanner.py` | 17 | **17 PASSED** (100%) | Tests 4-layer evaluation (Chart, Indicator, Sentiment, News), strict rejection gate, max 1–2 signals limit, zero signals on weak market, and cooldown enforcement. |
| `tests/test_v2_scanned_coins_visibility.py` | 3 | **1 FAILED**, 2 PASSED | `test_api_scanned_coins_endpoints` fails (`assert 0 >= 1`) because calling `POST /api/v2/scanner/poll` without mocking external exchange feeds results in 0 scanned coins in an isolated test environment. |
| `tests/test_v2_ai_intelligence.py` | 10 | **10 PASSED** (100%) | Covers Gemini client mock, FallbackEvaluator fallback, circuit breaker state transitions, and event bus emissions (`SIGNAL_AI_EVALUATED`, `SIGNAL_AI_CONFIRMED`, `SIGNAL_AI_REJECTED`). |
| `tests/test_v2_scanner_funnel.py` | 7 | **7 PASSED** (100%) | Validates B3 macro regime adjustment (+/-5 score) and B4 dynamic threshold bounds (80–92). |

### 1.2 Windows Test Runner & Fixture Concurrency Defect
- **Observation**: Running `py -m pytest` without `--basetemp` on Windows results in:
  `PermissionError: [WinError 5] Access is denied: 'C:\Users\ASUS\AppData\Local\Temp\pytest-of-ASUS'`.
- **Root Cause**: Windows user permissions restrict pytest default directory creation under `AppData\Local\Temp`. Furthermore, background pytest processes or unclosed aiosqlite SQLite database files lock files like `test_lifecycle.db` with `WinError 32`.
- **Required Test Runner Command**: Tests MUST always be executed with an explicit `--basetemp`, for example:
  ```powershell
  py -m pytest tests/test_v2_dashboard_ui.py tests/test_v2_price_precision_and_order_integrity.py --basetemp=.pytest_tmp -v
  ```

---

## 2. Scanner Feeds & Route Architecture

### 2.1 Route Mapping in `v2/api/router.py`

| HTTP Route | Method | Handler | Schema / Return Type | Description |
|---|---|---|---|---|
| `/scanner/signals` | GET | `get_signals` | `list[SignalSchema]` | Live signals sorted by score, optional priority filter. |
| `/scanner/signals/{signal_id}` | GET | `get_signal_by_id` | `SignalSchema` | Single live signal lookup by ID. |
| `/scanner/poll` | POST | `trigger_scanner_poll` | `dict` | Manual trigger for scan cycle. |
| `/scanner/refresh` | POST | `trigger_scanner_poll` | `dict` | Alias for manual scan poll. |
| `/scanner/coins` | GET | `get_scanned_coins` | `list[ScannedCoinSchema]` | Returns evaluated coins from the latest scan pass. Supports `min_score`, `limit`, `sort_by`. |
| `/scanner/coins/{symbol}` | GET | `get_scanned_coin_detail` | `ScannedCoinDetailSchema` | Full technical breakdown, MTF alignment, and C2 4-layer score breakdown. |
| `/scanner/health` | GET | `scanner_health` | `ScannerHealthSchema` | Poll count, live signal count, last error. |
| `/scanner/watchlist` | GET | **MISSING** | N/A | **Does not exist in `v2/api/router.py`**. |

### 2.2 Schema Comparison: `ScannedCoinSchema` vs Requirements

| Field | In `ScannedCoinSchema`? | Type | Notes |
|---|---|---|---|
| `symbol` | Yes | `str` | e.g. "BTC" |
| `coin` | Yes | `str` | e.g. "BTC" |
| `pair` | Yes | `str` | e.g. "BTC/INR" |
| `price` | Yes | `float` | Current price |
| `volume_24h` | Yes | `float` | 24h trading volume |
| `volume_ratio` | Yes | `float` | Volume spike ratio |
| `ema_trend` | Yes | `str` | "BULLISH", "BEARISH", "SIDEWAYS" |
| `rsi` | Yes | `float` | RSI (14) value |
| `mtf_alignment` | Yes | `str` | "5m_15m_1h" or "none" |
| `is_mtf_aligned` | Yes | `bool` | True if MTF aligned |
| `confluence_score`| Yes | `int` | Combined 0–100 score |
| `status` | Yes | `str` | "PASSED" or "REJECTED" |
| `accepted` | Yes | `bool` | True if passed strict gate |
| `rejection_reason`| Yes | `Optional[str]`| Semicolon-delimited reasons |
| `evaluated_at` | Yes | `str` | ISO 8601 timestamp |
| **`price_change` / `change_24h`** | **NO** | N/A | **Missing!** Causes frontend `dashboard.html` line 2354 to synthesize fake price change: `((c.volume_ratio - 1) * 2.5)` |

### 2.3 The Missing `/scanner/watchlist` Route
- `ORIGINAL_REQUEST.md` R3 states: "Wire the dashboard watchlist container to live scanner feeds (`/scanner/coins` / `/scanner/watchlist`), populating active universe coins, price change, volume ratios, and confluence scores."
- `ScannerService` has an internal method `_fetch_watchlist_coins()` returning `list[str]` (e.g. `["BTC", "ETH", "SOL", "BNB", "XRP", "ZEC", "AVAX", "LINK", "DOGE", "SHIB", "MATIC"]`).
- However, there is no GET `/scanner/watchlist` endpoint in `v2/api/router.py`. Implementing this endpoint or exposing the watchlist summary with active coins resolves this requirement cleanly.

---

## 3. AI Intelligence Service & Telemetry Architecture

### 3.1 Service Implementation
- **Location**: `v2/services/ai_intelligence_service/service.py` (`AIIntelligenceService`).
- **Gating Logic**: Evaluates candidate signals passing scanner gates using Gemini LLM (`GeminiClient`) or `FallbackEvaluator` if Gemini is disabled or circuit breaker is OPEN.
- **Circuit Breaker**: Tracks consecutive failures (`v2_ai_circuit_breaker_threshold`, default 3) and enters `OPEN` state with cooldown (`v2_ai_circuit_breaker_cooldown_seconds`, default 60s).
- **Confirmation Criteria**:
  - `recommendation in (AIRecommendation.APPROVE, AIRecommendation.SCALE_DOWN)`
  - `confidence_score >= v2_ai_confidence_threshold` (default 70)
- **Persistence**: Records full evaluation in SQLite `ai_analyses` table via `AIAnalysisRepository`.

### 3.2 Macro Regime, B3, B4, and Risk Telemetry Mapping

| Telemetry Concept | Backend Source Component | Key Variables / Formulas | Telemetry Exposure |
|---|---|---|---|
| **Market Regime** | `MarketContextService` (`v2/services/scanner_service/market_context.py`) | BTC & ETH EMA(9) vs EMA(21) + 2-bar momentum -> `RISK_ON` vs `RISK_OFF`. Fear & Greed index (0-100). | `DashboardService.get_telemetry_snapshot()["market_regime"]` (contains `btc_trend`, `eth_trend`, `market_regime`, `fear_and_greed`). |
| **B3 Score Adjustment** | `ConfluenceEngine` (`v2/services/scanner_service/confluence_engine.py:305-313`) | If `RISK_ON` and `BULLISH`: `+5`. If `RISK_OFF` or `BEARISH`: `-5`. If `SIDEWAYS`: `0`. Bounded strictly `[-5, +5]`. | Stored in `ConfluenceResult.regime_adjustment`, included in `Signal.raw_payload["regime_adjustment"]`. |
| **B4 Dynamic Threshold** | `ConfluenceEngine` (`confluence_engine.py:303, 108-140`) | Dynamically adjusts threshold between `[80, 92]` based on volatility (ATR ratio) and chop indicator. | Stored in `ConfluenceResult.dynamic_threshold`, included in `Signal.raw_payload["dynamic_threshold"]`. |
| **Risk Assessment** | `RiskService` (`v2/services/risk_service/service.py`) | `RiskState`: `trading_enabled`, `emergency_stop`, `circuit_breaker_open`, `per_bot_deployed`, `per_bot_open_count`, `total_capital_limit`. | `GET /api/v2/risk/state` and `DashboardService.get_overview()["risk"]`. |

### 3.3 Frontend Telemetry Disconnects in `v2/templates/dashboard.html`
1. **Crypto Market Regime Card (lines 1084–1096)**:
   - Contains hardcoded static values: `<span class="v2-panel-sub text-green">RISK-ON MOMENTUM</span>`, `<span class="market-metric-value text-green font-mono">91%</span>`, etc.
   - None of these DOM nodes have IDs or bindings in `refreshLiveTelemetry()`.
2. **Gemini AI Intelligence Verdict (lines 1377–1390)**:
   - Card has `<span id="si-ai-verdict">APPROVE (87.0% CONVICTION)</span>` and `<ul id="si-catalysts-list">` with hardcoded text.
   - `dashboard.html` JavaScript never updates `si-ai-verdict` or `si-catalysts-list` dynamically from API telemetry.
3. **Watchlist Center (lines 1701–1705)**:
   - Contains only `<p>Active Universe: BTC/INR, ETH/INR, ...</p>` without table structure or live data rendering.

---

## 4. Acceptance Criteria & Gap Analysis

| Acceptance Criteria in `ORIGINAL_REQUEST.md` | Current Implementation Status | Gap & Required Remediation |
|---|---|---|
| **1. Automated Verification: Pytest suites pass 100%** (`test_v2_dashboard_ui.py` + `test_v2_price_precision_and_order_integrity.py`) | **FAILING** | `test_v2_dashboard_ui.py` fails on lines 95 (`assert "110299" in resp.text`) and 139 (`assert "Security password required"` case mismatch). Correcting these 2 lines allows 100% pass rate. |
| **2. Automated Verification: No JS syntax errors or unhandled exceptions** | **PASS (Syntax)** / **PARTIAL (Exceptions)** | Both script blocks in `dashboard.html` compile and execute cleanly in node VM without syntax errors. However, telemetry code must defensively handle missing endpoints or null fields to prevent runtime exceptions. |
| **3. Functional Verification: Application restart hydrates active positions into KPI, tables, and bot fleet cards** | **FAILING** | `BotPipelineTracker` currently does not load active positions on startup. `DashboardService.get_overview()` lacks `open_positions` and `open_positions_count`. |
| **4. API Verification: GET `/api/v2/positions/open` returns all non-closed positions (`status != 'CLOSED'`)** | **FAILING** | `/positions/open` calls `_position_repo.get_open()` (`WHERE status='OPEN'`). It must call `_position_repo.get_active_positions()` (`WHERE status != 'CLOSED'`) so transitional states like `PENDING_ENTRY` and `PENDING_EXIT` are retained. |
| **5. API Verification: GET `/api/v2/dashboard/overview` contains valid `open_positions_count`** | **FAILING** | `DashboardOverviewSchema` and `DashboardService.get_overview()` do not include `open_positions_count` or `open_positions`. `dashboard_routes.py` is not mounted into `v2/api/router.py`. |
| **6. Functional Verification: Watchlist widget displays candidate coins with prices, volume, and confluence scores** | **FAILING** | `#watchlist-center` in `dashboard.html` is static placeholder text. Must be structured into a table populated by live scanner feeds (`/scanner/coins` or `/scanner/watchlist`). |
| **7. Functional Verification: Trade chart panel renders candlesticks and TP/SL levels for active pairs** | **FAILING** | No charting container (`#tradingview_widget` or `#trade-chart-container`) exists in `dashboard.html`. No candlestick endpoint (`/research/candles/{symbol}`) exists. |

---

## 5. Recommended Implementation Roadmap & Test Coverage Plan

### Phase A: Test Suite Fixes & Baseline Green
1. Update `tests/test_v2_dashboard_ui.py`:
   - Remove redundant `assert "110299" in resp.text` at line 95 (keep `assert "110299" not in resp.text`).
   - Fix case-insensitive check in `test_set_mode_security_password_protection` line 139 to match server response `"password required" in resp_live_fail.json()["detail"].lower()`.
2. Verify with test runner:
   ```powershell
   py -m pytest tests/test_v2_dashboard_ui.py tests/test_v2_price_precision_and_order_integrity.py --basetemp=.pytest_tmp -v
   ```

### Phase B: Backend Routing & Schema Updates
1. In `v2/api/router.py`:
   - Update `/positions/open` handler to invoke `_position_repo.get_active_positions()` instead of `_position_repo.get_open()`.
   - Mount `dashboard_routes` (`router.include_router(dashboard_router)`) and initialize with aggregator.
   - Add GET `/scanner/watchlist` endpoint returning active monitored coins with metadata.
   - Add GET `/research/candles/{symbol}` endpoint returning OHLCV candles for charting.
2. In `v2/api/schemas.py`:
   - Add `price_change_pct: float = 0.0` to `ScannedCoinSchema`.
   - Add `open_positions: Optional[list[dict[str, Any]]] = Field(default_factory=list)` and `open_positions_count: int = 0` to `DashboardOverviewSchema`.
3. In `v2/services/dashboard_service/service.py`:
   - Add `open_positions` and `open_positions_count` to `get_overview()`.
4. In `v2/services/scanner_service/service.py`:
   - Populate `change_24h` / `price_change` into `eval_item` snapshot.

### Phase C: Dashboard UI & Telemetry Synchronization
1. In `v2/templates/dashboard.html`:
   - Bind `#watchlist-center` to render active candidate coins, prices, volume ratios, and confluence scores.
   - Add DOM element IDs to the "Crypto Market Regime" panel (`#regime-badge`, `#regime-market-strength`, `#regime-btc-trend`, `#regime-eth-trend`) and update them dynamically from `status.telemetry.market_regime` or `/dashboard/overview`.
   - Bind `#si-ai-verdict` and `#si-catalysts-list` dynamically to AI Intelligence telemetry.
   - Embed lightweight canvas/TradingView charting container (`#tradingview_widget` or `#trade-chart-container`) in the deep dive / trade constructor panel with Entry, SL, and TP overlay markers.

### Phase D: Automated Verification Tests to Add
1. `tests/test_v2_active_positions_hydration.py`:
   - Test inserting positions with statuses `OPEN`, `PENDING_ENTRY`, `PENDING_EXIT`, `CLOSED`.
   - Verify `GET /api/v2/positions/open` returns exactly the 3 non-closed positions.
   - Verify `GET /api/v2/dashboard/overview` returns `open_positions_count == 3`.
2. `tests/test_v2_watchlist_and_telemetry.py`:
   - Verify `GET /api/v2/scanner/watchlist` returns active universe coins.
   - Verify `ScannedCoinSchema` contains valid `price_change_pct` and `confluence_score`.
   - Verify `GET /api/v2/research/candles/{symbol}` returns valid OHLCV candle arrays.
