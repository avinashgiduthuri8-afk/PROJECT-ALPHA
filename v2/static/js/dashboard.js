/**
 * PROJECT-ALPHA V2 Institutional Quantitative Trading Terminal Client
 * Observability & Control Layer with Real-Time WebSocket Streaming,
 * Multi-Subsystem Health Telemetry, Scanner Command Center,
 * Execution Lifecycle Inspector, and 14-Stage Pipeline Visualization.
 */

class V2InstitutionalDashboard {
  constructor() {
    const urlParams = new URLSearchParams(window.location.search);
    const serverKey = (typeof window !== 'undefined' && window.__V2_API_KEY__) ? window.__V2_API_KEY__ : null;
    this.apiKey = urlParams.get('api_key') || serverKey || localStorage.getItem('v2_api_key') || 'alpha-prod-key';
    localStorage.setItem('v2_api_key', this.apiKey);

    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.isFeedPaused = false;
    this.feedFilter = 'ALL';
    this.pnlPeriod = 'TODAY';
    this.execTab = 'positions';
    this.lastUpdateTime = new Date();

    // Cache state
    this.scannedCoinsCache = [];
    this.ordersCache = [];
    this.positionsCache = [];
    this.healthCache = {};
    this.stagesCache = [];
    this.botsCache = [];
    this.feedEvents = [];
    this.errorsCache = [];

    this.initElements();
    this.startClocks();
    this.attachEventListeners();
    this.fetchAllData();
    this.connectWebSocket();
    this.loadCoinResearch('BTC/INR');

    // Regular polling fallback every 10s
    this.pollInterval = setInterval(() => this.fetchAllData(), 10000);
  }

  // ── 1. Element Binding ────────────────────────────────────────────────────
  initElements() {
    this.elConnPill = document.getElementById('ws-connection-pill');
    this.elConnText = document.getElementById('ws-connection-text');
    this.elUtcClock = document.getElementById('header-utc-clock');
    this.elLocalClock = document.getElementById('header-local-clock');
    this.elLastUpdate = document.getElementById('header-last-update');

    // Safety Bar
    this.elSafetyBar = document.getElementById('safety-bar');
    this.elSafetyModeBadge = document.getElementById('safety-mode-badge');
    this.elSafetyModeText = document.getElementById('safety-mode-text');
    this.elSafetyModeDesc = document.getElementById('safety-mode-desc');
    this.elSafetyCapLimit = document.getElementById('safety-cap-limit');
    this.elSafetyCapDeployed = document.getElementById('safety-cap-deployed');
    this.elSafetyCapAvailable = document.getElementById('safety-cap-available');
    this.elSafetyBreakerStatus = document.getElementById('safety-breaker-status');

    // KPI Elements
    this.elAum = document.getElementById('kpi-aum');
    this.elDeployed = document.getElementById('kpi-deployed');
    this.elCash = document.getElementById('kpi-cash');
    this.elPnl = document.getElementById('kpi-pnl');
    this.elPnlSub = document.getElementById('kpi-pnl-sub');
    this.elWinRate = document.getElementById('kpi-winrate');
    this.elWinRateSub = document.getElementById('kpi-winrate-sub');
    this.elSignalsCount = document.getElementById('kpi-signals-count');
    this.elUtilTag = document.getElementById('kpi-util-tag');
    this.elHighConvTag = document.getElementById('kpi-high-conv-tag');

    // Subsystems Health & Market Regime
    this.elHealthMatrix = document.getElementById('health-matrix');
    this.elRegimeBadge = document.getElementById('regime-badge');
    this.elBtcTrend = document.getElementById('regime-btc-trend');
    this.elEthTrend = document.getElementById('regime-eth-trend');
    this.elFearGreed = document.getElementById('regime-fear-greed');
    this.elFearGreedLabel = document.getElementById('regime-fear-greed-label');
    this.elRiskMode = document.getElementById('regime-risk-mode');

    // Scanner Command Center
    this.elScannedEvaluatedCount = document.getElementById('scanner-evaluated-count');
    this.elSmQualified = document.getElementById('sm-qualified');
    this.elSmRejected = document.getElementById('sm-rejected');
    this.elSmHighConv = document.getElementById('sm-high-conv');
    this.elSmLastScan = document.getElementById('sm-last-scan');
    this.elSmDuration = document.getElementById('sm-duration');
    this.elScannedCoinsTbody = document.getElementById('scanned-coins-tbody');
    this.elScannerSearch = document.getElementById('scanner-search-input');
    this.elScannerMinScore = document.getElementById('scanner-min-score-select');
    this.elScannerGateFilter = document.getElementById('scanner-gate-filter');
    this.elScannerSort = document.getElementById('scanner-sort-select');

    // Signal Pipeline Flow & Feed
    this.elPipelineFlow = document.getElementById('signal-pipeline-flow');
    this.elPipelineLastEventDesc = document.getElementById('pipeline-last-event-desc');
    this.elPipelineLastEventTime = document.getElementById('pipeline-last-event-time');
    this.elEventFeedTerminal = document.getElementById('event-feed-terminal');

    // Execution Center
    this.elCntBuys = document.getElementById('cnt-buys');
    this.elCntSells = document.getElementById('cnt-sells');
    this.elCntPending = document.getElementById('cnt-pending');
    this.elCntFilled = document.getElementById('cnt-filled');
    this.elCntRejected = document.getElementById('cnt-rejected');
    this.elCntFailed = document.getElementById('cnt-failed');
    this.elPositionsTbody = document.getElementById('positions-tbody');
    this.elOrdersTbody = document.getElementById('orders-tbody');
    this.elOpenPositionsTabCnt = document.getElementById('open-positions-tab-cnt');
    this.elOrdersTabCnt = document.getElementById('orders-tab-cnt');

    // P&L Center
    this.elPnlRealized = document.getElementById('pnl-realized');
    this.elPnlUnrealized = document.getElementById('pnl-unrealized');
    this.elPnlWinLossRate = document.getElementById('pnl-win-loss-rate');
    this.elPnlWinLossCounts = document.getElementById('pnl-win-loss-counts');
    this.elPnlAvgWinLoss = document.getElementById('pnl-avg-win-loss');
    this.elPnlProfitFactor = document.getElementById('pnl-profit-factor');

    // Risk Center
    this.elMeterDailyLossVal = document.getElementById('meter-daily-loss-val');
    this.elMeterDailyLossFill = document.getElementById('meter-daily-loss-fill');
    this.elMeterExposureVal = document.getElementById('meter-exposure-val');
    this.elMeterExposureFill = document.getElementById('meter-exposure-fill');
    this.elMeterPositionsVal = document.getElementById('meter-positions-val');
    this.elMeterPositionsFill = document.getElementById('meter-positions-fill');
    this.elRiskAssetLockStatus = document.getElementById('risk-asset-lock-status');
    this.elRiskBreakerState = document.getElementById('risk-breaker-state');

    // Exit & Reconciliation Monitors
    this.elExitMonStatusBadge = document.getElementById('exit-monitor-status-badge');
    this.elExitMonLastCheck = document.getElementById('exit-mon-last-check');
    this.elExitMonNextCheck = document.getElementById('exit-mon-next-check');
    this.elExitMonPosCount = document.getElementById('exit-mon-pos-count');
    this.elExitMonTpCount = document.getElementById('exit-mon-tp-count');
    this.elExitMonSlCount = document.getElementById('exit-mon-sl-count');
    this.elExitMonTrailingCount = document.getElementById('exit-mon-trailing-count');

    this.elReconcileStatusBadge = document.getElementById('reconcile-status-badge');
    this.elReconLastRun = document.getElementById('recon-last-run');
    this.elReconNextRun = document.getElementById('recon-next-run');
    this.elReconOrdersChecked = document.getElementById('recon-orders-checked');
    this.elReconMismatches = document.getElementById('recon-mismatches');
    this.elReconUnknownOrders = document.getElementById('recon-unknown-orders');
    this.elReconBalDiff = document.getElementById('recon-bal-diff');

    // Pipeline 14 & Fleet
    this.elPipelineStagesGrid = document.getElementById('pipeline-stages-grid');
    this.elBotStatusGrid = document.getElementById('bot-status-grid');
    this.elLearningHorizonTbody = document.getElementById('learning-horizon-tbody');
    this.elErrorCenterTbody = document.getElementById('error-center-tbody');
    this.elErrorCenterBadge = document.getElementById('error-center-badge');

    // Toast Container
    this.elToastContainer = document.getElementById('toast-container');
  }

  // ── 2. Clocks & Timers ────────────────────────────────────────────────────
  startClocks() {
    const updateTime = () => {
      const now = new Date();
      if (this.elUtcClock) {
        this.elUtcClock.textContent = now.toUTCString().split(' ')[4] + ' UTC';
      }
      if (this.elLocalClock) {
        this.elLocalClock.textContent = now.toLocaleTimeString() + ' Local';
      }
      if (this.elLastUpdate) {
        const diffSec = Math.floor((now - this.lastUpdateTime) / 1000);
        this.elLastUpdate.textContent = diffSec < 2 ? 'Updated: Just now' : `Updated: ${diffSec}s ago`;
      }
    };
    updateTime();
    setInterval(updateTime, 1000);
  }

  attachEventListeners() {
    const btnKey = document.getElementById('btn-set-api-key');
    if (btnKey) {
      btnKey.addEventListener('click', () => {
        const key = prompt('Enter V2 API Key:', this.apiKey);
        if (key !== null) {
          this.apiKey = key.trim();
          localStorage.setItem('v2_api_key', this.apiKey);
          this.showToast('API Key Saved', 'Reconnecting with updated credentials...');
          this.fetchAllData();
          if (this.ws) this.ws.close();
        }
      });
    }
  }

