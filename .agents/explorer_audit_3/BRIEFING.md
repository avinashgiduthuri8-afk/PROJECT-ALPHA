# BRIEFING — 2026-09-17T08:25:54Z

## Mission
Survey & Exploration for Phases 3, 4, 5 (Manual Reference Validation: RSI, MACD, EMA50) and Phase 6 (Live Scanner SQLite Integration) on VPS.

## 🔒 My Identity
- Archetype: explorer
- Roles: explorer, auditor, investigator
- Working directory: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_3
- Original parent: 7b08aaa8-087c-44c6-8e57-82b8c9ddbd5d
- Milestone: Audit Phases 3, 4, 5, 6

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Strictly READ-ONLY on codebase and database (do not mutate live DB)
- SSH to VPS via paramiko from local Windows environment (Host: 148.113.9.103, Port: 20069, User: root)
- Write analysis report to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_3\handoff.md`
- Report completion back to parent orchestrator via send_message

## Current Parent
- Conversation ID: 7b08aaa8-087c-44c6-8e57-82b8c9ddbd5d
- Updated: 2026-09-17T08:34:00Z

## Investigation State
- **Explored paths**:
  - VPS: `/opt/project-alpha/data/project_alpha.db`
  - VPS: `/opt/project-alpha/v2/data/alpha_v2.db`
  - VPS: `/opt/project-alpha/scanner/research/indicators.py`
  - VPS: `/opt/project-alpha/scanner/market_context.py`
  - VPS: `/opt/project-alpha/scanner/service.py`
  - VPS: `/opt/project-alpha/tests/test_indicator_calculations.py`
  - Running process 71891 (`systemctl status project-alpha-v2.service`)
  - Live HTTP endpoints on port 5001 (`/api/v2/scanner/coins`, `/api/v2/scanner/signals`, `/api/v2/dashboard/overview`)
- **Key findings**:
  - **Phase 6 Live DB & Scanner**: `project-alpha-v2.service` (PID 71891) runs on port 5001 with `V2_DB_PATH=v2/data/alpha_v2.db`. Therefore, active signals are persisted to `/opt/project-alpha/v2/data/alpha_v2.db` (422 total signals, 14 generated today, latest at 2026-09-17 08:11:33 UTC). The database `data/project_alpha.db` has 408 signals, last updated 2026-09-11. In the last 5 minutes, 0 signals were generated because all 44 scanned candidates were filtered out by the C2 confluence gate (threshold 88 in RISK_OFF regime; e.g. top coin USELESS scored 87). Scanner poll runs every 60-90s without error.
  - **Indicator Blob**: Stored as JSON string in `raw_payload` column. Contains non-null `rsi` (e.g. 69.49, 67.91), `atr_pct` (0.82, 0.51), `volume_24h`, `volume_ratio`, `mtf_alignment` (true), and `mtf_timeframes` (["15m", "1h", "1d"]). MACD and explicit numeric EMA columns are not in `raw_payload` (EMA is evaluated to derive market_state, trend alignment, and score).
  - **Phase 3 (RSI)**: Validated on VPS. Uptrend produces RSI=100.0 (>70 overbought). Downtrend produces RSI=0.0 (<30 oversold). Flat series produces 100.0 without ZeroDivisionError. Short data (<15 bars) produces all NaNs. 100% PASS.
  - **Phase 4 (MACD)**: Validated on VPS. Multi-column DataFrame `['macd', 'signal', 'hist']` (40, 3) has non-null final values (macd=7.400167, signal=7.112607, hist=0.287560) and identity `hist == macd - signal`. Initial bars exhibit correct NaN warm-up (25 NaNs for macd, 33 for signal/hist). 100% PASS.
  - **Phase 5 (EMA50)**: Validated on VPS. Insufficient data (<50 candles) returns all NaNs (`compute_ema`) or empty list (`calculate_ema`). Exactly 50 candles seeds at index 49 with exact SMA mean (124.500000). >=50 candles produces valid, smoothed non-null values. 100% PASS.
- **Unexplored areas**: None for Phases 3, 4, 5, 6.

## Key Decisions Made
- Used paramiko with stdin piping to bypass Windows-to-Linux shell quote escaping issues.
- Conducted queries across both `/opt/project-alpha/data/project_alpha.db` and active `/opt/project-alpha/v2/data/alpha_v2.db` to give complete clarity on why `project_alpha.db` has no signals in last 5m.
- Executed both unit test suite (`pytest tests/test_indicator_calculations.py`) and custom parametric reference validation scripts directly on the VPS.

## Artifact Index
- DISPATCH.md — Initial dispatch and user task specifications
- BRIEFING.md — Working memory and status
- progress.md — Heartbeat and step tracking
- inspect_db.py — Read-only SQLite inspector
- check_proc.py — Process and systemd inspector
- check_service.py — DB and journal comparison script
- check_signals_deep.py — Deep JSON payload inspector
- check_modules.py — Module existence inspector
- check_indicators_vps.py — VPS indicators.py hash and line counter
- run_pytest_indicators.py — Pytest runner for indicator calculations
- run_phases_3_4_5_validation.py — Dedicated reference validation script for Phases 3, 4, 5
- check_phase6_live.py — Comprehensive Phase 6 live database and journal auditor
- query_auth_endpoints.py — Live FastAPI endpoint auditor
- handoff.md — Final structured handoff report

