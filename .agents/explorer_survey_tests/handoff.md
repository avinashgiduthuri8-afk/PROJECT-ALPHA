# HANDOFF REPORT: Survey Explorer 3 (Test Suite, Intelligence & Scanner Telemetry)

**Sender**: Survey Explorer 3  
**Working Directory**: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_tests`  
**Original Parent Conversation ID**: `23cd86ea-b363-4f96-89b2-56b04249c4b8`  
**Full Report**: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_tests\survey_report.md`  

---

## 1. Observation

1. **Test Suite Execution & Status**:
   - `tests/test_v2_dashboard_ui.py`: Ran with command `py -m pytest tests/test_v2_dashboard_ui.py --basetemp=.pytest_tmp_exp3 -v`. Result: 2 FAILED, 4 PASSED.
     - **Failure 1**: Line 95 contains `assert "110299" in resp.text`, while line 97 contains `assert "110299" not in resp.text`. This is an obsolete leftover assertion from Phase 2 auth hardening.
     - **Failure 2**: Line 139 contains `assert "Security password required" in resp_live_fail.json()["detail"]`. The actual API return is `"Configured security password required to switch to LIVE mode."` (case mismatch).
   - `tests/test_v2_price_precision_and_order_integrity.py`: 14/14 PASSED (100%).
   - `tests/test_v2_min_trading_value.py`: 4/4 PASSED (100%).
   - `tests/test_v2_c2_scanner.py`: 17/17 PASSED (100%).
   - Windows fixture defect: Running pytest without `--basetemp` throws `PermissionError: [WinError 5] Access is denied: 'C:\Users\ASUS\AppData\Local\Temp\pytest-of-ASUS'`.
2. **Scanner Feeds & Endpoints**:
   - `v2/api/router.py` lines 315–331 implements `GET /scanner/coins`, returning `list[ScannedCoinSchema]`.
   - `ScannedCoinSchema` (`v2/api/schemas.py:406-422`) includes `symbol`, `coin`, `pair`, `price`, `volume_24h`, `volume_ratio`, `ema_trend`, `rsi`, `mtf_alignment`, `is_mtf_aligned`, `confluence_score`, `status`, `accepted`, `rejection_reason`, `evaluated_at`. It **lacks** `price_change_pct` / `change_24h`.
   - In `v2/templates/dashboard.html` line 2354, price change is artificially synthesized because of this missing field:
     `const changePct = c.volume_ratio ? ((c.volume_ratio - 1) * 2.5) : 1.2;`.
   - `GET /scanner/watchlist` **does not exist** in `v2/api/router.py`.
3. **AI Intelligence & Telemetry Wiring**:
   - `AIIntelligenceService` (`v2/services/ai_intelligence_service/service.py`) handles signal gating and publishes `SIGNAL_AI_CONFIRMED` / `SIGNAL_AI_REJECTED`.
   - B3 Macro Regime adjustment is computed in `v2/services/scanner_service/confluence_engine.py` line 305–313 as a bounded `[-5, +5]` score adjustment based on `market_regime` and `btc_trend`.
   - B4 Dynamic Threshold is calculated in `confluence_engine.py` line 303 bounded between `[80, 92]`.
   - In `v2/templates/dashboard.html` lines 1084–1096, "Crypto Market Regime" is hardcoded static HTML without dynamic bindings.
   - In `v2/templates/dashboard.html` lines 1378–1390, Gemini AI Intelligence Verdict (`#si-ai-verdict`, `#si-catalysts-list`) has hardcoded static text that is never updated by JavaScript.
   - In `v2/templates/dashboard.html` lines 1701–1705, `#watchlist-center` has only a static paragraph and no live table.
4. **Backend Position Routing & Hydration**:
   - `v2/api/router.py` lines 683–690: `GET /positions/open` calls `get_positions(status="OPEN")`, which executes `_position_repo.get_open()` (`WHERE status='OPEN'`). This drops transitional active positions (`PENDING_ENTRY`, `PENDING_EXIT`).
   - `DashboardOverviewSchema` (`v2/api/schemas.py:338-350`) and `DashboardService.get_overview()` (`v2/services/dashboard_service/service.py:392-431`) **do not include** `open_positions` or `open_positions_count`.
   - `v2/api/dashboard_routes.py` is **not mounted** in `v2/api/router.py`.
5. **Trade Charting Integration**:
   - `dashboard.html` has no charting container (`#tradingview_widget` or `#trade-chart-container`).
   - `v2/api/research_routes.py` has no endpoint to fetch recent OHLCV candlestick bars for plotting.

---

## 2. Logic Chain

