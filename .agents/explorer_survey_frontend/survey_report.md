# Comprehensive Frontend & UI Survey Report (R1, R3, R4)

**Date**: 2026-09-11  
**Investigator**: Survey Explorer 1 (Frontend & UI)  
**Workspace**: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA`  
**Primary Target**: `v2/templates/dashboard.html` and related frontend assets & API endpoints  

---

## Executive Summary

This survey provides an exhaustive read-only architectural and behavioral analysis of the PROJECT-ALPHA V2 Mission Control Dashboard frontend. The survey covers requirements **R1** (JavaScript execution, DOM synchronization, bot capacities, duplicate declarations), **R3** (Watchlist container and intelligence feeds), and **R4** (Trade chart container and candlestick + TP/SL/Entry markers), as specified in `ORIGINAL_REQUEST.md`.

---

## 1. Issue #1: `v2/templates/dashboard.html` Duplicate Variable Declarations & Syntax Errors

### 1.1 Duplicate Declarations Investigation (`homeTbody`, `openTbody`)
- **Historical Context**: In prior commits, `homeTbody` and `openTbody` were declared twice within the telemetry polling function — once at the beginning of position processing and again at line ~2043 (in commit `dcac8585a00d221bc3eab7b9a5d6fae09acdc7d1` on 2026-09-07).
- **Current File Location**: In the current `v2/templates/dashboard.html`:
  - Line 2425: `const homeTbody = document.getElementById("home-positions-tbody");`
  - Line 2426: `const openTbody = document.getElementById("open-positions-tbody");`
  - Line 2544: `if (homeTbody) { homeTbody.innerHTML = ... }`
  - Line 2580: `if (openTbody) { openTbody.innerHTML = ... }`
  - Line 2611: `if (homeTbody) { homeTbody.innerHTML = ... }` (empty state fallback)
  - Line 2614: `if (openTbody) { openTbody.innerHTML = ... }` (empty state fallback)
- **Status**: The second duplicate declaration of `homeTbody` and `openTbody` was pruned in commit `dcac858`. `node -c` parses both inline `<script>` tags cleanly.

### 1.2 Syntax, Scope, and Structural Defects Identified
While AST parsing passes `node -c`, three critical structural and logic defects exist in `v2/templates/dashboard.html`:

1. **Split Script Architecture & Cross-Script Hoisting Hazards**:
   - `v2/templates/dashboard.html` contains **two separate inline `<script>` tags**:
     - Script 1: Lines 1734–2291 (UI navigation, Chart.js visualizers, Research Hub deep dive functions, position modals).
     - Script 2: Lines 2293–2897 (`API_KEY`, `API_BASE`, `apiFetch`, `refreshLiveTelemetry`, `pollLiveTicker`, WebSocket, security PIN handling, `DOMContentLoaded`).
   - **Hazard**: Script 1 invokes functions that are only declared in Script 2:
     - Line 1956: `await apiFetch('/research/pairs/' + ...)` in `searchStockDeepDive()`
     - Line 2111: `pollLiveTicker()` in `finally` of `searchStockDeepDive()`
     - Line 2121: `await apiFetch('/research/backtest', ...)` in `backtestCurrentStock()`
     - Line 2148: `await apiFetch('/research/predict', ...)` in `predictCurrentStockTrend()`
     - Line 2164: `apiFetch('/production/kill-switch', ...)` in `triggerEmergencyKill()`
     - Line 2193: `await apiFetch('/trading/positions/' + ...)` in `submitPositionModify()`
     - Line 2210: `await apiFetch('/trading/positions/' + ...)` in `submitImmediateCloseFromModal()`
     - Line 2226: `await apiFetch('/trading/positions/' + ...)` in `quickToggleTrailing()`
     - Line 2241: `await apiFetch('/trading/positions/' + ...)` in `manualClosePosition()`
     - Line 2266: `await apiFetch('/production/set-mode', ...)` in `toggleCryptoAutoExecution()`
     - Line 2285: `refreshLiveTelemetry()` in `triggerCryptoCycleNow()`
   - **Impact**: If any event or script invokes these functions prior to Script 2 being parsed, a runtime `ReferenceError: apiFetch is not defined` or `ReferenceError: refreshLiveTelemetry is not defined` occurs. Consolidating into a single `<script>` block eliminates cross-script evaluation ordering risks.

2. **Mismatched HTML Modal Tags & Broken Event Handlers**:
   - **`#positionActionModal` (Line 2912)**:
     ```html
     <form class="pos-modal-body" style="padding:16px 0;" onsubmit="event.preventDefault(); confirmLiveTradeMode();">
     ```
     The form submission handler calls `confirmLiveTradeMode()` instead of `submitPositionModify()`. Submitting the form triggers a live mode authentication modal action rather than saving position TP/SL/trailing changes.
   - **`#liveTradeConfirmModal` (Lines 2993–3006)**:
     ```html
     2993: <div class="pos-modal-body" style="padding:16px 0;">
     ...
     3004:     <button type="submit" class="btn-sm" style="...">🔴 Authorize & Switch to LIVE</button>
     3005: </div>
     3006: </form>
     ```
     Line 2993 opens a `<div>`, but Line 3006 closes with `</form>`. There is no matching `<form>` opening tag inside `#liveTradeConfirmModal`. This causes invalid DOM hierarchy in modern browser engines.

