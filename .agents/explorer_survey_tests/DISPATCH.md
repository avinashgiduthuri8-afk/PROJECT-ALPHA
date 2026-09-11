# DISPATCH: Survey Explorer 3 (Test Suite, Intelligence & Scanner Telemetry)

**Working Directory**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_tests
**Original Request**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md
**Project Workspace**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA

## Mission
Survey the test suite and telemetry/intelligence endpoints, focusing on R3, Verification Resources, and Acceptance Criteria of ORIGINAL_REQUEST.md.
Specifically:
1. Read `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md`.
2. Inspect existing test files:
   - `tests/test_v2_dashboard_ui.py`
   - `tests/test_v2_price_precision_and_order_integrity.py`
   - `tests/test_v2_min_trading_value.py`
   - `tests/test_v2_c2_scanner.py`
   Check their structure, current test assertions, fixtures, mocks, and what is tested.
3. Inspect scanner routes and feeds (`/scanner/coins`, `/scanner/watchlist`) and what data fields they return (coins, price change, volume ratios, confluence scores).
4. Inspect AI Intelligence service telemetry (market regime, B3/B4 scores, risk assessment) and where those endpoints/services are defined.
5. Identify any existing failures, missing test coverage, or edge cases needed for acceptance criteria.
6. Document exact file paths, test cases, endpoints, schemas, and recommendations for E2E and unit test coverage.
7. Write your complete findings to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_survey_tests\survey_report.md` and write a standard `handoff.md`.

