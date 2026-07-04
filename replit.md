# PROJECT-ALPHA Trading Dashboard

## Overview
A multi-bot crypto trading dashboard built with FastAPI. Runs four bots in paper or live mode:

- **Scanner Bot** — scans CoinDCX market data, generates signals, manages watchlist
- **MTB Bot** (Momentum Trading Bot) — acts on scanner signals
- **PMB Bot** (Portfolio Management Bot) — portfolio-level position management
- **VGX Bot** (Volatile GridX) — grid trading strategy for volatile coins

The web dashboard (port 5000) provides a unified view of all bots, positions, signals, and performance.

## Stack
- **Backend**: Python 3.12, FastAPI, Uvicorn
- **Frontend**: Jinja2 templates + static assets
- **Data**: JSON file storage (per-bot `data/` directories)
- **Exchange**: CoinDCX API
- **Notifications**: Telegram bots (optional, token-gated)

## How to Run
The app starts with `python app.py` on port 5000.

Login with the `DASHBOARD_API_KEY` (set in environment).

## Environment Variables
| Variable | Description |
|---|---|
| `SESSION_SECRET` | Flask/Starlette session signing key |
| `DASHBOARD_API_KEY` | API key for dashboard login |
| `SCANNER_BOT_TOKEN` | Telegram token for scanner bot (optional) |
| `VGX_BOT_TOKEN` | Telegram token for VGX bot (optional) |
| `PMB_BOT_TOKEN` | Telegram token for PMB bot (optional) |
| `MTB_BOT_TOKEN` | Telegram token for MTB bot (optional) |
| `ALERT_BOT_TOKEN` | Telegram token for alert notifications (optional) |
| `SCANNER_CHAT_ID` | Telegram chat ID for scanner alerts |
| `VGX_CHAT_ID` | Telegram chat ID for VGX alerts |
| `PMB_CHAT_ID` | Telegram chat ID for PMB alerts |
| `MTB_CHAT_ID` | Telegram chat ID for MTB alerts |
| `ALERT_CHAT_ID` | Telegram chat ID for system alerts |
| `TRADING_ENABLED` | `true`/`false` — master trading switch |
| `VGX_ENABLED` | Enable/disable VGX bot |
| `PMB_ENABLED` | Enable/disable PMB bot |
| `MTB_ENABLED` | Enable/disable MTB bot |
| `EMERGENCY_STOP` | `true` triggers emergency halt |

All bots run in **PAPER** mode by default until a live exchange API key is configured.

## User Preferences