3. **Inverted Security Gateway PIN Lock Logic**:
   - **Lines 2720–2728**:
     ```javascript
     const DASHBOARD_SECURITY_PIN = null;

     function checkDashboardSecurity() {
         const overlay = document.getElementById("dashboardSecurityOverlay");
         const storedPin = sessionStorage.getItem("alpha_auth_pin");
         if (storedPin === DASHBOARD_SECURITY_PIN) {
             if (overlay) overlay.style.display = "none";
         } else {
             if (overlay) {
                 overlay.style.display = "flex";
                 ...
             }
         }
     }
     ```
   - **Impact**: On a fresh session, `sessionStorage.getItem("alpha_auth_pin")` returns `null`. Because `storedPin === null` and `DASHBOARD_SECURITY_PIN === null`, the condition `storedPin === DASHBOARD_SECURITY_PIN` evaluates to `true`! The dashboard security overlay is immediately hidden on first load without prompting for a PIN. Conversely, once an operator successfully enters `"110299"`, `storedPin` becomes `"110299" !== null`, causing the overlay to display and lock the screen.
   - **Fix**: Check `sessionStorage.getItem("alpha_auth_unlocked") === "true"` or verify against the server `/api/v2/auth/verify-password` endpoint.

---

## 2. Issue #2: `refreshLiveTelemetry()` and DOMContentLoaded Initialization

### 2.1 DOMContentLoaded Flow
Lines 2882–2896 in `v2/templates/dashboard.html`:
```javascript
window.addEventListener("DOMContentLoaded", () => {
    checkDashboardSecurity();
    refreshLiveTelemetry();
    connectLiveWebSocket();
    // Fast 1-second live ticker snapshot refresh
    setInterval(pollLiveTicker, 1000);
    // Fast 2-second telemetry & positions refresh
    setInterval(refreshLiveTelemetry, 2000);
    // Fast 3-second deep research active coin indicators refresh
    setInterval(() => {
        if (activeDeepDiveSym) {
            searchStockDeepDive(activeDeepDiveSym, activeSelectedQuote);
        }
    }, 3000);
});
```

### 2.2 `refreshLiveTelemetry()` Step-by-Step Execution
1. **Production Status Polling**:
   - Calls `GET /api/v2/production/status`.
   - Updates `kpi-aum` (AUM limit), `kpi-capital` (capital deployed), `kpi-openpos` (`status.open_positions_count`), `beta-auto-label` (execution mode state), and runs `updateModeUI(status.deployment_mode)`.
2. **Scanner Feeds Polling**:
   - Calls `GET /api/v2/scanner/coins`.
   - Iterates through coins, updating `cryptoData[coinKey]` cache.
   - Re-renders `scanned-universe-tbody` (first 10 coins on Home view).
   - Re-renders `scanner-center-tbody` (all evaluated candidates on Scanner Center view).
3. **Open Positions & Fleet Telemetry Polling**:
   - Calls `GET /api/v2/trading/positions?status=OPEN`.
   - Updates `kpi-openpos` with `openPositions.length`.
   - Updates `kpi-openpos-sub` with the list of active coins.
   - Aggregates `totalPositionsCapital` and `totalUnrealisedPnl` and updates `kpi-capital`.
   - Groups open positions by bot (`STE`, `HDA`, `VCP`, `BBS`) into `positionsByBot`.
   - Updates Bot Fleet Cards (`bot-pos-ste`, `bot-status-ste`, `bot-cap-ste`, `bot-pnl-ste`, `bot-prog-ste`, etc.).
   - Updates Individual Bot Tab KPIs (`ste-tab-pos`, `ste-tab-pos-sub`, etc.).
   - Renders open position table rows in `home-positions-tbody` and `open-positions-tbody`.
   - If empty, renders clean empty state rows.

