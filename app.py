import asyncio
import json
import logging
import os
import time as _time
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bots.scanner_bot.scanner import get_signals, get_live_signals

from bots.scanner_bot.scanner import get_watchlist
from bots.scanner_bot.scanner import get_stats
from bots.scanner_bot.scanner import get_market_state, get_signal_stats, get_performance_stats, get_performance_signals, get_per_coin_performance, get_signal_history, get_signal_history_stats, get_coin_performance_data, get_coin_performance_stats, get_tier_accuracy_data, get_tier_accuracy_stats
import bots.scanner_bot.main as scanner_main
from bots.scanner_bot.main import scanner_router
import bots.mtb_bot.main as mtb_main
import bots.pmb_bot.main as pmb_main
import bots.volatile_gridX.main as vgx_main
import bots.scanner_bot.telegram_bot as scanner_tg
import bots.volatile_gridX.vgx_telegram_bot as vgx_tg
import bots.pmb_bot.pmb_telegram_bot as pmb_tg
import bots.mtb_bot.mtb_telegram_bot as mtb_tg
from bots.mtb_bot.storage import snapshot as mtb_snapshot
from bots.pmb_bot.storage import snapshot as pmb_snapshot
from bots.risk_engine.engine import snapshot as risk_snapshot

from bots.scanner_bot.scanner import get_watchlist as _scanner_get_watchlist

_VGX_STORAGE_FILE = os.path.join(
    os.path.dirname(__file__), "bots", "volatile_gridX", "storage", "TradingBotCrypto.json"
)
_VGX_PHASE5_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ZEC"]


def vgx_snapshot() -> dict:
    """
    Build a dashboard-ready VGX snapshot by reading the storage JSON directly.
    Never imports VGX config (which requires BOT_TOKEN / API_KEY env vars).
    Returns safe defaults if the file doesn't exist yet.
    """
    raw: dict = {}
    try:
        if os.path.exists(_VGX_STORAGE_FILE) and os.path.getsize(_VGX_STORAGE_FILE) > 0:
            with open(_VGX_STORAGE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        raw = {}

    virtual_balance = float(raw.get("virtual_balance", 1_000_000))
    positions_dict  = raw.get("positions", {})
    trade_log       = raw.get("trade_log",  [])

    open_positions = [
        {
            "coin":             p.get("coin", key.split("_")[0]),
            "buy_price":        round(float(p.get("buy_price", 0)), 4),
            "qty":              round(float(p.get("qty",       0)), 8),
            "amount":           round(float(p.get("amount",    0)), 2),
            "trailing_active":  bool(p.get("trailing_active", False)),
            "source":           p.get("trade_source", "SCANNER"),
        }
        for key, p in (positions_dict.items() if isinstance(positions_dict, dict) else [])
    ]

    sell_trades = [t for t in trade_log if "SELL" in str(t.get("action", "")).upper()]
    wins   = sum(1 for t in sell_trades if float(t.get("pnl", 0)) > 0)
    losses = sum(1 for t in sell_trades if float(t.get("pnl", 0)) < 0)
    total  = len(sell_trades)
    win_rate = round(wins / total * 100, 1) if total > 0 else 0.0

    from datetime import date
    today_str = date.today().isoformat()
    daily_pnl = round(sum(
        float(t.get("pnl", 0))
        for t in sell_trades
        if str(t.get("time", "")).startswith(today_str)
    ), 2)
    total_pnl = round(sum(float(t.get("pnl", 0)) for t in sell_trades), 2)

    last_trade: dict = {}
    if trade_log:
        lt = trade_log[-1]
        last_trade = {
            "time":   lt.get("time",   ""),
            "coin":   lt.get("coin",   ""),
            "action": lt.get("action", ""),
            "price":  lt.get("price",  0),
            "amount": lt.get("amount", 0),
            "pnl":    lt.get("pnl",    0),
        }

    vgx_mode = os.getenv("VGX_BOT_MODE", "PAPER")
    trade_amount = float(os.getenv("VGX_TRADE_AMOUNT", os.getenv("TRADE_AMOUNT", "110")))

    portfolio_hist = raw.get("portfolio_history", [])
    if portfolio_hist:
        _recent = portfolio_hist[-60:]
        equity_labels = [str(h.get("time", ""))[:16] for h in _recent]
        equity_data   = [round(float(h.get("portfolio", virtual_balance)), 2) for h in _recent]
    else:
        equity_labels = ["Start"]
        equity_data   = [round(virtual_balance, 2)]

    return {
        "status":          vgx_mode,
        "virtual_balance": round(virtual_balance, 2),
        "daily_pnl":       daily_pnl,
        "total_pnl":       total_pnl,
        "open_positions":  open_positions,
        "grid_levels":     len(_VGX_PHASE5_COINS),
        "grid_coins":      _VGX_PHASE5_COINS,
        "last_trade":      last_trade,
        "win_rate":        win_rate,
        "wins":            wins,
        "losses":          losses,
        "paper_trades":    len(trade_log),
        "trade_amount":    trade_amount,
        "target_pct":      5.0,
        "stop_loss_pct":   5.0,
        "equity_curve": {
            "labels": equity_labels,
            "data":   equity_data,
        },
        "win_loss_chart": {
            "labels": ["Wins", "Losses"],
            "data":   [wins, losses],
        },
    }


from contextlib import asynccontextmanager
from datetime import datetime, timezone

logger = logging.getLogger("app")
_APP_START_TIME = _time.time()


# ═══════════════════════════════════════════════════════════════
#  API KEY AUTH — fail-closed
# ═══════════════════════════════════════════════════════════════

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY")

if not DASHBOARD_API_KEY:
    async def require_api_key(request: Request, api_key: str = Depends(api_key_header)) -> str:
        if request.url.path in ("/health", "/"):
            return ""
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DASHBOARD_API_KEY not configured",
        )
