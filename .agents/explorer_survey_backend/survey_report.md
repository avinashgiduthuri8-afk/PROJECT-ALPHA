# Technical Investigation Report: Backend Startup Hydration & Active Positions Routing (R2)

**Explorer**: Survey Explorer 2 (Backend Startup Hydration & Routing)  
**Date**: 2026-09-11  
**Scope**: Requirement R2 (Issues #6 Dashboard Sync, #7 SQLite State Hydration, #8 Portfolio Telemetry, #9 Capital Inconsistency, #10 Equity Calculation, #11 Position Count Inconsistency)  
**Target Modules**:
- `v2/services/dashboard_service/bot_pipeline.py`
- `v2/services/dashboard_service/service.py`
- `v2/services/dashboard_service/aggregator.py`
- `v2/repository/position_repo.py`
- `v2/api/router.py`
- `v2/api/dashboard_routes.py`
- `v2/api/production_routes.py`
- `v2/api/schemas.py`
- `v2/services/portfolio_service/service.py`
- `v2/services/portfolio_service/aggregator.py`
- `v2/app_v2.py`

---

## Executive Summary

The platform's restart desynchronization and telemetry inconsistencies stem from three architectural root causes:
1. **Un-hydrated Pipeline Tracker**: `BotPipelineTracker` initializes in-memory counters (`open_positions = 0`, `capital_deployed = 0.0`, stage `scanner`, status `IDLE`) without reading active positions stored in SQLite. On server restart, bot fleet cards and header KPIs display zero active positions even when valid positions exist in the database.
2. **Missing Router Mounting**: `v2/api/dashboard_routes.py` defines critical fleet control endpoints (`/fleet`, `/signals`, `/fleet/{bot}/pause`, `/fleet/{bot}/resume`, `/emergency-stop`) and an aggregator-backed `/overview`. Although imported in `v2/api/router.py:20`, `dashboard_router` was never mounted via `router.include_router(dashboard_router)`. Furthermore, `init_dashboard_routes` was not wired into `init_router()`.
3. **Overly Restrictive Status Filter**: `/positions/open` delegates to `_position_repo.get_open()`, which explicitly queries `WHERE status='OPEN'`. This drops transitional active states (`PENDING_ENTRY`, `CLOSING`, `PENDING_EXIT`). `PositionRepository` already implements `get_active_positions()` (`WHERE status != 'CLOSED'`), but it was not wired to `/positions/open`, `/trading/positions?status=OPEN`, or `PortfolioService.get_snapshot()`.

---

## 1. BotPipelineTracker Startup Hydration

### 1.1 Current Architecture & Root Cause
- **File**: `v2/services/dashboard_service/bot_pipeline.py` (lines 123–254)
- **Class**: `BotPipelineTracker`, `BotState`
- **Current Initialization**:
  ```python
  class BotPipelineTracker:
      def __init__(self, config: Optional[V2Config] = None) -> None:
          self._config = config
          self._bots: Dict[str, BotState] = {
              BotName.STE.value: BotState("STE", config),
              BotName.HDA.value: BotState("HDA", config),
              BotName.VCP.value: BotState("VCP", config),
              BotName.BBS.value: BotState("BBS", config),
          }
  ```
  Each `BotState` begins with:
  - `open_positions = 0`
  - `capital_deployed = 0.0`
  - `current_stage = "scanner"`
  - `stage_status = "IDLE"`
- **Defect**: State changes are only driven by live `EventBus` events (`POSITION_OPENED`, `POSITION_CLOSED`). When the application restarts with active SQLite positions, `BotPipelineTracker` retains all zeros. Consequently:
  - Header KPI `kpi-openpos` and fleet cards show `0 / 3` (or fallback values).
  - Deployed capital is reported as ₹0.00.

### 1.2 Proposed Design: `sync_from_repository`
Add an asynchronous hydration method to `BotPipelineTracker`:
```python
async def sync_from_repository(
    self,
    repository_or_positions: Any,
) -> None:
    """
    Hydrate active positions and deployed capital from SQLite on startup.
    Queries all non-CLOSED positions via PositionRepository.get_active_positions().
    """
    if hasattr(repository_or_positions, "get_active_positions"):
        active_positions = await repository_or_positions.get_active_positions()
    elif hasattr(repository_or_positions, "get_open"):
        active_positions = await repository_or_positions.get_open()
    elif isinstance(repository_or_positions, list):
        active_positions = repository_or_positions
    else:
        logger.warning("sync_from_repository received unsupported source: %s", type(repository_or_positions))
        return

    # Reset in-memory counters prior to hydration
    for state in self._bots.values():
        state.open_positions = 0
        state.capital_deployed = 0.0

    for pos in active_positions:
        bot_raw = getattr(pos, "bot", "")
        bot_key = bot_raw.value if hasattr(bot_raw, "value") else str(bot_raw).upper()
        
        if bot_key in self._bots:
            s = self._bots[bot_key]
            s.open_positions += 1
            
            qty = float(getattr(pos, "qty", 0.0) or 0.0)
            entry_price = float(getattr(pos, "entry_price", 0.0) or 0.0)
            s.capital_deployed += (qty * entry_price)

            # Advance pipeline stage to reflect active position
            s.current_stage = "position_manager"
            s.stage_status = "IN_POSITION"
            coin = getattr(pos, "coin", "")
            s.last_coin = coin
            s.last_action = f"Tracking active position: {coin}"
            entry_time = getattr(pos, "entry_time", None)
            if entry_time:
                s.last_action_time = entry_time.strftime("%H:%M:%S UTC") if hasattr(entry_time, "strftime") else str(entry_time)

    logger.info(
        "BotPipelineTracker hydrated from repository: %s",
        {b: f"{s.open_positions} pos, ₹{s.capital_deployed:.2f}" for b, s in self._bots.items()}
    )
```

### 1.3 Startup Lifespan Wiring
1. **`v2/services/dashboard_service/service.py`**:
   - Accept optional `position_repo: Optional[PositionRepository] = None` in `DashboardService.__init__`.
   - In `DashboardService.start()`:
     ```python
     if self._position_repo:
         await self._bot_tracker.sync_from_repository(self._position_repo)
     elif self._trading_service and hasattr(self._trading_service, "_position_repo"):
         await self._bot_tracker.sync_from_repository(self._trading_service._position_repo)
     ```
2. **`v2/app_v2.py`**:
   - In `lifespan`:
     ```python
     _dashboard_service = DashboardService(
         bus               = bus,
         config            = cfg,
         position_repo     = position_repo,
         scanner_service   = _scanner_service,
         ai_service        = _ai_service,
         risk_service      = _risk_service,
         portfolio_service = _portfolio_service,
         trading_service   = _trading_service,
         shadow_service    = _shadow_service,
     )
     await _dashboard_service.start()
     ```
   - Explicitly call `await _dashboard_service.bot_tracker.sync_from_repository(position_repo)` before yielding to guarantee hydration completes before requests are accepted.

---

## 2. Mounting `dashboard_routes` and Aggregator Initialization in `v2/api/router.py`

### 2.1 Current Architecture & Gap
- **File**: `v2/api/router.py` (lines 20, 44–47, 78–154)
- **Observations**:
  - Line 20: `from .dashboard_routes import router as dashboard_router, init_dashboard_routes` is imported.
  - Lines 44–46:
    ```python
    router = APIRouter()
    router.include_router(research_router, prefix="/research", tags=["research"])
    router.include_router(production_router, prefix="/production", tags=["production"])
    ```
    Notice `dashboard_router` is missing.
  - Lines 78–154: `init_router()` wires research and production routers (`init_research_router`, `init_production_router`), but never calls `init_dashboard_routes()`.
  - In `v2/api/dashboard_routes.py`:
    `router = APIRouter(prefix="/dashboard", tags=["dashboard"])`
    Endpoints defined:
    - `GET /dashboard/overview`
    - `GET /dashboard/fleet`
    - `GET /dashboard/signals`
    - `POST /dashboard/fleet/{bot_name}/pause`
    - `POST /dashboard/fleet/{bot_name}/resume`
    - `POST /dashboard/emergency-stop`

### 2.2 Proposed Solution
1. **Mount Router in `v2/api/router.py`**:
   ```python
   router = APIRouter()
   router.include_router(research_router, prefix="/research", tags=["research"])
   router.include_router(production_router, prefix="/production", tags=["production"])
   router.include_router(dashboard_router)  # Already has prefix="/dashboard"
   ```
2. **Aggregator Dependency Initialization in `init_router()`**:
   In `init_router()`:
   ```python
   if dashboard_service and hasattr(dashboard_service, "aggregator"):
       init_dashboard_routes(dashboard_service.aggregator)
   else:
       init_dashboard_routes(DashboardAggregator(
           scanner_service   = scanner_service,
           trading_service   = trading_service,
           portfolio_service = portfolio_service,
           risk_service      = risk_service,
           journal_service   = journal_service or kwargs.get("journal_service"),
           analytics_service = analytics_service or kwargs.get("analytics_service"),
           feedback_service  = feedback_service or kwargs.get("feedback_service"),
       ))
   ```
3. **Reconciling `/dashboard/overview`**:
   Currently, both `dashboard_routes.py:36` and `router.py:918` define `GET /dashboard/overview`.
   - `dashboard_routes.py` calls `agg.get_overview_snapshot()`.
   - `router.py:918` calls `_dashboard_service.get_overview()`.
   - Solution: Enhance `DashboardAggregator.get_overview_snapshot()` and `DashboardService.get_overview()` so both return the superset schema containing `status: "ok"`, `system_status: "OPERATIONAL"`, `execution_fleet`, `pipeline_stages` (14 stages), `open_positions`, `open_positions_count`, `active_positions`, `portfolio`, `bots`, and `scanned_coins`.
   - In `v2/api/dashboard_routes.py`, update `get_dashboard_overview()` to delegate to `_dashboard_service.get_overview()` if available or return the enhanced snapshot.

---

## 3. Active Positions Querying in `/positions/open`

### 3.1 Current Architecture & Bug Analysis
- **File**: `v2/api/router.py` (lines 640–691)
- **Code**:
  ```python
  @router.get("/trading/positions")
  async def get_positions(status: Optional[str] = None, limit: int = 50):
      if status and status.upper() == "OPEN":
          positions = await _position_repo.get_open()
      else:
          positions = await _position_repo.get_all(limit=limit)
      ...

  @router.get("/positions/open")
  async def get_open_positions_alias() -> list[PositionSchema]:
      """Convenience alias for /trading/positions?status=OPEN."""
      return await get_positions(status="OPEN")
  ```
- **File**: `v2/repository/position_repo.py`:
  ```python
  async def get_open(self, bot: Optional[BotName] = None) -> list[Position]:
      ...
      "SELECT * FROM positions WHERE status='OPEN' ORDER BY entry_time DESC"
  ```
- **Impact**:
  - `PositionState` defines `PENDING_ENTRY`, `OPEN`, `PENDING_EXIT`, `CLOSED`.
  - Positions transitioning through `PENDING_ENTRY` or `CLOSING` have `status != 'CLOSED'`, but `status != 'OPEN'`.
  - Calling `get_open()` filters out `PENDING_ENTRY` positions entirely!
  - `PositionRepository` already provides `get_active_positions()`:
    ```python
    async def get_active_positions(self, bot: Optional[BotName] = None) -> list[Position]:
        """Fetch all non-CLOSED positions (OPEN, PENDING_ENTRY, PENDING_EXIT)."""
        ...
        "SELECT * FROM positions WHERE status != 'CLOSED' ORDER BY entry_time DESC"
    ```

### 3.2 Proposed Implementation
In `v2/api/router.py`:
```python
@router.get(
    "/trading/positions",
    response_model=list[PositionSchema],
    dependencies=[Depends(require_api_key)],
    tags=["trading"],
)
async def get_positions(
    status: Optional[str] = Query(default=None, description="Filter by OPEN | CLOSED | ACTIVE"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[PositionSchema]:
    """List positions from repository, returning all non-closed positions when querying open/active."""
    if _position_repo is None:
        raise HTTPException(status_code=503, detail="Position repository not initialized.")

    if status and status.upper() in ("OPEN", "ACTIVE"):
        positions = await _position_repo.get_active_positions()
    elif status and status.upper() == "CLOSED":
        rows = await _position_repo._fetchall(
            "SELECT * FROM positions WHERE status='CLOSED' ORDER BY entry_time DESC LIMIT ?", (limit,)
        )
        positions = [_row_to_position(r) for r in rows]
    else:
        positions = await _position_repo.get_all(limit=limit)

    return [_position_to_schema(p) for p in positions]


@router.get(
    "/positions/open",
    response_model=list[PositionSchema],
    dependencies=[Depends(require_api_key)],
    tags=["trading"],
)
async def get_open_positions_alias() -> list[PositionSchema]:
    """Return all non-closed active positions (status != 'CLOSED') including transitional states."""
    if _position_repo is None:
        raise HTTPException(status_code=503, detail="Position repository not initialized.")
    positions = await _position_repo.get_active_positions()
    return [_position_to_schema(p) for p in positions]
```
Additionally, update `v2/api/production_routes.py:77`:
```python
if _position_repo:
    try:
        active_pos = await _position_repo.get_active_positions()
        deployed = sum(p.deployed_capital for p in active_pos)
        open_count = len(active_pos)
    except Exception as exc:
        logger.debug("Failed fetching active positions for status: %s", exc)
```
This ensures `/api/v2/production/status` also returns accurate `open_positions_count` and `capital_pool_deployed`.

---

## 4. `DashboardService.get_overview()` Enhancement

### 4.1 Missing Fields & Schema Incompatibility
- **File**: `v2/services/dashboard_service/service.py` (lines 392–432)
- **File**: `v2/api/schemas.py` (lines 338–350)
- **Observation**:
  `DashboardService.get_overview()` currently returns:
  `status`, `active_ws_clients`, `portfolio`, `risk`, `shadow`, `subsystems`, `pipeline_stages`, `bots`, `scanned_coins`, `watchlist_summary`, `telemetry`.
  It lacks:
  - `open_positions`
  - `open_positions_count`
  - `active_positions`
  - `system_status`
  - `execution_fleet`
  `DashboardOverviewSchema` does not define `open_positions` or `open_positions_count`, so any added fields would be rejected by Pydantic validation if `extra="forbid"` or silently dropped.

### 4.2 Proposed Implementation
1. **Update `DashboardOverviewSchema` in `v2/api/schemas.py`**:
   ```python
   class DashboardOverviewSchema(BaseModel):
       status:             str = "ok"
       system_status:      Optional[str] = "OPERATIONAL"
       active_ws_clients:  int = 0
       portfolio:          Optional[dict[str, Any]] = None
       risk:               Optional[dict[str, Any]] = None
       shadow:             Optional[dict[str, Any]] = None
       subsystems:         dict[str, Any] = Field(default_factory=dict)
       pipeline_stages:    Optional[list[dict[str, Any]]] = None
       bots:               Optional[list[dict[str, Any]]] = None
       execution_fleet:    Optional[dict[str, Any]] = None
       open_positions:     Optional[list[dict[str, Any]]] = Field(default_factory=list)
       open_positions_count: int = 0
       active_positions:   Optional[list[dict[str, Any]]] = Field(default_factory=list)
       scanned_coins:      Optional[list[dict[str, Any]]] = Field(default_factory=list)
       watchlist_summary:  Optional[dict[str, Any]] = Field(default_factory=dict)
       telemetry:          Optional[dict[str, Any]] = None
   ```
2. **Update `DashboardService.get_overview()` in `v2/services/dashboard_service/service.py`**:
   ```python
   async def get_overview(self) -> dict[str, Any]:
       """Aggregate the full platform state in a single call for dashboard initial load."""
       portfolio = await self._portfolio_service.get_snapshot() if self._portfolio_service else None
       risk_state = await self._risk_service.get_state() if self._risk_service else None
       shadow_summary = await self._shadow_service.get_summary() if self._shadow_service else {}
       scanned_coins = self._scanner_service.get_scanned_coins() if self._scanner_service else []

       # Fetch active positions directly from PositionRepository
       active_positions_list: List[Dict[str, Any]] = []
       pos_repo = getattr(self, "_position_repo", None)
       if pos_repo is None and self._trading_service and hasattr(self._trading_service, "_position_repo"):
           pos_repo = self._trading_service._position_repo
       if pos_repo is None and self._portfolio_service and hasattr(self._portfolio_service, "_position_repo"):
           pos_repo = self._portfolio_service._position_repo

       if pos_repo is not None:
           try:
               raw_positions = await pos_repo.get_active_positions()
               for p in raw_positions:
                   active_positions_list.append({
                       "id": p.id,
                       "position_id": p.id,
                       "bot": p.bot.value if hasattr(p.bot, "value") else str(p.bot),
                       "bot_name": p.bot.value if hasattr(p.bot, "value") else str(p.bot),
                       "coin": p.coin,
                       "pair": p.pair,
                       "qty": p.qty,
                       "quantity": p.qty,
                       "entry_price": p.entry_price,
                       "entry_time": p.entry_time.isoformat() if hasattr(p.entry_time, "isoformat") else str(p.entry_time),
                       "current_price": p.current_price,
                       "current_mark_price": p.current_price if p.current_price is not None else p.entry_price,
                       "unrealised_pnl": p.unrealised_pnl if p.unrealised_pnl is not None else 0.0,
                       "unrealized_pnl": p.unrealised_pnl if p.unrealised_pnl is not None else 0.0,
                       "stop_loss": p.stop_loss,
                       "take_profit": p.take_profit,
                       "mode": p.mode.value if hasattr(p.mode, "value") else str(p.mode),
                       "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                       "signal_id": p.signal_id,
                   })
           except Exception as exc:
               logger.warning("Error fetching active positions in get_overview: %s", exc)

       bot_statuses = self.get_bot_statuses()
       fleet_data = {b["bot_name"]: b for b in bot_statuses}

       is_emergency = bool(risk_state and (risk_state.circuit_breaker_open or risk_state.emergency_stop))

       return {
           "status": "ok",
           "system_status": "OPERATIONAL" if not is_emergency else "EMERGENCY_STOP",
           "active_ws_clients": self._ws_manager.active_count,
           "portfolio": {
               "total_aum": portfolio.total_aum if portfolio else 0.0,
               "total_deployed": portfolio.total_deployed if portfolio else 0.0,
               "total_cash": portfolio.total_cash if portfolio else 0.0,
               "daily_pnl": portfolio.daily_pnl if portfolio else 0.0,
               "capital_utilisation": portfolio.capital_utilisation if portfolio else 0.0,
           } if portfolio else None,
           "risk": {
               "trading_enabled": risk_state.trading_enabled if risk_state else False,
               "circuit_breaker_open": risk_state.circuit_breaker_open if risk_state else False,
               "emergency_stop": risk_state.emergency_stop if risk_state else False,
               "per_bot_deployed": risk_state.per_bot_deployed if risk_state else {},
           } if risk_state else None,
           "shadow": shadow_summary,
           "subsystems": {
               "scanner": self._scanner_service.get_health() if self._scanner_service else {"healthy": False},
               "ai": self._ai_service.get_health() if self._ai_service else {"healthy": False},
               "trading": self._trading_service.get_health() if self._trading_service else {"healthy": False},
           },
           "pipeline_stages": self.get_pipeline_stages(),
           "bots": bot_statuses,
           "execution_fleet": fleet_data,
           "open_positions": active_positions_list,
           "open_positions_count": len(active_positions_list),
           "active_positions": active_positions_list,
           "scanned_coins": scanned_coins,
           "watchlist_summary": {
               "total_evaluated": len(scanned_coins),
               "passed_confluence_count": len([c for c in scanned_coins if c.get("status") == "PASSED"]),
               "top_candidates": scanned_coins[:5],
               "last_scan_at": scanned_coins[0]["evaluated_at"] if scanned_coins else None,
           },
           "telemetry": self.get_telemetry_snapshot(),
       }
   ```
3. **Update `DashboardAggregator.get_overview_snapshot()` in `v2/services/dashboard_service/aggregator.py`**:
   Also include `"open_positions": active_positions` and `"open_positions_count": len(active_positions)` in `DashboardAggregator.get_overview_snapshot()`.

---

## 5. Dynamic Total Equity & Deployed Capital Calculation

### 5.1 Mathematical Derivation
The platform requires dynamic total equity and deployed capital calculations combining:
- **Available Cash Balance**: Liquid funds remaining in the capital pool.
- **Mark-to-Market (MTM) Asset Valuations**: Current market price of open positions.
- **Friction Costs**: Statutory round-trip drag (1.572% total: 0.20% exchange fee + 18% GST + 1.00% Sec 194S TDS + 0.10% slippage).

#### Mathematical Model:
For an active portfolio of positions $P = \{p_1, p_2, \dots, p_n\}$:
1. **Deployed Capital**:
   $$\text{Deployed}_i = p_i.\text{qty} \times p_i.\text{entry\_price}$$
   $$\text{Total Deployed} = \sum_{i=1}^n \text{Deployed}_i$$

2. **Live Mark-to-Market Valuation**:
   $$\text{Mark Price}_i = \begin{cases} p_i.\text{current\_price} & \text{if } p_i.\text{current\_price} > 0 \\ p_i.\text{entry\_price} & \text{otherwise} \end{cases}$$
   $$\text{MTM}_i = p_i.\text{qty} \times \text{Mark Price}_i$$
   $$\text{Total MTM} = \sum_{i=1}^n \text{MTM}_i$$

3. **Statutory Round-Trip Friction Cost**:
   $$\text{Friction}_i = (\text{Deployed}_i + \text{MTM}_i) \times \frac{0.01572}{2} = (\text{Deployed}_i + \text{MTM}_i) \times 0.00786$$
   $$\text{Total Friction} = \sum_{i=1}^n \text{Friction}_i$$

4. **Cash Balance**:
   Given base pool capital $C_0 = ₹100,000.00$ and completed closed trades $T$:
   $$\text{Realized PnL} = \sum_{t \in T} t.\text{pnl} \quad (\text{friction is already deducted on closure})$$
   $$\text{Total Cash} = \max(0.0, C_0 + \text{Realized PnL} - \text{Total Deployed})$$

5. **Dynamic Total Equity**:
   $$\text{Total Equity} = \text{Total Cash} + \text{Total MTM} - \text{Total Friction}$$

   Since $\text{MTM}_i = \text{Deployed}_i + \text{Gross Unrealised}_i$:
   $$\text{Total MTM} - \text{Total Friction} = \text{Total Deployed} + (\text{Total Gross Unrealised} - \text{Total Friction}) = \text{Total Deployed} + \text{Total Net Unrealised}$$
   $$\text{Total Equity} = \text{Total Cash} + \text{Total Deployed} + \text{Total Net Unrealised}$$

### 5.2 Implementation in `v2/services/portfolio_service/aggregator.py`
```python
class PortfolioAggregator:
    """Pure mathematical aggregator for multi-bot portfolio state."""

    STATUTORY_ROUND_TRIP_DRAG_RATE = 0.01572

    @staticmethod
    def aggregate(
        positions: list[Position],
        closed_trades: list[Trade],
        base_cash: float = 100000.0,
    ) -> PortfolioSnapshot:
        """Calculate live AUM, deployed capital, cash, and PnL breakdown."""
        positions_by_bot: dict[str, list[Position]] = {
            BotName.STE.value: [],
            BotName.HDA.value: [],
            BotName.VCP.value: [],
            BotName.BBS.value: [],
        }

        total_deployed = 0.0
        total_mtm = 0.0
        total_friction = 0.0
        total_unrealised = 0.0

        for pos in positions:
            b_key = pos.bot.value if isinstance(pos.bot, BotName) else str(pos.bot)
            if b_key not in positions_by_bot:
                positions_by_bot[b_key] = []
            positions_by_bot[b_key].append(pos)

            deployed = pos.deployed_capital
            total_deployed += deployed

            # Mark-to-market valuation
            mark_price = pos.current_price if (pos.current_price is not None and pos.current_price > 0) else pos.entry_price
            mtm_val = pos.qty * mark_price
            total_mtm += mtm_val

            # Statutory round-trip friction cost
            friction = (deployed + mtm_val) * (PortfolioAggregator.STATUTORY_ROUND_TRIP_DRAG_RATE / 2.0)
            total_friction += friction

            if pos.unrealised_pnl is not None:
                total_unrealised += pos.unrealised_pnl
            else:
                total_unrealised += (mark_price - pos.entry_price) * pos.qty

        total_realised = sum(t.pnl for t in closed_trades)

        # Cash = Initial Cash + Realised PnL - Currently Deployed Capital
        total_cash = max(0.0, base_cash + total_realised - total_deployed)

        # Total AUM / Equity combines cash balances with mark-to-market valuations
        total_aum = total_cash + total_deployed + total_unrealised

        capital_util = round((total_deployed / total_aum * 100.0), 2) if total_aum > 0 else 0.0

        # Calculate daily realised PnL (from today UTC)
        today_utc = datetime.now(timezone.utc).date()
        daily_pnl = sum(
            t.pnl for t in closed_trades
            if hasattr(t, "exit_time") and t.exit_time and t.exit_time.date() == today_utc
        ) + total_unrealised

        return PortfolioSnapshot(
            total_aum=round(total_aum, 2),
            total_deployed=round(total_deployed, 2),
            total_cash=round(total_cash, 2),
            total_unrealised_pnl=round(total_unrealised, 2),
            total_realised_pnl=round(total_realised, 2),
            daily_pnl=round(daily_pnl, 2),
            capital_utilisation=capital_util,
            positions_by_bot=positions_by_bot,
            captured_at=datetime.now(timezone.utc),
        )
```

### 5.3 Hydration in `PortfolioService.get_snapshot()`
In `v2/services/portfolio_service/service.py`:
Change:
```python
open_positions = []
if self._position_repo is not None:
    open_positions = await self._position_repo.get_open()
```
To:
```python
open_positions = []
if self._position_repo is not None:
    if hasattr(self._position_repo, "get_active_positions"):
        open_positions = await self._position_repo.get_active_positions()
    else:
        open_positions = await self._position_repo.get_open()
```
This ensures non-`OPEN` active positions (e.g. `PENDING_ENTRY`) are accurately captured in portfolio aggregation.

---

## 6. Implementation Summary Matrix

| Requirement Component | Current Status | Proposed Change | Target Files & Lines |
|---|---|---|---|
| **BotPipelineTracker Hydration** | Unhydrated (starts with 0s) | Add `sync_from_repository(repo)`, wire to `app_v2.py` lifespan and `DashboardService.start()` | `v2/services/dashboard_service/bot_pipeline.py:240+`<br>`v2/services/dashboard_service/service.py:180+`<br>`v2/app_v2.py:254, 384` |
| **Mount `dashboard_routes`** | Unmounted in `router.py` | Call `router.include_router(dashboard_router)` and `init_dashboard_routes(...)` in `init_router()` | `v2/api/router.py:46, 147` |
| **`/positions/open` Query** | Queries `status='OPEN'`, dropping `PENDING_ENTRY` | Call `_position_repo.get_active_positions()` (`status != 'CLOSED'`) | `v2/api/router.py:646, 688`<br>`v2/api/production_routes.py:77` |
| **`DashboardService.get_overview()`** | Lacks `open_positions` & count | Fetch active positions from `_position_repo`, return `open_positions`, `open_positions_count`, `active_positions`, `execution_fleet`, `system_status` | `v2/services/dashboard_service/service.py:392`<br>`v2/api/schemas.py:338` |
| **Dynamic Equity & Capital** | Excludes transitional active positions | Query `get_active_positions()` in `PortfolioService.get_snapshot()`; compute cash + MTM - friction in `PortfolioAggregator` | `v2/services/portfolio_service/service.py:82`<br>`v2/services/portfolio_service/aggregator.py:17` |

---

## 7. Verification Method

Once implemented, the changes can be verified using the following automated and functional checks:
1. **Automated Unit Tests**:
   - `py -m pytest tests/test_v2_phase7_dashboard.py --basetemp=.pytest_tmp_dash -v` (verifies `/dashboard/overview`, `/dashboard/fleet`, `/dashboard/signals`, pause/resume, emergency stop).
   - `py -m pytest tests/test_v2_mark_to_market.py --basetemp=.pytest_tmp_mtm -v` (verifies MTM valuation and unrealized PnL).
   - `py -m pytest tests/test_v2_portfolio_service.py --basetemp=.pytest_tmp_port -v` (verifies portfolio lifecycle).
   - `py -m pytest tests/test_v2_price_precision_and_order_integrity.py --basetemp=.pytest_tmp_prec -v` (verifies order precision and integrity).
2. **Functional API Checks**:
   - Insert an active position with `status = 'PENDING_ENTRY'` into SQLite.
   - `GET /api/v2/positions/open`: verify HTTP 200 and the `PENDING_ENTRY` position is present in the list.
   - `GET /api/v2/dashboard/overview`: verify `open_positions_count >= 1` and `open_positions` contains the position.
   - Restart the server: verify that `GET /api/v2/dashboard/overview` immediately displays the active position and updated deployed capital without needing new market events.