### 2.3 Critical Observation on Endpoint Alignment
- Line 2421 calls `GET /api/v2/trading/positions?status=OPEN`.
- Requirement R2 states:
  > Update `/positions/open` endpoint to query non-closed positions (`status != 'CLOSED'`) via `get_active_positions()` so transitional active positions (like `PENDING_ENTRY`) are never dropped.
- In `v2/api/router.py` lines 683–690:
  ```python
  @router.get("/positions/open", ...)
  async def get_open_positions_alias() -> list[PositionSchema]:
      return await get_positions(status="OPEN")
  ```
- If `dashboard.html` calls `/positions/open` (or if `/trading/positions?status=OPEN` delegates to `PositionRepository.get_active_positions()`), all transitional positions (e.g. `PENDING_ENTRY`, `PENDING_EXIT`, `ACTIVE`, `OPEN`) will be reflected across the dashboard without risk of transitional drop.

---

## 3. Issue #3: Header KPI, Open Positions Tables, and Bot Fleet Capacities

### 3.1 Header KPI Elements
- **Location**: Lines 941–945 in `v2/templates/dashboard.html`:
  ```html
  <div class="kpi-card accent-blue">
      <div class="kpi-label">Open Positions</div>
      <div class="kpi-value font-mono" id="kpi-openpos">0</div>
      <div class="kpi-sub" id="kpi-openpos-sub">0 active positions</div>
  </div>
  ```
- **Live Updating**:
  - Line 2430: `kpiOpenPos.innerText = openPositions.length;`
  - Line 2438: `kpiPosSub.innerText = activeCoinList + " active";` (or `"0 active positions"`)
  - **Behavior**: Smoothly updates on every 2-second cycle once positions data arrives.

### 3.2 Positions Tables
- **Home View Table**: `id="home-positions-tbody"` (Line 1049) — 10 columns: Bot/ID, Asset Pair, Qty, Entry Price, Current LTP, Target/SL, Profit Trailing, Net Realizable P&L, Mode, Manual Actions (Trail, SL/TP modal, Close).
- **Open Positions View Table**: `id="open-positions-tbody"` (Line 1433) — 10 columns: Bot/ID, Pair, Qty, Avg Entry, LTP, Gross P&L, Friction (1.572%), Net P&L, Mode, Action (Close).
- **Static Fallback Issue**:
  - In the HTML template, lines 1050–1054 and 1434–1438 have initial fallback rows:
    `<span ...>⏳</span> Loading active positions from SQLite...`
  - When live API data arrives, `homeTbody.innerHTML` and `openTbody.innerHTML` are immediately overwritten with mapped rows or empty-state rows.

### 3.3 Bot Fleet Cards Capacity Discrepancy
- **Requirement R1**:
  > Fleet bot cards displaying accurate position counts and configured capacities (`STE: 3, HDA: 3, VCP: 2, BBS: 4`) instead of hardcoded `0 / 1 (None)`.
- **Finding in HTML Source**:
  - Line 970 (STE Card): `<span ... id="bot-pos-ste">0 / 1 (None)</span>` (Incorrect: must be `0 / 3 (None)`)
  - Line 986 (HDA Card): `<span ... id="bot-pos-hda">0 / 1 (None)</span>` (Incorrect: must be `0 / 3 (None)`)
  - Line 1002 (VCP Card): `<span ... id="bot-pos-vcp">0 / 1 (None)</span>` (Incorrect: must be `0 / 2 (None)`)
  - Line 1018 (BBS Card): `<span ... id="bot-pos-bbs">0 / 1 (None)</span>` (Incorrect: must be `0 / 4 (None)`)
  - In Individual Bot Tabs:
    - Line 1568 (STE Tab): `<div ... id="ste-tab-pos">0 / 1</div>` (Incorrect: must be `0 / 3`)
    - Line 1598 (HDA Tab): `<div ... id="hda-tab-pos">0 / 1</div>` (Incorrect: must be `0 / 3`)
    - Line 1628 (VCP Tab): `<div ... id="vcp-tab-pos">0 / 1</div>` (Incorrect: must be `0 / 2`)
    - Line 1658 (BBS Tab): `<div ... id="bbs-tab-pos">0 / 1</div>` (Incorrect: must be `0 / 4`)
- **Finding in JavaScript**:
  - In `refreshLiveTelemetry()` line 2457:
    `const botMaxPositions = { STE: 3, HDA: 3, VCP: 2, BBS: 4 };` is correctly defined.
  - However, until `refreshLiveTelemetry()` completes, or if an error halts script execution, the UI displays the invalid `0 / 1` capacity. Updating the static HTML default values eliminates visual flickering on startup.