else:
    async def require_api_key(request: Request, api_key: str = Depends(api_key_header)) -> str:
        if request.url.path in ("/health", "/"):
            return ""
        if api_key != DASHBOARD_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing X-API-Key header",
            )
        return api_key


# ═══════════════════════════════════════════════════════════════
#  SNAPSHOT CACHE — 3-second TTL, asyncio.to_thread offloading
# ═══════════════════════════════════════════════════════════════

_SNAPSHOT_CACHE: dict[str, tuple[float, dict]] = {}
_SNAPSHOT_TTL = 3.0


async def _cached_snapshot(key: str, fn) -> dict:
    """Return a cached snapshot, refreshing via asyncio.to_thread when stale."""
    entry = _SNAPSHOT_CACHE.get(key)
    if entry and (_time.monotonic() - entry[0]) < _SNAPSHOT_TTL:
        return entry[1]
    result: dict = await asyncio.to_thread(fn)
    _SNAPSHOT_CACHE[key] = (_time.monotonic(), result)
    return result


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    """Root dashboard lifespan — starts all bot background tasks."""
    await scanner_main.startup_event()
    await mtb_main.startup_event()
    await pmb_main.startup_event()
    await vgx_main.startup_event()
    try:
        await scanner_tg.startup_event()
    except Exception as e:
        logger.warning("Scanner Telegram bot failed to start: %s", e)
    try:
        await vgx_tg.startup_event()
    except Exception as e:
        logger.warning("VGX Telegram bot failed to start: %s", e)
    try:
        await pmb_tg.startup_event()
    except Exception as e:
        logger.warning("PMB Telegram bot failed to start: %s", e)
    try:
        await mtb_tg.startup_event()
    except Exception as e:
        logger.warning("MTB Telegram bot failed to start: %s", e)
    # AlertManager smoke-check
    try:
        from monitoring.telegram_alerts import AlertManager
        _am = AlertManager()
        logger.info("AlertManager ready — ALERT_BOT_TOKEN=%s",
                    "SET" if _am._telegram._bot_token else "UNSET")
    except Exception as e:
        logger.warning("AlertManager not available: %s", e)
    yield
    await mtb_tg.shutdown_event()
    await pmb_tg.shutdown_event()
    await vgx_tg.shutdown_event()
    await scanner_tg.shutdown_event()
    await vgx_main.shutdown_event()
    await pmb_main.shutdown_event()
    await mtb_main.shutdown_event()
    # scanner shutdown handled by its own _do_shutdown_save in scanner_main


app = FastAPI(
    title="PROJECT-ALPHA ULTIMATE DASHBOARD Framework",
    lifespan=_app_lifespan,
    dependencies=[Depends(require_api_key)],
)


@app.get("/health", include_in_schema=False)
async def health_probe():
    return {"status": "ok"}


# Mount all /api/v1/scanner/* routes from the scanner bot into the dashboard app.
app.include_router(scanner_router)

app.mount(
    "/static",
    StaticFiles(directory="dashboard/static"),
    name="static"
)
templates = Jinja2Templates(directory="dashboard/templates")

def _get_uptime() -> str:
    seconds = int(_time.time() - _APP_START_TIME)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{days}d {hours}h {minutes}m"


def _get_cpu_usage() -> str:
    try:
        import psutil
        return f"{psutil.cpu_percent(interval=None):.1f}%"
    except Exception:
        return "N/A"


def _get_memory_usage() -> str:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return f"{mem.used // (1024 * 1024)}MB"
    except Exception:
        return "N/A"


def _get_health_pct() -> int:
    try:
        scanner_ok = (
            getattr(scanner_main, "_SCANNER_TASK", None) is not None
            and not getattr(scanner_main, "_SCANNER_TASK").done()
        )
        tg_ok = any([
            getattr(scanner_tg, "_SCANNER_TG_APP", None),
            getattr(vgx_tg, "_VGX_TG_APP", None),
            getattr(pmb_tg, "_PMB_TG_APP", None),
            getattr(mtb_tg, "_MTB_TG_APP", None),
        ])
        return 100 if (scanner_ok and tg_ok) else 50
    except Exception:
        return 0


