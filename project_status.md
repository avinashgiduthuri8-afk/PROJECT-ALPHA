# PROJECT-ALPHA — System Status Report
**Architecture**: V2 Production Build (V1 Fully Retired)
**Date**: September 2026

---

## 🔎 Overview

PROJECT-ALPHA is an autonomous, event-driven cryptocurrency algorithmic trading platform integrated with the **CoinDCX** exchange. Built entirely on **Python 3.12 / FastAPI**, the system runs four multi-timeframe quantitative trading strategies under a unified capital pool, featuring real-time WebSocket telemetry, SQLite persistence with WAL mode, Gemini AI-assisted signal verification with automated circuit breaking, and an interactive Telegram C2 command layer.

---

## 🤖 Active Strategy Bots

| Bot | Name | Strategy Type | Targets | Order Sizing | Status |
|---|---|---|---|---|---|
| **STE** | SuperTrend Momentum | ATR Range Expansion (10,3), Close > EMA50, RSI > 55 | TP: +4.6%, SL: 2.0% | ₹200 Shared Pool | 🟢 Active (PAPER/LIVE) |
| **HDA** | High-Delivery Absorption | Orderflow Accumulation, Delta Spike & Volume Absorption | TP: +5.0%, SL: 2.5% | ₹200 Shared Pool | 🟢 Active (PAPER/LIVE) |
| **VCP** | Volatility Contraction | Minervini Range Squeeze & ATR Contraction | TP: +3.5%, SL: 1.8% | ₹200 Shared Pool | 🟢 Active (PAPER/LIVE) |
| **BBS** | Bollinger-Keltner Squeeze | Volatility Expansion & Momentum Breakout | TP: +4.0%, SL: 2.0% | ₹200 Shared Pool | 🟢 Active (PAPER/LIVE) |

---

## 🏗️ Architecture Stack

`
v2/
├── app_v2.py                 ← Single unified FastAPI application
├── bus/                      ← Asynchronous in-process EventBus (pub/sub)
├── core/                     ← Config (Pydantic BaseSettings), domain types, exceptions, logging
├── market/                   ← Live CoinDCX public WebSocket & REST ticker feed
├── monitoring/               ← Telemetry, health checks, watchdog monitor
├── repository/               ← Async SQLite repository layer with schema migrations
│   └── migrations/           ← 001 through 013 SQL schema definitions
├── services/
│   ├── ai_intelligence_service/ ← Gemini API confirmation + CircuitBreaker + FallbackEvaluator
│   ├── analytics_service/       ← Performance attribution & Sharpe/Sortino ratios
│   ├── backtest_service/        ← Historical walk-forward backtesting
│   ├── dashboard_service/       ← Real-time WebSocket streaming gateway
│   ├── feedback_service/        ← Post-trade learning & weight adjustments
│   ├── journal_service/         ← Execution audit logs & trade journaling
│   ├── learning_service/        ← Strategy parameter calibration
│   ├── notification_service/    ← Async Telegram C2 bot & real-time alerts
│   ├── portfolio_service/       ← Live AUM, cash, and unrealized P&L aggregation
│   ├── production_service/      ← Watchdog health, mode switching, kill-switch
│   ├── research_service/        ← Coin metadata & liquidity research
│   ├── risk_service/            ← Unified capital guard & drawdown breakers
│   ├── scanner_service/         ← 5-layer C2 confluence scanner & technical filters
│   ├── shadow_service/          ← Shadow execution logging
│   └── trading_service/         ← PositionManager, mark-to-market exit loop, CoinDCX execution
└── trading/                  ← Subaccount manager, precision lot/tick rules, CoinDCX auth
`

---

## 📊 Operational Metrics

- **Core Application**: 2/app_v2.py
- **Services**: 15 integrated micro-services
- **Event Bus**: 30+ strongly-typed events
- **Database**: Single SQLite WAL store (2/data/alpha_v2.db)
- **Default Trade Amount**: ₹200 INR (micro-order allocation)
- **Circuit Breakers**: Dual-layer (AI availability circuit breaker + Risk capital/drawdown breaker)
- **CI/CD**: GitHub Actions (.github/workflows/test.yml)
- **Containerization**: Docker (Dockerfile) & Docker Compose (docker-compose.yml)
