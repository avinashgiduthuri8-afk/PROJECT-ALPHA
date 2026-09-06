# PROJECT-ALPHA V2 — Production Runbook

## 1. Overview & Architecture
PROJECT-ALPHA V2 is an event-driven, autonomous multi-strategy cryptocurrency trading system running against the CoinDCX exchange.

### System Architecture
- **Web & API Framework**: FastAPI application (2/app_v2.py)
- **Event Bus**: Central asynchronous in-process pub/sub (2/bus/event_bus.py)
- **Persistence Layer**: SQLite database (2/data/alpha_v2.db) in WAL mode
- **Strategies**:
  - **STE**: SuperTrend ATR Range Expansion
  - **HDA**: High-Delivery Absorption & Orderflow
  - **VCP**: Volatility Contraction Pattern
  - **BBS**: Bollinger-Keltner Squeeze Expansion
- **Safety**:
  - Unified Capital Pool with dynamic headroom
  - Heuristic & Gemini AI signal evaluation with automated Circuit Breaker
  - High-frequency (~5s) mark-to-market position exit evaluation
  - Single-coin active position lock (fleet-wide deduplication)
  - Friction-aware minimum R:R >= 1.50 calculation

---

## 2. Environment Configuration Reference

| Environment Variable | Required | Default | Description |
|---|---|---|---|
| DEPLOYMENT_MODE | No | PAPER | Operating mode: PAPER or LIVE_MICROCASH. |
| DASHBOARD_API_KEY | Yes | lpha-dev-key | Secret key for REST API (X-API-Key) and WebSocket auth. |
| COINDCX_API_KEY | If LIVE | None | Master CoinDCX API key. |
| COINDCX_API_SECRET | If LIVE | None | Master CoinDCX API secret for HMAC-SHA256 signatures. |
| GEMINI_API_KEY | Optional | None | Google Gemini API key for quantitative signal confirmation. |
| V2_PORT / PORT | No | 5001 | HTTP and WebSocket binding port. |
| ORDER_SIZE_INR | No | 200.0 | Default micro-cash order size in INR (minimum ₹200). |
| ALERT_BOT_TOKEN | Optional | None | Telegram Bot token for C2 interface and alerts. |
| ALERT_CHAT_ID | Optional | None | Authorized Telegram Chat ID. |
| TELEGRAM_ALLOWED_CHAT_IDS| Optional | None | Whitelist of Telegram user/chat IDs permitted to execute commands. |

---

## 3. Pre-Flight Checklist: Transitioning from PAPER to LIVE

Before switching DEPLOYMENT_MODE=LIVE_MICROCASH, the operator MUST verify:

1. **Exchange Account Connectivity**:
   - Verify CoinDCX API Key has Spot Trading permissions enabled.
   - Verify CoinDCX available INR wallet balance >= ₹1,000 via /capital or /status.
2. **Dashboard Sanity Check**:
   - Connect to dashboard (http://<host>:5001/).
   - Confirm WebSocket telemetry status is 🟢 CONNECTED.
   - Confirm all 4 bot statuses are ONLINE.
   - Confirm ticker loop is active with live CoinDCX prices.
3. **Database Health**:
   - Verify 2/data/alpha_v2.db is writable.
   - Confirm no corrupt migrations (journal_mode=WAL).
4. **Risk Breakers Reset**:
   - Confirm circuit_breaker_open=false and emergency_stop=false.
5. **Mode Flip**:
   - Update .env: DEPLOYMENT_MODE=LIVE_MICROCASH.
   - Or use Telegram C2 command: /mode LIVE_MICROCASH (requires operator confirmation).

---

## 4. Telegram C2 Command Reference

| Command | Arguments | Description |
|---|---|---|
| /status | None | System health, active bots, uptime, and deployment mode. |
| /positions | None | Open positions, mark-to-market prices, and unrealized P&L. |
| /trades | None | Last 10 executed and closed trades with realized P&L. |
| /pnl | None | Daily realized and unrealized P&L breakdown. |
| /capital | None | Live exchange wallet balance, deployed capital, and pool headroom. |
| /pause | [BOT] | Temporarily pause new entries without closing open positions. |
| /resume | [BOT] | Resume signal processing and new entries. |
| /emergency_stop | None | Trip circuit breaker and immediately halt all trade entries. |
| /setamount | <INR> | Update runtime trade amount (e.g. /setamount 250). |
| /reconcile | None | Trigger immediate order reconciliation against exchange. |

---

## 5. Order Execution & Protective Stop Constraints

> [!WARNING]
> **Exchange Protective Order Exposure**:
> CoinDCX Spot INR REST API does **NOT** support native OCO (One-Cancels-the-Other) or server-side bracket orders.
> Stop-loss, take-profit, and trailing stops are actively tracked in memory and SQLite by TradingService.poll_exits(), evaluating authoritative exchange ticker prices every ~5 seconds.
>
> If the process crashes or is stopped:
> 1. Open positions remain unhedged on the exchange.
> 2. Upon restart, RestartRecoveryService automatically rehydrates active positions from lpha_v2.db and immediately resumes exit evaluation.

---

## 6. Circuit Breaker Recovery Protocol

### A. Gemini AI Circuit Breaker (AI_CIRCUIT_OPENED)
- **Cause**: 3 consecutive Gemini API failures or timeouts.
- **System Behavior**: Skips Gemini API; executes zero-latency heuristic FallbackEvaluator. Trading is **not** halted.
- **Recovery**: Automatic. After 60s cooldown, breaker transitions to HALF_OPEN and sends a trial probe. If successful, breaker closes automatically.

### B. Risk Engine Circuit Breaker (CIRCUIT_BREAKER_TRIGGERED)
- **Cause**: Daily drawdown limit hit or consecutive trade losses.
- **System Behavior**: Halts all new trade entries. Existing open positions continue to be monitored for exit.
- **Recovery**:
  1. Inspect root cause via /status or /risk.
  2. Review recent closed trades via /trades.
  3. Send /resume to reset breaker state once conditions stabilize.

---

## 7. Rollback & Emergency Procedures

### Immediate Kill Switch
`ash
# Via Telegram
/emergency_stop

# Or via REST API
curl -X POST http://localhost:5001/api/v2/production/kill-switch -H "X-API-Key: <KEY>"
`

### Rollback to PAPER Mode
`ash
# Via Telegram
/mode PAPER

# Or via REST API
curl -X POST http://localhost:5001/api/v2/production/set-mode -H "X-API-Key: <KEY>" -H "Content-Type: application/json" -d '{"mode": "PAPER"}'
`