def _compute_market_strength(signals: list) -> int:
    """Return a 0-100 integer gauge value derived from live signal confidence scores."""
    if not signals:
        return 0
    scores = [s.get("confidence", s.get("score", 0)) for s in signals]
    avg = sum(scores) / len(scores)
    # confidence/score are already 0-100 scale; clamp to int
    return max(0, min(100, int(avg)))


def _build_charts_payload(signals: list) -> dict:
    """
    Build the charts sub-dict that script.js expects.
    All four Chart.js widgets read from this structure.
    """
    # --- distribution (doughnut) ---
    # Count signals by priority tier: ELITE → High, STRONG SIGNAL → Medium, rest → Low
    tier_counts = {"High": 0, "Medium": 0, "Low": 0}
    for s in signals:
        tier = s.get("tier", s.get("priority", ""))
        if tier in ("ELITE", "HIGH"):
            tier_counts["High"] += 1
        elif tier in ("STRONG SIGNAL", "MEDIUM"):
            tier_counts["Medium"] += 1
        else:
            tier_counts["Low"] += 1

    # --- daily_signals (line) ---
    # Group signal counts by date from timestamps in the latest scanner signals
    from collections import defaultdict
    day_counts: dict = defaultdict(int)
    for s in signals:
        ts = s.get("timestamp", "")
        if ts:
            try:
                day = ts[:10]   # "YYYY-MM-DD"
                day_counts[day] += 1
            except Exception:
                pass
    sorted_days = sorted(day_counts.keys())
    daily_labels = sorted_days if sorted_days else ["--"]
    daily_data   = [day_counts[d] for d in sorted_days] if sorted_days else [0]

    # --- asset_allocation (pie) ---
    # Distribute signals by coin_class if available, else by coin name
    allocation: dict = defaultdict(int)
    for s in signals:
        key = s.get("coin_class", s.get("coin", "OTHER"))
        allocation[key] += 1
    alloc_labels = list(allocation.keys()) if allocation else ["No Data"]
    alloc_data   = list(allocation.values()) if allocation else [1]

    # --- portfolio_growth (line) ---
    # Placeholder cumulative signal count curve (filled by live trading data when available)
    growth_labels = daily_labels
    cumulative = 0
    growth_data = []
    for d in sorted_days:
        cumulative += day_counts[d]
        growth_data.append(cumulative)
    if not growth_data:
        growth_labels = ["--"]
        growth_data   = [0]

    return {
        "distribution": {
            "labels": list(tier_counts.keys()),
            "data":   list(tier_counts.values()),
        },
        "daily_signals": {
            "labels": daily_labels,
            "data":   daily_data,
        },
        "asset_allocation": {
            "labels": alloc_labels,
            "data":   alloc_data,
        },
        "portfolio_growth": {
            "labels": growth_labels,
            "data":   growth_data,
        },
    }


