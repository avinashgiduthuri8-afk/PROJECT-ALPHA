# DISPATCH: Worker M2 (Frontend Script, DOM Telemetry Sync, Watchlist, Intelligence & Trade Chart Plotting)

**Working Directory**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\worker_m2
**Original Request**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md
**Project Plan**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\PROJECT.md
**Frontend Survey Report**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_frontend\survey_report.md
**Project Workspace**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA

## Mission
Implement Milestone 2 & 3 (Features 6, 7, 8, 9, 10, 11, 12) per `ORIGINAL_REQUEST.md` (R1, R3, R4) and `PROJECT.md`:

### 1. Frontend Syntax & Modal DOM Cleanup (Feature 6)
In `v2/templates/dashboard.html`:
- Fix `#positionActionModal`: Change `onsubmit="event.preventDefault(); confirmLiveTradeMode();"` to `onsubmit="event.preventDefault(); submitPositionModify();"`.
- Fix `#liveTradeConfirmModal`: Replace unclosed `<div class="pos-modal-body" style="padding:16px 0;">` / `</form>` mismatch with clean balanced tags.
- Fix Security PIN check in `checkDashboardSecurity()`: Ensure that if `DASHBOARD_SECURITY_PIN` is null or not set, security check does not bypass unauthenticated fresh sessions (`null === null`). Ensure valid session state is required or initialized properly.
- Verify zero JavaScript syntax errors via Node vm syntax test.

### 2. Fleet Bot Capacities & Count Alignment (Feature 8)
In `v2/templates/dashboard.html`:
- Update initial HTML render of bot cards (lines ~970, 986, 1002, 1018) from hardcoded `0 / 1 (None)` to reflect configured capacities:
  - STE: `0 / 3 (None)` (capacity: 3)
  - HDA: `0 / 3 (None)` (capacity: 3)
  - VCP: `0 / 2 (None)` (capacity: 2)
  - BBS: `0 / 4 (None)` (capacity: 4)
- Update Bot Tab view placeholders (lines ~1568, 1598, 1628, 1658) to show capacities `3, 3, 2, 4`.
- Ensure `updateFleetMetrics()` in JS populates counts and configured capacity dynamically.

### 3. Dashboard Telemetry DOM Synchronization (Feature 7)
In `v2/templates/dashboard.html`:
- In `refreshLiveTelemetry()`:
  - Header KPI `kpi-openpos` must reflect actual `openPositions.length` from `/positions/open` (or overview `open_positions_count`).
  - Open positions tables (`home-positions-tbody` and `open-positions-tbody`) must clear static placeholder/fallback rows and populate live rows when positions exist, or show clean empty state when 0 positions.
  - Populate symbol, bot name, entry price, mark price, unrealized PnL, and action buttons.

### 4. Watchlist Widget & Intelligence Analytics Telemetry (Features 9, 10)
- In `v2/templates/dashboard.html`:
  - Wire `#watchlist-center` (or container) with an institutional table displaying candidate coins from `/api/v2/scanner/coins` (or `/api/v2/scanner/watchlist`). Show: Symbol/Coin, Price, 24h Change %, Volume Ratio, EMA Trend, Confluence Score, and Action.
  - Connect AI Intelligence telemetry: Wire Market Regime card (`#market-regime-card`), Gemini AI verdict (`#si-ai-verdict`), and catalyst list (`#si-catalysts-list`) to update dynamically from `/dashboard/overview` or `/scanner/coins` telemetry.
- In `v2/api/schemas.py`:
  - Ensure `ScannedCoinSchema` includes `price_change_pct: float = Field(default=0.0)`.
- In `v2/api/router.py`:
  - Add `GET /scanner/watchlist` convenience alias returning the scanned universe coins.

### 5. OHLCV Candlestick Feed & Interactive Trade Chart Plotting (Features 11, 12)
- In `v2/api/research_routes.py`:
  - Implement `GET /candles/{symbol}` (or `/research/candles/{symbol}`): Returns recent 50 OHLCV candlestick bars for the given symbol. Generates or fetches realistic OHLCV bars (timestamp, open, high, low, close, volume) for active universe coins (e.g. BTC/INR, ETH/INR, SOL/INR).
- In `v2/templates/dashboard.html`:
  - In the Research Hub (`#stock-research-view` or `#research-hub`), add the trade chart container `#trade-chart-container` containing `#tradingview_widget` and `<canvas id="trade-candlestick-canvas">`.
  - Implement responsive Canvas-based OHLCV candlestick chart plotter:
    - Renders green/red candlestick bodies and wicks.
    - Draws dashed overlay horizontal marker lines for **Entry Price**, **Stop-Loss (SL)**, and **Take-Profit (TP)**.
    - Updates dynamically when a symbol or position is selected.

### 6. Defense-in-Depth Lifecycle Statuses
- In `v2/core/types.py`:
  - In `PositionStatus(str, Enum)`, ensure `PENDING_ENTRY = "PENDING_ENTRY"` and `PENDING_EXIT = "PENDING_EXIT"` are included alongside `OPEN`, `CLOSING`, `CLOSED` so raw database queries never crash on deserialization.

You own the following files exclusively:
- `v2/templates/dashboard.html`
- `v2/api/research_routes.py`
- `v2/api/router.py`
- `v2/api/schemas.py`
- `v2/core/types.py`

Run the test suite to verify:
`py -m pytest tests/test_v2_dashboard_ui.py tests/e2e/test_v2_e2e_platform.py --basetemp=.pytest_tmp_m2 -v`
Ensure Node syntax check on `v2/templates/dashboard.html` passes.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
