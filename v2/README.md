# PROJECT-ALPHA V2 — Production Architecture

PROJECT-ALPHA V2 is the complete, standalone architecture for algorithmic trading on CoinDCX.
The system is built on an event-driven design where all services interact asynchronously via a central EventBus.

---

## Architecture Overview

`
┌─────────────────────────────────────────────────────────────┐
│                       FastAPI (v2/app_v2.py)                │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  Async EventBus (v2/bus/)                   │
└───┬────────────┬─────────────┬─────────────┬────────────┬───┘
    │            │             │             │            │
┌───▼───┐    ┌───▼───┐     ┌───▼───┐     ┌───▼───┐    ┌───▼───┐
│Scanner│    │  AI   │     │ Risk  │     │Trading│    │Portfo-│
│Service│───>│Service│────>│Service│────>│Service│    │lio Svc│
└───────┘    └───────┘     └───────┘     └───────┘    └───────┘
                 │                             │          │
                 ▼                             ▼          ▼
          CircuitBreaker               PositionManager  Live AUM
                                        Mark-to-Market
`

---

## Key Components

1. **Scanner Service (2/services/scanner_service)**:
   - Multi-timeframe (5m, 15m, 1h) technical indicator calculation.
   - 5-layer C2 Confluence Engine (chart, indicators, sentiment, news, scoring).
   - Generates high-conviction candidate signals.

2. **AI Intelligence Service (2/services/ai_intelligence_service)**:
   - Evaluates signals using Google Gemini API.
   - **Automated Circuit Breaker**: Trips to OPEN after 3 consecutive failures to eliminate network latency spikes; falls back immediately to heuristic FallbackEvaluator.
   - Automatically probes HALF_OPEN after 60s cooldown to test recovery.

3. **Risk Service (2/services/risk_service)**:
   - Enforces fleet-wide unified capital limits and per-strategy headroom.
   - Fleet-wide single-coin position lock.
   - Trailing loss & drawdown circuit breakers.

4. **Trading Service (2/services/trading_service)**:
   - PositionManager: tracks open positions in SQLite.
   - High-frequency (~5s) mark-to-market exit polling.
   - Dynamic trailing-stop ratcheting.
   - Native precision lot and tick rounding.

5. **Notification & C2 Service (2/services/notification_service)**:
   - Async Telegram bot dispatcher using httpx.
   - Full interactive C2 command suite (/status, /positions, /trades, /pnl, /pause, /resume, /setamount, /emergency_stop).

6. **Persistence (2/repository/)**:
   - Single SQLite database (2/data/alpha_v2.db) in WAL mode.
   - Automated versioned SQL migrations (001 through 013).

---

## Running the Application

### Local Python
`ash
uvicorn v2.app_v2:app --host 0.0.0.0 --port 5001 --reload
`

### Docker
`ash
docker build -t project-alpha-v2 .
docker run -p 5001:5001 -v alpha_v2_data:/app/v2/data project-alpha-v2
`

### Docker Compose
`ash
docker-compose up -d
`
