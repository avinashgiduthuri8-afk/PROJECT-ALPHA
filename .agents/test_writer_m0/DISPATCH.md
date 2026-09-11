# DISPATCH: E2E Test Writer (Track 2 - Milestone M0)

**Working Directory**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\test_writer_m0
**Original Request**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md
**Project Plan**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\PROJECT.md
**Test Infra**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\TEST_INFRA.md
**Project Workspace**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA

## Mission
Design and write an authoritative, opaque-box E2E test suite for PROJECT-ALPHA V2 in `tests/e2e/test_v2_e2e_platform.py`.
Derive test cases directly from `ORIGINAL_REQUEST.md`, `PROJECT.md`, and `TEST_INFRA.md`.

You own the following files exclusively:
- `tests/e2e/test_v2_e2e_platform.py`
- `TEST_READY.md` (at project root)

Methodology:
- Implement test cases covering Tier 1 (Feature Coverage), Tier 2 (Boundary & Corner Cases), Tier 3 (Cross-Feature Combinations), and Tier 4 (Real-World Scenarios).
- Cover:
  1. Startup hydration of active positions from SQLite into `BotPipelineTracker` and `/api/v2/dashboard/overview` / `/fleet`.
  2. `/api/v2/positions/open` returning non-closed positions (`status != 'CLOSED'`, including `PENDING_ENTRY` and `PENDING_EXIT`).
  3. Dynamic Total Equity ($\text{Cash} + \text{MTM} - \text{Friction}$).
  4. Watchlist feed (`/scanner/coins` / `/scanner/watchlist`).
  5. Candidate candle feed (`/research/candles/{symbol}`).
  6. HTML template sanity and JavaScript syntax integrity.
- Tests must be runnable with pytest using `--basetemp=.pytest_tmp`.
- When tests are written, verify they run cleanly, then publish `TEST_READY.md` at the project root per the template in `TEST_INFRA.md` and deliver `handoff.md`.

