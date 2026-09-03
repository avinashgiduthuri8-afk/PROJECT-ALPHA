"""
V2 Application Entry Point.

Runs a standalone FastAPI server on V2_PORT (default 5001).
V1 app.py on port 5000 is completely untouched.

Startup sequence:
  1. Load V2Config
  2. Open SQLite database (apply migrations)
  3. Initialise repositories
  4. Initialise ScannerService
  5. Start BackgroundScheduler + register jobs
  6. Wire API router
  7. Serve on V2_PORT

Shutdown sequence (lifespan):
  1. Stop scheduler
  2. Stop scanner service
  3. Close database

Run:
    python v2/app_v2.py
    # or via workflow: python -m v2.app_v2
"""

from __future__ import annotations

import asyncio
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ── Ensure project root is on sys.path when run directly ─────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from v2.core.config import get_config
from v2.core.logging import get_logger
from v2.bus import bus
from v2.repository.db import Database
from v2.repository.signal_repo import SignalRepository
from v2.repository.ai_repo import AIAnalysisRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.repository.shadow_repo import ShadowRepository
from v2.repository.metrics_repo import MetricsRepository
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.candle_repo import CandleRepository

from v2.services.scanner_service import ScannerService
from v2.services.ai_intelligence_service import AIIntelligenceService
from v2.services.risk_service import RiskService
from v2.services.portfolio_service import PortfolioService
from v2.services.trading_service import TradingService
from v2.services.shadow_service import ShadowService
from v2.services.notification_service import NotificationService
from v2.services.dashboard_service import DashboardService
from v2.services.research_service import CoinResearchService

from v2.monitoring import HealthChecker, MetricsCollector, AlertManager
from v2.scheduler import BackgroundScheduler, register_all_jobs
from v2.api.router import router as api_router, init_router
from v2.api.websocket import router as ws_router, init_websocket
from v2.bus.subscribers import register_all as register_all_subscribers

logger = get_logger("v2.app")

