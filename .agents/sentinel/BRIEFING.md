# BRIEFING — 2026-09-13T10:35:11Z

## Mission
Monitor orchestration and verification for permanently removing legacy v2/ directory and updating test imports to canonical modules in PROJECT-ALPHA.

## 🔒 My Identity
- Archetype: sentinel
- Working directory: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\sentinel
- Orchestrator: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Victory Auditor: [to be spawned on victory claim]
- Active SWE Agent: 6194becb-ccad-468a-95df-014bea946aeb

## 🔒 Key Constraints
- No technical decisions — relay only
- Victory Audit is MANDATORY before reporting completion
- Preserve Paper Trading: Do NOT enable live execution. Maintain BotMode.PAPER across all services.
- Data Preservation: Do NOT mutate, delete, or drop historical trades or positions in SQLite.
- Capital Rule: Enforce unified shared capital pool and ₹200 minimum notional per order across all bots.
- Route & Schema Invariants Preservation: Maintain all backward-compatibility API/WebSocket endpoints (/api/v2/*, /v2/dashboard, /v2-static/*, /ws/v2/feed) in app.py and dashboard/. Do not alter database migrations or table schemas.

## User Context
- **Last user request**: Permanently remove legacy v2/ directory from PROJECT-ALPHA and update test imports to canonical modules; single self-contained fix, keep small and focused.
- **Pending clarifications**: none
- **Delivered results**: none

## Routing Decision
- **Route**: SWE Light (teamwork_preview_swe)
- **Rationale**: User explicitly stated "This is a single self-contained fix; keep it small and focused" and the task is removing legacy directory and updating remaining test imports.

## Project Status
- **Phase**: in progress
- **Cron 1 (Reporting)**: 22301caa-270c-4d90-8384-c57db8446ff2/task-24
- **Cron 2 (Liveness)**: 22301caa-270c-4d90-8384-c57db8446ff2/task-26

## Victory Audit Status
- **Triggered**: no
- **Verdict**: pending
- **Retry count**: 0

## Artifact Index
- c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md — Authoritative record of user request
