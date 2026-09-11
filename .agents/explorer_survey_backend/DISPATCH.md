# DISPATCH: Survey Explorer 2 (Backend Startup Hydration & Routing)

**Working Directory**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_backend
**Original Request**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md
**Project Workspace**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA

## Mission
Survey the backend codebase, focusing on R2 of ORIGINAL_REQUEST.md.
Specifically:
1. Read `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md`.
2. Inspect `BotPipelineTracker` (find where it is defined, e.g. in `v2/services/` or `v2/trading/` or `src/`) and analyze how active positions and deployed capital are tracked. Check how `sync_from_repository` or equivalent startup hydration routine can be integrated using `PositionRepository.get_active_positions()`.
3. Inspect `v2/api/router.py` and `dashboard_routes` to see if/how `dashboard_routes` is mounted, how aggregator dependencies are initialized.
4. Inspect `/positions/open` endpoint and check how it queries positions. Verify where transitional statuses like `PENDING_ENTRY` are handled and ensure `status != 'CLOSED'` is used.
5. Inspect `DashboardService.get_overview()` and see how `open_positions` and `open_positions_count` are included.
6. Inspect how dynamic total equity and deployed capital are calculated (cash balances + live mark-to-market valuations of active positions - friction costs).
7. Document exact file paths, class/function names, signatures, current logic, and proposed implementation details.
8. Write your complete findings to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_backend\survey_report.md` and write a standard `handoff.md`.

