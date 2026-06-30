---
name: API auth pattern
description: Dashboard API key authentication setup in app.py
---

`APIKeyHeader(name="X-API-Key")` from `fastapi.security`, checked against `DASHBOARD_API_KEY` env var.

**Why:** All dashboard API routes must be locked down; fail-closed means if the env var is unset the app returns HTTP 500 rather than silently allowing access.

**How to apply:**
- `DASHBOARD_API_KEY` missing → `require_api_key` always raises HTTP 500 (fail-closed).
- Applied as global `dependencies=[Depends(require_api_key)]` on the FastAPI `app` instance.
- Exempted routes use `dependencies=[]` override: `GET /` (dashboard root), `GET /health`, `GET /api/v1/scanner/signals`.
- `DASHBOARD_API_KEY` env var is not set in dev by default — all API routes return 500 until set.