async def pull_state_payload():

    watchlist = get_watchlist()
    stats = get_stats()
    mtb_state = await _cached_snapshot("mtb", mtb_snapshot)
    pmb_state = await _cached_snapshot("pmb", pmb_snapshot)
    vgx_trade_amount = float(os.getenv("VGX_TRADE_AMOUNT", os.getenv("TRADE_AMOUNT", "110")))
    # Read live scan signals from live_signals.json (written each scan cycle by main.py)
    signal_data = get_live_signals()
    latest_signals = signal_data.get("signals", [])[-50:]   # last 50 signals
    latest_market_state = get_market_state()
    signal_stats = get_signal_stats()

    # Compute per-tier signal counts from JSON stats (persists across restarts)
    _elite  = signal_stats.get("elite_signals", 0)
    _high   = signal_stats.get("high_signals", 0)
    _medium = signal_stats.get("medium_signals", 0)

    # I-04: Cleanup engine stats from scanner bot in-memory state
    try:
        import bots.scanner_bot.main as _scanner_main
        _cleanup_stats = getattr(_scanner_main, "_CLEANUP_STATS", {})
    except Exception:
        _cleanup_stats = {}

    # I-05 / I-07: Health + recovery stats from scanner bot
    try:
        import bots.scanner_bot.main as _scanner_main
        _health_stats    = getattr(_scanner_main, "_HEALTH_STATS",    {})
        _recovery_stats  = getattr(_scanner_main, "_RECOVERY_STATS",  {})
    except Exception:
        _health_stats   = {}
        _recovery_stats = {}

    def _signal_age(ts_str: str) -> str:
        """Return a human-readable relative age string for a signal timestamp."""
        try:
            from datetime import timezone as _tz
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_tz.utc)
            diff = int((datetime.now(_tz.utc) - ts).total_seconds())
            if diff < 60:    return f"{diff}s ago"
            if diff < 3600:  return f"{diff // 60}m ago"
            if diff < 86400: return f"{diff // 3600}h ago"
            return f"{diff // 86400}d ago"
        except Exception:
            return "—"

    # Normalise recent_signals: map internal field names to template-expected names
    recent_signals = [
        {
            "coin":         s.get("coin",         ""),
            "category":     s.get("tier",         ""),   # template uses trace.category
            "score":        s.get("score",        0),
            "signal_price": s.get("price",        0),    # template uses trace.signal_price
            "timestamp":    s.get("timestamp",    ""),
            "market_state": s.get("market_state", ""),
            "confidence":   s.get("confidence",   0),
            "coin_class":   s.get("coin_class",   ""),
            "signal_age":   _signal_age(s.get("timestamp", "")),
            "market":       s.get("market", "INR"),    # I-10: INR/USDT market
        }
        for s in latest_signals
    ]

    return {

        "portfolio_overview": {
            "total_value":    "$0",
            "daily_pnl":      "$0",
            "available_cash": "$0",
            "invested_amount": "$0",
            "total_pnl":      "$0",
            "open_positions": 0,
        },

        "mtb_status": mtb_state["status"],
        "mtb_open_positions": mtb_state["open_positions"],
        "mtb_closed_trades": mtb_state["closed_trades"],
        "mtb_daily_pnl": mtb_state["daily_pnl"],
        "mtb_trade_amount": mtb_state["trade_amount"],
        "mtb_overview": mtb_state,
        "vgx_overview":  await _cached_snapshot("vgx", vgx_snapshot),
        "pmb_overview": pmb_state,
        "risk_engine":  await _cached_snapshot("risk", risk_snapshot),
        "vgx_trade_amount": vgx_trade_amount,

        "scanner_overview": {
            "coins":           _scanner_get_watchlist().get("coins", []),
            "coins_scanned":   len(_scanner_get_watchlist().get("coins", [])),
            "active_signals":  len(latest_signals),
            "elite_signals":   _elite,
            "high_signals":    _high,
            "medium_signals":  _medium,
            "market_state":    "ACTIVE",
            "last_scan_time":  "LIVE",
            # I-04: Cleanup engine stats
            "expired_signals":    _cleanup_stats.get("expired_last_run", 0),
            "last_cleanup_time":  _cleanup_stats.get("last_cleanup_time"),
            "next_cleanup_time":  _cleanup_stats.get("next_cleanup_time"),
            "total_expired":      _cleanup_stats.get("total_expired_lifetime", 0),
            # I-05: Scanner health monitor
            "api_status":             _health_stats.get("api_status", "ONLINE"),
            "last_successful_scan":   _health_stats.get("last_successful_scan"),
            "total_scans":            _health_stats.get("total_scans", 0),
            "failed_scans":           _health_stats.get("failed_scans", 0),
            "consecutive_failures":   _health_stats.get("consecutive_failures", 0),
            "scan_duration_ms":       _health_stats.get("scan_duration_ms", 0),
            "current_market_status":  _health_stats.get("current_market_status", ""),
            "health_score":           _health_stats.get("health_score", 100),
            "health_color":           _health_stats.get("health_color", "green"),
            # I-07: Restart recovery
            "last_restart_time":      _recovery_stats.get("last_restart_time"),
            "recovered_signals":      _recovery_stats.get("recovered_signals", 0),
            "recovery_status":        _recovery_stats.get("recovery_status", "SUCCESS"),
        },

        "service_statuses": {
            "scanner": (
                "ONLINE"
                if getattr(scanner_main, "_SCANNER_TASK", None)
                and not getattr(scanner_main, "_SCANNER_TASK").done()
                else "OFFLINE"
            ),
            "vgx": (await _cached_snapshot("vgx", vgx_snapshot)).get("status", "OFFLINE"),
            "mtb": (
                "ONLINE"
                if getattr(mtb_main, "_MTB_TASK", None)
                and not getattr(mtb_main, "_MTB_TASK").done()
                else "OFFLINE"
            ),
            "pmb": (
                "ONLINE"
                if getattr(pmb_main, "_PMB_TASK", None)
                and not getattr(pmb_main, "_PMB_TASK").done()
                else "OFFLINE"
            ),
            "scanner_telegram": (
                "ONLINE" if getattr(scanner_tg, "_SCANNER_TG_APP", None) is not None
                else "OFFLINE"
            ),
            "vgx_telegram": (
                "ONLINE" if getattr(vgx_tg, "_VGX_TG_APP", None) is not None
                else "OFFLINE"
            ),
            "pmb_telegram": (
                "ONLINE" if getattr(pmb_tg, "_PMB_TG_APP", None) is not None
                else "OFFLINE"
            ),
            "mtb_telegram": (
                "ONLINE" if getattr(mtb_tg, "_MTB_TG_APP", None) is not None
                else "OFFLINE"
            ),
        },

        "railway_monitoring": {
            "status":        "ACTIVE",
            "cpu_usage":     _get_cpu_usage(),
            "memory_usage":  _get_memory_usage(),
            "restart_count": int(os.getenv("RAILWAY_RESTART_COUNT", "0")),
        },

        "system_meta": {
            "uptime":             _get_uptime(),
            "version":            "v1.0",
            "environment":        os.getenv("RAILWAY_ENVIRONMENT", "PRODUCTION"),
            "overall_health_pct": _get_health_pct(),
        },

        "recent_signals": recent_signals,

        "market_state": {
            **latest_market_state,
            "market_strength": latest_market_state.get("strength", _compute_market_strength(latest_signals)),
        },

        "charts": _build_charts_payload(latest_signals),

        "activity_timeline": [],
        "open_positions":    [],
        "closed_trades":     [],

        "watchlist":       watchlist,
        "stats":           stats,
        "notifications":   [],
        "error_logs":      [],
        "performance_stats": get_performance_stats(),
        "performance_signals": get_performance_signals(),
        "coin_performance": {
            "BTC": get_per_coin_performance("BTC"),
            "ETH": get_per_coin_performance("ETH"),
            "SOL": get_per_coin_performance("SOL"),
            "XRP": get_per_coin_performance("XRP"),
        },
        "signal_history": get_signal_history(),
        "signal_history_stats": get_signal_history_stats(),
        "coin_performance_data": get_coin_performance_data(),
        "coin_performance_stats": get_coin_performance_stats(),
        "tier_accuracy_data": get_tier_accuracy_data(),
        "tier_accuracy_stats": get_tier_accuracy_stats(),
        "scanner_meta": {
            "last_scan_time": getattr(scanner_main, "_LAST_SCAN_TIME", None),
            "scan_cycles": getattr(scanner_main, "_SCAN_CYCLES", 0),
            "signals_generated": getattr(scanner_main, "_SIGNALS_GENERATED", 0),
            "status": "RUNNING" if getattr(scanner_main, "_SCAN_CYCLES", 0) > 0 else "STOPPED",
            "next_scan_in": 300,
        },
    }
  
