## 2026-09-13T10:35:53Z

You are teamwork_preview_swe operating in working directory:
c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\swe_1

The user's original request is recorded at:
c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md

Task summary:
This is a single self-contained fix; keep it small and focused. Permanently remove the legacy v2/ directory from PROJECT-ALPHA and update any remaining test suite imports to canonical modules so the entire system and test suite run cleanly and independently.

Requirements:
R1. Remove Legacy `v2/` Directory: Permanently delete the legacy `v2/` directory tree. No active application service, script, or configuration may depend on the existence of `v2/`.
R2. Test Suite Import Migration: Migrate any remaining test files in `tests/` that import from `v2.*` so they import directly from the six canonical packages: `core`, `scanner`, `execution`, `telegram`, `background`, and `dashboard`.
R3. Route & Schema Invariants Preservation: Maintain all backward-compatibility API and WebSocket endpoints (`/api/v2/*`, `/v2/dashboard`, `/v2-static/*`, `/ws/v2/feed`) defined in `app.py` and `dashboard/` so existing external clients remain fully supported. Do not alter database migrations or table schemas.

Acceptance Criteria:
- The `v2/` directory no longer exists in the repository.
- No active file in `core`, `scanner`, `execution`, `telegram`, `background`, `dashboard`, `app.py`, or `scripts` contains imports from `v2`.
- `python -m compileall core scanner execution telegram dashboard background app.py scripts` exits with code 0.
- `python -m pytest tests/test_canonical_config.py tests/test_canonical_app.py tests/test_v2_dashboard_ui.py tests/test_v2_pipeline_dashboard.py tests/test_v2_phase7_dashboard.py tests/test_v2_safety_invariants.py --basetemp=.pytest_temp -v` exits with code 0 (0 failed).
- Full pytest discovery (`python -m pytest --collect-only`) collects all tests without any `ModuleNotFoundError` for `v2`.

Operating instructions:
Maintain `BRIEFING.md` and `progress.md` in your working directory `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\swe_1`.
Execute the SWE Light loop: dispatch implementation to a teamwork_preview_implementer, then run reviewer rounds, establishing correctness by running tests.
When the entire task is complete and all acceptance criteria pass, write a final handoff report and notify me (the Sentinel) via send_message.

