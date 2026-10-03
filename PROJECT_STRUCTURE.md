# PROJECT-ALPHA: Reusable Architecture & System Blueprint

> **PROJECT-ALPHA** is an institutional-grade, closed-loop quantitative trading platform built in Python. It features an asynchronous event-driven core, multi-timeframe market scanning, dynamic risk & sizing controls, dual Telegram C2 interfaces (Paper & Live), a real-time FastAPI telemetry dashboard, and background learning/watchdog schedulers.

---

## 1. High-Level System Architecture

```
                                  +---------------------------------------+
                                  |         External Market Feeds         |
                                  |   (CoinDCX Public API / WebSockets)   |
                                  +---------------------------------------+
                                                      |
                                                      v
+---------------------------------------------------------------------------------------------------------+
|                                             PROJECT-ALPHA CORE                                          |
|                                                                                                         |
|  +--------------------+      +------------------------+      +--------------------+                     |
|  |   Market Scanner   | ---> |  C2 Confluence Engine  | ---> |  AI Intelligence   |                     |
|  |  (5-Layer Funnel)  |      |   (80-89 & 90+ Elite)  |      |  (Gemini Analysis) |                     |
|  +--------------------+      +------------------------+      +--------------------+                     |
|            |                                                            |                               |
|            v                                                            v                               |
|  +--------------------------------------------------------------------------------+                     |
|  |                       Async In-Memory EventBus (Pub/Sub)                       |                     |
|  +--------------------------------------------------------------------------------+                     |
|            |                                   |                                |                       |
|            v                                   v                                v                       |
|  +--------------------+               +--------------------+          +--------------------+            |
|  |    Risk Engine     |               |  Execution Engine  |          | Dual Telegram C2   |            |
|  | - Circuit Breakers |               | - Paper Simulator  |          | - Paper Bot (C2)   |            |
|  | - Capital Guards   |               | - Live Micro-Cash  |          | - Live Bot (C2)    |            |
|  | - Correlation Caps |               | - Auto-Reconcile   |          | - Slash Autofill   |            |
|  +--------------------+               +--------------------+          +--------------------+            |
|            |                                   |                                |                       |
|            +-----------------------------------+--------------------------------+                       |
|                                                |                                                        |
|                                                v                                                        |
|  +--------------------------------------------------------------------------------+                     |
|  |                       WAL SQLite Database (14 Migrations)                      |                     |
|  +--------------------------------------------------------------------------------+                     |
|            ^                                                                    ^                       |
|            |                                                                    |                       |
|  +--------------------+                                               +--------------------+            |
|  | FastAPI Dashboard  |                                               | Background Workers |            |
|  | - REST Telemetry   |                                               | - Exit Watchdog    |            |
|  | - WebSocket Gateway|                                               | - Feedback Loop    |            |
|  | - HTML5 Dark UI    |                                               | - Strategy Decay   |            |
|  +--------------------+                                               +--------------------+            |
+---------------------------------------------------------------------------------------------------------+
```

---

## 2. Directory & File Structure