---

## 4. Issue #4: Watchlist Container & Live Feeds (R3)

### 4.1 Current Implementation in `v2/templates/dashboard.html`
- **Sidebar Nav Anchor**:
  - Line 768–770:
    ```html
    <button class="nav-dropdown-toggle" data-menu="watchlist">Watchlist</button>
    <div class="nav-dropdown-menu view-hidden" id="menu-watchlist">
        <a href="#" class="nav-anchor" data-target="watchlist-center">CoinDCX Universe</a>
    </div>
    ```
- **Target SPA View**:
  - Lines 1701–1705:
    ```html
    <div id="watchlist-center" class="spa-view-layer view-hidden">
        <div class="dashboard-grid-matrix">
            <div class="metric-card span-12">
                <h3>⭐ CoinDCX Universe Watchlist</h3>
                <p style="color:var(--text-secondary);">Active Universe: BTC/INR, ETH/INR, SOL/INR, NEAR/INR, FET/INR, DOGE/INR, BNB/INR, XRP/INR, ZEC/USDT.</p>
            </div>
        </div>
    </div>
    ```
  - **Status**: The container is a bare static placeholder. There is no table, card grid, or dynamic data binding.

### 4.2 Backend Scanner Feeds
- **Available Endpoint**: `GET /api/v2/scanner/coins`
  - Returns `list[ScannedCoinSchema]` with fields:
    `symbol`, `coin`, `pair`, `price`, `volume_24h`, `volume_ratio`, `ema_trend`, `rsi`, `mtf_alignment`, `is_mtf_aligned`, `confluence_score`, `status`, `accepted`, `rejection_reason`, `evaluated_at`.
- **Missing Alias/Endpoint**: `GET /api/v2/scanner/watchlist`
  - Schema exists in `v2/api/schemas.py` (`WatchlistSummarySchema`), but the endpoint is not yet mounted in `router.py`.

### 4.3 Proposed Watchlist Table & Data Binding
1. Add an institutional table structure inside `#watchlist-center`:
   - Columns: Asset Pair, Live Price, 24h Volume, Volume Ratio (RVOL), EMA Trend, RSI (14), MTF Alignment, Confluence Score, Status, Quick Actions ("Research Deep Dive", "Trade Constructor").
   - Target Tbody: `<tbody id="watchlist-table-tbody"></tbody>`
2. Update `refreshLiveTelemetry()` to render `scannedCoins` into `watchlist-table-tbody` with color-coded score tiers (Elite ≥ 85 in emerald, High ≥ 75 in amber, Filtered < 75 in muted slate).
3. Connect AI Intelligence service telemetry (market regime, B3/B4 scores, risk assessment) to the status badges.

---

## 5. Issue #5: Trade Chart Container & Candlestick + TP/SL/Entry Markers (R4)

### 5.1 Current Chart State
- **Existing Elements**:
  - Line 9: `<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>`
  - Lines 1104, 1108, 1112: Three small canvas charts for Home view diagnostics:
    - `#homePieChart` (Signal Quality doughnut)
    - `#homeGaugeChart` (Subsystem Health gauge)
    - `#homeLineChart` (7-Day Signal Velocity line chart)
- **Deficiency**:
  - Neither `#tradingview_widget` nor `#trade-chart-container` exists in `v2/templates/dashboard.html`.
  - The Deep Dive Research Hub (lines 1250–1400) displays text cards for Price Metrics, Trade Constructor Setup, and Scorecard, but **no visual price action / OHLCV candlestick chart**.

### 5.2 Required Implementation Architecture
1. **Chart Container Markup**:
   Insert `#trade-chart-container` inside the Research Hub grid matrix (between `#si-symbol` header and the parameter cards):
   ```html
   <div class="metric-card span-12" id="trade-chart-container" style="min-height: 420px; position: relative;">
       <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;">
           <div style="display:flex; align-items:center; gap:8px;">
               <span style="font-size:1.1rem;">📈</span>
               <h5 style="margin:0;">Interactive Price Action & Trade Execution Levels</h5>
               <span id="chart-timeframe-badge" class="row-badge-pill">15M TIMEFRAME</span>
           </div>
           <div style="display:flex; gap:6px;">
               <button class="btn-sm btn-outline active" onclick="switchChartTimeframe('15m')">15m</button>
               <button class="btn-sm btn-outline" onclick="switchChartTimeframe('1h')">1h</button>
               <button class="btn-sm btn-outline" onclick="switchChartTimeframe('1d')">1d</button>
           </div>
       </div>
       <div id="tradingview_widget" style="width: 100%; height: 360px;">
           <canvas id="trade-candlestick-canvas" style="width:100%; height:100%;"></canvas>
       </div>
   </div>
   ```

