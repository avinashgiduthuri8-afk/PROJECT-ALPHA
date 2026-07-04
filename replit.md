# PROJECT-ALPHA

A multi-bot cryptocurrency trading system with a FastAPI web dashboard.

## Project Overview

PROJECT-ALPHA is a paper/live trading platform consisting of four trading bots, a signal scanner, a risk engine, and a real-time web dashboard.

### Bots
- **Scanner Bot** (`bots/scanner_bot/`) — Scans the market for trading signals and maintains a watchlist
- **Volatile Grid X (VGX)** (`bots/volatile_gridX/`) — Grid-style trading bot with trailing stops and circuit breaker
- **Price Movement Bot (PMB)** (`bots/pmb_bot/`) — DCA-style bot triggered by price dips
- **MACD Trend Bounce Bot (MTB)** (`bots/mtb_bot/`) — MACD-based trend following bot

### Core Modules
- **Risk Engine** (`bots/risk_engine/`) — Kill switches, circuit breaker, drawdown limits
- **Monitoring** (`monitoring/`) — System health, metrics, Telegram alerts
- **Dashboard** (`dashboard/`) — HTML/CSS/JS frontend served by FastAPI

### Entry Point
- `app.py` — FastAPI application; mounts all bot routers and serves the dashboard

## Stack
- **Backend**: Python, FastAPI, asyncio
- **Frontend**: Jinja2 templates, vanilla JS, CSS
- **Storage**: JSON files (per-bot, thread-safe with locks)
- **Notifications**: Telegram bots (one per trading bot)

## Environment Variables Required to Run
See `.emergent/emergent.yml` and `CHANGELOG.md` for the full list. Key variables:
- `SESSION_SECRET` — Flask/Starlette session secret
- `BOT_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram (legacy/fallback)
- `SCANNER_BOT_TOKEN`, `VGX_BOT_TOKEN`, `PMB_BOT_TOKEN`, `MTB_BOT_TOKEN` — Per-bot Telegram tokens
- `API_KEY` — Dashboard API authentication
- Exchange API credentials (per-bot config files)

## User Preferences
- Imported for code study — no run workflow needed
