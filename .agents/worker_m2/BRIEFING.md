# BRIEFING — 2026-09-11T12:40:00Z

## Mission
Implement Frontend Script, DOM Telemetry Sync, Watchlist, Intelligence & Trade Chart Plotting (Features 6, 7, 8, 9, 10, 11, 12).

## 🔒 My Identity
- Archetype: implementer
- Roles: implementer, qa, specialist
- Working directory: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\worker_m2
- Original parent: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Milestone: M2 & M3

## 🔒 Key Constraints
- Preserve Paper Trading: Do NOT enable live execution. Maintain BotMode.PAPER across all services.
- Data Preservation: Do NOT mutate, delete, or drop historical trades or positions in SQLite.
- Capital Rule: Enforce the unified shared capital pool and ₹200 minimum notional per order across all bots.
- Integrity: DO NOT hardcode test results, expected outputs, or create dummy implementations.
- Write only to .agents/worker_m2/ for metadata, never put code/tests in .agents/.
- Only modify assigned files: v2/templates/dashboard.html, v2/api/research_routes.py, v2/api/router.py, v2/api/schemas.py, v2/core/types.py.

## Current Parent
- Conversation ID: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Updated: 2026-09-11T12:40:00Z

## Task Summary
- **What to build**: Fix HTML/JS modal syntax & tags, bot capacities, live DOM sync, Watchlist widget, AI intelligence telemetry, OHLCV candle endpoint, interactive canvas chart with Entry/SL/TP markers, PositionStatus enum additions.
- **Success criteria**: All syntax checks and pytest suites pass (test_v2_dashboard_ui.py, test_v2_e2e_platform.py).
- **Interface contracts**: PROJECT.md
- **Code layout**: PROJECT.md

## Change Tracker
- **Files modified**: None yet
- **Build status**: Pending
- **Pending issues**: None

## Quality Status
- **Build/test result**: Untested
- **Lint status**: Clean
- **Tests added/modified**: TBD

## Loaded Skills
- None

## Key Decisions Made
- Check and fix modal DOM tag nesting, #positionActionModal onsubmit handler, and PIN check logic.
- Update fleet bot card initial HTML render and tab views to capacities STE: 3, HDA: 3, VCP: 2, BBS: 4.
- Wire #watchlist-center to live scanner feed with institutional table, and bind AI Intelligence cards. Add price_change_pct to ScannedCoinSchema and /scanner/watchlist route.
- Implement /research/candles/{symbol} in v2/api/research_routes.py and embed interactive Canvas OHLCV candlestick chart widget #trade-chart-container / #tradingview_widget with Entry/SL/TP overlay markers.
- Add PENDING_ENTRY and PENDING_EXIT to PositionStatus enum in v2/core/types.py.

## Artifact Index
- c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\worker_m2\DISPATCH.md — Assignment instructions
- c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\worker_m2\BRIEFING.md — Situational awareness
- c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\worker_m2\progress.md — Liveness & progress tracker
