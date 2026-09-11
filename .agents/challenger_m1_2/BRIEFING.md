# BRIEFING — 2026-09-11T14:50:00+05:30

## Mission
Adversarially challenge dynamic equity, mark-to-market calculations, and shared capital invariants for Milestone 1.

## 🔒 My Identity
- Archetype: EMPIRICAL CHALLENGER
- Roles: critic, specialist
- Working directory: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_m1_2
- Original parent: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Milestone: M1
- Instance: 2 of 2

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code
- Enforce unified shared capital pool and ₹200 minimum notional per order across all bots
- Maintain BotMode.PAPER across all services
- Do not mutate, delete, or drop historical trades or positions in SQLite
- All verification must be empirical (write and execute verification code)

## Current Parent
- Conversation ID: 23cd86ea-b363-4f96-89b2-56b04249c4b8
- Updated: not yet

## Review Scope
- **Files to review**:
  - `v2/services/dashboard_service/bot_pipeline.py`
  - `v2/services/dashboard_service/service.py`
  - `v2/services/dashboard_service/aggregator.py`
  - `v2/services/portfolio_service/service.py`
  - `v2/services/portfolio_service/aggregator.py`
  - `v2/services/trading_service/service.py`
  - `v2/api/router.py`
  - `v2/api/dashboard_routes.py`
  - `v2/api/production_routes.py`
  - `v2/api/schemas.py`
  - `v2/app_v2.py`
- **Interface contracts**: PROJECT.md / ORIGINAL_REQUEST.md
- **Review criteria**:
  1. Dynamic total equity formula: Cash + MTM - Friction handling positive/negative unrealized PnL, varying tick sizes, and zero-cash states.
  2. Shared capital pool constraints: No negative pool, ₹200 minimum notional enforcement.
  3. Startup hydration idempotency: Restarting server twice in succession preserves idempotency without multiplying position counts or capital.

## Attack Surface
- **Hypotheses tested**: [TBD]
- **Vulnerabilities found**: [TBD]
- **Untested angles**: [TBD]

## Loaded Skills
- None

## Key Decisions Made
- Initial setup

## Artifact Index
- `.agents/challenger_m1_2/BRIEFING.md`
- `.agents/challenger_m1_2/progress.md`
- `.agents/challenger_m1_2/handoff.md`