@app.get("/", response_class=HTMLResponse, dependencies=[])
async def viewport_router(request: Request):

    state = await pull_state_payload()
    signals = get_signals()
    stats = get_stats()
    watchlist = get_watchlist()


    return templates.TemplateResponse(
        request=request,

        name="dashboard.html",
        context={
            "request": request,
            "data": state,
            "signals": signals,
            "stats": stats,
            "watchlist": watchlist
        }
    )
   
# ──────────────────────────────────────────────────────────────
# Watchlist Center API
# ──────────────────────────────────────────────────────────────

from pydantic import BaseModel

class WatchlistRequest(BaseModel):
    coin: str

async def _get_coin_markets() -> tuple:
    """Return (inr_coins, usdt_coins) — two separate sets of base symbols.

    INR set: coins that have a direct COIN+INR pair on CoinDCX.
    USDT set: coins that have a COIN+USDT pair but no INR pair.

    Uses the scanner's in-memory ticker cache when available; falls back to a
    fresh API call so validation still works before the scanner has run.
    """
    import bots.scanner_bot.main as _sm
    tickers: list = []
    scanner = getattr(_sm, "_SCANNER", None)
    if scanner is not None:
        cached = getattr(scanner, "_ticker_cache", None)
        if cached:
            tickers = cached
    if not tickers:
        try:
            import requests as _req
            resp = _req.get(
                "https://api.coindcx.com/exchange/ticker", timeout=6
            )
            resp.raise_for_status()
            tickers = resp.json()
        except Exception:
            return set(), set()
    inr_coins: set = set()
    usdt_coins: set = set()
    for ticker in tickers:
        market = ticker.get("market", "")
        if market.endswith("INR") and len(market) > 3:
            inr_coins.add(market[:-3])
        elif market.endswith("USDT") and len(market) > 4:
            usdt_coins.add(market[:-4])
    return inr_coins, usdt_coins


async def _get_supported_coins() -> set:
    """Return the union of INR + USDT coins. Used by /api/supported-coins."""
    inr, usdt = await _get_coin_markets()
    return inr | usdt


# I-08: Manual refresh endpoint
@app.get("/api/watchlist", response_class=JSONResponse)
async def get_scanner_watchlist():
    """Return the unified scanner watchlist (single source of truth)."""
    return _scanner_get_watchlist()


