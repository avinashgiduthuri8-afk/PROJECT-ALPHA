# Dispatch for explorer_audit_3

## Task
Survey & Exploration for Phases 3, 4, 5 (Manual Reference Validation: RSI, MACD, EMA50) and Phase 6 (Live Scanner SQLite Integration) on VPS.

## Working Directory
`c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_3`

## Credentials & VPS Info
- IP: 148.113.9.103, Port: 20069
- User: root, Password: SMT6SiQU2nIUMj0V
- Use paramiko via local python script if running commands on VPS.

## Instructions
1. First read `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md` (specifically header `## 2026-09-17T08:22:34Z`).
2. Discover the VPS deployment environment, Python environment, and SQLite database `data/project_alpha.db` location.
3. Check Phase 6 prerequisites: inspect `data/project_alpha.db` on the VPS. Check table schema for signals/scanner, check timestamp of the most recent signals (within last 5 minutes?), and inspect the structure of the `indicators` JSON blob in the database records.
4. Prepare and test the validation logic for:
   - Phase 3: RSI overbought (>70) on an uptrend and oversold (<30) on a downtrend.
   - Phase 4: MACD returns valid multi-column DataFrame with non-null final values.
   - Phase 5: EMA50 handling of <50 candles (None/NaN) vs >=50 candles (valid values).
5. Strictly READ-ONLY on codebase and database (do not mutate live DB). Use temporary scripts or python snippets run via paramiko/SSH on VPS.
6. Write your detailed findings and evidence to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_3\handoff.md`.
7. Send a message to orchestrator with summary and path to handoff.md.