```
PROJECT-ALPHA/
|-- app.py                          # Main application entrypoint (FastAPI, Lifespan, Wiring)
|-- requirements.txt                # Python dependencies
|-- pytest.ini                      # Pytest runner configuration
|-- .env.example                    # Environment variable template
|
+-- core/                           # Foundation layer: EventBus, Configuration, Database
|   |-- __init__.py
|   |-- config.py                   # Pydantic v2 Settings & environment variable resolution
|   |-- logging.py                  # Structured JSON & console logger setup
|   |-- types.py                    # Domain models, enums & type definitions
|   +-- bus/
|   |   |-- __init__.py
|   |   |-- event_bus.py            # High-throughput asynchronous Pub/Sub EventBus
|   |   |-- event_types.py          # Strongly typed EventType enum definitions
|   |   \-- subscribers.py          # Central event handler & subscriber registry
|   \-- repository/                 # SQLite persistence layer with connection pool & WAL
|       |-- __init__.py
|       |-- db.py                   # Async SQLite Database manager & migration runner
|       |-- base.py                 # Abstract base repository class
|       |-- signal_repo.py          # Scanner signal persistence & lookup
|       |-- position_repo.py        # Active & historical trade position repository
|       |-- trade_repo.py           # Executed trade ledger
|       |-- order_repo.py           # Exchange order state persistence
|       |-- candle_repo.py          # OHLCV candle history & cache
|       |-- ai_repo.py              # Gemini AI recommendation logs
|       |-- feedback_repo.py        # Pre-deployment gate & feedback logs
|       |-- journal_repo.py         # Post-trade analysis journal
|       |-- learning_repo.py        # Strategy learning & parameter optimization
|       |-- metrics_repo.py         # Rolling telemetry & performance metrics
|       |-- production_repo.py      # Production fleet state & health records
|       |-- production_state_repo.py# Live mode toggles & kill switch state
|       |-- shadow_repo.py          # Shadow trading & divergence metrics
|       |-- event_log_repo.py       # Full system audit event trail
|       \-- migrations/             # Idempotent SQL migration files
|           |-- 001_core_tables.sql
|           |-- 002_ai_intelligence.sql
|           |-- 003_shadow_and_trading.sql
|           |-- 004_production_fleet.sql
|           |-- 005_candle_history.sql
|           |-- 006_exchange_order_persistence.sql
|           |-- 007_execution_positions.sql
|           |-- 008_post_trade_journal.sql
|           |-- 009_production_runtime_state.sql
|           |-- 010_learning_engine.sql
|           |-- 011_backtest_results.sql
|           |-- 012_feedback_loop.sql
|           |-- 013_production_ops.sql
|           \-- 014_live_order_lifecycle.sql
|
+-- scanner/                        # Market ingestion & technical scoring
|   |-- __init__.py
|   |-- service.py                  # Scanner lifecycle & periodic polling coordinator
|   |-- confluence_engine.py        # Multi-indicator technical scoring (C2 Confluence)
|   |-- market_context.py           # Market regime (BULL, BEAR, SIDEWAYS, RISK_ON)
|   |-- signal_filter.py            # 5-Layer filter cascade (Liq, Vol, Pump/Dump, Trend, ATR)
|   |-- anomaly_detector.py         # Volume & price spike anomaly detection
|   |-- lookahead_guard.py          # Data leakage & lookahead bias prevention
|   |-- calibration_worker.py       # Dynamic threshold auto-tuner
|   |-- sentiment_analyzer.py       # Fear & Greed / Social sentiment ingestion
|   |-- news_fetcher.py             # Macro & crypto news parser
|   +-- market/
|   |   |-- __init__.py
|   |   |-- feeder.py               # Live market data feed coordinator
|   |   \-- public_client.py        # CoinDCX / Exchange REST & Candle client
|   \-- research/
|       |-- __init__.py
|       |-- indicators.py           # Vectorized technical indicator computations (EMA, RSI, ATR)
|       |-- service.py              # In-depth coin technical breakdown & research
|       \-- symbol_normalizer.py    # Pair symbol normalization (e.g. BTC/INR, ETH/USDT)
|
+-- execution/                      # Order routing, position management & safety
|   |-- __init__.py
|   |-- service.py                  # Unified Trading Service entrypoint
|   |-- auto_trader.py              # Automated signal-to-order converter
|   |-- position_manager.py         # Dynamic TP/SL, trailing stops & multi-tranche pyramiding
|   |-- reconciliation.py           # Local ledger vs Exchange active order & balance reconciler
|   |-- recovery.py                 # Cold-start crash & restart recovery service
|   +-- adapters/                   # Bot strategy adapters
|   |   |-- __init__.py
|   |   |-- base.py                 # Base strategy execution adapter
|   |   |-- ste_adapter.py          # Swing Trend Expansion bot adapter
|   |   |-- hda_adapter.py          # High-Frequency Divergence Acceleration adapter
|   |   |-- vcp_adapter.py          # Volatility Contraction Pattern adapter
|   |   \-- bbs_adapter.py          # Bollinger Breakout Strategy adapter
|   +-- risk/                       # Autonomous risk management layer
|   |   |-- __init__.py
|   |   |-- service.py              # Central Risk Service evaluator
|   |   |-- capital_guard.py        # Max drawdown & daily loss guardrails
|   |   |-- circuit_breaker.py      # Tripping & cooldown mechanism
|   |   |-- correlation_limits.py   # Sector & portfolio correlation ceilings
|   |   |-- liquidity_sizing.py     # Order size cap based on 24h market volume
|   |   \-- strategy_decay.py       # Dynamic bot de-weighting on consecutive losses
|   +-- shadow/                     # Shadow (Paper vs Live) execution tracker
|   |   |-- __init__.py
|   |   |-- service.py              # Shadow tracking coordinator
|   |   |-- engine.py               # Parallel paper fill simulator
|   |   |-- divergence.py           # Real vs Simulated slippage & fill divergence
|   |   \-- tracker.py              # Performance tracking & delta ledger
|   \-- trading/                    # Low-level exchange protocol & safeguards
|       |-- __init__.py
|       |-- execution_guards.py     # Pre-trade sanity checks (min size, precision, limits)
|       |-- idempotency.py          # Client order ID deduplication & replay protection
|       |-- mode_isolation.py       # Strict separation of PAPER vs LIVE accounts
|       |-- order_state_machine.py  # SUBMITTED -> OPEN -> FILLED -> CLOSED lifecycle
|       |-- precision_rules.py      # Price & quantity lot-size rounders
|       \-- subaccount_manager.py   # Multi-wallet & margin capital manager
|
+-- telegram/                       # Mobile Command & Control (C2) & Notifications
|   |-- __init__.py
|   |-- telegram.py                 # Async Telegram Bot API Client (Long-polling & setMyCommands)
|   |-- telegram_interface.py       # Interactive C2 listener & 22-command autofill dispatcher
|   |-- service.py                  # Central NotificationService & Paper/Live alert router
|   \-- formatters.py               # Rich HTML alert, card & telemetry formatters
|
+-- dashboard/                      # Real-time Web Telemetry UI & REST APIs
|   |-- __init__.py
|   |-- service.py                  # Dashboard aggregation service
|   |-- bot_pipeline.py             # Active bot candidate & position pipeline tracker
|   |-- pipeline.py                 # Telemetry pipeline broadcaster
|   |-- ws_gateway.py               # WebSocket telemetry gateway with 15s heartbeats
|   +-- api/
|   |   |-- __init__.py
|   |   |-- router.py               # Central FastAPI router (/api & /api/v2)
|   |   |-- auth.py                 # API Key & Password security middleware
|   |   |-- schemas.py              # Pydantic request & response models
|   |   |-- dashboard_routes.py     # Telemetry, balance, position & metrics endpoints
|   |   |-- production_routes.py    # Mode-switch & emergency stop endpoints
|   |   \-- research_routes.py      # On-demand coin technical breakdown endpoints
|   +-- static/                     # CSS & Vanilla JS client bundle
|   |   +-- css/dashboard.css
|   |   \-- js/dashboard.js
|   \-- templates/
|       \-- dashboard.html          # Mission Control single-page HTML5 dark interface
|
+-- background/                     # Autonomous schedulers, feedback loops & AI
|   |-- __init__.py
|   |-- scheduler/
|   |   |-- __init__.py
|   |   |-- scheduler.py            # Periodic background job runner
|   |   \-- jobs.py                 # Scan, exit monitor, reconciliation, flush job bindings
|   +-- ai/                         # Gemini AI Intelligence integration
|   |   |-- __init__.py
|   |   |-- client.py               # Async Gemini API client
|   |   |-- intelligence.py         # Signal reasoning & trade recommendation engine
|   |   \-- service.py              # AI service lifecycle & circuit breaker
|   +-- analytics/
|   |   |-- __init__.py
|   |   \-- service.py              # Rolling Sharpe, Sortino, Win Rate & Drawdown analytics
|   +-- backtest/
|   |   |-- __init__.py
|   |   |-- engine.py               # Historical candle backtesting engine
|   |   \-- service.py              # Fleet backtest runner
|   +-- feedback/
|   |   |-- __init__.py
|   |   |-- orchestrator.py         # Closed-loop trade outcome feedback
|   |   |-- gate.py                 # Pre-deployment validation gatekeeper
|   |   \-- service.py              # Feedback service lifecycle
|   +-- learning/
|   |   |-- __init__.py
|   |   |-- optimizer.py            # Parameter self-optimization
|   |   \-- service.py              # Continuous learning coordinator
|   +-- monitoring/
|   |   |-- __init__.py
|   |   |-- alerts.py               # Alert threshold monitor
|   |   |-- health.py               # Subsystem connectivity & latency prober
|   |   \-- metrics.py              # System uptime & memory metrics collector
|   +-- production/
|   |   |-- __init__.py
|   |   |-- controller.py           # Production safety controller & mode gatekeeper
|   |   |-- watchdog.py             # Heartbeat watchdog & thread liveness guard
|   |   \-- service.py              # Production fleet manager
|   \-- journal/
|       |-- __init__.py
|       \-- service.py              # Automated trade journaling & PnL tagger
|
+-- tests/                          # 100% Comprehensive Pytest Suite
|   |-- conftest.py                 # Shared fixtures (mock DB, EventBus, MockTelegramClient)
|   |-- test_telegram_commands.py   # Unit tests for all 22 Telegram slash commands
|   |-- test_telegram_interface.py  # Telegram polling, routing & fallback tests
|   |-- test_safety_invariants.py   # Circuit breaker, kill switch & precision invariants
|   |-- test_c2_scanner.py          # Confluence scoring & 5-layer funnel tests
|   |-- test_execution_master.py    # Order state machine & execution tests
|   \-- e2e/                        # End-to-end integration tests
|       |-- test_v2_e2e_platform.py
|       \-- test_paper_live_isolation.py
|
\-- scripts/                        # Ops & deployment utilities
    |-- deploy_latest_vps.py        # Automated tarball sync & systemd restart script
    \-- benchmark_paper_mode.py     # Paper engine execution benchmark
```

