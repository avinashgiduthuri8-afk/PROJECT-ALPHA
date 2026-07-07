---
name: V2 Architecture decisions
description: Key decisions made during V2 Phase 1 architecture design — topology, constraints, and schema choices that implementation must honour.
---

## V2 runs on a separate port (5001), not mounted in app.py
V2 serves from `v2/app_v2.py` on port 5001. V1 `app.py` on port 5000 is never modified.
At V2.7 cut-over, `app.py` is replaced (delete + rename), not edited.

**Why:** "Do NOT modify any V1 files" is a hard user constraint. Mounting a router in app.py would violate it.

## Event routing rule: alerts always go through AlertManager → ALERT_GENERATED → NotificationService
Risk events (TRADE_DENIED, CAPITAL_LIMIT_HIT, CIRCUIT_BREAKER_TRIGGERED) are NOT subscribed to directly by NotificationService. They go: risk event → AlertManager → ALERT_GENERATED → NotificationService.

**Why:** Keeps NotificationService with a single subscription point; prevents duplicate alert dispatch paths.

## TradingService subscribes to TRADE_APPROVED only (not SIGNAL_GENERATED)
Signal evaluation is RiskService's job. TradingService is an executor, not a decision-maker.

**Why:** Prevents a second, unguarded path from signal → execution that bypasses capital limits.

## daily_pnl in RiskService maintained from POSITION_CLOSED (not TRADE_CLOSED)
TRADE_CLOSED is not a defined event. POSITION_CLOSED carries the pnl field. RiskService accumulates daily_pnl from POSITION_CLOSED events for drawdown/circuit-breaker logic.

**Why:** POSITION_CLOSED is the canonical "trade is done" event in the bus topology.

## positions table has exit_price, exit_reason, closed_at columns (NULLable until closed)
PositionRepository.close(id, exit_price, exit_reason) writes all three atomically. TradeRepository.insert() is called immediately after.

**Why:** Code review identified that PositionRepository.close() had no corresponding schema columns.

## V2 SQLite uses WAL journal mode
Allows concurrent reads while one writer is active. Dashboard reads never block bot writes.

## All V2 architecture is in v2/ARCHITECTURE.md (1294 lines, Phase 1)
Covers: folder structure, shared core, event bus (28 events), 6 services, 7 repositories, SQLite schema, config system, scheduler (8 jobs), WebSocket feed, monitoring/metrics, 3 data flows, 8-phase migration roadmap.