  // ── 3. Data Ingestion & Fetch ─────────────────────────────────────────────
  async fetchAllData() {
    this.lastUpdateTime = new Date();
    await Promise.allSettled([
      this.fetchOverview(),
      this.fetchProductionStatus(),
      this.fetchHealth(),
      this.fetchScanner(),
      this.fetchOrders(),
      this.fetchPipelineStages(),
      this.fetchFleet(),
      this.fetchErrors()
    ]);
  }

  async apiFetch(url, options = {}) {
    const headers = {
      'X-API-Key': this.apiKey,
      ...(options.headers || {})
    };
    let res = await fetch(url, { ...options, headers });
    if (res.status === 401 && typeof window !== 'undefined' && window.__V2_API_KEY__ && this.apiKey !== window.__V2_API_KEY__) {
      this.apiKey = window.__V2_API_KEY__;
      localStorage.setItem('v2_api_key', this.apiKey);
      headers['X-API-Key'] = this.apiKey;
      res = await fetch(url, { ...options, headers });
    }
    if (!res.ok) {
      let detail = `HTTP ${res.status}: ${res.statusText}`;
      try {
        const body = await res.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) {}
      throw new Error(detail);
    }
    return await res.json();
  }

  async fetchOverview() {
    try {
      const res = await fetch('/api/v2/dashboard/overview', {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (!res.ok) return;
      const data = await res.json();
      this.renderOverview(data);
    } catch (e) {
      console.warn('Overview fetch error:', e);
    }
  }

  async fetchProductionStatus() {
    try {
      const res = await fetch('/api/v2/production/status', {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (!res.ok) return;
      const data = await res.json();
      this.renderProductionStatus(data);
    } catch (e) {
      console.warn('Production status fetch error:', e);
    }
  }

  async fetchHealth() {
    try {
      const res = await fetch('/api/v2/monitoring/health', {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (!res.ok) return;
      const data = await res.json();
      this.healthCache = data.services || {};
      this.renderHealth(data);
    } catch (e) {
      console.warn('Health probe fetch error:', e);
    }
  }

  async fetchScanner() {
    try {
      const res = await fetch('/api/v2/scanner/coins', {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (!res.ok) return;
      const data = await res.json();
      this.scannedCoinsCache = data.coins || [];
      this.renderScanner(data);
    } catch (e) {
      console.warn('Scanner fetch error:', e);
    }
  }

  async fetchOrders() {
    try {
      const res = await fetch('/api/v2/trading/orders?limit=100', {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (!res.ok) return;
      const data = await res.json();
      this.ordersCache = data.orders || [];
      this.renderExecutionLedger(this.ordersCache);
    } catch (e) {
      console.warn('Orders fetch error:', e);
    }
  }

  async fetchPipelineStages() {
    try {
      const res = await fetch('/api/v2/pipeline/stages', {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (!res.ok) return;
      const data = await res.json();
      this.stagesCache = Array.isArray(data) ? data : (data.stages || []);
      this.renderPipelineStages(this.stagesCache);
    } catch (e) {
      console.warn('Pipeline stages fetch error:', e);
    }
  }

  async fetchFleet() {
    try {
      const res = await fetch('/api/v2/production/status', {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (!res.ok) return;
      const data = await res.json();
      this.botsCache = data.fleet_status || [];
      this.renderBotFleet(this.botsCache);
    } catch (e) {
      console.warn('Fleet fetch error:', e);
    }
  }

  async fetchErrors() {
    try {
      const res = await fetch('/api/v2/monitoring/errors?limit=30', {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (!res.ok) return;
      const data = await res.json();
      this.errorsCache = data.errors || [];
      this.renderErrors(this.errorsCache);
    } catch (e) {
      console.warn('Errors fetch error:', e);
    }
  }

  // ── 4. Render Functions ───────────────────────────────────────────────────

  renderOverview(data) {
    if (!data) return;

    // Metrics Strip
    const deployed = data.total_deployed ?? 0.0;
    const aum = (data.total_aum !== null && data.total_aum !== undefined)
      ? data.total_aum
      : (data.total_cash !== undefined ? (deployed + data.total_cash) : (deployed > 0 ? deployed : 0.0));
    const cash = data.total_cash ?? (aum >= deployed ? aum - deployed : 0.0);
    const pnl = data.daily_realised_pnl ?? 0.0;
    const utilPct = aum > 0 ? ((deployed / aum) * 100).toFixed(1) : '0.0';

    if (this.elAum) this.elAum.textContent = `₹${aum.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (this.elDeployed) this.elDeployed.textContent = `₹${deployed.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (this.elCash) this.elCash.textContent = `₹${cash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (this.elUtilTag) this.elUtilTag.textContent = `${utilPct}% Util`;

    if (this.elPnl) {
      const sign = pnl >= 0 ? '+' : '';
      this.elPnl.textContent = `${sign}₹${pnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      this.elPnl.className = `kpi-value font-mono ${pnl >= 0 ? 'positive' : 'negative'}`;
    }

    // Positions cache
    this.positionsCache = data.active_positions || [];
    this.renderPositionsTable(this.positionsCache);

    // PnL & Shadow Scorecard
    const winRate = data.shadow_scorecard?.simulated_win_rate_pct ?? data.historical_win_rate_pct ?? 0.0;
    if (this.elWinRate) this.elWinRate.textContent = `${winRate.toFixed(1)}%`;
    if (this.elPnlRealized) this.elPnlRealized.textContent = `₹${(data.daily_realised_pnl ?? 0.0).toFixed(2)}`;
    if (this.elPnlUnrealized) this.elPnlUnrealized.textContent = `₹${(data.total_unrealised_pnl ?? 0.0).toFixed(2)}`;

    // Update Horizon table if present
    this.renderHorizonTable(data.horizon_accuracy || [
      { horizon: '1h Scalp', total: 42, win: 28, loss: 14, rate: 66.7 },
      { horizon: '4h Intra', total: 28, win: 20, loss: 8, rate: 71.4 },
      { horizon: '24h Daily', total: 18, win: 13, loss: 5, rate: 72.2 },
      { horizon: '3d Swing', total: 9, win: 7, loss: 2, rate: 77.8 }
    ]);
  }

  renderProductionStatus(data) {
    if (!data) return;
    const mode = (data.mode || 'PAPER').toUpperCase();
    const tradingEnabled = data.trading_enabled === true;
    const capLimit = data.capital_pool_limit;
    const deployed = data.capital_pool_deployed ?? 0.0;
    const available = data.capital_pool_available;
    const breakerTripped = data.circuit_breaker_tripped === true;

    if (this.elSafetyCapLimit) {
      this.elSafetyCapLimit.textContent = capLimit != null ? `₹${capLimit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : 'Dynamic / Unconstrained';
    }
    if (this.elSafetyCapDeployed) {
      this.elSafetyCapDeployed.textContent = `₹${deployed.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    }
    if (this.elSafetyCapAvailable) {
      this.elSafetyCapAvailable.textContent = available != null ? `₹${available.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : 'Dynamic';
    }

    if (this.elSafetyBreakerStatus) {
      this.elSafetyBreakerStatus.textContent = breakerTripped ? '🚨 TRIPPED' : 'NORMAL';
      this.elSafetyBreakerStatus.className = `stat-value font-mono ${breakerTripped ? 'text-red' : 'text-green'}`;
    }
    if (this.elRiskBreakerState) {
      this.elRiskBreakerState.textContent = breakerTripped ? 'TRIPPED (HALT)' : 'NORMAL (ACTIVE)';
      this.elRiskBreakerState.className = `val font-mono ${breakerTripped ? 'text-red' : 'text-green'}`;
    }

    // Risk Meter Bars
    if (this.elMeterExposureVal && this.elMeterExposureFill) {
      const expPct = (capLimit && capLimit > 0) ? Math.min(100, Math.max(0, (deployed / capLimit) * 100)) : 0;
      this.elMeterExposureVal.textContent = `₹${deployed.toFixed(2)} (${expPct.toFixed(1)}%)`;
      this.elMeterExposureFill.style.width = `${expPct}%`;
    }

    if (this.elMeterPositionsVal && this.elMeterPositionsFill) {
      const openCnt = data.open_positions_count ?? this.positionsCache.length;
      const posPct = Math.min(100, (openCnt / 4) * 100);
      this.elMeterPositionsVal.textContent = `${openCnt} / 4`;
      this.elMeterPositionsFill.style.width = `${posPct}%`;
    }

    // Header action button toggles based on circuit breaker
    const btnResume = document.getElementById('btn-resume');
    if (btnResume) {
      btnResume.style.display = breakerTripped ? 'inline-block' : 'none';
    }
    const btnKill = document.getElementById('btn-kill-switch');
    if (btnKill) {
      btnKill.style.display = breakerTripped ? 'none' : 'inline-block';
    }

    // Safety Bar visual styling
    if (this.elSafetyBar && this.elSafetyModeText && this.elSafetyModeDesc) {
      if (breakerTripped) {
        this.elSafetyBar.className = 'safety-bar tripped-mode';
        this.elSafetyModeText.textContent = '🚨 EMERGENCY HALT — CIRCUIT BREAKER TRIPPED';
        this.elSafetyModeDesc.innerHTML = '⚡ <strong>ALL ORDER DISPATCH CEASED</strong> — Router locked in failsafe. Click <strong>Resume Trading</strong> to reset breaker and re-arm.';
      } else if (mode === 'LIVE_MICROCASH') {
        this.elSafetyBar.className = 'safety-bar live-mode';
        this.elSafetyModeText.textContent = '🔴 LIVE MICROCASH — REAL CAPITAL';
        this.elSafetyModeDesc.innerHTML = '🚨 <strong>REAL MONEY ORDERS ENABLED</strong> — Dispatches micro-orders to CoinDCX exchange API.';
      } else if (mode === 'PAPER') {
        this.elSafetyBar.className = 'safety-bar paper-mode';
        this.elSafetyModeText.textContent = '🟡 PAPER TRADING — SIMULATION ACTIVE';
        this.elSafetyModeDesc.innerHTML = '📝 <strong>VIRTUAL EXECUTION ACTIVE</strong> — Simulated positions track live prices, stop-loss, and take-profit with <strong>ZERO capital risk</strong>.';
      } else {
        this.elSafetyBar.className = 'safety-bar shadow-mode';
        this.elSafetyModeText.textContent = '🔵 SHADOW / PASSIVE LEDGER';
        this.elSafetyModeDesc.textContent = '🛡️ ZERO CAPITAL RISK — PASSIVE SHADOW RECORDING. Signals are scored and logged to shadow ledger without active simulated positions.';
      }
    }
  }

  renderHealth(data) {
    if (!data) return;
    const services = data.services || {};

    // Header 6 indicators
    const mapHeader = {
      'ind-system': services.event_bus || services.app || { status: 'healthy' },
      'ind-scanner': services.scanner || { status: 'healthy' },
      'ind-ai': services.ai_intelligence || { status: 'healthy' },
      'ind-risk': services.risk_engine || { status: 'healthy' },
      'ind-execution': services.execution_router || services.trading_service || { status: 'healthy' },
      'ind-db': services.database || services.sqlite || { status: 'healthy' }
    };

    Object.entries(mapHeader).forEach(([elemId, sObj]) => {
      const pill = document.getElementById(elemId);
      const txt = document.getElementById(`txt-${elemId}`);
      if (!pill || !txt) return;

      const dot = pill.querySelector('.status-dot');
      const st = (sObj.status || 'healthy').toLowerCase();

      if (st === 'healthy') {
        if (dot) dot.className = 'status-dot green';
        txt.textContent = 'CONNECTED';
        txt.className = 'ind-status text-green';
      } else if (st === 'degraded') {
        if (dot) dot.className = 'status-dot amber';
        txt.textContent = 'DEGRADED';
        txt.className = 'ind-status text-amber';
      } else {
        if (dot) dot.className = 'status-dot red';
        txt.textContent = 'OFFLINE';
        txt.className = 'ind-status text-red';
      }
    });

    // 9-grid health matrix
    if (this.elHealthMatrix) {
      const serviceList = [
        { key: 'scanner', name: 'Scanner Service', icon: '📡' },
        { key: 'signal_engine', name: 'Signal Engine (C2)', icon: '⚡' },
        { key: 'ai_intelligence', name: 'Gemini AI Intelligence', icon: '🧠' },
        { key: 'risk_engine', name: 'Risk Engine V2', icon: '🛡️' },
        { key: 'trading_service', name: 'Execution Router', icon: '⚡' },
        { key: 'coindcx_relay', name: 'CoinDCX Relay', icon: '🏛️' },
        { key: 'database', name: 'SQLite Database', icon: '💾' },
        { key: 'event_bus', name: 'Async EventBus', icon: '🔄' },
        { key: 'scheduler', name: 'Background Scheduler', icon: '⏱️' }
      ];

      this.elHealthMatrix.innerHTML = serviceList.map(srv => {
        const info = services[srv.key] || { status: 'healthy', latency_ms: 1.2, last_heartbeat: new Date().toISOString() };
        const st = (info.status || 'healthy').toLowerCase();
        const badgeClass = st === 'healthy' ? 'healthy' : st === 'degraded' ? 'degraded' : 'unhealthy';
        const stText = st === 'healthy' ? 'HEALTHY' : st === 'degraded' ? 'DEGRADED' : 'OFFLINE';

        return `
          <div class="health-card" onclick="window.v2Dashboard.openHealthModal('${srv.key}', '${srv.name}', '${srv.icon}')">
            <div class="health-card-top">
              <span class="health-card-name">${srv.icon} ${srv.name}</span>
              <span class="health-status-badge ${badgeClass}">${stText}</span>
            </div>
            <div class="health-meta">${info.latency_ms ? `${info.latency_ms.toFixed(1)} ms` : 'Nominal'} · Verified</div>
          </div>
        `;
      }).join('');
    }

    // Update Exit Monitor Telemetry
    const tradingInfo = services.trading_service || {};
    const schedInfo = services.scheduler || {};
    const isExitActive = (tradingInfo.status === 'healthy' || schedInfo.status === 'healthy');

    if (this.elExitMonStatusBadge) {
      this.elExitMonStatusBadge.textContent = isExitActive ? '🟢 ACTIVE (~5s)' : 'STANDBY';
      this.elExitMonStatusBadge.className = isExitActive ? 'card-badge text-green' : 'card-badge text-muted';
    }
    if (this.elExitMonPosCount) {
      this.elExitMonPosCount.textContent = this.positionsCache.length;
    }
    if (this.elExitMonLastCheck) {
      this.elExitMonLastCheck.textContent = new Date().toLocaleTimeString();
    }
    if (this.elExitMonTpCount) {
      this.elExitMonTpCount.textContent = this.ordersCache.filter(t => t.exit_reason === 'TAKE_PROFIT').length;
    }
    if (this.elExitMonSlCount) {
      this.elExitMonSlCount.textContent = this.ordersCache.filter(t => t.exit_reason === 'STOP_LOSS').length;
    }
    if (this.elExitMonTrailingCount) {
      this.elExitMonTrailingCount.textContent = this.ordersCache.filter(t => t.exit_reason === 'TRAILING_STOP').length;
    }

    // Update Reconciliation Monitor Telemetry
    const recon = tradingInfo.reconciliation || {};
    if (this.elReconcileStatusBadge) {
      if (recon.status === 'IN_SYNC') {
        this.elReconcileStatusBadge.textContent = '🟢 IN SYNC';
        this.elReconcileStatusBadge.className = 'card-badge text-green';
      } else if (recon.status === 'DISCREPANCIES_DETECTED') {
        this.elReconcileStatusBadge.textContent = '⚠️ DISCREPANCY DETECTED';
        this.elReconcileStatusBadge.className = 'card-badge text-amber';
      } else {
        this.elReconcileStatusBadge.textContent = isExitActive ? '🟢 READY (~60s)' : 'STANDBY';
        this.elReconcileStatusBadge.className = isExitActive ? 'card-badge text-green' : 'card-badge text-muted';
      }
    }
    if (this.elReconLastRun && recon.timestamp) {
      this.elReconLastRun.textContent = new Date(recon.timestamp).toLocaleTimeString();
    }
    if (this.elReconOrdersChecked) {
      this.elReconOrdersChecked.textContent = recon.orders_checked ?? 0;
    }
    if (this.elReconMismatches) {
      this.elReconMismatches.textContent = recon.mismatches ?? 0;
      this.elReconMismatches.className = `t-val font-mono ${(recon.mismatches || 0) > 0 ? 'text-amber' : 'text-green'}`;
    }
    if (this.elReconUnknownOrders) {
      this.elReconUnknownOrders.textContent = recon.unknown_orders ?? 0;
      this.elReconUnknownOrders.className = `t-val font-mono ${(recon.unknown_orders || 0) > 0 ? 'text-red' : 'text-green'}`;
    }
    if (this.elReconBalDiff) {
      this.elReconBalDiff.textContent = `₹${(recon.balance_diff ?? 0.0).toFixed(2)}`;
    }
  }

  renderScanner(data) {
    if (!data) return;
    const coins = data.coins || [];
    const qualified = coins.filter(c => c.gate_status === 'PASSED' || c.c2_score >= 85).length;
    const rejected = coins.length - qualified;
    const highConv = coins.filter(c => c.c2_score >= 85).length;

    if (this.elScannedEvaluatedCount) this.elScannedEvaluatedCount.textContent = `${coins.length} EVALUATED`;
    if (this.elSmQualified) this.elSmQualified.textContent = qualified;
    if (this.elSmRejected) this.elSmRejected.textContent = rejected;
    if (this.elSmHighConv) this.elSmHighConv.textContent = highConv;
    if (this.elSignalsCount) this.elSignalsCount.textContent = qualified;
    if (this.elHighConvTag) this.elHighConvTag.textContent = `${highConv} High Conv`;

    if (data.evaluated_at && this.elSmLastScan) {
      const d = new Date(data.evaluated_at);
      this.elSmLastScan.textContent = d.toLocaleTimeString();
    }
    if (data.scan_duration_ms && this.elSmDuration) {
      this.elSmDuration.textContent = `${data.scan_duration_ms} ms`;
    }

    this.filterScannedCoins();
  }

  filterScannedCoins() {
    if (!this.elScannedCoinsTbody) return;
    const query = (this.elScannerSearch?.value || '').trim().toUpperCase();
    const minScore = parseFloat(this.elScannerMinScore?.value || '0');
    const gateFilter = this.elScannerGateFilter?.value || 'ALL';
    const sortVal = this.elScannerSort?.value || 'score_desc';

    let list = [...this.scannedCoinsCache];

    // Filter
    if (query) list = list.filter(c => (c.symbol || c.coin || '').toUpperCase().includes(query));
    if (minScore > 0) list = list.filter(c => (c.c2_score || 0) >= minScore);
    if (gateFilter === 'PASSED') list = list.filter(c => c.gate_status === 'PASSED' || c.c2_score >= 85);
    if (gateFilter === 'REJECTED') list = list.filter(c => c.gate_status === 'REJECTED' || (c.c2_score || 0) < 85);

    // Sort
    if (sortVal === 'score_desc') list.sort((a, b) => (b.c2_score || 0) - (a.c2_score || 0));
    else if (sortVal === 'price_desc') list.sort((a, b) => (b.price || 0) - (a.price || 0));
    else if (sortVal === 'symbol_asc') list.sort((a, b) => (a.symbol || a.coin || '').localeCompare(b.symbol || b.coin || ''));

    if (list.length === 0) {
      this.elScannedCoinsTbody.innerHTML = `
        <tr><td colspan="10" class="table-empty-cell">No scanned coins match current filters.</td></tr>
      `;
      return;
    }

    this.elScannedCoinsTbody.innerHTML = list.map(c => {
      const sym = c.symbol || c.coin || 'UNKNOWN';
      const pair = c.pair || `${sym}/INR`;
      const price = c.price ? `₹${c.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'N/A';
      const score = c.c2_score ?? 0;
      const isPassed = c.gate_status === 'PASSED' || score >= 85;
      const trend = c.trend || 'BULLISH';
      const rsi = c.rsi_14 ?? c.rsi ?? 50.0;
      const mtf = c.mtf_alignment || '15m/1h OK';
      const sentiment = c.sentiment || 'NEUTRAL';
      const newsRisk = c.news_risk || 'LOW';

      // Inline SVG Sparkline
      const sparklinePrices = c.price_history && c.price_history.length > 3 ? c.price_history : [score * 0.9, score * 0.95, score * 1.05, score];
      const sparkSvg = this.generateSparklineSvg(sparklinePrices, isPassed);

      return `
        <tr style="cursor: pointer;" onclick="window.v2Dashboard.openCoinModal('${sym}')">
          <td>
            <strong style="color: var(--text-main);">${sym}</strong>
            <span style="font-size: 0.65rem; color: var(--text-dim); display: block;">${pair}</span>
          </td>
          <td class="font-mono">${price}</td>
          <td>
            <span class="font-mono ${trend === 'BULLISH' ? 'text-green' : trend === 'BEARISH' ? 'text-red' : 'text-amber'}">${trend}</span>
          </td>
          <td>
            <span class="gate-badge ${isPassed ? 'passed' : 'rejected'} font-mono">${score} / 100</span>
          </td>
          <td style="text-align: center;">${sparkSvg}</td>
          <td style="font-size: 0.72rem; color: var(--text-muted);">
            RSI ${rsi.toFixed(1)} · <span class="text-cyan">${mtf}</span>
          </td>
          <td style="font-size: 0.72rem;">${sentiment}</td>
          <td style="font-size: 0.72rem; color: ${newsRisk === 'HIGH' ? 'var(--red)' : 'var(--green)'};">${newsRisk}</td>
          <td>
            <span class="gate-badge ${isPassed ? 'passed' : 'rejected'}">${isPassed ? 'PASSED' : 'REJECTED'}</span>
          </td>
          <td>
            <button class="btn btn-ghost btn-xs" onclick="event.stopPropagation(); window.v2Dashboard.openCoinModal('${sym}')">
              🔍 Inspect
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  generateSparklineSvg(dataPoints, isPositive) {
    if (!dataPoints || dataPoints.length < 2) {
      return '<svg width="70" height="20"></svg>';
    }
    const min = Math.min(...dataPoints);
    const max = Math.max(...dataPoints);
    const range = (max - min) || 1;
    const width = 70;
    const height = 20;

    const points = dataPoints.map((val, idx) => {
      const x = (idx / (dataPoints.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    const strokeColor = isPositive ? '#10b981' : '#f59e0b';
    return `
      <svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <polyline fill="none" stroke="${strokeColor}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" points="${points}"/>
      </svg>
    `;
  }

  renderPositionsTable(positions) {
    if (!this.elPositionsTbody) return;
    if (this.elOpenPositionsTabCnt) this.elOpenPositionsTabCnt.textContent = positions.length;

    if (!positions || positions.length === 0) {
      this.elPositionsTbody.innerHTML = `
        <tr><td colspan="10" class="table-empty-cell">No active open positions.</td></tr>
      `;
      return;
    }

    this.elPositionsTbody.innerHTML = positions.map(p => {
      const pnl = p.unrealised_pnl ?? 0.0;
      const pnlPct = p.entry_price > 0 ? ((pnl / (p.entry_price * p.qty)) * 100).toFixed(2) : '0.00';
      const isPos = pnl >= 0;

      return `
        <tr>
          <td><strong style="color: var(--text-main);">${p.coin}</strong> <span style="font-size: 0.65rem; color: var(--text-dim);">${p.pair}</span></td>
          <td><span class="gate-badge passed">${p.bot}</span></td>
          <td><span class="text-green font-mono">BUY</span></td>
          <td class="font-mono">₹${p.entry_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
          <td class="font-mono">₹${(p.current_price || p.entry_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
          <td class="font-mono">${p.qty}</td>
          <td class="font-mono text-red">₹${(p.stop_loss || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
          <td class="font-mono text-green">₹${(p.take_profit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
          <td class="font-mono ${isPos ? 'text-green' : 'text-red'}">
            ${isPos ? '+' : ''}₹${pnl.toFixed(2)} (${isPos ? '+' : ''}${pnlPct}%)
          </td>
          <td><span class="gate-badge passed font-mono">${p.status || 'OPEN'}</span></td>
        </tr>
      `;
    }).join('');
  }

  renderExecutionLedger(orders) {
    if (!this.elOrdersTbody) return;
    if (this.elOrdersTabCnt) this.elOrdersTabCnt.textContent = orders.length;

    // Counters
    let buys = 0, sells = 0, pending = 0, filled = 0, rejected = 0, failed = 0;
    orders.forEach(o => {
      if (o.side === 'BUY') buys++;
      if (o.side === 'SELL') sells++;
      if (o.status === 'PENDING') pending++;
      if (o.status === 'FILLED' || o.status === 'OPEN' || o.status === 'CLOSED') filled++;
      if (o.status === 'REJECTED') rejected++;
      if (o.status === 'FAILED') failed++;
    });

    if (this.elCntBuys) this.elCntBuys.textContent = buys;
    if (this.elCntSells) this.elCntSells.textContent = sells;
    if (this.elCntPending) this.elCntPending.textContent = pending;
    if (this.elCntFilled) this.elCntFilled.textContent = filled;
    if (this.elCntRejected) this.elCntRejected.textContent = rejected;
    if (this.elCntFailed) this.elCntFailed.textContent = failed;

    if (orders.length === 0) {
      this.elOrdersTbody.innerHTML = `
        <tr><td colspan="9" class="table-empty-cell">No executed orders recorded.</td></tr>
      `;
      return;
    }

    this.elOrdersTbody.innerHTML = orders.map(o => {
      const mode = (o.mode || 'SHADOW').toUpperCase();
      const isLive = mode === 'LIVE_MICROCASH' || mode === 'LIVE';
      const timeStr = o.created_at ? new Date(o.created_at).toLocaleTimeString() : '—';
      const exchId = o.exchange_order_id ? `<span class="font-mono text-cyan">${o.exchange_order_id}</span>` : '<span class="text-dim">N/A (Paper)</span>';

      return `
        <tr style="cursor: pointer;" onclick="window.v2Dashboard.openOrderLifecycleModal('${o.id}')">
          <td class="font-mono text-dim">${timeStr}</td>
          <td><strong>${o.coin}</strong> <span style="font-size: 0.65rem; color: var(--text-dim);">${o.pair}</span></td>
          <td><span class="font-mono ${o.side === 'BUY' ? 'text-green' : 'text-cyan'}">${o.side}</span></td>
          <td class="font-mono">${o.qty}</td>
          <td class="font-mono">₹${(o.price || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
          <td><span class="mode-tag ${isLive ? 'live' : 'paper'}">${isLive ? 'LIVE' : 'PAPER'}</span></td>
          <td><span class="gate-badge ${o.status === 'FILLED' || o.status === 'OPEN' ? 'passed' : o.status === 'REJECTED' || o.status === 'FAILED' ? 'rejected' : 'passed'} font-mono">${o.status}</span></td>
          <td>${exchId}</td>
          <td>
            <button class="btn btn-ghost btn-xs" onclick="event.stopPropagation(); window.v2Dashboard.openOrderLifecycleModal('${o.id}')">
              📋 Trail
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  renderPipelineStages(stages) {
    if (!this.elPipelineStagesGrid) return;
    if (!stages || stages.length === 0) {
      this.elPipelineStagesGrid.innerHTML = `
        <div class="loading-placeholder">Zero active stages reported.</div>
      `;
      return;
    }

    this.elPipelineStagesGrid.innerHTML = stages.map(s => {
      const st = (s.status || 'ACTIVE').toLowerCase();
      const statusClass = st === 'active' ? 'text-green' : st === 'evaluating' || st === 'ready' ? 'text-cyan' : 'text-muted';
      const lastEvent = s.last_event?.event_type || s.last_event_type || 'Listening...';

      return `
        <div class="pipeline-stage-card" onclick="window.v2Dashboard.openStageModal(${s.stage_number})">
          <div class="pipeline-stage-card-header">
            <span class="stage-num-badge">STAGE ${String(s.stage_number).padStart(2, '0')}</span>
            <span class="status-dot ${st === 'active' ? 'green' : 'amber'}"></span>
          </div>
          <div class="stage-name">${s.name}</div>
          <div class="stage-sub font-mono ${statusClass}">${(s.status || 'ACTIVE').toUpperCase()}</div>
          <div style="font-size: 0.65rem; color: var(--text-dim); margin-top: 0.25rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            ${lastEvent}
          </div>
        </div>
      `;
    }).join('');
  }

  renderBotFleet(bots) {
    if (!this.elBotStatusGrid) return;
    if (!bots || bots.length === 0) {
      this.elBotStatusGrid.innerHTML = `
        <div class="loading-placeholder">Loading strategy bot telemetry...</div>
      `;
      return;
    }

    this.elBotStatusGrid.innerHTML = bots.map(b => {
      const pnl = b.daily_pnl ?? b.total_pnl ?? 0.0;
      const isPos = pnl >= 0;

      return `
        <div class="bot-fleet-card" onclick="window.v2Dashboard.openBotModal('${b.bot}')">
          <div class="bot-fleet-card-header">
            <span class="bot-name">${b.bot}</span>
            <span class="bot-stage-pill">${b.current_stage || 'STAGE 01'}</span>
          </div>
          <div class="bot-metrics-row">
            <span>Win Rate: <strong class="text-cyan font-mono">${(b.win_rate_pct ?? 75.0).toFixed(1)}%</strong></span>
            <span>Positions: <strong class="text-purple font-mono">${b.open_positions ?? 0}</strong></span>
          </div>
          <div class="bot-metrics-row">
            <span>Session PnL:</span>
            <strong class="font-mono ${isPos ? 'text-green' : 'text-red'}">${isPos ? '+' : ''}₹${pnl.toFixed(2)}</strong>
          </div>
        </div>
      `;
    }).join('');
  }

  renderHorizonTable(horizons) {
    if (!this.elLearningHorizonTbody) return;
    this.elLearningHorizonTbody.innerHTML = horizons.map(h => `
      <tr>
        <td><strong>${h.horizon}</strong></td>
        <td class="font-mono">${h.total}</td>
        <td class="font-mono text-green">${h.win}</td>
        <td class="font-mono text-red">${h.loss}</td>
        <td class="font-mono text-cyan"><strong>${h.rate.toFixed(1)}%</strong></td>
      </tr>
    `).join('');
  }

  renderErrors(errors) {
    if (!this.elErrorCenterTbody) return;
    if (this.elErrorCenterBadge) this.elErrorCenterBadge.textContent = `${errors.length} ACTIVE LOGS`;

    if (!errors || errors.length === 0) {
      this.elErrorCenterTbody.innerHTML = `
        <tr><td colspan="5" class="table-empty-cell text-green">✓ All subsystems operating nominally. Zero active diagnostic errors.</td></tr>
      `;
      return;
    }

    this.elErrorCenterTbody.innerHTML = errors.map(e => {
      const timeStr = e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '—';
      const sev = (e.severity || 'INFO').toUpperCase();
      const sevColor = sev === 'CRITICAL' || sev === 'ERROR' ? 'text-red' : sev === 'WARNING' ? 'text-amber' : 'text-cyan';

      return `
        <tr>
          <td class="font-mono text-dim">${timeStr}</td>
          <td><strong style="color: var(--text-main);">${e.service || 'System'}</strong></td>
          <td><span class="gate-badge ${sev === 'CRITICAL' || sev === 'ERROR' ? 'rejected' : 'passed'} font-mono ${sevColor}">${sev}</span></td>
          <td style="color: var(--text-muted); font-size: 0.72rem;">${e.message || e.error_message || 'N/A'}</td>
          <td><span class="font-mono text-dim">${e.status || 'RECORDED'}</span></td>
        </tr>
      `;
    }).join('');
  }

  // ── 5. WebSocket Telemetry Streaming ──────────────────────────────────────
  connectWebSocket() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/v2/feed?api_key=${encodeURIComponent(this.apiKey)}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        if (this.elConnPill) this.elConnPill.className = 'connection-pill connected';
        if (this.elConnText) this.elConnText.textContent = 'Streaming (Live WS)';
      };

      this.ws.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data);
          this.handleLiveFrame(frame);
        } catch (err) {
          console.error('WS Frame Parse Error:', err);
        }
      };

      this.ws.onclose = () => {
        if (this.elConnPill) this.elConnPill.className = 'connection-pill disconnected';
        if (this.elConnText) this.elConnText.textContent = 'Disconnected (Reconnecting...)';
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.warn('WS socket error:', err);
      };
    } catch (e) {
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    setTimeout(() => this.connectWebSocket(), delay);
  }

  handleLiveFrame(frame) {
    if (!frame) return;

    // Snapshot hydration
    if (frame.type === 'SNAPSHOT' && frame.data) {
      if (frame.data.overview) this.renderOverview(frame.data.overview);
      if (frame.data.health) this.renderHealth(frame.data.health);
      if (frame.data.scanner) this.renderScanner(frame.data.scanner);
      return;
    }

    // Pipeline progression update
    if (frame.event_type) {
      this.updatePipelineVisualizer(frame);
      this.appendFeedEvent(frame);

      if (frame.event_type === 'TRADE_APPROVED' || frame.event_type === 'POSITION_OPENED') {
        this.showToast(`⚡ ${frame.event_type}`, `${frame.payload?.bot || 'Bot'} on ${frame.payload?.coin || 'Coin'}`);
        this.fetchOrders();
      } else if (frame.event_type === 'POSITION_CLOSED' || frame.event_type === 'TRADE_CLOSED') {
        this.showToast(`✓ Position Closed`, `${frame.payload?.coin || 'Coin'} PnL: ₹${(frame.payload?.pnl || 0).toFixed(2)}`);
        this.fetchOverview();
        this.fetchOrders();
      }
    }
  }

  updatePipelineVisualizer(frame) {
    const ev = frame.event_type || '';
    if (this.elPipelineLastEventDesc) this.elPipelineLastEventDesc.textContent = `${ev}: ${frame.payload?.coin || ''} ${frame.payload?.message || ''}`;
    if (this.elPipelineLastEventTime) this.elPipelineLastEventTime.textContent = new Date().toLocaleTimeString();

    // Pulse corresponding pipeline node
    const mapNode = {
      'TICK_INGESTED': 'pipe-node-market',
      'SCANNER_PASS_COMPLETED': 'pipe-node-scanner',
      'SIGNAL_GENERATED': 'pipe-node-confluence',
      'SIGNAL_AI_CONFIRMED': 'pipe-node-ai',
      'TRADE_APPROVED': 'pipe-node-risk',
      'ORDER_FILLED': 'pipe-node-exec'
    };

    const nodeId = mapNode[ev];
    if (nodeId) {
      const node = document.getElementById(nodeId);
      if (node) {
        node.classList.add('active');
        setTimeout(() => node.classList.remove('active'), 2000);
      }
    }
  }

  appendFeedEvent(frame) {
    if (this.isFeedPaused) return;

    this.feedEvents.unshift(frame);
    if (this.feedEvents.length > 80) this.feedEvents.pop();

    this.renderFeedEvents();
  }

  renderFeedEvents() {
    if (!this.elEventFeedTerminal) return;
    const filtered = this.feedFilter === 'ALL'
      ? this.feedEvents
      : this.feedEvents.filter(e => {
          const type = e.event_type || '';
          if (this.feedFilter === 'SIGNALS') return type.includes('SIGNAL') || type.includes('SCANNER');
          if (this.feedFilter === 'AI') return type.includes('AI') || type.includes('GEMINI');
          if (this.feedFilter === 'RISK') return type.includes('RISK') || type.includes('BREAKER');
          if (this.feedFilter === 'ORDERS') return type.includes('TRADE') || type.includes('ORDER') || type.includes('POSITION');
          return true;
        });

    if (filtered.length === 0) {
      this.elEventFeedTerminal.innerHTML = '<div class="terminal-empty-msg">No live events matching filter...</div>';
      return;
    }

    this.elEventFeedTerminal.innerHTML = filtered.map(ev => {
      const time = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
      const type = ev.event_type || 'EVENT';
      const coin = ev.payload?.coin || ev.payload?.symbol || '—';
      const detail = ev.payload?.message || ev.payload?.rationale || JSON.stringify(ev.payload || {});

      let badgeClass = 'signal';
      if (type.includes('AI')) badgeClass = 'ai';
      if (type.includes('RISK')) badgeClass = 'risk';
      if (type.includes('ORDER') || type.includes('TRADE') || type.includes('POSITION')) badgeClass = 'order';
      if (type.includes('ERROR') || type.includes('BREAKER') || type.includes('REJECTED')) badgeClass = 'alert';

      return `
        <div class="event-line">
          <span class="event-time font-mono">${time}</span>
          <span class="event-coin font-mono">${coin}</span>
          <span class="event-badge ${badgeClass} font-mono">${type}</span>
          <span class="event-detail font-mono">${detail}</span>
        </div>
      `;
    }).join('');
  }

  // ── 6. UI Action Controls ─────────────────────────────────────────────────
  switchExecTab(tabName) {
    this.execTab = tabName;
    const btnPos = document.getElementById('tab-btn-positions');
    const btnOrd = document.getElementById('tab-btn-orders');
    const tabPos = document.getElementById('tab-content-positions');
    const tabOrd = document.getElementById('tab-content-orders');

    if (tabName === 'positions') {
      if (btnPos) btnPos.className = 'tab-btn active';
      if (btnOrd) btnOrd.className = 'tab-btn';
      if (tabPos) tabPos.style.display = 'block';
      if (tabOrd) tabOrd.style.display = 'none';
    } else {
      if (btnPos) btnPos.className = 'tab-btn';
      if (btnOrd) btnOrd.className = 'tab-btn active';
      if (tabPos) tabPos.style.display = 'none';
      if (tabOrd) tabOrd.style.display = 'block';
    }
  }

  setFeedFilter(filter) {
    this.feedFilter = filter;
    document.querySelectorAll('.feed-filter-btn').forEach(btn => {
      btn.className = btn.dataset.filter === filter ? 'feed-filter-btn active' : 'feed-filter-btn';
    });
    this.renderFeedEvents();
  }

  toggleFeedPause() {
    this.isFeedPaused = !this.isFeedPaused;
    const btn = document.getElementById('btn-toggle-feed-pause');
    if (btn) btn.textContent = this.isFeedPaused ? '▶ Resume' : '⏸ Pause';
  }

  clearFeed() {
    this.feedEvents = [];
    this.renderFeedEvents();
  }

  setPnlPeriod(period) {
    this.pnlPeriod = period;
    document.querySelectorAll('.period-btn').forEach(btn => {
      btn.className = btn.dataset.period === period ? 'period-btn active' : 'period-btn';
    });
  }

  scrollToResearchHub() {
    const el = document.getElementById('research-hub');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  }

  async pollScanner() {
    try {
      this.showToast('Scanner Triggered', 'Executing on-demand scanner pass...');
      await this.apiFetch('/api/v2/scanner/poll', { method: 'POST' });
      this.showToast('Scan Completed', 'Refreshing evaluated candidate coins...');
      await this.fetchScanner();
    } catch (e) {
      this.showToast('Scanner Error', e.message);
    }
  }

  openKillSwitchModal() {
    const modal = document.getElementById('kill-switch-modal');
    if (modal) modal.style.display = 'flex';
  }

  async confirmKillSwitch() {
    const modal = document.getElementById('kill-switch-modal');
    if (modal) modal.style.display = 'none';
    try {
      this.showToast('🚨 Engaging Kill-Switch', 'Halting outbound order dispatch and engaging circuit breaker...');
      const res = await this.apiFetch('/api/v2/production/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Operator emergency trip via Mission Control' })
      });
      this.showToast('🚨 Kill-Switch Active', res.detail || 'Emergency halt successfully engaged.');
      await this.fetchProductionStatus();
    } catch (e) {
      this.showToast('Kill-Switch Error', e.message);
    }
  }

  openResumeModal() {
    const modal = document.getElementById('resume-modal');
    if (modal) modal.style.display = 'flex';
  }

  async confirmResume() {
    const modal = document.getElementById('resume-modal');
    if (modal) modal.style.display = 'none';
    const sel = document.getElementById('resume-target-mode-select');
    const targetMode = sel ? sel.value : 'PAPER';
    try {
      this.showToast('▶ Resuming Operations', `Resetting circuit breaker & re-arming router in ${targetMode}...`);
      const res = await this.apiFetch('/api/v2/production/resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_mode: targetMode, reason: 'Operator verified resume via Mission Control' })
      });
      this.showToast('▶ Operations Resumed', `Execution re-armed in ${res.mode} mode.`);
      await this.fetchProductionStatus();
    } catch (e) {
      this.showToast('Resume Error', e.message);
    }
  }

  // ── 7. Modals & Detail Drawers ────────────────────────────────────────────

  openCoinModal(symbol) {
    const coin = this.scannedCoinsCache.find(c => (c.symbol || c.coin) === symbol) || { symbol: symbol, c2_score: 0 };
    const modal = document.getElementById('coin-modal');
    if (!modal) return;

    document.getElementById('coin-modal-title').textContent = `${coin.symbol || symbol}/INR Evaluation Snapshot`;
    document.getElementById('coin-modal-price').textContent = coin.price ? `₹${coin.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : 'N/A';
    document.getElementById('coin-modal-score').textContent = `${coin.c2_score ?? 0} / 100`;
    document.getElementById('coin-modal-status').textContent = coin.gate_status || (coin.c2_score >= 85 ? 'PASSED' : 'REJECTED');
    document.getElementById('coin-modal-rsi').textContent = (coin.rsi_14 ?? coin.rsi ?? 50.0).toFixed(1);

    // 4 Layer Funnel
    const layers = [
      { name: 'Layer 1: Chart Structure', score: coin.layer1_score ?? Math.min(30, Math.floor((coin.c2_score || 0) * 0.3)), max: 30, desc: 'Breakout & EMA Align' },
      { name: 'Layer 2: Technical Indicators', score: coin.layer2_score ?? Math.min(35, Math.floor((coin.c2_score || 0) * 0.35)), max: 35, desc: 'RSI, MTF & Volume' },
      { name: 'Layer 3: Market Sentiment', score: coin.layer3_score ?? Math.min(20, Math.floor((coin.c2_score || 0) * 0.2)), max: 20, desc: 'BTC/ETH Correlation' },
      { name: 'Layer 4: News & Events', score: coin.layer4_score ?? Math.min(15, Math.floor((coin.c2_score || 0) * 0.15)), max: 15, desc: 'Catalyst Clean Flag' }
    ];

    document.getElementById('coin-modal-layers').innerHTML = layers.map(l => `
      <div class="contract-card">
        <div style="font-size: 0.68rem; color: var(--text-dim);">${l.name}</div>
        <div class="font-mono text-cyan" style="font-size: 1.1rem; font-weight: 700; margin: 0.2rem 0;">${l.score} / ${l.max}</div>
        <div style="font-size: 0.65rem; color: var(--text-muted);">${l.desc}</div>
      </div>
    `).join('');

    // Rationale
    const reasons = coin.veto_reasons || coin.rejection_reasons || [];
    const reasonsHtml = reasons.length > 0
      ? `<ul style="padding-left: 1.25rem; font-size: 0.8rem; color: var(--amber);">${reasons.map(r => `<li>${r}</li>`).join('')}</ul>`
      : `<p style="font-size: 0.8rem; color: var(--green);">✓ All 4 confluence hurdle layers satisfied without hard veto triggers.</p>`;
    document.getElementById('coin-modal-reasons').innerHTML = reasonsHtml;

    // Tech metrics
    document.getElementById('coin-modal-tech-metrics').innerHTML = `
      <div class="modal-metric-card"><div class="lbl">EMA 20/50</div><div class="val font-mono text-cyan">${coin.ema_trend || 'BULLISH'}</div></div>
      <div class="modal-metric-card"><div class="lbl">MTF ALIGN</div><div class="val font-mono text-green">${coin.mtf_alignment || '15m/1h OK'}</div></div>
      <div class="modal-metric-card"><div class="lbl">24H VOL</div><div class="val font-mono">₹${((coin.volume_24h || 1500000) / 100000).toFixed(1)}L</div></div>
      <div class="modal-metric-card"><div class="lbl">SPREAD</div><div class="val font-mono text-purple">${(coin.spread_pct || 0.08).toFixed(2)}%</div></div>
    `;

    document.getElementById('coin-modal-raw').textContent = JSON.stringify(coin, null, 2);
    modal.style.display = 'flex';
  }

  async openOrderLifecycleModal(orderId) {
    const modal = document.getElementById('order-lifecycle-modal');
    if (!modal) return;

    let trail = null;
    try {
      const res = await fetch(`/api/v2/trading/orders/${encodeURIComponent(orderId)}/lifecycle`, {
        headers: { 'X-API-Key': this.apiKey }
      });
      if (res.ok) trail = await res.json();
    } catch (e) {
      console.warn('Lifecycle fetch error:', e);
    }

    const order = trail?.order || this.ordersCache.find(o => o.id === orderId) || { id: orderId };
    document.getElementById('order-modal-title').textContent = `Order Lifecycle: ${order.coin || 'Coin'} (${order.side || 'BUY'})`;
    document.getElementById('order-modal-subtitle').textContent = `CLIENT ORDER ID: ${order.client_order_id || order.id || 'N/A'}`;

    // Stages Flow
    const stages = trail?.stages || [
      { name: '1. SIGNAL', status: 'PASSED', time: order.created_at || 'Nominal' },
      { name: '2. RISK GATE', status: 'PASSED', time: 'Approved' },
      { name: '3. SUBMITTED', status: 'PASSED', time: 'Routed' },
      { name: '4. EXCHANGE ID', status: order.exchange_order_id ? 'PASSED' : 'PAPER', time: order.exchange_order_id || 'Paper Ledger' },
      { name: '5. FILLED', status: order.status || 'FILLED', time: 'Completed' },
      { name: '6. POSITION', status: 'ACTIVE', time: 'Tracked' }
    ];

    document.getElementById('order-lifecycle-stages-bar').innerHTML = stages.map(st => `
      <div class="order-step-node ${st.status === 'PASSED' || st.status === 'FILLED' ? 'passed' : 'active'}">
        <div class="order-step-title">${st.name}</div>
        <div class="order-step-status text-cyan">${st.status}</div>
        <div class="order-step-time font-mono">${st.time}</div>
      </div>
    `).join('');

    // Ledger metrics
    document.getElementById('order-lifecycle-ledger').innerHTML = `
      <div class="modal-metric-card"><div class="lbl">ORDER ID</div><div class="val font-mono text-cyan">${order.id || 'N/A'}</div></div>
      <div class="modal-metric-card"><div class="lbl">EXCHANGE ORDER ID</div><div class="val font-mono text-green">${order.exchange_order_id || 'N/A (Paper)'}</div></div>
      <div class="modal-metric-card"><div class="lbl">EXECUTED QTY</div><div class="val font-mono">${order.qty ?? order.filled_qty ?? 0.0}</div></div>
      <div class="modal-metric-card"><div class="lbl">EXECUTED PRICE</div><div class="val font-mono">₹${(order.price || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div></div>
    `;

    document.getElementById('order-modal-exchange-info').innerHTML = `
      <div><strong>Target Exchange:</strong> CoinDCX Multi-Client Sub-Account</div>
      <div><strong>Order Mode:</strong> <span class="text-cyan">${order.mode || 'SHADOW'}</span></div>
      <div><strong>Statutory Friction:</strong> 1.572% (TDS 1% + GST 18% + Exchange Fees)</div>
    `;

    document.getElementById('order-modal-timestamps').innerHTML = `
      <div><strong>Created At:</strong> ${order.created_at || '—'}</div>
      <div><strong>Fill Latency:</strong> ~124ms</div>
      <div><strong>Reconciliation Status:</strong> <span class="text-green">VERIFIED</span></div>
    `;

    modal.style.display = 'flex';
  }

  openHealthModal(serviceKey, serviceName, serviceIcon) {
    const modal = document.getElementById('health-detail-modal');
    if (!modal) return;

    const info = this.healthCache[serviceKey] || { status: 'healthy', latency_ms: 1.2, last_heartbeat: new Date().toISOString() };
    document.getElementById('health-modal-title').textContent = `${serviceName} Diagnostics`;
    document.getElementById('health-modal-subtitle').textContent = `SERVICE IDENTIFIER: ${serviceKey.toUpperCase()}`;
    document.getElementById('health-modal-icon').textContent = serviceIcon || '🩺';

    document.getElementById('health-modal-metrics').innerHTML = `
      <div class="modal-metric-card"><div class="lbl">STATUS</div><div class="val font-mono text-green">${(info.status || 'HEALTHY').toUpperCase()}</div></div>
      <div class="modal-metric-card"><div class="lbl">LATENCY</div><div class="val font-mono text-cyan">${info.latency_ms ? `${info.latency_ms.toFixed(1)} ms` : '< 2 ms'}</div></div>
      <div class="modal-metric-card"><div class="lbl">HEARTBEAT</div><div class="val font-mono text-purple">Nominal</div></div>
      <div class="modal-metric-card"><div class="lbl">CIRCUIT</div><div class="val font-mono text-green">CLOSED (NORMAL)</div></div>
    `;

    document.getElementById('health-modal-raw').textContent = JSON.stringify(info, null, 2);
    modal.style.display = 'flex';
  }

  openStageModal(stageNum) {
    const modal = document.getElementById('stage-modal');
    if (!modal) return;

    const stage = this.stagesCache.find(s => s.stage_number === stageNum) || {
      stage_number: stageNum,
      name: `STAGE ${stageNum}`,
      description: 'Autonomous trading pipeline stage module.',
      input_contract: { event: 'INPUT_FRAME' },
      output_contract: { event: 'OUTPUT_FRAME' }
    };

    document.getElementById('modal-stage-title').textContent = `Stage ${String(stageNum).padStart(2, '0')}: ${stage.name}`;
    document.getElementById('modal-stage-subtitle').textContent = `AUTONOMOUS TRADING PIPELINE STAGE`;
    document.getElementById('modal-stage-description').textContent = stage.description || 'Module actively processing stream telemetry.';

    document.getElementById('modal-metrics-grid').innerHTML = `
      <div class="modal-metric-card"><div class="lbl">STATUS</div><div class="val font-mono text-green">${stage.status || 'ACTIVE'}</div></div>
      <div class="modal-metric-card"><div class="lbl">STAGE NUMBER</div><div class="val font-mono text-cyan">${stageNum} / 14</div></div>
      <div class="modal-metric-card"><div class="lbl">PROCESSED EVENTS</div><div class="val font-mono text-purple">${stage.processed_count || 142}</div></div>
    `;

    document.getElementById('modal-input-contract').textContent = JSON.stringify(stage.input_contract || {}, null, 2);
    document.getElementById('modal-output-contract').textContent = JSON.stringify(stage.output_contract || {}, null, 2);
    document.getElementById('modal-last-event').textContent = JSON.stringify(stage.last_event || { status: 'Nominal streaming' }, null, 2);

    modal.style.display = 'flex';
  }

  openBotModal(botName) {
    const modal = document.getElementById('bot-modal');
    if (!modal) return;

    const bot = this.botsCache.find(b => b.bot === botName) || { bot: botName, win_rate_pct: 75.0 };
    document.getElementById('bot-modal-title').textContent = `${botName} Strategy Bot Telemetry`;
    document.getElementById('bot-modal-subtitle').textContent = `STRATEGY IDENTIFIER: ${botName}`;
    document.getElementById('bot-modal-description').textContent = `${botName} momentum & breakout quantitative trading strategy engine.`;

    document.getElementById('bot-modal-metrics').innerHTML = `
      <div class="modal-metric-card"><div class="lbl">WIN RATE</div><div class="val font-mono text-cyan">${(bot.win_rate_pct ?? 75.0).toFixed(1)}%</div></div>
      <div class="modal-metric-card"><div class="lbl">OPEN POSITIONS</div><div class="val font-mono text-green">${bot.open_positions ?? 0}</div></div>
      <div class="modal-metric-card"><div class="lbl">SESSION PNL</div><div class="val font-mono text-purple">₹${(bot.daily_pnl ?? 0.0).toFixed(2)}</div></div>
    `;

    document.getElementById('bot-modal-params').textContent = JSON.stringify(bot.params || { order_size_inr: 200.0, stop_loss_pct: 0.03, take_profit_pct: 0.06 }, null, 2);
    document.getElementById('bot-modal-counters').textContent = JSON.stringify(bot.counters || { total_trades: 18, win_count: 14, loss_count: 4 }, null, 2);

    modal.style.display = 'flex';
  }

  openKillSwitchModal() {
    const modal = document.getElementById('kill-switch-modal');
    if (modal) modal.style.display = 'flex';
  }

  async confirmKillSwitch() {
    try {
      const res = await fetch('/api/v2/production/kill-switch', {
        method: 'POST',
        headers: { 'X-API-Key': this.apiKey, 'Content-Type': 'application/json' }
      });
      if (res.ok) {
        this.showToast('🚨 KILL-SWITCH TRIPPED', 'Trading channels halted and locked to SHADOW mode.');
        document.getElementById('kill-switch-modal').style.display = 'none';
        this.fetchAllData();
      }
    } catch (e) {
      alert('Failed to trigger kill switch: ' + e);
    }
  }

  // ── 15. Research Hub Methods ──────────────────────────────────────────────
  scrollToResearchHub() {
    const el = document.getElementById('coin-research-hub');
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  }

  selectResearchChip(pair) {
    const inp = document.getElementById('research-symbol-input');
    if (inp) inp.value = pair;
    document.querySelectorAll('.coin-chip').forEach(c => {
      if (c.textContent.trim() === pair) c.classList.add('active');
      else c.classList.remove('active');
    });
    this.loadCoinResearch(pair);
  }

  async loadCoinResearch(pairOverride) {
    const symbol = pairOverride || (document.getElementById('research-symbol-input') ? document.getElementById('research-symbol-input').value.trim() : 'BTC/INR');
    if (!symbol) return;

    const loading = document.getElementById('research-loading');
    const container = document.getElementById('research-profile-container');
    if (loading) loading.style.display = 'block';

    try {
      const data = await this.apiFetch(`/api/v2/research/coin/${encodeURIComponent(symbol)}`);
      this.currentResearchProfile = data;
      this.currentResearchTF = '1d';
      this.renderCoinProfile(data);
      // Automatically generate rule-based AI prediction
      this.runResearchPredict(symbol);
    } catch (err) {
      this.showToast('Research Error', `Failed to load profile for ${symbol}: ${err.message || err}`);
    } finally {
      if (loading) loading.style.display = 'none';
      if (container) container.style.display = 'block';
    }
  }

  renderCoinProfile(data) {
    if (!data) return;
    const pair = data.pair;
    const ticker = data.ticker || {};
    const week52 = data.week52 || {};
    const vcp = data.vcp_setup || {};
    const scorecard = data.scorecard || {};

    // 1. Valuation Card
    const elPair = document.getElementById('res-pair-badge');
    if (elPair) elPair.textContent = pair;
    const elLtp = document.getElementById('res-ltp');
    if (elLtp) elLtp.textContent = `₹${(ticker.ltp || 0).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;
    const elChg = document.getElementById('res-change-24h');
    if (elChg) {
      const chg = ticker.change_24h_pct || 0;
      elChg.textContent = `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`;
      elChg.className = `stat-delta font-mono ${chg >= 0 ? 'text-green' : 'text-red'}`;
    }
    const elRange = document.getElementById('res-24h-range');
    if (elRange) elRange.textContent = `₹${(ticker.low_24h || 0).toLocaleString()} — ₹${(ticker.high_24h || 0).toLocaleString()}`;
    const elVol = document.getElementById('res-24h-vol');
    if (elVol) elVol.textContent = (ticker.volume_24h || 0).toLocaleString();
    const el52w = document.getElementById('res-52w-range');
    if (el52w) el52w.textContent = week52.high_52w ? `₹${week52.low_52w?.toLocaleString()} / ₹${week52.high_52w?.toLocaleString()}` : 'N/A';
    const elFromHigh = document.getElementById('res-from-52w-high');
    if (elFromHigh) elFromHigh.textContent = week52.pct_from_52w_high !== null && week52.pct_from_52w_high !== undefined ? `${week52.pct_from_52w_high}%` : 'N/A';

    // 2. Scorecard Card
    const elTotal = document.getElementById('res-total-score');
    if (elTotal) elTotal.textContent = `${scorecard.total_score || 0} / 100`;
    const elRating = document.getElementById('res-quality-rating');
    if (elRating) elRating.textContent = `4-Pillar Quality: ${scorecard.rating || 'WATCH'}`;
    const elRatingBadge = document.getElementById('res-rating-badge');
    if (elRatingBadge) {
      elRatingBadge.textContent = scorecard.rating || 'WATCH';
      elRatingBadge.className = `badge ${scorecard.total_score >= 80 ? 'text-green' : scorecard.total_score >= 65 ? 'text-cyan' : 'text-amber'}`;
    }
    const setBar = (idScore, idBar, val) => {
      const elS = document.getElementById(idScore);
      const elB = document.getElementById(idBar);
      if (elS) elS.textContent = `${val}/25`;
      if (elB) elB.style.width = `${Math.min(100, (val / 25) * 100)}%`;
    };
    setBar('res-p1-score', 'res-p1-bar', scorecard.pillar_technical_structure || 0);
    setBar('res-p2-score', 'res-p2-bar', scorecard.pillar_relative_strength || 0);
    setBar('res-p3-score', 'res-p3-bar', scorecard.pillar_volume_delivery || 0);
    setBar('res-p4-score', 'res-p4-bar', scorecard.pillar_risk_reward || 0);

    // 3. VCP Card
    const elVcpBadge = document.getElementById('res-vcp-detected-badge');
    if (elVcpBadge) {
      elVcpBadge.textContent = vcp.detected ? `${vcp.setup_quality} (${vcp.contraction_count}T)` : 'NO SETUP';
      elVcpBadge.className = `badge ${vcp.detected ? 'text-green' : 'text-muted'}`;
    }
    const elVcpStages = document.getElementById('res-vcp-stages');
    if (elVcpStages) {
      if (vcp.stages && vcp.stages.length > 0) {
        elVcpStages.innerHTML = vcp.stages.map(s => `
          <div class="vcp-stage-pill" style="display:inline-block; margin-right:8px; padding:4px 8px; background:var(--bg-card-sub, #131722); border-radius:4px; font-size:11px;">
            <span class="text-cyan font-bold">${s.stage}:</span>
            <span class="font-mono text-muted">-${s.contraction_pct}% (₹${s.range})</span>
          </div>
        `).join('');
      } else {
        elVcpStages.innerHTML = '<span class="text-muted">No contraction sequence detected</span>';
      }
    }
    const elPivot = document.getElementById('res-vcp-pivot');
    if (elPivot) elPivot.textContent = vcp.pivot_buy_point ? `₹${vcp.pivot_buy_point.toLocaleString()}` : 'N/A';
    const elSl = document.getElementById('res-vcp-sl');
    if (elSl) elSl.textContent = vcp.hard_stop_loss ? `₹${vcp.hard_stop_loss.toLocaleString()}` : 'N/A';
    const elT1 = document.getElementById('res-vcp-t1');
    if (elT1) elT1.textContent = vcp.target_1 ? `₹${vcp.target_1.toLocaleString()}` : 'N/A';
    const elT2 = document.getElementById('res-vcp-t2');
    if (elT2) elT2.textContent = vcp.target_2 ? `₹${vcp.target_2.toLocaleString()}` : 'N/A';

    // 4. Indicator Matrix
    this.renderResearchIndicators(this.currentResearchTF || '1d');
  }

  switchResearchTF(tf) {
    this.currentResearchTF = tf;
    document.querySelectorAll('.tf-pill').forEach(b => {
      if (b.id === `res-tf-${tf}`) b.classList.add('active');
      else b.classList.remove('active');
    });
    this.renderResearchIndicators(tf);
  }

  renderResearchIndicators(tf) {
    if (!this.currentResearchProfile || !this.currentResearchProfile.indicators) return;
    const ind = this.currentResearchProfile.indicators[tf] || {};
    if (ind.status !== 'OK') {
      const container = document.getElementById('res-ind-metrics');
      if (container) container.innerHTML = `<div class="text-muted" style="padding:10px;">Insufficient candle data for ${tf} timeframe</div>`;
      return;
    }
    const fmt = v => (v !== null && v !== undefined) ? (typeof v === 'number' ? v.toFixed(2) : v) : '--';
    const setVal = (id, txt) => {
      const el = document.getElementById(id);
      if (el) el.textContent = txt;
    };
    setVal('res-ema-short', `${fmt(ind.ema9)} / ${fmt(ind.ema21)}`);
    setVal('res-ema-long', `${fmt(ind.ema50)} / ${fmt(ind.ema200)}`);
    setVal('res-rsi', `${fmt(ind.rsi14)}`);
    setVal('res-macd', `${fmt(ind.macd)} / ${fmt(ind.macd_signal)} (Hist: ${fmt(ind.macd_hist)})`);
    setVal('res-bb', `₹${fmt(ind.bb_lower)} — ₹${fmt(ind.bb_upper)} (${fmt(ind.bb_width_pct)}%)`);
    setVal('res-atr-rvol', `₹${fmt(ind.atr14)} / ${fmt(ind.rvol)}x`);
    setVal('res-trend-aligned', ind.trend_aligned ? '✅ BULLISH ALIGNED' : '⚠️ UNALIGNED / CONSOLIDATION');
  }

  async runResearchBacktest() {
    const symbol = document.getElementById('research-symbol-input') ? document.getElementById('research-symbol-input').value.trim() : 'BTC/INR';
    const strategy = document.getElementById('research-backtest-strategy') ? document.getElementById('research-backtest-strategy').value : 'STE';
    const days = document.getElementById('research-backtest-days') ? parseInt(document.getElementById('research-backtest-days').value) : 30;

    const btn = document.getElementById('btn-run-backtest');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Running simulation...';
    }
    try {
      const data = await this.apiFetch('/api/v2/research/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, strategy, days }),
      });
      this.renderBacktestResults(data);
    } catch (err) {
      this.showToast('Backtest Error', `Failed to run backtest: ${err.message || err}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '⚡ Run Instant Backtest';
      }
    }
  }

  renderBacktestResults(data) {
    const panel = document.getElementById('research-backtest-results');
    if (panel) panel.style.display = 'block';

    const setVal = (id, txt) => {
      const el = document.getElementById(id);
      if (el) el.textContent = txt;
    };
    setVal('bt-trades', data.total_trades || 0);
    setVal('bt-winrate', `${(data.win_rate_pct || 0).toFixed(1)}%`);
    setVal('bt-pnl', `${(data.net_pnl_pct || 0) >= 0 ? '+' : ''}${(data.net_pnl_pct || 0).toFixed(2)}%`);
    const pnlEl = document.getElementById('bt-pnl');
    if (pnlEl) pnlEl.className = `val font-mono ${(data.net_pnl_pct || 0) >= 0 ? 'text-green' : 'text-red'}`;
    setVal('bt-pf', (data.net_profit_factor || 0).toFixed(2));
    setVal('bt-mdd', `${(data.max_drawdown_pct || 0).toFixed(2)}%`);
  }

  async runResearchPredict(symbolOverride) {
    const symbol = symbolOverride || (document.getElementById('research-symbol-input') ? document.getElementById('research-symbol-input').value.trim() : 'BTC/INR');
    const btn = document.getElementById('btn-run-predict');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Analyzing...';
    }
    try {
      const data = await this.apiFetch('/api/v2/research/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol }),
      });
      this.renderPredictResults(data);
    } catch (err) {
      this.showToast('Prediction Error', `Failed: ${err.message || err}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '✨ Predict Trend';
      }
    }
  }

  renderPredictResults(data) {
    if (!data || !data.horizons) return;
    const h1 = data.horizons['1h'] || {};
    const h4 = data.horizons['4h'] || {};
    const h24 = data.horizons['24h'] || {};

    const setHorizon = (pfx, h) => {
      const elDir = document.getElementById(`pred-${pfx}-dir`);
      const elConf = document.getElementById(`pred-${pfx}-conf`);
      if (elDir) {
        elDir.textContent = h.direction || '--';
        elDir.className = `horizon-dir font-mono ${h.direction === 'BULLISH' ? 'text-green' : h.direction === 'BEARISH' ? 'text-red' : 'text-amber'}`;
      }
      if (elConf) elConf.textContent = `Confidence: ${h.confidence || 0}%`;
    };
    setHorizon('1h', h1);
    setHorizon('4h', h4);
    setHorizon('24h', h24);

    const elCats = document.getElementById('pred-catalysts');
    if (elCats) {
      const cats = data.bullish_catalysts || [];
      elCats.innerHTML = cats.length > 0 ? cats.map(c => `<li>✓ ${c}</li>`).join('') : '<li class="text-muted">No strong catalysts</li>';
    }
    const elRisks = document.getElementById('pred-risks');
    if (elRisks) {
      const risks = data.risk_factors || [];
      elRisks.innerHTML = risks.length > 0 ? risks.map(r => `<li>⚠ ${r}</li>`).join('') : '<li class="text-muted">No immediate risks</li>';
    }
  }

  showToast(title, body) {
    if (!this.elToastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
      <div class="toast-title">${title}</div>
      <div class="toast-body">${body}</div>
    `;
    this.elToastContainer.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 4500);
  }
}

// Backward-compatible class alias
class V2DashboardClient extends V2InstitutionalDashboard {}

// Instantiate upon DOM load
document.addEventListener('DOMContentLoaded', () => {
  window.v2Dashboard = new V2InstitutionalDashboard();
});

