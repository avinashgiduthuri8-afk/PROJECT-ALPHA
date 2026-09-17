# Scope: VPS Scanner Indicator Calculations Read-Only Audit

## Architecture & Infrastructure
- Remote Target: Linux VPS (`root@148.113.9.103:20069`, password `SMT6SiQU2nIUMj0V`)
- Access Mechanism: Python scripts via `paramiko` executing remote commands and querying remote files/databases over SSH.
- Target Paths on VPS:
  - Repository root on VPS: `/opt/project-alpha` (service `project-alpha-v2.service`, PID 71891, port 5001) and `/root/PROJECT-ALPHA`
  - Canonical Indicator File: `scanner/research/indicators.py` (203 lines)
  - Non-existent File in Prompt: `scanner/indicators.py` (verified 0 lines / never existed)
  - Canonical Unit Test File: `tests/test_indicator_calculations.py` (6/6 tests passed)
  - Non-existent Test File in Prompt: `tests/test_v2_indicators.py` (verified 0 lines / never existed)
  - Active Live SQLite DB: `/opt/project-alpha/v2/data/alpha_v2.db` (422 signals, 14 today)
  - Historical Snapshot DB: `/opt/project-alpha/data/project_alpha.db` (408 signals, last updated 2026-09-11)
- Invariant: Strictly READ-ONLY. No logic, thresholds, or scoring modified.

## Feature / Requirement Inventory
| # | Requirement | Description | Milestone | Status | Source |
|---|-------------|-------------|-----------|--------|--------|
| 1 | R1 (Phase 1) | Code Inspection of `scanner/indicators.py` & `scanner/research/indicators.py` on VPS (line counts, active function signatures, look-ahead scan) | M1 | DONE | ORIGINAL_REQUEST R1 |
| 2 | R2 (Phase 2) | Unit Test Coverage: Execute indicator test suite on VPS, summarize results and failures | M2 | DONE | ORIGINAL_REQUEST R2 |
| 3 | R3 (Phase 3) | Manual Reference Validation: RSI overbought (>70) & oversold (<30) validation on VPS | M3 | DONE | ORIGINAL_REQUEST R3 |
| 4 | R3 (Phase 4) | Manual Reference Validation: MACD multi-column DataFrame with non-null final values on VPS | M3 | DONE | ORIGINAL_REQUEST R3 |
| 5 | R3 (Phase 5) | Manual Reference Validation: EMA50 handling of <50 candles (None/NaN) vs >=50 candles (valid) on VPS | M3 | DONE | ORIGINAL_REQUEST R3 |
| 6 | R4 (Phase 6) | Live Scanner Integration: Query live SQLite DBs on VPS for signals in last 5 min and indicator JSON blobs | M4 | DONE | ORIGINAL_REQUEST R4 |
| 7 | M5 | Multi-Agent Review, Adversarial Challenge & Forensic Integrity Audit | M5 | DONE | Project Pattern |
| 8 | AC (Phase 7) | Synthesis & Strictly Formatted Summary Report detailing RSI, MACD, EMA, and Live Scanner Integration status | M6 | DONE | ORIGINAL_REQUEST AC |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Phase 1 Code Inspection | Discover VPS repo path, inspect line counts, function signatures, and look-ahead bias patterns | none | DONE |
| M2 | Phase 2 Unit Test Execution | Execute `tests/test_indicator_calculations.py` on VPS via SSH, report full pass/fail stats | M1 | DONE |
| M3 | Phases 3-5 Reference Validation | Execute validation scripts on VPS for RSI, MACD, EMA50; collect data | M1 | DONE |
| M4 | Phase 6 Live Integration Query | Query SQLite DBs on VPS for recent signals (<5m) and indicator blobs | M1 | DONE |
| M5 | Verification Gating | Reviewers (2), Challengers (2), and Forensic Auditor (1) multi-agent gating | M1-M4 | DONE |
| M6 | Phase 7 Synthesis & Final Report | Formulate strict Phase 7 Summary Report, verify all ACs, prepare handoff | M1-M5 | DONE |