@app.post("/api/watchlist/add", response_class=JSONResponse)
async def add_coin_to_scanner_watchlist(req: WatchlistRequest):
    """Add a coin to the unified scanner watchlist."""
    coin = req.coin.strip().upper()
    inr_coins, usdt_coins = await _get_coin_markets()

    if inr_coins or usdt_coins:
        if coin in inr_coins:
            market = "INR"
        elif coin in usdt_coins:
            market = "USDT"
        else:
            return JSONResponse({
                "success": False,
                "error": "Invalid Coin - Not Available on CoinDCX",
            })
    else:
        market = "INR"

    try:
        from bots.scanner_bot.scanner import WatchlistStore
        store = WatchlistStore()
        store.add(coin)
        coins = store.all()
        return {
            "success": True,
            "coin": coin,
            "market": market,
            "watchlist": coins,
        }
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@app.post("/api/watchlist/remove", response_class=JSONResponse)
async def remove_coin_from_scanner_watchlist(req: WatchlistRequest):
    """Remove a coin from the unified scanner watchlist."""
    try:
        from bots.scanner_bot.scanner import WatchlistStore
        store = WatchlistStore()
        store.remove(req.coin.strip().upper())
        coins = store.all()
        return {
            "success": True,
            "coin": req.coin.upper(),
            "watchlist": coins,
        }
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@app.post("/api/scanner/refresh", response_class=JSONResponse)
async def refresh_scanner():
    """Trigger an immediate scanner refresh from the dashboard.
    Directly sets the scanner's refresh event (same process)."""
    try:
        import bots.scanner_bot.main as _scanner_main
        _scanner_main._REFRESH_EVENT.set()
        return JSONResponse(content={"success": True, "message": "Scan triggered"})
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": "Scanner refresh failed"},
            status_code=503,
        )




@app.get("/api/supported-coins", response_class=JSONResponse)
async def supported_coins_endpoint():
    """Return sorted list of coin symbols that have an INR or USDT pair on CoinDCX."""
    coins = sorted(await _get_supported_coins())
    return {"coins": coins}


@app.get("/api/v1/state", response_class=JSONResponse)
async def unified_state_polling_endpoint():
    """Future production data hook. Live bots simply post metrics to rewrite state."""
    return await pull_state_payload()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
  

# ═══════════════════════════════════════════════════════════════
#  UNIFIED STATISTICS ENGINE
# ═══════════════════════════════════════════════════════════════