# ── Module-level service singletons (assigned in lifespan) ────────────────────
_db: Database | None = None
_scanner_service: ScannerService | None = None
_ai_service: AIIntelligenceService | None = None
_risk_service: RiskService | None = None
_portfolio_service: PortfolioService | None = None
_trading_service: TradingService | None = None
_shadow_service: ShadowService | None = None
_notification_service: NotificationService | None = None
_dashboard_service: DashboardService | None = None
_scheduler: BackgroundScheduler | None = None
_metrics_collector: MetricsCollector | None = None
_health_checker: HealthChecker | None = None
_alert_manager: AlertManager | None = None
_research_service: CoinResearchService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: startup then shutdown."""
    global _db, _scanner_service, _ai_service, _risk_service
    global _portfolio_service, _trading_service, _shadow_service
    global _notification_service, _dashboard_service, _scheduler
    global _metrics_collector, _health_checker, _alert_manager
    global _research_service

    cfg = get_config()
    logger.info("V2 starting", extra={"port": cfg.v2_port, "db": cfg.v2_db_path})

    # 1. Database
    _db = Database(cfg.v2_db_path)
    await _db.open()

    # 2. Repositories
    conn = _db.connection
    signal_repo    = SignalRepository(conn)
    ai_repo        = AIAnalysisRepository(conn)
    position_repo  = PositionRepository(conn)
    trade_repo     = TradeRepository(conn)
    shadow_repo    = ShadowRepository(conn)
    metrics_repo   = MetricsRepository(conn)
    event_log_repo = EventLogRepository(conn)
    candle_repo    = CandleRepository(conn)

    # 3. Services
    _scanner_service = ScannerService(
        bus            = bus,
        signal_repo    = signal_repo,
        event_log_repo = event_log_repo,
        config         = cfg,
        candle_repo    = candle_repo,
    )
    await _scanner_service.start()

    _ai_service = AIIntelligenceService(
        bus            = bus,
        ai_repo        = ai_repo,
        event_log_repo = event_log_repo,
        config         = cfg,
        signal_repo    = signal_repo,
    )
    await _ai_service.start()

    _risk_service = RiskService(
        bus            = bus,
        position_repo  = position_repo,
        trade_repo     = trade_repo,
        event_log_repo = event_log_repo,
        config         = cfg,
    )
    await _risk_service.start()

    _portfolio_service = PortfolioService(
        bus            = bus,
        position_repo  = position_repo,
        trade_repo     = trade_repo,
        metrics_repo   = metrics_repo,
        config         = cfg,
    )
    await _portfolio_service.start()

    _shadow_service = ShadowService(
        bus            = bus,
        shadow_repo    = shadow_repo,
        event_log_repo = event_log_repo,
        config         = cfg,
    )
    await _shadow_service.start()

    _trading_service = TradingService(
        bus            = bus,
        position_repo  = position_repo,
        trade_repo     = trade_repo,
        event_log_repo = event_log_repo,
        config         = cfg,
        shadow_engine  = _shadow_service.engine,
    )
    await _trading_service.start()

    _notification_service = NotificationService(
        bus            = bus,
        config         = cfg,
        signal_repo    = signal_repo,
        position_repo  = position_repo,
        trade_repo     = trade_repo,
        portfolio_service = _portfolio_service,
        risk_service   = _risk_service,
        trading_service = _trading_service,
    )

    _dashboard_service = DashboardService(
        bus               = bus,
        config            = cfg,
        scanner_service   = _scanner_service,
        ai_service        = _ai_service,
        risk_service      = _risk_service,
        portfolio_service = _portfolio_service,
        trading_service   = _trading_service,
        shadow_service    = _shadow_service,
    )
    await _dashboard_service.start()
    _notification_service.wire_dependencies(dashboard_service=_dashboard_service)
    await _notification_service.start()

    # 4. Monitoring & Observability
    _metrics_collector = MetricsCollector()
    _health_checker = HealthChecker(
        db                   = _db,
        scanner_service      = _scanner_service,
        ai_service           = _ai_service,
        risk_service         = _risk_service,
        portfolio_service    = _portfolio_service,
        trading_service      = _trading_service,
        shadow_service       = _shadow_service,
        notification_service = _notification_service,
    )
    _alert_manager = AlertManager(
        bus            = bus,
        health_checker = _health_checker,
        metrics        = _metrics_collector,
    )

    # 5. Scheduler
    _scheduler = BackgroundScheduler(bus)
    register_all_jobs(
        scheduler       = _scheduler,
        config          = cfg,
        scanner_service = _scanner_service,
        trading_service = _trading_service,
    )
    await _scheduler.start()
    _health_checker._scheduler = _scheduler

    # 6. Wire WebSocket & subscriber registry
    init_websocket(_dashboard_service.ws_manager, dashboard_service=_dashboard_service)
    register_all_subscribers(
        bus,
        scanner_service      = _scanner_service,
        ai_service           = _ai_service,
        risk_service         = _risk_service,
        portfolio_service    = _portfolio_service,
        trading_service      = _trading_service,
        shadow_service       = _shadow_service,
        notification_service = _notification_service,
        dashboard_service    = _dashboard_service,
    )

    _research_service = CoinResearchService(
        candle_repo = candle_repo,
        config      = cfg,
    )

    # 7. Wire API router state
    init_router(
        scanner_service      = _scanner_service,
        scheduler            = _scheduler,
        config               = cfg,
        ai_service           = _ai_service,
        ai_repo              = ai_repo,
        signal_repo          = signal_repo,
        risk_service         = _risk_service,
        portfolio_service    = _portfolio_service,
        trading_service      = _trading_service,
        shadow_service       = _shadow_service,
        shadow_repo          = shadow_repo,
        position_repo        = position_repo,
        trade_repo           = trade_repo,
        event_log_repo       = event_log_repo,
        notification_service = _notification_service,
        dashboard_service    = _dashboard_service,
        health_checker       = _health_checker,
        metrics_collector    = _metrics_collector,
        research_service     = _research_service,
    )

    # Trigger initial warm-up scanner poll in background
    asyncio.create_task(_scanner_service.poll())
    logger.info("V2 startup complete — background scanner warm-up triggered")

    yield  # ── application is running ──────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("V2 shutting down")
    if _scheduler:
        await _scheduler.stop()
    if _dashboard_service:
        await _dashboard_service.stop()
    if _notification_service:
        await _notification_service.stop()
    if _trading_service:
        await _trading_service.stop()
    if _shadow_service:
        await _shadow_service.stop()
    if _portfolio_service:
        await _portfolio_service.stop()
    if _risk_service:
        await _risk_service.stop()
    if _ai_service:
        await _ai_service.stop()
    if _scanner_service:
        await _scanner_service.stop()
    if _db:
        await _db.close()
    logger.info("V2 shutdown complete")


# ── FastAPI application ───────────────────────────────────────────────────────

app = FastAPI(
    title       = "PROJECT-ALPHA V2",
    description = "V2 event-driven trading infrastructure",
    version     = "2.1.0",
    lifespan    = lifespan,
    docs_url    = "/api/v2/docs",
    redoc_url   = "/api/v2/redoc",
    openapi_url = "/api/v2/openapi.json",
)

app.include_router(api_router, prefix="/api/v2")
app.include_router(ws_router)

# Mount static assets and templates for V2 Mission Control Dashboard
_v2_static_dir = _ROOT / "v2" / "static"
_v2_template_dir = _ROOT / "v2" / "templates"

if _v2_static_dir.exists():
    app.mount("/v2-static", StaticFiles(directory=str(_v2_static_dir)), name="v2-static")

templates = Jinja2Templates(directory=str(_v2_template_dir)) if _v2_template_dir.exists() else None


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
@app.get("/v2/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard(request: Request):
    """Serve the standalone V2 Mission Control Dashboard UI."""
    if templates is None:
        return HTMLResponse("<h2>PROJECT-ALPHA V2 templates directory not found</h2>", status_code=404)
    return templates.TemplateResponse(request=request, name="dashboard.html")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = get_config()
    uvicorn.run(
        "v2.app_v2:app",
        host       = cfg.v2_host,
        port       = cfg.v2_port,
        log_level  = "info",
        access_log = True,
    )
