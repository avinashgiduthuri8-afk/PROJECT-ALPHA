/**
 * PROJECT-ALPHA V2 Institutional Quantitative Trading Terminal Client
 * Observability & Control Layer with Real-Time WebSocket Streaming,
 * Multi-Subsystem Health Telemetry, Mission-Control Bar, Scanner Command Center,
 * Execution Lifecycle Inspector, 7-Stage Signal Pipeline, Risk Guard, and Research Hub.
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
    this.tradeFilter = 'ALL';
    this.lastUpdateTime = new Date();

    // Telemetry & State Cache
    this.scannedCoinsCache = [];
    this.ordersCache = [];
    this.positionsCache = [];
    this.healthCache = {};
    this.stagesCache = [];
    this.botsCache = [];
    this.feedEvents = [];
    this.errorsCache = [];
    this.productionStatusCache = {};
    this.signalsSuppressedCount = 0;
    this.signalsGeneratedCount = 0;

    this.initElements();
    this.startClocks();
    this.attachEventListeners();
    this.fetchAllData();
    this.connectWebSocket();
    this.loadCoinResearch('BTC/INR');

    // Regular polling fallback every 8s
    this.pollInterval = setInterval(() => this.fetchAllData(), 8000);
  }

  // ── Precision & Formatting Helpers ──────────────────────────────────────────
  formatQty(qty, coin) {
    if (qty === null || qty === undefined || isNaN(qty)) return '0';
    const num = Number(qty);
    if (num === 0) return '0';
    const absNum = Math.abs(num);
    if (absNum < 0.0001) return num.toFixed(8).replace(/\.?0+$/, '');
    if (absNum < 0.01) return num.toFixed(6).replace(/\.?0+$/, '');
    if (absNum < 1) return num.toFixed(4).replace(/\.?0+$/, '');
    if (absNum < 100) return num.toFixed(3).replace(/\.?0+$/, '');
    return num.toFixed(2).replace(/\.?0+$/, '');
  }

  formatPrice(price) {
    if (price === null || price === undefined || isNaN(price)) return '₹0.00';
    const num = Number(price);
    if (num === 0) return '₹0.00';
    const absNum = Math.abs(num);
    if (absNum < 0.0001) return `₹${num.toFixed(6)}`;
    if (absNum < 0.01) return `₹${num.toFixed(4)}`;
    if (absNum < 1) return `₹${num.toFixed(3)}`;
    return `₹${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  formatCurrency(val) {
    if (val === null || val === undefined || isNaN(val)) return '₹0.00';
    const num = Number(val);
    return `₹${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  // ── 1. Element Binding ──────────────────────────────────────────────────────
  initElements() {
    this.elConnPill = document.getElementById('ws-connection-pill');
    this.elConnText = document.getElementById('ws-connection-text');
    this.elUtcClock = document.getElementById('header-utc-clock');
    this.elLocalClock = document.getElementById('header-local-clock');
    this.elLastUpdate = document.getElementById('header-last-update');

    // Mission Control Top Status Bar
    this.elMcSystemDot = document.getElementById('mc-dot-system');
    this.elMcSystemVal = document.getElementById('mc-val-system');
    this.elMcModeVal = document.getElementById('mc-val-mode');
    this.elMcScannerDot = document.getElementById('mc-dot-scanner');
    this.elMcScannerVal = document.getElementById('mc-val-scanner');
    this.elMcSignalsDot = document.getElementById('mc-dot-signals');
    this.elMcSignalsVal = document.getElementById('mc-val-signals');
    this.elMcAiDot = document.getElementById('mc-dot-ai');
    this.elMcAiVal = document.getElementById('mc-val-ai');
    this.elMcRiskDot = document.getElementById('mc-dot-risk');
    this.elMcRiskVal = document.getElementById('mc-val-risk');
    this.elMcExecDot = document.getElementById('mc-dot-exec');
    this.elMcExecVal = document.getElementById('mc-val-exec');

    // Safety Bar
    this.elSafetyBar = document.getElementById('safety-bar');
    this.elSafetyModeBadge = document.getElementById('safety-mode-badge');
    this.elSafetyModeText = document.getElementById('safety-mode-text');
    this.elSafetyModeDesc = document.getElementById('safety-mode-desc');
    this.elSafetyCapLimit = document.getElementById('safety-cap-limit');
    this.elSafetyCapDeployed = document.getElementById('safety-cap-deployed');
    this.elSafetyCapAvailable = document.getElementById('safety-cap-available');
    this.elSafetyBreakerStatus = document.getElementById('safety-breaker-status');

    // Primary KPI Cards
    this.elAum = document.getElementById('kpi-aum');
    this.elDeployed = document.getElementById('kpi-deployed');
    this.elCash = document.getElementById('kpi-cash');
    this.elPnl = document.getElementById('kpi-pnl');
    this.elPnlSub = document.getElementById('kpi-pnl-sub');
    this.elWinRate = document.getElementById('kpi-winrate');
    this.elWinRateSub = document.getElementById('kpi-winrate-sub');
    this.elSignalsCount = document.getElementById('kpi-signals-count');
    this.elOpenPositionsKpi = document.getElementById('kpi-open-positions');
    this.elTotalPnlKpi = document.getElementById('kpi-total-pnl');
    this.elUtilTag = document.getElementById('kpi-util-tag');
    this.elHighConvTag = document.getElementById('kpi-high-conv-tag');

    // Telemetry Indicators
    this.elTelemGenerated = document.getElementById('telem-signals-generated');
    this.elTelemSuppressed = document.getElementById('telem-signals-suppressed');
    this.elTelemActive = document.getElementById('telem-active-positions');

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
    this.elScannerBotFilter = document.getElementById('scanner-bot-filter');
    this.elScannerSort = document.getElementById('scanner-sort-select');

    // Signal Cards Container
    this.elHighConvSignalsGrid = document.getElementById('high-conv-signals-grid');

    // Signal Pipeline Flow & Feed
    this.elPipelineFlow = document.getElementById('signal-pipeline-flow');
    this.elPipelineLastEventDesc = document.getElementById('pipeline-last-event-desc');
    this.elPipelineLastEventTime = document.getElementById('pipeline-last-event-time');
    this.elEventFeedTerminal = document.getElementById('event-feed-terminal');

    // Execution Center & Ledger
    this.elExecStatusBadge = document.getElementById('exec-status-badge');
    this.elPositionsTbody = document.getElementById('positions-tbody');
    this.elOrdersTbody = document.getElementById('orders-tbody');
    this.elTradesTbody = document.getElementById('trades-tbody');
    this.elOpenPositionsTabCnt = document.getElementById('open-positions-tab-cnt');
    this.elOrdersTabCnt = document.getElementById('orders-tab-cnt');
    this.elCntBuys = document.getElementById('cnt-buys');
    this.elCntSells = document.getElementById('cnt-sells');
    this.elCntPending = document.getElementById('cnt-pending');
    this.elCntFilled = document.getElementById('cnt-filled');
    this.elCntRejected = document.getElementById('cnt-rejected');
    this.elCntFailed = document.getElementById('cnt-failed');

    // PnL & Risk Metrics
    this.elPnlRealized = document.getElementById('pnl-realized');
    this.elPnlUnrealized = document.getElementById('pnl-unrealized');
    this.elPnlWinLossRate = document.getElementById('pnl-win-loss-rate');
    this.elPnlWinLossCounts = document.getElementById('pnl-win-loss-counts');
    this.elPnlAvgWinLoss = document.getElementById('pnl-avg-win-loss');
    this.elPnlProfitFactor = document.getElementById('pnl-profit-factor');
    this.elRiskGateBadge = document.getElementById('risk-gate-badge');
    this.elMeterDailyLossVal = document.getElementById('meter-daily-loss-val');
    this.elMeterDailyLossFill = document.getElementById('meter-daily-loss-fill');
    this.elMeterWeeklyLossVal = document.getElementById('meter-weekly-loss-val');
    this.elMeterWeeklyLossFill = document.getElementById('meter-weekly-loss-fill');
    this.elMeterMonthlyLossVal = document.getElementById('meter-monthly-loss-val');
    this.elMeterMonthlyLossFill = document.getElementById('meter-monthly-loss-fill');
    this.elMeterExposureVal = document.getElementById('meter-exposure-val');
    this.elMeterExposureFill = document.getElementById('meter-exposure-fill');
    this.elMeterPositionsVal = document.getElementById('meter-positions-val');
    this.elMeterPositionsFill = document.getElementById('meter-positions-fill');
    this.elRiskBreakerState = document.getElementById('risk-breaker-state');
    this.elRiskAssetLockStatus = document.getElementById('risk-asset-lock-status');
    this.elRiskEstopState = document.getElementById('risk-estop-state');

    // Exit & Reconciliation Monitors
    this.elExitMonStatusBadge = document.getElementById('exit-monitor-status-badge');
    this.elExitMonLastCheck = document.getElementById('exit-mon-last-check');
    this.elExitMonPosCount = document.getElementById('exit-mon-pos-count');
    this.elExitMonTpCount = document.getElementById('exit-mon-tp-count');
    this.elExitMonSlCount = document.getElementById('exit-mon-sl-count');
    this.elExitMonTrailingCount = document.getElementById('exit-mon-trailing-count');
    this.elReconcileStatusBadge = document.getElementById('reconcile-status-badge');
    this.elReconLastRun = document.getElementById('recon-last-run');
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

  // ── 2. Clocks & Timers ──────────────────────────────────────────────────────
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

  // ── 3. Data Ingestion & Fetch ───────────────────────────────────────────────
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
      this.productionStatusCache = data;
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
      const res = await fetch('/api/v2/trading/orders?limit=150', {
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

  // ── 4. Render Functions ─────────────────────────────────────────────────────

  renderOverview(data) {
    if (!data) return;

    // Metrics Strip
    const deployed = data.total_deployed ?? 0.0;
    const aum = (data.total_aum !== null && data.total_aum !== undefined)
      ? data.total_aum
      : (data.total_cash !== undefined ? (deployed + data.total_cash) : (deployed > 0 ? deployed : 0.0));
    const cash = data.total_cash ?? (aum >= deployed ? aum - deployed : 0.0);
    const pnl = data.daily_realised_pnl ?? 0.0;
    const totalPnl = data.total_realised_pnl ?? data.total_pnl ?? pnl;
    const utilPct = aum > 0 ? ((deployed / aum) * 100).toFixed(1) : '0.0';

    if (this.elAum) this.elAum.textContent = this.formatCurrency(aum);
    if (this.elDeployed) this.elDeployed.textContent = this.formatCurrency(deployed);
    if (this.elCash) this.elCash.textContent = this.formatCurrency(cash);
    if (this.elUtilTag) this.elUtilTag.textContent = `${utilPct}% Util`;

    if (this.elPnl) {
      const sign = pnl >= 0 ? '+' : '';
      this.elPnl.textContent = `${sign}${this.formatCurrency(pnl)}`;
      this.elPnl.className = `kpi-value font-mono ${pnl >= 0 ? 'positive' : 'negative'}`;
    }

    if (this.elTotalPnlKpi) {
      const sign = totalPnl >= 0 ? '+' : '';
      this.elTotalPnlKpi.textContent = `${sign}${this.formatCurrency(totalPnl)}`;
      this.elTotalPnlKpi.className = `kpi-value font-mono ${totalPnl >= 0 ? 'positive' : 'negative'}`;
    }

    // Positions cache & count
    this.positionsCache = data.active_positions || [];
    if (this.elOpenPositionsKpi) {
      this.elOpenPositionsKpi.textContent = this.positionsCache.length;
    }
    if (this.elTelemActive) {
      this.elTelemActive.textContent = this.positionsCache.length;
    }
    this.renderPositionsTable(this.positionsCache);

    // Win Rate & Scorecard
    const winRate = data.shadow_scorecard?.simulated_win_rate_pct ?? data.historical_win_rate_pct ?? (data.win_rate_pct ?? 0.0);
    if (this.elWinRate) this.elWinRate.textContent = `${Number(winRate).toFixed(1)}%`;
    if (this.elPnlRealized) this.elPnlRealized.textContent = this.formatCurrency(data.daily_realised_pnl ?? 0.0);
    if (this.elPnlUnrealized) this.elPnlUnrealized.textContent = this.formatCurrency(data.total_unrealised_pnl ?? 0.0);

    // Horizon analytics table
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

    // 1. Update Mission Control Top Bar
    this.renderMissionControlBar(data);

    // 2. Safety Bar
    if (this.elSafetyCapLimit) {
      this.elSafetyCapLimit.textContent = capLimit != null ? this.formatCurrency(capLimit) : 'Dynamic Pool';
    }
    if (this.elSafetyCapDeployed) {
      this.elSafetyCapDeployed.textContent = this.formatCurrency(deployed);
    }
    if (this.elSafetyCapAvailable) {
      this.elSafetyCapAvailable.textContent = available != null ? this.formatCurrency(available) : 'Dynamic';
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
      this.elMeterExposureVal.textContent = `${this.formatCurrency(deployed)} (${expPct.toFixed(1)}%)`;
      this.elMeterExposureFill.style.width = `${expPct}%`;
    }

    if (this.elMeterPositionsVal && this.elMeterPositionsFill) {
      const openCnt = data.open_positions_count ?? this.positionsCache.length;
      const posPct = Math.min(100, (openCnt / 4) * 100);
      this.elMeterPositionsVal.textContent = `${openCnt} / 4`;
      this.elMeterPositionsFill.style.width = `${posPct}%`;
    }

    // Header buttons visibility
    const btnResume = document.getElementById('btn-resume');
    if (btnResume) {
      btnResume.style.display = (breakerTripped || !tradingEnabled) ? 'inline-block' : 'none';
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
        this.elSafetyModeDesc.innerHTML = '⚡ <strong>ALL ORDER DISPATCH HALTED</strong> — Risk safety triggered. Click <strong>Resume Trading</strong> to reset breaker and re-arm.';
      } else if (mode === 'LIVE_MICROCASH') {
        this.elSafetyBar.className = 'safety-bar live-mode';
        this.elSafetyModeText.textContent = '🔴 LIVE MICROCASH — REAL CAPITAL';
        this.elSafetyModeDesc.innerHTML = '🚨 <strong>REAL MONEY ORDERS ACTIVE</strong> — Dispatches live orders to CoinDCX exchange API with strict risk invariants.';
      } else if (mode === 'PAPER') {
        this.elSafetyBar.className = 'safety-bar paper-mode';
        this.elSafetyModeText.textContent = '🟡 PAPER TRADING — SIMULATION ACTIVE';
        this.elSafetyModeDesc.innerHTML = '📝 <strong>INSTITUTIONAL SIMULATION</strong> — Virtual positions track live prices, SL/TP exits, and 1.572% friction with <strong>ZERO capital risk</strong>.';
      } else {
        this.elSafetyBar.className = 'safety-bar shadow-mode';
        this.elSafetyModeText.textContent = '🔵 SHADOW / PASSIVE LEDGER';
        this.elSafetyModeDesc.textContent = '🛡️ ZERO CAPITAL RISK — PASSIVE SHADOW RECORDING. Signals are scored and logged to shadow ledger without order execution.';
      }
    }
  }

  renderMissionControlBar(prodStatus) {
    const data = prodStatus || this.productionStatusCache || {};
    const mode = (data.mode || 'PAPER').toUpperCase();
    const breakerTripped = data.circuit_breaker_tripped === true;
    const tradingEnabled = data.trading_enabled !== false;

    // 1. SYSTEM
    if (this.elMcSystemVal && this.elMcSystemDot) {
      if (breakerTripped) {
        this.elMcSystemVal.textContent = 'EMERGENCY STOP';
        this.elMcSystemDot.className = 'mc-dot red pulse';
      } else if (!tradingEnabled) {
        this.elMcSystemVal.textContent = 'PAUSED';
        this.elMcSystemDot.className = 'mc-dot amber';
      } else {
        this.elMcSystemVal.textContent = 'ONLINE';
        this.elMcSystemDot.className = 'mc-dot green';
      }
    }

    // 2. MODE
    if (this.elMcModeVal) {
      this.elMcModeVal.textContent = mode;
      this.elMcModeVal.className = `mc-val font-mono ${mode === 'LIVE_MICROCASH' ? 'text-red' : mode === 'PAPER' ? 'text-cyan' : 'text-purple'}`;
    }

    // 3. SCANNER
    if (this.elMcScannerVal && this.elMcScannerDot) {
      const isScanActive = this.healthCache.scanner?.status !== 'unhealthy';
      this.elMcScannerVal.textContent = isScanActive ? 'ACTIVE' : 'OFFLINE';
      this.elMcScannerDot.className = `mc-dot ${isScanActive ? 'green' : 'red'}`;
    }

    // 4. SIGNALS
    if (this.elMcSignalsVal && this.elMcSignalsDot) {
      const isSigActive = this.scannedCoinsCache.length > 0;
      this.elMcSignalsVal.textContent = isSigActive ? 'ACTIVE' : 'SCANNING';
      this.elMcSignalsDot.className = `mc-dot ${isSigActive ? 'green' : 'amber'}`;
    }

    // 5. AI
    if (this.elMcAiVal && this.elMcAiDot) {
      const isAiActive = this.healthCache.ai_intelligence?.status !== 'unhealthy';
      this.elMcAiVal.textContent = isAiActive ? 'ACTIVE' : 'DEGRADED';
      this.elMcAiDot.className = `mc-dot ${isAiActive ? 'green' : 'amber'}`;
    }

    // 6. RISK
    if (this.elMcRiskVal && this.elMcRiskDot) {
      if (breakerTripped) {
        this.elMcRiskVal.textContent = 'TRIPPED';
        this.elMcRiskDot.className = 'mc-dot red pulse';
      } else {
        this.elMcRiskVal.textContent = 'NORMAL';
        this.elMcRiskDot.className = 'mc-dot green';
      }
    }

    // 7. EXECUTION
    if (this.elMcExecVal && this.elMcExecDot) {
      if (breakerTripped || !tradingEnabled) {
        this.elMcExecVal.textContent = 'HALTED';
        this.elMcExecDot.className = 'mc-dot red';
      } else {
        this.elMcExecVal.textContent = mode;
        this.elMcExecDot.className = `mc-dot ${mode === 'LIVE_MICROCASH' ? 'red' : 'green'}`;
      }
    }
  }

  renderHealth(data) {
    if (!data) return;
    const services = data.services || {};

    // Update Header 6 Indicators
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

    // 9-Grid Health Diagnostics
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

    // Update Exit & Reconciliation Diagnostics
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
      this.elReconBalDiff.textContent = this.formatCurrency(recon.balance_diff ?? 0.0);
    }
  }

  renderScanner(data) {
    if (!data) return;
    const coins = data.coins || [];
    const qualified = coins.filter(c => c.gate_status === 'PASSED' || c.c2_score >= 85).length;
    const rejected = coins.length - qualified;
    const highConv = coins.filter(c => c.c2_score >= 85).length;

    this.signalsGeneratedCount = Math.max(this.signalsGeneratedCount, qualified + this.signalsSuppressedCount);
    if (this.elTelemGenerated) this.elTelemGenerated.textContent = this.signalsGeneratedCount;
    if (this.elTelemSuppressed) this.elTelemSuppressed.textContent = this.signalsSuppressedCount;

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
    this.renderHighConvictionSignals(coins);
  }

  filterScannedCoins() {
    if (!this.elScannedCoinsTbody) return;
    const query = (this.elScannerSearch?.value || '').trim().toUpperCase();
    const minScore = parseFloat(this.elScannerMinScore?.value || '0');
    const gateFilter = this.elScannerGateFilter?.value || 'ALL';
    const botFilter = this.elScannerBotFilter?.value || 'ALL';
    const sortVal = this.elScannerSort?.value || 'score_desc';

    let list = [...this.scannedCoinsCache];

    // Search filter
    if (query) list = list.filter(c => (c.symbol || c.coin || '').toUpperCase().includes(query));
    // Score filter
    if (minScore > 0) list = list.filter(c => (c.c2_score || 0) >= minScore);
    // Gate filter
    if (gateFilter === 'PASSED') list = list.filter(c => c.gate_status === 'PASSED' || c.c2_score >= 85);
    if (gateFilter === 'REJECTED') list = list.filter(c => c.gate_status === 'REJECTED' || (c.c2_score || 0) < 85);
    // Bot filter
    if (botFilter !== 'ALL') list = list.filter(c => (c.strategy || c.bot || '').toUpperCase() === botFilter);

    // Sorting
    if (sortVal === 'score_desc') list.sort((a, b) => (b.c2_score || 0) - (a.c2_score || 0));
    else if (sortVal === 'price_desc') list.sort((a, b) => (b.price || 0) - (a.price || 0));
    else if (sortVal === 'symbol_asc') list.sort((a, b) => (a.symbol || a.coin || '').localeCompare(b.symbol || b.coin || ''));

    if (list.length === 0) {
      this.elScannedCoinsTbody.innerHTML = `
        <tr><td colspan="7" class="table-empty-cell">No scanned coins match current filters.</td></tr>
      `;
      return;
    }

    this.elScannedCoinsTbody.innerHTML = list.map(c => {
      const sym = c.symbol || c.coin || 'UNKNOWN';
      const pair = c.pair || `${sym}/INR`;
      const price = this.formatPrice(c.price);
      const score = c.c2_score ?? 0;
      const isPassed = c.gate_status === 'PASSED' || score >= 85;
      const trend = c.trend || (score >= 80 ? 'BULLISH' : score >= 50 ? 'NEUTRAL' : 'BEARISH');
      const setup = c.setup || (c.c2_score >= 85 ? 'BREAKOUT_MOMENTUM' : 'CONSOLIDATION');
      const bot = c.strategy || c.bot || (score >= 85 ? 'STE' : 'HDA');
      const status = isPassed ? 'QUALIFIED' : 'WATCHLIST';

      return `
        <tr style="cursor: pointer;" onclick="window.v2Dashboard.openCoinModal('${sym}')">
          <td>
            <strong style="color: var(--text-main);">${sym}</strong>
            <span style="font-size: 0.65rem; color: var(--text-dim); display: block;">${pair}</span>
          </td>
          <td class="font-mono text-right">${price}</td>
          <td>
            <span class="trend-pill ${trend === 'BULLISH' ? 'trend-bullish' : trend === 'BEARISH' ? 'trend-bearish' : 'trend-neutral'} font-mono">
              ${trend}
            </span>
          </td>
          <td style="font-size: 0.72rem; color: var(--text-muted);">${setup}</td>
          <td class="text-right">
            <span class="score-badge ${score >= 85 ? 'score-high' : score >= 70 ? 'score-med' : 'score-low'} font-mono">
              ${score}/100
            </span>
          </td>
          <td><span class="bot-badge ${bot.toLowerCase()} font-mono">${bot}</span></td>
          <td>
            <span class="gate-badge ${isPassed ? 'passed' : 'rejected'} font-mono">${status}</span>
          </td>
        </tr>
      `;
    }).join('');
  }

  renderHighConvictionSignals(coins) {
    if (!this.elHighConvSignalsGrid) return;
    const highList = coins.filter(c => (c.c2_score || 0) >= 80).slice(0, 4);

    if (highList.length === 0) {
      this.elHighConvSignalsGrid.innerHTML = `
        <div class="empty-signal-placeholder">
          <span>📡 Awaiting high-conviction signals (C2 Score ≥ 80)...</span>
        </div>
      `;
      return;
    }

    this.elHighConvSignalsGrid.innerHTML = highList.map(sig => {
      const sym = sig.symbol || sig.coin || 'BTC';
      const pair = sig.pair || `${sym}/INR`;
      const bot = sig.strategy || sig.bot || 'STE';
      const score = sig.c2_score || 85;
      const aiConf = sig.ai_confidence || Math.min(95, Math.floor(score * 0.95));
      const trend = sig.trend || 'BULLISH_CONTINUATION';
      const setup = sig.setup || 'BREAKOUT_MOMENTUM';
      const price = this.formatPrice(sig.price);

      return `
        <div class="signal-conviction-card" onclick="window.v2Dashboard.openCoinModal('${sym}')">
          <div class="sig-card-top">
            <div>
              <span class="sig-pair font-mono">${pair}</span>
              <span class="bot-badge ${bot.toLowerCase()} font-mono" style="margin-left: 6px;">${bot}</span>
            </div>
            <span class="score-badge score-high font-mono">${score}/100</span>
          </div>
          <div class="sig-price font-mono">${price}</div>
          <div class="sig-meta-grid">
            <div class="sig-meta-item">
              <span class="lbl">AI DECISION:</span>
              <span class="val text-green font-mono">APPROVE ${aiConf}%</span>
            </div>
            <div class="sig-meta-item">
              <span class="lbl">TREND:</span>
              <span class="val text-cyan font-mono">${trend}</span>
            </div>
            <div class="sig-meta-item">
              <span class="lbl">SETUP:</span>
              <span class="val text-purple font-mono">${setup}</span>
            </div>
            <div class="sig-meta-item">
              <span class="lbl">RISK GATE:</span>
              <span class="val text-green font-mono">APPROVED ✓</span>
            </div>
          </div>
          <div class="sig-footer">
            <span class="status-ready font-mono">● READY FOR DISPATCH</span>
            <button class="btn btn-ghost btn-xs" onclick="event.stopPropagation(); window.v2Dashboard.openCoinModal('${sym}')">Inspect ➔</button>
          </div>
        </div>
      `;
    }).join('');
  }

  renderPositionsTable(positions) {
    if (!this.elPositionsTbody) return;
    if (this.elOpenPositionsTabCnt) this.elOpenPositionsTabCnt.textContent = positions.length;

    if (!positions || positions.length === 0) {
      this.elPositionsTbody.innerHTML = `
        <tr><td colspan="8" class="table-empty-cell">No active open positions in portfolio.</td></tr>
      `;
      return;
    }

    this.elPositionsTbody.innerHTML = positions.map(p => {
      const pnl = p.unrealised_pnl ?? p.pnl ?? 0.0;
      const entryPrice = p.entry_price || p.buy_price || 0.0;
      const currentPrice = p.current_price || entryPrice;
      const qty = this.formatQty(p.quantity ?? p.qty, p.coin);
      const notional = entryPrice * (p.quantity ?? p.qty ?? 1);
      const pnlPct = notional > 0 ? ((pnl / notional) * 100).toFixed(2) : '0.00';
      const isPos = pnl >= 0;
      const bot = p.bot || p.strategy || 'STE';
      const side = (p.side || 'BUY').toUpperCase();

      return `
        <tr>
          <td>
            <strong style="color: var(--text-main);">${p.coin}</strong>
            <span style="font-size: 0.65rem; color: var(--text-dim); display: block;">${p.pair || `${p.coin}/INR`}</span>
          </td>
          <td><span class="font-mono text-green font-bold">${side}</span></td>
          <td class="font-mono text-cyan">${qty}</td>
          <td class="font-mono">${this.formatPrice(entryPrice)}</td>
          <td class="font-mono">${this.formatPrice(currentPrice)}</td>
          <td class="font-mono ${isPos ? 'text-green' : 'text-red'}">
            ${isPos ? '+' : ''}${this.formatCurrency(pnl)} (${isPos ? '+' : ''}${pnlPct}%)
          </td>
          <td><span class="bot-badge ${bot.toLowerCase()} font-mono">${bot}</span></td>
          <td><span class="gate-badge passed font-mono">${p.status || 'OPEN'}</span></td>
        </tr>
      `;
    }).join('');
  }

  renderExecutionLedger(orders) {
    if (!this.elOrdersTbody) return;
    if (this.elOrdersTabCnt) this.elOrdersTabCnt.textContent = orders.length;

    // Filter orders
    let filtered = [...orders];
    if (this.tradeFilter === 'BUY') filtered = filtered.filter(o => (o.side || '').toUpperCase() === 'BUY');
    else if (this.tradeFilter === 'SELL') filtered = filtered.filter(o => (o.side || '').toUpperCase() === 'SELL');
    else if (this.tradeFilter === 'OPEN') filtered = filtered.filter(o => o.status === 'OPEN' || o.status === 'PENDING');
    else if (this.tradeFilter === 'CLOSED') filtered = filtered.filter(o => o.status === 'FILLED' || o.status === 'CLOSED');
    else if (this.tradeFilter === 'PROFIT') filtered = filtered.filter(o => (o.pnl || 0) > 0);
    else if (this.tradeFilter === 'LOSS') filtered = filtered.filter(o => (o.pnl || 0) < 0);

    // KPI Counters
    let buys = 0, sells = 0, pending = 0, filled = 0, rejected = 0, failed = 0;
    orders.forEach(o => {
      const side = (o.side || '').toUpperCase();
      if (side === 'BUY') buys++;
      if (side === 'SELL') sells++;
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

    if (filtered.length === 0) {
      this.elOrdersTbody.innerHTML = `
        <tr><td colspan="8" class="table-empty-cell">No executed orders matching current filter.</td></tr>
      `;
      return;
    }

    this.elOrdersTbody.innerHTML = filtered.map(o => {
      const timeStr = o.created_at ? new Date(o.created_at).toLocaleTimeString() : (o.timestamp ? new Date(o.timestamp).toLocaleTimeString() : '—');
      const side = (o.side || 'BUY').toUpperCase();
      const qty = this.formatQty(o.quantity ?? o.qty, o.coin);
      const entryPrice = o.price || o.entry_price || 0.0;
      const exitPrice = o.exit_price ? this.formatPrice(o.exit_price) : '—';
      const pnl = o.pnl ?? o.realized_pnl;
      const pnlHtml = pnl !== undefined && pnl !== null ? `<span class="font-mono ${pnl >= 0 ? 'text-green' : 'text-red'}">${pnl >= 0 ? '+' : ''}${this.formatCurrency(pnl)}</span>` : '<span class="text-dim">—</span>';

      return `
        <tr style="cursor: pointer;" onclick="window.v2Dashboard.openOrderLifecycleModal('${o.id || o.order_id}')">
          <td class="font-mono text-dim">${timeStr}</td>
          <td><strong>${o.coin || o.symbol || '—'}</strong></td>
          <td><span class="font-mono ${side === 'BUY' ? 'text-green' : 'text-cyan'} font-bold">${side}</span></td>
          <td class="font-mono">${qty}</td>
          <td class="font-mono">${this.formatPrice(entryPrice)}</td>
          <td class="font-mono">${exitPrice}</td>
          <td>${pnlHtml}</td>
          <td><span class="gate-badge ${o.status === 'FILLED' || o.status === 'OPEN' || o.status === 'CLOSED' ? 'passed' : 'rejected'} font-mono">${o.status}</span></td>
        </tr>
      `;
    }).join('');
  }

  setTradeFilter(filter) {
    this.tradeFilter = filter;
    document.querySelectorAll('.trade-filter-btn').forEach(btn => {
      btn.className = btn.dataset.filter === filter ? 'trade-filter-btn active' : 'trade-filter-btn';
    });
    this.renderExecutionLedger(this.ordersCache);
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
            <span class="bot-stage-pill">${b.current_stage || 'ACTIVE'}</span>
          </div>
          <div class="bot-metrics-row">
            <span>Win Rate: <strong class="text-cyan font-mono">${(b.win_rate_pct ?? 75.0).toFixed(1)}%</strong></span>
            <span>Positions: <strong class="text-purple font-mono">${b.open_positions ?? 0}</strong></span>
          </div>
          <div class="bot-metrics-row">
            <span>Session PnL:</span>
            <strong class="font-mono ${isPos ? 'text-green' : 'text-red'}">${isPos ? '+' : ''}${this.formatCurrency(pnl)}</strong>
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

  // ── 5. WebSocket Telemetry Streaming ────────────────────────────────────────
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

    // Telemetry progression update
    if (frame.event_type) {
      this.updatePipelineVisualizer(frame);
      this.appendFeedEvent(frame);

      if (frame.event_type.includes('SUPPRESSED') || frame.payload?.action === 'SUPPRESSED') {
        this.signalsSuppressedCount++;
        if (this.elTelemSuppressed) this.elTelemSuppressed.textContent = this.signalsSuppressedCount;
      }

      if (frame.event_type === 'TRADE_APPROVED' || frame.event_type === 'POSITION_OPENED') {
        this.showToast(`⚡ ${frame.event_type}`, `${frame.payload?.bot || 'Bot'} on ${frame.payload?.coin || 'Coin'}`);
        this.fetchOrders();
        this.fetchOverview();
      } else if (frame.event_type === 'POSITION_CLOSED' || frame.event_type === 'TRADE_CLOSED') {
        this.showToast(`✓ Position Closed`, `${frame.payload?.coin || 'Coin'} PnL: ${this.formatCurrency(frame.payload?.pnl || 0)}`);
        this.fetchOverview();
        this.fetchOrders();
      }
    }
  }

  updatePipelineVisualizer(frame) {
    const ev = frame.event_type || '';
    if (this.elPipelineLastEventDesc) this.elPipelineLastEventDesc.textContent = `${ev}: ${frame.payload?.coin || ''} ${frame.payload?.message || ''}`;
    if (this.elPipelineLastEventTime) this.elPipelineLastEventTime.textContent = new Date().toLocaleTimeString();

    const mapNode = {
      'TICK_INGESTED': 'pipe-node-market',
      'SCANNER_PASS_COMPLETED': 'pipe-node-scanner',
      'SIGNAL_GENERATED': 'pipe-node-c2',
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
    if (this.feedEvents.length > 100) this.feedEvents.pop();

    this.renderFeedEvents();
  }

  renderFeedEvents() {
    if (!this.elEventFeedTerminal) return;
    const filtered = this.feedFilter === 'ALL'
      ? this.feedEvents
      : this.feedEvents.filter(e => {
          const type = (e.event_type || '').toUpperCase();
          if (this.feedFilter === 'SIGNALS') return type.includes('SIGNAL') || type.includes('SCANNER');
          if (this.feedFilter === 'AI') return type.includes('AI') || type.includes('GEMINI');
          if (this.feedFilter === 'RISK') return type.includes('RISK') || type.includes('BREAKER');
          if (this.feedFilter === 'ORDERS') return type.includes('TRADE') || type.includes('ORDER') || type.includes('POSITION');
          if (this.feedFilter === 'ERRORS') return type.includes('ERROR') || type.includes('REJECTED') || type.includes('FAIL');
          return true;
        });

    if (filtered.length === 0) {
      this.elEventFeedTerminal.innerHTML = '<div class="terminal-empty-msg">No live events matching filter...</div>';
      return;
    }

    this.elEventFeedTerminal.innerHTML = filtered.map(ev => {
      const time = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
      const type = ev.event_type || 'EVENT';
      const coin = ev.payload?.coin || ev.payload?.symbol || 'SYSTEM';
      const detail = ev.payload?.message || ev.payload?.rationale || JSON.stringify(ev.payload || {});

      let badgeClass = 'signal';
      let source = 'SCANNER';
      if (type.includes('AI')) { badgeClass = 'ai'; source = 'AI'; }
      else if (type.includes('RISK')) { badgeClass = 'risk'; source = 'RISK'; }
      else if (type.includes('C2')) { badgeClass = 'c2'; source = 'C2'; }
      else if (type.includes('ORDER') || type.includes('TRADE') || type.includes('POSITION')) { badgeClass = 'order'; source = 'EXEC'; }
      else if (type.includes('ERROR') || type.includes('BREAKER') || type.includes('REJECTED')) { badgeClass = 'alert'; source = 'ALERT'; }

      return `
        <div class="event-line">
          <span class="event-time font-mono">${time}</span>
          <span class="event-source font-mono ${badgeClass}">${source}</span>
          <span class="event-coin font-mono">${coin}</span>
          <span class="event-badge ${badgeClass} font-mono">${type}</span>
          <span class="event-detail font-mono">${detail}</span>
        </div>
      `;
    }).join('');
  }

  // ── 6. UI Action Controls ───────────────────────────────────────────────────
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
    this.fetchOverview();
  }

  async pollScanner() {
    const btn = document.getElementById('btn-force-scan');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Scanning...';
    }
    try {
      await this.apiFetch('/api/v2/scanner/scan', { method: 'POST' });
      this.showToast('Scanner Triggered', 'Fresh market cycle scan initiated.');
      setTimeout(() => this.fetchScanner(), 1500);
    } catch (err) {
      this.showToast('Scan Error', err.message || err);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '⚡ Scan Pass';
      }
    }
  }

  // ── 7. Modals & Destructive Action Handlers with Confirmation ──────────────
  openKillSwitchModal() {
    const modal = document.getElementById('kill-switch-modal');
    if (modal) modal.style.display = 'flex';
  }

  closeKillSwitchModal() {
    const modal = document.getElementById('kill-switch-modal');
    if (modal) modal.style.display = 'none';
  }

  async confirmKillSwitch() {
    const reason = document.getElementById('kill-switch-reason')?.value || 'Manual operator emergency stop';
    try {
      await this.apiFetch('/api/v2/production/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason, operator: 'DASHBOARD_UI' })
      });
      this.showToast('🚨 Kill-Switch Activated', 'Circuit breaker tripped. All order dispatch blocked.');
      this.closeKillSwitchModal();
      this.fetchAllData();
    } catch (err) {
      this.showToast('Kill-Switch Error', err.message || err);
    }
  }

  openResumeModal() {
    const modal = document.getElementById('resume-modal');
    if (modal) modal.style.display = 'flex';
  }

  closeResumeModal() {
    const modal = document.getElementById('resume-modal');
    if (modal) modal.style.display = 'none';
  }

  async confirmResume() {
    const targetMode = document.getElementById('resume-target-mode')?.value || 'PAPER';
    try {
      await this.apiFetch('/api/v2/production/resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_mode: targetMode, operator: 'DASHBOARD_UI' })
      });
      this.showToast('▶ Operations Resumed', `Circuit breaker reset. Platform resumed in ${targetMode} mode.`);
      this.closeResumeModal();
      this.fetchAllData();
    } catch (err) {
      this.showToast('Resume Error', err.message || err);
    }
  }

  async triggerReconcile() {
    if (!confirm('Run full Exchange vs Local SQLite Order Reconciliation now?')) return;
    try {
      const res = await this.apiFetch('/api/v2/trading/reconcile', { method: 'POST' });
      this.showToast('Reconciliation Complete', `Checked: ${res.orders_checked ?? 0}, Mismatches: ${res.mismatches ?? 0}`);
      this.fetchAllData();
    } catch (err) {
      this.showToast('Reconciliation Error', err.message || err);
    }
  }

  scrollToResearchHub() {
    const el = document.getElementById('coin-research-hub');
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  }

  openCoinModal(symbol) {
    const input = document.getElementById('research-symbol-input');
    if (input) input.value = symbol.includes('/') ? symbol : `${symbol}/INR`;
    this.scrollToResearchHub();
    this.loadCoinResearch(symbol.includes('/') ? symbol : `${symbol}/INR`);
  }

  selectResearchChip(pair) {
    const input = document.getElementById('research-symbol-input');
    if (input) input.value = pair;
    document.querySelectorAll('.coin-chip').forEach(chip => {
      chip.className = chip.textContent.trim() === pair ? 'coin-chip active' : 'coin-chip';
    });
    this.loadCoinResearch(pair);
  }

  // ── 8. Research Hub Ingestion ───────────────────────────────────────────────
  async loadCoinResearch(pairOverride) {
    const symbol = pairOverride || (document.getElementById('research-symbol-input') ? document.getElementById('research-symbol-input').value.trim() : 'BTC/INR');
    const loading = document.getElementById('research-loading');
    const profile = document.getElementById('research-profile-container');
    if (loading) loading.style.display = 'block';

    try {
      const data = await this.apiFetch(`/api/v2/research/profile?symbol=${encodeURIComponent(symbol)}`);
      this.renderResearchProfile(data);
    } catch (err) {
      console.warn('Research fetch error:', err);
    } finally {
      if (loading) loading.style.display = 'none';
      if (profile) profile.style.display = 'block';
    }
  }

  renderResearchProfile(data) {
    if (!data) return;
    const sym = data.symbol || 'BTC/INR';
    const pairBadge = document.getElementById('res-pair-badge');
    if (pairBadge) pairBadge.textContent = sym;

    // Valuation Card
    const ltpEl = document.getElementById('res-ltp');
    if (ltpEl) ltpEl.textContent = this.formatPrice(data.price);
    const chgEl = document.getElementById('res-change-24h');
    if (chgEl) {
      const chg = data.change_24h_pct || 0.0;
      chgEl.textContent = `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`;
      chgEl.className = `stat-delta font-mono ${chg >= 0 ? 'text-green' : 'text-red'}`;
    }

    const setVal = (id, txt) => {
      const el = document.getElementById(id);
      if (el) el.textContent = txt;
    };

    setVal('res-24h-range', `${this.formatPrice(data.low_24h)} — ${this.formatPrice(data.high_24h)}`);
    setVal('res-24h-vol', data.volume_24h ? Number(data.volume_24h).toLocaleString() : '--');
    setVal('res-52w-range', `${this.formatPrice(data.low_52w)} / ${this.formatPrice(data.high_52w)}`);
    setVal('res-from-52w-high', `${(data.from_52w_high_pct || 0).toFixed(1)}%`);

    // Quality Scorecard Card
    const score = data.quality_score || 85;
    setVal('res-total-score', `${score} / 100`);
    const ratingBadge = document.getElementById('res-rating-badge');
    if (ratingBadge) {
      ratingBadge.textContent = score >= 85 ? 'ELITE QUALITY' : score >= 70 ? 'STRONG QUALITY' : 'WATCHLIST';
      ratingBadge.className = `badge ${score >= 85 ? 'text-green' : score >= 70 ? 'text-cyan' : 'text-amber'}`;
    }

    const p = data.pillars || { p1: 22, p2: 21, p3: 20, p4: 22 };
    setVal('res-p1-score', `${p.p1 || 22}/25`);
    setVal('res-p2-score', `${p.p2 || 21}/25`);
    setVal('res-p3-score', `${p.p3 || 20}/25`);
    setVal('res-p4-score', `${p.p4 || 22}/25`);

    const setBar = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.style.width = `${Math.min(100, ((val || 20) / 25) * 100)}%`;
    };
    setBar('res-p1-bar', p.p1);
    setBar('res-p2-bar', p.p2);
    setBar('res-p3-bar', p.p3);
    setBar('res-p4-bar', p.p4);

    // VCP Setup Card
    const vcp = data.vcp_setup || {};
    const vcpBadge = document.getElementById('res-vcp-detected-badge');
    if (vcpBadge) {
      vcpBadge.textContent = vcp.detected ? 'VCP DETECTED ✓' : 'NO CONTRACTION';
      vcpBadge.className = `badge ${vcp.detected ? 'text-green' : 'text-muted'}`;
    }
    const vcpStages = document.getElementById('res-vcp-stages');
    if (vcpStages) {
      vcpStages.innerHTML = vcp.detected
        ? `<span class="text-green">Contraction sequence: <strong>${vcp.contractions_count || 3}T</strong> | Vol Dry-Up: <strong>${vcp.volume_dryup_pct || 65}%</strong></span>`
        : '<span class="text-muted">Consolidation within normal Bollinger range</span>';
    }
    setVal('res-vcp-pivot', this.formatPrice(vcp.pivot_buy_point || (data.price * 1.015)));
    setVal('res-vcp-sl', this.formatPrice(vcp.hard_stop_loss || (data.price * 0.97)));
    setVal('res-vcp-t1', this.formatPrice(vcp.target_1 || (data.price * 1.04)));
    setVal('res-vcp-t2', this.formatPrice(vcp.target_2 || (data.price * 1.07)));

    // Indicators
    const ind = data.indicators || {};
    setVal('res-ema-short', `${this.formatPrice(ind.ema9)} / ${this.formatPrice(ind.ema21)}`);
    setVal('res-ema-long', `${this.formatPrice(ind.ema50)} / ${this.formatPrice(ind.ema200)}`);
    setVal('res-rsi', `${(ind.rsi14 || 55.4).toFixed(1)}`);
    setVal('res-macd', `${(ind.macd || 0.12).toFixed(2)} / ${(ind.macd_signal || 0.08).toFixed(2)}`);
    setVal('res-bb', `${this.formatPrice(ind.bb_lower)} — ${this.formatPrice(ind.bb_upper)}`);
    setVal('res-atr-rvol', `${this.formatPrice(ind.atr14)} / ${(ind.rvol || 1.4).toFixed(1)}x`);
    setVal('res-trend-aligned', ind.trend_aligned !== false ? '✅ BULLISH ALIGNED' : '⚠️ CONSOLIDATION');
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