2. **Candlestick & Reference Line Rendering Engine**:
   - Can be rendered using an HTML5 Canvas OHLCV renderer (zero external CDN dependency) or TradingView Lightweight Charts with canvas fallback.
   - **Visual Elements to Plot**:
     - **Candlestick bars**: Green (`#10b981`) for `close >= open`, Red (`#ef4444`) for `close < open`, with center high-low wick lines.
     - **Horizontal Reference Lines with Badges**:
       - **Entry / Pivot Price**: Blue dashed line (`#3b82f6`, `strokeDasharray: [4, 4]`) with badge `ENTRY: ₹...`.
       - **Hard Stop Loss (SL)**: Red dashed line (`#ef4444`) with badge `SL: ₹...`.
       - **Take-Profit 1 (TP1)**: Green dashed line (`#10b981`) with badge `TP1: ₹...`.
       - **Take-Profit 2 (TP2)**: Emerald dashed line (`#059669`) with badge `TP2: ₹...`.
   - **Dynamic Data Feeding**:
     - When `searchStockDeepDive(sym)` or `selectStockSearch(sym)` is called, fetch candles for `sym` (from `/api/v2/research/candles/{sym}` or extracted from `res.indicators`), calculate coordinates, and render candles and TP/SL overlay lines onto `#trade-candlestick-canvas`.

---

## 6. Test Suite Findings (`tests/test_v2_dashboard_ui.py`)

During test suite verification, two test assertion defects were uncovered in `tests/test_v2_dashboard_ui.py`:

1. **`test_dashboard_security_elements_rendered` (Lines 94–98)**:
   ```python
   assert "dashboardSecurityOverlay" in resp.text
   assert "securityPasswordInput" in resp.text
   assert "110299" in resp.text
   # Phase 2: PIN must NOT be in HTML (server-side validation only)
   assert "110299" not in resp.text
   ```
   - **Conflict**: Line 96 asserts `"110299" in resp.text`, while line 98 asserts `"110299" not in resp.text`. Both cannot pass simultaneously. In commit `a8f8b8e`, the PIN was removed from HTML source for server-side security, but line 96 was erroneously retained. Removing line 96 resolves the contradiction.
2. **`test_set_mode_security_password_protection` (Lines 139–140)**:
   ```python
   assert "Security password required" in resp_live_fail.json()["detail"]
   assert "password required" in resp_live_fail.json()["detail"].lower()
   ```
   - **Conflict**: The API returns `"Configured security password required to switch to LIVE mode."` (lowercase `s`). Line 139 fails case sensitivity. Line 140 already tests the lowercase assertion correctly.

---

## 7. Synthesis & Action Plan for Implementation Agents

| Issue | Target File(s) | Specific Action Required |
|---|---|---|
| **R1: Syntax & Modal Errors** | `v2/templates/dashboard.html` | Consolidate the two `<script>` tags into one. Fix mismatched `<div>`/`</form>` in `#liveTradeConfirmModal`. Correct `#positionActionModal` onsubmit to call `submitPositionModify()`. Fix inverted security PIN check in `checkDashboardSecurity()`. |
| **R1: Bot Capacities** | `v2/templates/dashboard.html` | Change hardcoded `0 / 1` in initial HTML for bot cards (lines 970, 986, 1002, 1018) and bot tab views (lines 1568, 1598, 1628, 1658) to configured capacities: `STE: 3, HDA: 3, VCP: 2, BBS: 4`. |
| **R2: Positions Endpoint Alignment** | `v2/templates/dashboard.html`, `v2/api/router.py` | Ensure `/positions/open` endpoint and `refreshLiveTelemetry()` query non-closed positions via `PositionRepository.get_active_positions()`. Mount `dashboard_routes`. |
| **R3: Watchlist Container** | `v2/templates/dashboard.html` | Replace placeholder in `#watchlist-center` with a live interactive data table (`watchlist-table-tbody`). Populate from `/scanner/coins`. |
| **R4: Trade Chart Panel** | `v2/templates/dashboard.html`, `v2/api/research_routes.py` | Insert `#trade-chart-container` / `#tradingview_widget` / `#trade-candlestick-canvas`. Implement Canvas OHLCV candlestick renderer with Entry, SL, TP1, and TP2 price marker overlays. |
| **Tests: UI Test Suite** | `tests/test_v2_dashboard_ui.py` | Prune contradictory `assert "110299" in resp.text` and uppercase `"Security password required"`. |
