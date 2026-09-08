# Replit setup

## V2 dashboard workflow

The standalone V2 application runs in the `V2 Trading Dashboard` workflow:

```text
V2_DEPLOYMENT_MODE=PAPER V2_TRADING_ENABLED=false uvicorn v2.app_v2:app --host 0.0.0.0 --port 5001
```

The dashboard is available on port `5001` at `/` (also `/dashboard` and
`/v2/dashboard`). The health and operational status endpoint is
`/api/v2/production/status`.

## Safe operating mode

The Replit workflow starts with:

- `V2_DEPLOYMENT_MODE=PAPER`
- `V2_TRADING_ENABLED=false`

This is a non-live environment. Do not change the deployment mode to
`LIVE_MICROCASH` or enable live trading without explicit approval, verified
CoinDCX credentials, and a separate production-readiness review.

## Settings and credentials

Paper mode uses CoinDCX's public market data endpoints and does not require
external-service credentials. Optional integrations are configured through
Replit Secrets or environment variables; never commit their values:

| Setting | Required for this workflow | Purpose |
| --- | --- | --- |
| `DASHBOARD_API_KEY` | Recommended | Protects `/api/v2/*` routes. |
| `SESSION_SECRET` | Not used by standalone V2 | Retained for other application components that use sessions. |
| `COINDCX_API_KEY` | Only for approved live mode | Authenticated CoinDCX account access. |
| `COINDCX_API_SECRET` | Only for approved live mode | CoinDCX request signing. |
| `ALERT_BOT_TOKEN` | Optional | Telegram notifications. |
| `ALERT_CHAT_ID` | Optional | Telegram notification destination. |
| `GEMINI_API_KEY` | Optional | AI signal evaluation. |

The committed V2 runtime override file intentionally contains no notification
or exchange credentials.