# PROJECT-ALPHA Trading Dashboard

## Overview
A FastAPI-based crypto trading dashboard running multiple automated trading bots against the CoinDCX exchange (INR and USDT markets). Includes a web dashboard, Telegram bot integrations, and a paper/live trading mode.

### Bots
| Bot | Description |
|-----|-------------|
| **scanner_bot** | Scans watchlist coins, generates buy signals by tier (ELITE / HIGH / MEDIUM) |
| **mtb_bot** | Momentum Trading Bot — opens/closes paper positions from scanner signals |
| **pmb_bot** | Portfolio Management Bot — partial-sell ladder strategy |
| **volatile_gridX (VGX)** | Grid-style paper trader with trailing stop and stop-loss |
| **risk_engine** | Cross-bot deployed-capital and drawdown guard |

### Stack
- **Backend**: FastAPI + Uvicorn (Python 3.12)
- **Templates**: Jinja2 (`dashboard/templates/`)
- **Storage**: JSON files under each bot's `storage/` or `data/` directory
- **Bots**: python-telegram-bot library

## How to run
```
python app.py
```
The app serves on port 5000.

## Environment variables
| Variable | Required | Description |
|----------|----------|-------------|
| `DASHBOARD_API_KEY` | Yes (set in .replit) | Protects all API routes |
| `BOT_TOKEN` | Optional | Telegram bot token for VGX |
| `API_KEY` | Optional | CoinDCX API key (paper trading works without it) |
| `SCANNER_BOT_TOKEN` / `MTB_BOT_TOKEN` / `PMB_BOT_TOKEN` | Optional | Per-bot Telegram tokens |
| `VGX_BOT_MODE` | Optional | `PAPER` (default) or `LIVE` |
| `VGX_ENABLED` / `MTB_ENABLED` / `PMB_ENABLED` | Optional | Toggle each bot (all default true) |

Without Telegram tokens the bots run headlessly; the dashboard still works.

## Dependencies
Install with:
```
pip install -r requirements.txt
```
The `ta` package (Technical Analysis library) is required and included in `requirements.txt`.

## User preferences
- Prefers bug audits and code quality improvements.