1. **Why `test_v2_dashboard_ui.py` fails**:
   - Observation 1.1 shows line 95 asserting `"110299" in resp.text` and line 97 asserting `"110299" not in resp.text`. Because Phase 2 auth hardening rightfully removed the plaintext PIN from HTML templates, line 95 must fail.
   - Observation 1.2 shows line 139 asserting `"Security password required"` with uppercase S, while the backend error string starts with `"Configured security password required..."` with lowercase s.
   - Inference: Both failures are test file assertion defects rather than server implementation bugs. Fixing these two assertions will bring `tests/test_v2_dashboard_ui.py` to 100% green.
2. **Why `/positions/open` violates Acceptance Criteria**:
   - The acceptance criteria requires: `GET /api/v2/positions/open returns all non-closed positions (status != 'CLOSED')`.
   - Observation 4 shows `/positions/open` queries `get_open()`, filtering strictly by `status='OPEN'`.
   - Inference: When positions transition through `PENDING_ENTRY` or `PENDING_EXIT`, they are omitted from the response, causing telemetry drops. Changing the query to `_position_repo.get_active_positions()` directly satisfies the acceptance criteria.
3. **Why Dashboard Overview position counts fail**:
   - `DashboardOverviewSchema` and `DashboardService.get_overview()` currently omit `open_positions` and `open_positions_count`.
   - Inference: Adding `open_positions` and `open_positions_count` to both the service and schema directly resolves the acceptance criterion `GET /api/v2/dashboard/overview contains valid open_positions_count matching SQLite active positions`.
4. **Why the Watchlist and Market Regime widgets are disconnected**:
   - The DOM elements in `dashboard.html` for Market Regime and Watchlist are static markup.
   - Inference: Adding element IDs and hooking `refreshLiveTelemetry()` to fetch `/scanner/coins` (or a newly mounted `/scanner/watchlist`) and `/dashboard/overview` telemetry will animate these cards live.
5. **Why the Trade Chart is missing**:
   - Neither the DOM container nor an OHLCV candle endpoint currently exists in the research routes.
   - Inference: Adding a lightweight canvas/TradingView charting container in `#stock-research-view` and providing a candle data endpoint (`/research/candles/{symbol}`) completes R4.

---

## 3. Caveats

- **External Network Access in Tests**: In isolated test environments, tests making unmocked external requests (such as `test_api_scanned_coins_endpoints` in `test_v2_scanned_coins_visibility.py` calling `/scanner/poll`) will receive 0 coins unless external feeds are mocked.
- **Process Concurrency on Windows**: When running tests, ensure no lingering python processes are holding lock handles on temporary SQLite databases.
- **Read-Only Investigation**: Explorer 3 adhered strictly to read-only investigation rules; no source code or test files outside `.agents/explorer_survey_tests/` were altered.

---

## 4. Conclusion

The core algorithmic trading and precision foundations (`test_v2_price_precision_and_order_integrity.py`, `test_v2_min_trading_value.py`, `test_v2_c2_scanner.py`) are 100% sound and passing. The remaining gaps are localized to:
1. Two stale test assertions in `tests/test_v2_dashboard_ui.py`.
2. Routing `/positions/open` to `get_active_positions()`.
3. Adding `open_positions` and `open_positions_count` to `DashboardOverviewSchema` and `DashboardService.get_overview()`.
4. Mounting `dashboard_routes.py` in `v2/api/router.py`.
5. Adding `price_change_pct` to `ScannedCoinSchema` and wiring `/scanner/watchlist`.
6. Dynamically populating the Watchlist, Market Regime, and AI Verdict DOM elements in `dashboard.html`.
7. Embedding the lightweight trade chart container and OHLCV feed.

---

## 5. Verification Method

To independently verify all observations and test states:

1. **Run Dashboard UI & Precision Test Suite**:
   ```powershell
   py -m pytest tests/test_v2_dashboard_ui.py tests/test_v2_price_precision_and_order_integrity.py --basetemp=.pytest_tmp -v
   ```
   *Expected Current Output*: Precision tests pass (14/14); Dashboard UI tests fail 2 specific assertions (lines 95 and 139).
2. **Run Invariant & Scanner Suites**:
   ```powershell
   py -m pytest tests/test_v2_min_trading_value.py tests/test_v2_c2_scanner.py --basetemp=.pytest_tmp -v
   ```
   *Expected Current Output*: 21/21 PASSED (100%).
3. **Inspect Code Locations**:
   - `tests/test_v2_dashboard_ui.py:95` and `139`
   - `v2/api/router.py:683-690` (`/positions/open`)
   - `v2/services/dashboard_service/service.py:392-431` (`get_overview`)
   - `v2/templates/dashboard.html:1084-1096` (Market Regime static card)
   - `v2/templates/dashboard.html:1701-1705` (Watchlist Center static card)
   - `v2/templates/dashboard.html:2354` (Synthetic price change formula)
