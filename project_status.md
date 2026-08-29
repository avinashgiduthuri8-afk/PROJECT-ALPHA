# PROJECT-ALPHA — Status Report
**Date**: 2026-08-18

---

## 🔎 What Is It?

A **multi-bot crypto trading dashboard** built on **Python 3.12 / FastAPI**, targeting the **CoinDCX** exchange. It runs four bots in paper or live mode, with a unified web dashboard on port 5000, Telegram integration for commands/alerts, and a comprehensive monitoring/observability layer.

---

## 🤖 Bot Fleet

| Bot | Purpose | Status |
|-----|---------|--------|
| **Scanner Bot** | Scans CoinDCX market data, generates signals, manages watchlist | ✅ Operational (V1) |
| **MTB Bot** (Momentum Trading) | Acts on scanner signals with momentum strategy | ✅ Operational (V1) |
| **PMB Bot** (Portfolio Management) | Portfolio-level position management, DCA, partial sells | ✅ Operational (V1) |
| **VGX Bot** (Volatile GridX) | Grid trading strategy for volatile coins | ✅ Operational (V1) |
| **Risk Engine** | Circuit breaker, drawdown enforcement, capital limits | ✅ Operational (V1) |

---

## 📊 Project Metrics

| Metric | Value |
|--------|-------|
| **Files** | 291 |
| **Codebase Size** | ~7.5 MB |
| **Total Commits** | 147 |
| **Branch** | `main` (single branch) |
| **Test Files** | 35 (comprehensive suite) |
| **Main App** | [`app.py`](file:///c:/Users/chikk/Documents/GitHub/PROJECT-ALPHA/PROJECT-ALPHA/app.py) — 88 KB |
| **API Endpoints** | 22+ monitoring + trading/dashboard endpoints |
| **Telegram Commands** | 18 commands |
| **Working Tree** | Clean (no uncommitted changes) |

---

## 🏗️ Architecture

### V1 (Production — Current)
```
app.py                    ← FastAPI main (88 KB monolith)
bots/
├── scanner_bot/          ← Signal generation
├── mtb_bot/              ← Momentum trading engine
├── pmb_bot/              ← Portfolio management engine
├── volatile_gridX/       ← Grid trading engine
├── risk_engine/          ← Circuit breaker + capital enforcement
└── shared/               ← Shared utilities
telegram_core/            ← Telegram bot integration (multi-bot config)
monitoring/               ← Observability: metrics, health, alerts, load tests
dashboard/                ← Frontend (Jinja2 templates + static assets)
config/                   ← Configuration & validation
data/                     ← JSON file storage (per-bot)
```

### V2 (Scaffold Only — In Progress)
An **event-driven architecture** redesign with an async pub/sub event bus. Currently at **Phase V2.0** (foundation scaffold completed 2026-07-04).

| Phase | Milestone | Status |
|-------|-----------|--------|
| **V2.0** | Foundation scaffold + event bus skeleton | ✅ Done |
| **V2.1** | Scanner service wraps V1 scanner | 📋 Planned |
| **V2.2** | Risk service + circuit breaker events | 📋 Planned |
| **V2.3** | Portfolio service + async storage | 📋 Planned |
| **V2.4** | Notification service (replaces V1 Telegram) | 📋 Planned |
| **V2.5** | Dashboard service via event bus | 📋 Planned |
| **V2.6** | Full integration tests + parallel shadow run | 📋 Planned |
| **V2.7** | V1 retirement → V2 production | 📋 Planned |

---

## ✅ Major Completed Work

### Recent (2026-07)
- **Async Blocking I/O Hardening** — Fixed critical event-loop blocking across MTB, PMB, Scanner, and app.py; all file I/O and network calls now offloaded via `asyncio.to_thread`
- **V2 Foundation** — Event bus skeleton with 16 typed events, service stubs, zero V1 coupling

### Infrastructure (2025-12)
- **Production Telegram Bot** — 18 commands, 8 trade notification types, 7 risk notifications, 11 system notifications; validation score **100/100**
- **Multi-Bot Telegram Config** — Dedicated tokens/chat IDs per bot, backward-compatible fallback
- **Monitoring & Observability** — 22 API endpoints, safety dashboard, storage health, security dashboard, trading stats, Railway system metrics
- **Production Validation** — 100/100 readiness score, load tested (100 concurrent signals, 50 position updates), 0% error rate

### Stability Hardening (multiple sprints)
- Thread-safe singleton patterns & shared state locking
- Atomic statistics tracking for PMB/MTB
- Storage corruption recovery for VGX
- Circuit breaker + emergency stop mechanisms
- Rate limiting (30 req/60s per user)
- Signal cleanup made atomic to prevent data loss
- Non-blocking Telegram notifications

---

## ⚠️ Key Observations

> [!IMPORTANT]
> **`app.py` is an 88 KB monolith** — the single largest file in the project. The V2 migration plan addresses this by splitting into dedicated services.

> [!NOTE]
> **Paper mode by default** — All bots run in paper trading mode until a live CoinDCX API key is configured. The `TRADING_ENABLED` env var acts as a master switch.

> [!NOTE]
> **V2 migration is at Phase 0 of 7** — Only the event bus scaffold exists. V1 is fully untouched and remains the production system. No services have been implemented yet in V2.

> [!TIP]
> **35 test files** cover sprints SP1 through SP6, plus production safety, risk engine config, shared state locking, VGX grid management, storage corruption recovery, and watchlist removal. Test coverage appears strong across critical paths.

---

## 🗂️ Stack Summary

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Frontend | Jinja2 templates + static assets |
| Storage | JSON file storage (per-bot `data/` dirs) |
| Exchange | CoinDCX API |
| Notifications | Telegram (5 bots — multi-bot config) |
| Deployment | Railway (`railway.json` present) |
| Monitoring | Custom observability layer (22 endpoints) |
