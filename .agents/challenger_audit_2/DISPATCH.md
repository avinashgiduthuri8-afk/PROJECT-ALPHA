# Dispatch for challenger_audit_2

## Role
Code-executing Adversarial Verifier (Live Scanner DB & Telemetry Verification)

## Working Directory
`c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_2`

## Credentials & VPS Info
- IP: 148.113.9.103, Port: 20069
- User: root, Password: SMT6SiQU2nIUMj0V
- Use paramiko via local python script to execute queries / checks on the Linux VPS.

## Mandatory Reading
1. `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md` (specifically header `## 2026-09-17T08:22:34Z`).
2. `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_3\handoff.md`.

## Objectives
1. Connect to VPS over SSH and adversarially verify the Phase 6 Live Scanner SQLite integration:
   - Query `/opt/project-alpha/data/project_alpha.db` directly: verify signal count and timestamp of latest row.
   - Query `/opt/project-alpha/v2/data/alpha_v2.db` directly: verify signal count and timestamp of latest row.
   - Parse `raw_payload` JSON of the latest 5 signals: assert that `rsi`, `atr_pct`, `volume_24h`, `volume_ratio`, `mtf_alignment`, and `score` exist, parse cleanly as JSON, and are non-null.
   - Verify scanner service status and recent journalctl entries (`journalctl -u project-alpha-v2.service -n 50 --no-pager`): confirm that scanner background loops are running without errors or uncaught exceptions.
   - Query live HTTP endpoint `http://127.0.0.1:5001/api/v2/scanner/coins` with header `X-API-Key: alpha-prod-key` to confirm active candidate evaluation in memory.
2. Strictly READ-ONLY on DB and codebase (do not execute INSERT/UPDATE/DELETE).
3. Write your findings, verification outputs, and verdict (`APPROVE` or `REJECT`) to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_2\handoff.md`.
4. Send a message to orchestrator (conversation ID: `7b08aaa8-087c-44c6-8e57-82b8c9ddbd5d`) with verdict and report path.

## 2026-09-17T08:35:29Z

You are challenger_audit_2, a code-executing adversarial verifier for PROJECT-ALPHA.
Your working directory is: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_2`.

You MUST read:
1. `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md` (header `## 2026-09-17T08:22:34Z`).
2. `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_2\DISPATCH.md`.

VPS SSH: 148.113.9.103:20069, root, SMT6SiQU2nIUMj0V
Use paramiko via local Python script on Windows to connect over SSH.
Adversarially verify Phase 6 (Live Scanner SQLite Integration):
- Query `data/project_alpha.db` and `v2/data/alpha_v2.db` directly on the VPS.
- Verify latest signal timestamps, count of signals in last 5m vs today.
- Parse `raw_payload` JSON of recent signals: verify `rsi`, `atr_pct`, `volume_24h`, `volume_ratio`, `mtf_alignment`, `score`.
- Check live service logs (`journalctl -u project-alpha-v2.service -n 50 --no-pager`) for scanner errors.
- Query live HTTP endpoint `http://127.0.0.1:5001/api/v2/scanner/coins` with header `X-API-Key: alpha-prod-key`.
Strictly read-only on DB and codebase.
Issue a clear verdict: APPROVE or REJECT.
Write your report to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_2\handoff.md`.
Send a message back to orchestrator (ID: 7b08aaa8-087c-44c6-8e57-82b8c9ddbd5d) with your verdict and handoff path.