def _unified_stats(
    vgx: dict | None = None,
    mtbs: dict | None = None,
    pmbs: dict | None = None,
) -> dict:
    """
    Single source of truth for all analytics across VGX, PMB, MTB.
    Win rate, best/worst signal, coin leaderboard — computed fresh each call.
    Accepts pre-fetched snapshot dicts so async callers can supply them via
    asyncio.to_thread instead of blocking here.
    """
    from bots.scanner_bot.scanner import get_signals as _get_signals

    raw_signals: list = []
    try:
        data = _get_signals()
        raw_signals = data.get("signals", []) if isinstance(data, dict) else []
    except Exception:
        pass

    wins = losses = 0
    best_signal = worst_signal = None
    best_ret = worst_ret = None
    coin_stats: dict = {}

    for sig in raw_signals:
        coin  = sig.get("coin", "UNKNOWN")
        evals = sig.get("evaluations") or {}
        ret   = None
        for h in ("24h", "4h", "1h"):
            ev = evals.get(h)
            if ev:
                try:
                    ret = float(ev["change_percent"]); break
                except (KeyError, TypeError, ValueError):
                    pass
        if ret is None:
            continue
        if ret > 0:
            wins += 1
        else:
            losses += 1
        if best_ret is None or ret > best_ret:
            best_ret = ret
            best_signal = {"coin": coin, "return": round(ret, 4), "tier": sig.get("priority", ""), "timestamp": sig.get("timestamp", "")}
        if worst_ret is None or ret < worst_ret:
            worst_ret = ret
            worst_signal = {"coin": coin, "return": round(ret, 4), "tier": sig.get("priority", ""), "timestamp": sig.get("timestamp", "")}
        if coin not in coin_stats:
            coin_stats[coin] = {"coin": coin, "signals": 0, "wins": 0, "losses": 0, "total_return": 0.0}
        coin_stats[coin]["signals"] += 1
        coin_stats[coin]["total_return"] = round(coin_stats[coin]["total_return"] + ret, 4)
        if ret > 0:
            coin_stats[coin]["wins"] += 1
        else:
            coin_stats[coin]["losses"] += 1

    evaluated = wins + losses
    win_rate  = round(wins / evaluated * 100, 2) if evaluated else 0.0
    leaderboard = sorted(coin_stats.values(), key=lambda x: x["total_return"], reverse=True)
    for entry in leaderboard:
        n = entry["wins"] + entry["losses"]
        entry["win_rate"] = round(entry["wins"] / n * 100, 1) if n else 0.0

    if vgx is None:
        vgx  = vgx_snapshot()
    if mtbs is None:
        mtbs = mtb_snapshot()
    if pmbs is None:
        pmbs = pmb_snapshot()

    return {
        "signals_total":     len(raw_signals),
        "signals_evaluated": evaluated,
        "win_rate":          win_rate,
        "wins":              wins,
        "losses":            losses,
        "best_signal":       best_signal,
        "worst_signal":      worst_signal,
        "coin_leaderboard":  leaderboard[:20],
        "bot_pnl": {
            "vgx": {"daily_pnl": vgx.get("daily_pnl", 0),  "total_pnl": vgx.get("total_pnl", 0)},
            "mtb": {"daily_pnl": mtbs.get("daily_pnl", 0), "total_pnl": mtbs.get("total_pnl", 0)},
            "pmb": {"daily_pnl": pmbs.get("daily_pnl", 0), "total_pnl": pmbs.get("total_pnl", 0)},
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/stats/unified", response_class=JSONResponse)
async def unified_statistics():
    """Unified statistics engine — win rate, best/worst signal, coin leaderboard."""
    try:
        vgx, mtbs, pmbs = await asyncio.gather(
            _cached_snapshot("vgx", vgx_snapshot),
            _cached_snapshot("mtb", mtb_snapshot),
            _cached_snapshot("pmb", pmb_snapshot),
        )
        return _unified_stats(vgx=vgx, mtbs=mtbs, pmbs=pmbs)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/v1/stats/leaderboard", response_class=JSONResponse)
async def coin_leaderboard():
    """Coin leaderboard sorted by total return across all evaluated signals."""
    try:
        stats = _unified_stats()
        return {"leaderboard": stats["coin_leaderboard"], "timestamp": stats["timestamp"]}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ═══════════════════════════════════════════════════════════════
#  ALERT NOTIFICATION CENTER
# ═══════════════════════════════════════════════════════════════

_ALERT_LOG: list = []
_ALERT_LOG_MAX = 200


def _push_alert(level: str, source: str, message: str) -> None:
    _ALERT_LOG.append({
        "level":     level,
        "source":    source,
        "message":   message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if len(_ALERT_LOG) > _ALERT_LOG_MAX:
        del _ALERT_LOG[: len(_ALERT_LOG) - _ALERT_LOG_MAX]


@app.get("/api/v1/alerts", response_class=JSONResponse)
async def alert_center(limit: int = 50):
    """Alert Notification Center — most recent alerts, newest first."""
    alerts = list(reversed(_ALERT_LOG[-limit:]))
    return {"alerts": alerts, "total": len(_ALERT_LOG), "limit": limit}


@app.post("/api/v1/alerts/push", response_class=JSONResponse)
async def push_alert(level: str = "INFO", source: str = "system", message: str = ""):
    """Push a new alert into the notification center."""
    _push_alert(level.upper(), source, message)
    return {"ok": True, "total": len(_ALERT_LOG)}


# ═══════════════════════════════════════════════════════════════
#  ERROR LOG VIEWER
# ═══════════════════════════════════════════════════════════════

_ERROR_LOG: list = []
_ERROR_LOG_MAX = 100


def _log_error(source: str, error: str, context: str = "") -> None:
    _ERROR_LOG.append({
        "source":    source,
        "error":     error,
        "context":   context,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if len(_ERROR_LOG) > _ERROR_LOG_MAX:
        del _ERROR_LOG[: len(_ERROR_LOG) - _ERROR_LOG_MAX]


@app.get("/api/v1/errors", response_class=JSONResponse)
async def error_log_viewer(limit: int = 50):
    """Error Log Viewer — most recent errors, newest first."""
    errors = list(reversed(_ERROR_LOG[-limit:]))
    return {"errors": errors, "total": len(_ERROR_LOG), "limit": limit}


# ═══════════════════════════════════════════════════════════════
#  TELEGRAM ANALYTICS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/stats/telegram", response_class=JSONResponse)
async def telegram_analytics():
    """Telegram-ready analytics summary — compact format for bot /stats command."""
    try:
        risk, vgx, mtbs, pmbs = await asyncio.gather(
            _cached_snapshot("risk", risk_snapshot),
            _cached_snapshot("vgx",  vgx_snapshot),
            _cached_snapshot("mtb",  mtb_snapshot),
            _cached_snapshot("pmb",  pmb_snapshot),
        )
        stats = _unified_stats(vgx=vgx, mtbs=mtbs, pmbs=pmbs)

        lines = [
            "📊 PROJECT-ALPHA ANALYTICS",
            "",
            "📡 Scanner",
            f"  Signals: {stats['signals_total']}  Evaluated: {stats['signals_evaluated']}",
            f"  Win Rate: {stats['win_rate']}%  (W:{stats['wins']} L:{stats['losses']})",
        ]
        if stats["best_signal"]:
            b = stats["best_signal"]
            lines.append(f"  Best: {b['coin']} +{b['return']}%")
        if stats["worst_signal"]:
            w = stats["worst_signal"]
            lines.append(f"  Worst: {w['coin']} {w['return']}%")
        lines += [
            "",
            f"🤖 VGX  [{vgx.get('status','?')}]",
            f"  Daily PnL: ₹{vgx.get('daily_pnl', 0):.2f}  Total: ₹{vgx.get('total_pnl', 0):.2f}",
            f"  Positions: {len(vgx.get('open_positions', []))}  Win Rate: {vgx.get('win_rate', 0)}%",
            "",
            f"🤖 MTB  [{mtbs.get('status','?')}]",
            f"  Daily PnL: ₹{mtbs.get('daily_pnl', 0):.4f}  Cash: ₹{mtbs.get('cash_balance', 0):.2f}",
            f"  Positions: {len(mtbs.get('open_positions', []))}",
            "",
            f"🤖 PMB  [{pmbs.get('status','?')}]",
            f"  Daily PnL: ₹{pmbs.get('daily_pnl', 0):.4f}  Cash: ₹{pmbs.get('cash_balance', 0):.2f}",
            f"  Positions: {len(pmbs.get('open_positions', []))}",
            "",
            "⚡ Risk Engine",
            f"  Trading: {'✅' if risk.get('trading_enabled') else '❌'}  Emergency Stop: {'🔴' if risk.get('emergency_stop') else '✅'}",
            f"  Capital: ₹{risk.get('total_deployed', 0):.2f} / ₹{risk.get('total_capital_limit', 0):.0f}  ({risk.get('capital_utilisation_pct', 0):.1f}%)",
        ]

        return {
            "text": "\n".join(lines),
            "stats": stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        _log_error("telegram_analytics", str(exc))
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ═══════════════════════════════════════════════════════════════
#  CSV / JSON EXPORT
# ═══════════════════════════════════════════════════════════════

from fastapi.responses import StreamingResponse
import csv
import io


@app.get("/api/v1/export/signals.json")
async def export_signals_json():
    """Download all scanner signals as JSON."""
    try:
        import json as _json
        from bots.scanner_bot.scanner import get_signals as _gs
        content = _json.dumps(_gs(), indent=2, ensure_ascii=False)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=signals.json"},
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/v1/export/signals.csv")
async def export_signals_csv():
    """Download all scanner signals as CSV."""
    try:
        from bots.scanner_bot.scanner import get_signals as _gs
        data = _gs()
        signals = data.get("signals", []) if isinstance(data, dict) else []
        output = io.StringIO()
        fieldnames = ["coin", "priority", "market_state", "opportunity_score",
                      "opp_confidence", "risk_level", "timestamp", "eval_1h", "eval_4h", "eval_24h"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for sig in signals:
            evals = sig.get("evaluations") or {}
            writer.writerow({
                "coin":              sig.get("coin", ""),
                "priority":          sig.get("priority", ""),
                "market_state":      sig.get("market_state", ""),
                "opportunity_score": sig.get("opportunity_score", 0),
                "opp_confidence":    sig.get("opp_confidence", 0),
                "risk_level":        sig.get("risk_level", ""),
                "timestamp":         sig.get("timestamp", ""),
                "eval_1h":           evals.get("1h", {}).get("change_percent", ""),
                "eval_4h":           evals.get("4h", {}).get("change_percent", ""),
                "eval_24h":          evals.get("24h", {}).get("change_percent", ""),
            })
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=signals.csv"},
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/v1/export/trades.csv")
async def export_trades_csv():
    """Download all trades from VGX, MTB, PMB as unified CSV."""
    try:
        from bots.mtb_bot.storage import load_trades as mtb_trades
        from bots.pmb_bot.storage import load_trades as pmb_trades
        output = io.StringIO()
        fieldnames = ["bot", "coin", "symbol", "action", "status", "price", "amount", "pnl", "timestamp"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        vgx_raw = await _cached_snapshot("vgx", vgx_snapshot)
        for t in vgx_raw.get("open_positions", []):
            writer.writerow({"bot": "VGX", "coin": t.get("coin"), "action": "BUY",
                             "status": "OPEN", "price": t.get("buy_price"), "amount": t.get("amount")})
        for trade in mtb_trades():
            row = dict(trade); row["bot"] = "MTB"; writer.writerow(row)
        for trade in pmb_trades():
            row = dict(trade); row["bot"] = "PMB"; writer.writerow(row)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=trades.csv"},
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/v1/export/stats.json")
async def export_stats_json():
    """Download unified stats snapshot as JSON."""
    try:
        import json as _json
        risk, vgx, mtbs, pmbs = await asyncio.gather(
            _cached_snapshot("risk", risk_snapshot),
            _cached_snapshot("vgx",  vgx_snapshot),
            _cached_snapshot("mtb",  mtb_snapshot),
            _cached_snapshot("pmb",  pmb_snapshot),
        )
        payload = {
            "unified":     _unified_stats(vgx=vgx, mtbs=mtbs, pmbs=pmbs),
            "risk":        risk,
            "vgx":         vgx,
            "mtb":         mtbs,
            "pmb":         pmbs,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        content = _json.dumps(payload, indent=2, ensure_ascii=False)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=stats.json"},
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