---

## 3. Core Modules & Responsibilities

| Module | Responsibility | Primary Entry Point |
|---|---|---|
| **`core`** | EventBus pub/sub, SQLite WAL database, 14 schema migrations, logging & config | [`core/config.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/core/config.py), [`core/repository/db.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/core/repository/db.py) |
| **`scanner`** | Multi-timeframe (15m, 1h, 1d) candle ingestion, 5-layer funnel filtering, C2 Confluence engine | [`scanner/service.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/scanner/service.py), [`scanner/confluence_engine.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/scanner/confluence_engine.py) |
| **`execution`** | Dynamic TP/SL, position pyramiding, subaccount isolation, broker order reconciliation | [`execution/service.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/execution/service.py), [`execution/position_manager.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/execution/position_manager.py) |
| **`telegram`** | Dual Telegram bots (Paper + Live), native `/` autofill command registration, instant C2 alerts | [`telegram/service.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/telegram/service.py), [`telegram/telegram_interface.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/telegram/telegram_interface.py) |
| **`dashboard`** | FastAPI REST endpoints, real-time WebSocket telemetry push, single-page Dark UI | [`dashboard/service.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/dashboard/service.py), [`dashboard/api/router.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/dashboard/api/router.py) |
| **`background`** | AI trade reasoning (Gemini), exit watchdog (5s), auto-reconciliation (60s), feedback loops | [`background/scheduler/scheduler.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/background/scheduler/scheduler.py), [`background/ai/service.py`](file:///c:/Users/ndeam/OneDrive/Documents/GitHub/PROJECT-ALPHA/background/ai/service.py) |

---

## 4. Environment Configuration Template (`.env`)

```ini
# ==============================================================================
# PROJECT-ALPHA ENVIRONMENT CONFIGURATION
# ==============================================================================

# Execution Deployment Mode: PAPER or LIVE
DEPLOYMENT_MODE=PAPER
V2_DEPLOYMENT_MODE=PAPER

# Database Path
DATABASE_PATH=data/project_alpha.db
V2_DB_PATH=data/project_alpha.db

# Server & Telemetry Network
PORT=5001
HOST=0.0.0.0
WEBSOCKET_ENABLED=true
DASHBOARD_API_KEY=your_secure_api_key_here
DASHBOARD_SECURITY_PASSWORD=your_secure_password_here

# CoinDCX Exchange Credentials (For Real Execution & Data Feeds)
COINDCX_API_KEY=your_coindcx_api_key
COINDCX_API_SECRET=your_coindcx_api_secret

# Telegram Dual Bot Architecture
# Paper Bot (Simulated Trading & Win Rate Optimization)
PAPER_BOT_TOKEN=your_paper_telegram_bot_token
PAPER_CHAT_ID=your_telegram_chat_id

# Live Bot (Real Money Trading Alerts & Emergency Control)
LIVE_BOT_TOKEN=your_live_telegram_bot_token
LIVE_CHAT_ID=your_telegram_chat_id

# Comma-separated authorized chat IDs for operator security
TELEGRAM_ALLOWED_CHAT_IDS=your_telegram_chat_id
TELEGRAM_INTERACTIVE_ENABLED=true

# Google Gemini AI Intelligence
GEMINI_API_KEY=your_gemini_api_key
AI_ENABLED=true
AI_CONFIDENCE_THRESHOLD=70

# Risk Management Ceilings
ORDER_SIZE_INR=200.0
MAX_POSITIONS=3
MAX_CONCURRENT_ORDERS=3
TRAILING_STOP_PERCENT=3.5
DYNAMIC_TP_ENABLED=true
```

---

## 5. How to Replicate for a New Project

1. **Clone this repository structure** and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```
2. **Configure your `.env` file** using the template above.
3. **Run database migrations**:
   The SQLite migration runner inside `core/repository/db.py` automatically applies all 14 `.sql` scripts located in `core/repository/migrations/` on startup.
4. **Launch the platform**:
   ```bash
   python app.py
   ```
5. **Run the test suite**:
   ```bash
   pytest tests/ -q
   ```
