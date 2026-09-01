/**
 * PROJECT-ALPHA V2 Mission Control Dashboard Client
 * Real-time WebSocket streaming with auto-reconnect, 14-stage autonomous pipeline, and REST fallback.
 */

class V2DashboardClient {
  constructor() {
    const urlParams = new URLSearchParams(window.location.search);
    this.apiKey = urlParams.get("api_key") || localStorage.getItem("v2_api_key") || "alpha-dev-key";
    localStorage.setItem("v2_api_key", this.apiKey);
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.pollInterval = null;
    this.stagesCache = [];

    this.initElements();
    this.attachEventListeners();
    this.fetchInitialState();
    this.connectWebSocket();

    // Fallback polling every 15s in case of WS disconnect or static initial state
    this.pollInterval = setInterval(() => this.fetchInitialState(), 15000);
  }

  initElements() {
    this.elConnPill = document.getElementById("ws-connection-pill");
    this.elConnText = document.getElementById("ws-connection-text");

    // KPI elements
    this.elAum = document.getElementById("kpi-aum");
    this.elDeployed = document.getElementById("kpi-deployed");
    this.elCash = document.getElementById("kpi-cash");
    this.elPnl = document.getElementById("kpi-pnl");
    this.elUtil = document.getElementById("kpi-util");

    // Pipeline elements
    this.elPipelineGrid = document.getElementById("pipeline-stages-grid");

    // Bot status panel
    this.elBotGrid = document.getElementById("bot-status-grid");
    this.botsCache = [];

    // Section elements
    this.elAiFeed = document.getElementById("ai-feed");
    this.elPositionsTbody = document.getElementById("positions-tbody");
    this.elScannedCoinsTbody = document.getElementById("scanned-coins-tbody");
    this.elWatchlistBadge = document.getElementById("watchlist-count-badge");
    this.scannedCoinsCache = [];
    this.elEventStream = document.getElementById("event-stream");
    this.elHealthMatrix = document.getElementById("health-matrix");
    this.elToastContainer = document.getElementById("toast-container");

    // Shadow & Risk elements
    this.elShadowWinRate = document.getElementById("shadow-win-rate");
    this.elShadowPnl = document.getElementById("shadow-pnl");
    this.elShadowCount = document.getElementById("shadow-divergences-count");
    this.elDivergenceLogs = document.getElementById("divergence-logs");
    this.elBreakerStatus = document.getElementById("risk-breaker-status");

    // Modal elements
    this.elStageModal = document.getElementById("stage-modal");
    this.elModalClose = document.getElementById("modal-close-btn");
    this.elModalTitle = document.getElementById("modal-stage-title");
    this.elModalSubtitle = document.getElementById("modal-stage-subtitle");
    this.elModalIcon = document.getElementById("modal-stage-icon");
    this.elModalDesc = document.getElementById("modal-stage-description");
    this.elModalMetricsGrid = document.getElementById("modal-metrics-grid");
    this.elModalInputContract = document.getElementById("modal-input-contract");
    this.elModalOutputContract = document.getElementById("modal-output-contract");
    this.elModalLastEvent = document.getElementById("modal-last-event");
  }

  attachEventListeners() {
    const btnKey = document.getElementById("btn-set-api-key");
    if (btnKey) {
      btnKey.addEventListener("click", () => {
        const key = prompt("Enter V2 Dashboard API Key:", this.apiKey);
        if (key !== null) {
          this.apiKey = key.trim();
          localStorage.setItem("v2_api_key", this.apiKey);
          this.showToast("API Key Updated", "Reconnecting WebSocket...");
          if (this.ws) this.ws.close();
          this.connectWebSocket();
          this.fetchInitialState();
        }
      });
    }

    if (this.elModalClose && this.elStageModal) {
      this.elModalClose.addEventListener("click", () => {
        this.elStageModal.style.display = "none";
      });
      this.elStageModal.addEventListener("click", (e) => {
        if (e.target === this.elStageModal) {
          this.elStageModal.style.display = "none";
        }
      });
    }
  }

  // ── WebSocket Real-Time Connection ──────────────────────────────────────────

  connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/v2/feed?api_key=${encodeURIComponent(this.apiKey)}`;

    this.updateConnectionStatus(false, "Connecting...");

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.updateConnectionStatus(true, "WS Live");
        this.showToast("Connected", "Real-time event feed active");
      };

      this.ws.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data);
          this.handleEventFrame(frame);
        } catch (e) {
          console.warn("Invalid WebSocket message:", event.data);
        }
      };

      this.ws.onclose = () => {
        this.updateConnectionStatus(false, "Disconnected");
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.updateConnectionStatus(false, "Connection Error");
      };
    } catch (err) {
      this.updateConnectionStatus(false, "Failed to connect");
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts++;
    setTimeout(() => this.connectWebSocket(), delay);
  }

  updateConnectionStatus(connected, text) {
    if (this.elConnPill && this.elConnText) {
      this.elConnPill.className = `connection-pill ${connected ? "connected" : "disconnected"}`;
      this.elConnText.textContent = text;
    }
  }

  // ── REST Initial State Loading ──────────────────────────────────────────────

  async fetchInitialState() {
    const headers = {};
    if (this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }

    try {
      // 1. Fetch unified overview
      const overviewRes = await fetch("/api/v2/dashboard/overview", { headers });
      if (overviewRes.ok) {
        const overview = await overviewRes.json();
        this.renderOverview(overview);
      }

      // 2. Fetch health matrix
      const healthRes = await fetch("/api/v2/monitoring/health", { headers });
      if (healthRes.ok) {
        const health = await healthRes.json();
        this.renderHealthMatrix(health.services || {});
      }

      // 3. Fetch open positions
      const posRes = await fetch("/api/v2/positions/open", { headers });
      if (posRes.ok) {
        const pData = await posRes.json();
        this.renderPositions(pData);
      }

      // 4. Fetch evaluated scanned coins
      const coinsRes = await fetch("/api/v2/scanner/coins", { headers });
      if (coinsRes.ok) {
        const coins = await coinsRes.json();
        this.renderScannedCoins(coins);
      }

      // 5. Fetch recent AI analyses if feed is empty
      const aiRes = await fetch("/api/v2/ai/analyses?limit=10", { headers });
      if (aiRes.ok) {
        const analyses = await aiRes.json();
        if (Array.isArray(analyses) && analyses.length > 0 && this.elAiFeed) {
          // Clear default placeholder if real analyses exist
          if (this.elAiFeed.innerHTML.includes("Listening for live signals")) {
            this.elAiFeed.innerHTML = "";
          }
          analyses.forEach(a => this.appendAiCard(a, a.recommendation === "APPROVE"));
        }
      }
    } catch (err) {
      console.warn("Initial state fetch warning:", err);
    }
  }

  // ── Event Handlers ──────────────────────────────────────────────────────────

  handleEventFrame(frame) {
    const { type, data } = frame;
    this.appendEventRow(type, data);

    if (type === "TELEMETRY_SNAPSHOT" && data) {
      if (data.fleet_telemetry && Array.isArray(data.fleet_telemetry)) {
        this.renderBotPanel(data.fleet_telemetry);
      }
      if (data.watchlist_summary && Array.isArray(data.watchlist_summary.top_candidates)) {
        this.renderScannedCoins(data.watchlist_summary.top_candidates);
      }
      return;
    }

    if (type === "signal.ai_confirmed" || type === "signal.ai_rejected") {
      this.appendAiCard(data, type === "signal.ai_confirmed");
      const emoji = data.recommendation === "APPROVE" ? "🟢" : data.recommendation === "SCALE_DOWN" ? "🟡" : "🔴";
      this.showToast(`${emoji} AI: ${data.coin || "UNKNOWN"}`, `${data.recommendation} (${data.confidence_score || 0}% Conf)`);
      this.patchStageStatus("ai_intelligence", "ACTIVE", `${data.coin || "COIN"} (${data.confidence_score || 85}%)`);
      this.patchBotCard(data.bot, "AI_EVALUATING", `AI ${type === "signal.ai_confirmed" ? "✓" : "✗"} ${data.coin || ""}`);
    } else if (type === "signal.generated") {
      this.patchStageStatus("signal_engine", "ACTIVE", `${data.coin || "COIN"} (${data.score || 0} pts)`);
      this.patchBotCard(data.bot, "SCANNING", `Signal: ${data.coin || ""}`, true);
    } else if (type === "trade.approved") {
      this.patchStageStatus("risk_engine", "ACTIVE", `Approved ${data.coin || ""}`);
      this.patchStageStatus("trade_constructor", "ACTIVE", `Sized ${data.coin || ""}`);
      this.patchBotCard(data.bot, "RISK_CHECK", `Risk ✓ ${data.coin || ""}`);
    } else if (type === "trade.executed") {
      this.patchStageStatus("auto_trade", "ACTIVE", `Executed ${data.coin || ""}`);
      this.patchBotCard(data.bot, "EXECUTING", `Exec ${data.coin || ""} @ ₹${Number(data.entry_price || 0).toFixed(2)}`);
    } else if (type === "portfolio.updated") {
      this.renderPortfolio(data);
      this.patchStageStatus("analytics", "ACTIVE", `PnL: ₹${Number(data.daily_pnl || 0).toFixed(2)}`);
    } else if (type === "position.opened" || type === "position.closed") {
      this.fetchInitialState(); // Refresh positions
      this.patchStageStatus("position_manager", "ACTIVE", `${data.coin || "Position"} ${type}`);
      if (type === "position.opened") {
        this.patchBotCard(data.bot, "IN_POSITION", `Pos open: ${data.coin || ""}`);
      }
      if (type === "position.closed") {
        this.patchStageStatus("trade_journal", "ACTIVE", `Logged ${data.coin || ""}`);
        this.patchStageStatus("autonomous_loop", "CONTINUOUS", `Loop ↺ Active`);
        const pnl = Number(data.pnl || 0);
        this.patchBotCard(data.bot, "IDLE", `Closed ${data.coin || ""} ${pnl >= 0 ? "+" : ""}₹${pnl.toFixed(2)}`);
      }
      this.showToast(`⚡ Position Event`, `${data.bot || "Bot"}: ${data.coin || ""} (${type})`);
    } else if (type === "circuit_breaker.triggered") {
      this.showToast("🚨 CIRCUIT BREAKER TRIPPED", data.reason || "Drawdown limit reached");
      if (this.elBreakerStatus) {
        this.elBreakerStatus.textContent = "TRIPPED";
        this.elBreakerStatus.style.color = "var(--red)";
      }
      this.patchStageStatus("risk_engine", "TRIPPED", "Circuit Breaker Active");
    } else if (type === "divergence.detected") {
      this.appendDivergenceLog(data);
      this.patchStageStatus("backtest_test", "ACTIVE", `Divergence: ${data.coin || ""}`);
    }
  }

  // ── 14-Stage Autonomous Pipeline Rendering ──────────────────────────────────

  renderPipelineStages(stages) {
    if (!this.elPipelineGrid || !stages || stages.length === 0) return;
    this.stagesCache = stages;

    this.elPipelineGrid.innerHTML = stages.map(stage => {
      const isLoop = stage.id === "autonomous_loop";
      const cardClass = `stage-card ${isLoop ? "loop-stage" : ""}`;
      const statusClass = stage.status || "ONLINE";

      // Pick top metric to preview
      let metricPreview = "";
      if (stage.metrics) {
        const [firstKey, firstVal] = Object.entries(stage.metrics)[0] || ["Status", "Active"];
        const formattedKey = firstKey.replace(/_/g, " ").toUpperCase();
        metricPreview = `<span>${formattedKey}</span><strong>${this.esc(firstVal)}</strong>`;
      }

      return `
        <div class="${cardClass}" onclick="window.v2Dashboard.openStageModal('${this.esc(stage.id)}')">
          <div class="stage-top">
            <span class="stage-num">STAGE ${String(stage.number).padStart(2, '0')}</span>
            <span class="stage-badge ${statusClass}">${this.esc(stage.status)}</span>
          </div>
          <div class="stage-header">
            <span class="stage-icon">${stage.icon || "⚙"}</span>
            <div>
              <div class="stage-name">${this.esc(stage.name)}</div>
              <div style="font-size: 0.65rem; color: var(--text-dim);">${this.esc(stage.category)}</div>
            </div>
          </div>
          <div class="stage-metric-preview">
            ${metricPreview}
          </div>
        </div>
      `;
    }).join("");
  }

  patchStageStatus(stageId, newStatus, metricText) {
    const card = document.querySelector(`.stage-card[onclick*="'${stageId}'"]`);
    if (!card) return;

    const badge = card.querySelector(".stage-badge");
    if (badge) {
      badge.className = `stage-badge ${newStatus}`;
      badge.textContent = newStatus;
    }

    if (metricText) {
      const preview = card.querySelector(".stage-metric-preview");
      if (preview) {
        preview.innerHTML = `<span>LATEST</span><strong>${this.esc(metricText)}</strong>`;
      }
    }

    card.classList.add("active-stage");
    setTimeout(() => card.classList.remove("active-stage"), 2500);
  }

  async openStageModal(stageId) {
    if (!this.elStageModal) return;

    try {
      const headers = {};
      if (this.apiKey) headers["X-API-Key"] = this.apiKey;

      const res = await fetch(`/api/v2/pipeline/stages/${encodeURIComponent(stageId)}`, { headers });
      if (res.ok) {
        const detail = await res.json();
        this.renderStageModalDetail(detail);
      } else {
        // Fallback to cache
        const cached = this.stagesCache.find(s => s.id === stageId);
        if (cached) this.renderStageModalDetail(cached);
      }
    } catch (e) {
      console.warn("Failed to fetch stage detail:", e);
      const cached = this.stagesCache.find(s => s.id === stageId);
      if (cached) this.renderStageModalDetail(cached);
    }

    this.elStageModal.style.display = "flex";
  }

  renderStageModalDetail(d) {
    if (this.elModalIcon) this.elModalIcon.textContent = d.icon || "⚙";
    if (this.elModalTitle) this.elModalTitle.textContent = `${d.name} (${d.category})`;
    if (this.elModalSubtitle) this.elModalSubtitle.textContent = `STAGE ${String(d.number).padStart(2, '0')} · STATUS: ${d.status}`;
    if (this.elModalDesc) this.elModalDesc.textContent = d.description || "";

    // Metrics grid
    if (this.elModalMetricsGrid) {
      const metrics = Object.entries(d.metrics || {});
      this.elModalMetricsGrid.innerHTML = metrics.map(([k, v]) => `
        <div class="metric-chip">
          <div class="metric-chip-label">${this.esc(k.replace(/_/g, " "))}</div>
          <div class="metric-chip-value">${this.esc(v)}</div>
        </div>
      `).join("");
    }

    // Contracts
    if (this.elModalInputContract) {
      this.elModalInputContract.textContent = JSON.stringify(d.input_contract || { source: "EventBus stream" }, null, 2);
    }
    if (this.elModalOutputContract) {
      this.elModalOutputContract.textContent = JSON.stringify(d.output_contract || { destination: "Next Pipeline Stage" }, null, 2);
    }

    // Last event payload
    if (this.elModalLastEvent) {
      this.elModalLastEvent.textContent = d.last_event
        ? JSON.stringify(d.last_event, null, 2)
        : JSON.stringify({ status: "Awaiting next trigger event...", telemetry: d.telemetry || {} }, null, 2);
    }
  }

  // ── Overview & Rendering Functions ──────────────────────────────────────────

  renderOverview(data) {
    if (data.portfolio) this.renderPortfolio(data.portfolio);
    if (data.pipeline_stages) this.renderPipelineStages(data.pipeline_stages);
    if (data.bots) this.renderBotPanel(data.bots);

    if (data.risk && this.elBreakerStatus) {
      const tripped = data.risk.circuit_breaker_open || data.risk.emergency_stop;
      this.elBreakerStatus.textContent = tripped ? "TRIPPED" : "NORMAL";
      this.elBreakerStatus.style.color = tripped ? "var(--red)" : "var(--green)";
    }
    if (data.shadow) {
      if (this.elShadowWinRate) this.elShadowWinRate.textContent = `${data.shadow.simulated_win_rate_pct || 0}%`;
      if (this.elShadowPnl) {
        const pnl = data.shadow.total_simulated_pnl || 0;
        this.elShadowPnl.textContent = `₹${pnl.toFixed(2)}`;
        this.elShadowPnl.style.color = pnl >= 0 ? "var(--green)" : "var(--red)";
      }
      if (this.elShadowCount) this.elShadowCount.textContent = data.shadow.total_divergences || 0;
    }
  }

  renderPortfolio(p) {
    if (this.elAum) this.elAum.textContent = `₹${Number(p.total_aum || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
    if (this.elDeployed) this.elDeployed.textContent = `₹${Number(p.total_deployed || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
    if (this.elCash) this.elCash.textContent = `₹${Number(p.total_cash || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
    if (this.elPnl) {
      const pnl = Number(p.daily_pnl || 0);
      this.elPnl.textContent = `${pnl >= 0 ? "+" : ""}₹${pnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
      this.elPnl.className = `kpi-value ${pnl >= 0 ? "positive" : "negative"}`;
    }
    if (this.elUtil) this.elUtil.textContent = `${Number(p.capital_utilisation || 0).toFixed(1)}%`;
  }

  renderPositions(positions) {
    if (!this.elPositionsTbody) return;
    if (!positions || positions.length === 0) {
      this.elPositionsTbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 1.5rem;">No active open positions</td></tr>`;
      return;
    }

    this.elPositionsTbody.innerHTML = positions.map(pos => {
      const pnl = pos.unrealised_pnl || 0;
      const pnlClass = pnl >= 0 ? "positive" : "negative";
      return `
        <tr>
          <td><strong>${this.esc(pos.coin)}</strong></td>
          <td><span class="card-badge">${this.esc(pos.bot)}</span></td>
          <td>₹${Number(pos.entry_price || 0).toFixed(2)}</td>
          <td>${Number(pos.qty || 0).toFixed(4)}</td>
          <td class="${pnlClass}">${pnl >= 0 ? "+" : ""}₹${Number(pnl).toFixed(2)}</td>
          <td>${pos.take_profit ? `₹${Number(pos.take_profit).toFixed(2)}` : "—"}</td>
          <td>${pos.stop_loss ? `₹${Number(pos.stop_loss).toFixed(2)}` : "—"}</td>
        </tr>
      `;
    }).join("");
  }

  renderHealthMatrix(services) {
    if (!this.elHealthMatrix) return;
    const entries = Object.entries(services);
    if (entries.length === 0) return;

    this.elHealthMatrix.innerHTML = entries.map(([name, status]) => {
      const isHealthy = status.healthy !== false;
      const cls = isHealthy ? "healthy" : "unhealthy";
      const icon = isHealthy ? "🟢" : "🔴";
      return `
        <div class="health-node ${cls}">
          <span class="health-node-icon">${icon}</span>
          <span class="health-node-name">${this.esc(name)}</span>
          <span class="health-node-status">${isHealthy ? "ONLINE" : "DEGRADED"}</span>
        </div>
      `;
    }).join("");
  }

  appendAiCard(data, confirmed) {
    if (!this.elAiFeed) return;
    const card = document.createElement("div");
    card.className = "ai-card";
    const recClass = (data.recommendation || "watch").toLowerCase();

    const factors = (data.supporting_factors || []).slice(0, 2);
    const risks = (data.risk_factors || []).slice(0, 2);

    card.innerHTML = `
      <div class="ai-card-top">
        <span class="ai-coin-tag">${this.esc(data.coin || "UNKNOWN")}</span>
        <span class="ai-rec-badge ${recClass}">${this.esc(data.recommendation || "WATCH")} (${data.confidence_score || 0}%)</span>
      </div>
      <div class="ai-analysis-text">${this.esc(data.trend_evaluation || "Trend evaluation active")} · Setup: ${this.esc(data.setup_quality || "N/A")}</div>
      <div class="ai-factors-list">
        ${factors.map(f => `<span class="ai-factor-pill">✓ ${this.esc(f)}</span>`).join("")}
        ${risks.map(r => `<span class="ai-factor-pill" style="color: var(--amber)">⚠ ${this.esc(r)}</span>`).join("")}
      </div>
    `;

    this.elAiFeed.prepend(card);
    while (this.elAiFeed.children.length > 20) {
      this.elAiFeed.removeChild(this.elAiFeed.lastChild);
    }
  }

  appendDivergenceLog(data) {
    if (!this.elDivergenceLogs) return;
    const item = document.createElement("div");
    item.className = "div-item";
    item.innerHTML = `
      <div><strong>${this.esc(data.coin || "COIN")}</strong> <span style="color: var(--text-dim)">(${this.esc(data.bot || "MTB")})</span></div>
      <div style="color: var(--amber); font-size: 0.75rem;">${this.esc(data.divergence_type || "AI_FILTERED")}</div>
    `;
    this.elDivergenceLogs.prepend(item);
  }

  appendEventRow(type, data) {
    if (!this.elEventStream) return;
    const row = document.createElement("div");
    row.className = "event-row";
    const time = new Date().toLocaleTimeString();
    row.innerHTML = `
      <span class="event-time">${time}</span>
      <span class="event-type">[${this.esc(type)}]</span>
      <span class="event-data">${this.esc(JSON.stringify(data))}</span>
    `;
    this.elEventStream.prepend(row);
    while (this.elEventStream.children.length > 30) {
      this.elEventStream.removeChild(this.elEventStream.lastChild);
    }
  }

  showToast(title, msg) {
    if (!this.elToastContainer) return;
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `<strong>${this.esc(title)}</strong><div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">${this.esc(msg)}</div>`;
    this.elToastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  esc(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ── 3-Bot Pipeline Status Panel ─────────────────────────────────────────────

  _stageStatusCssClass(status) {
    const map = {
      IDLE: "idle",
      SCANNING: "scanning",
      AI_EVALUATING: "evaluating",
      RISK_CHECK: "risk",
      EXECUTING: "executing",
      IN_POSITION: "in-position",
      JOURNALING: "idle",
    };
    return map[status] || "idle";
  }

  renderBotPanel(bots) {
    if (!this.elBotGrid || !bots || bots.length === 0) return;
    this.botsCache = bots;

    this.elBotGrid.innerHTML = bots.map(bot => {
      const botName = bot.bot || bot.bot_name || bot.name || "BOT";
      const strategy = bot.strategy || botName;
      const stageLabel = bot.current_stage_label || bot.stage_label || bot.stage || "Scanner";
      const stageStatus = bot.stage_status || bot.status || "IDLE";
      const signals = bot.signals_generated ?? bot.signals ?? bot.signals_count ?? 0;
      const openPositions = bot.open_positions ?? bot.open_pos ?? 0;
      const winRate = bot.win_rate_pct != null ? bot.win_rate_pct : (parseFloat(bot.win_rate) || 0);
      const dailyPnl = typeof bot.daily_pnl === "number" ? bot.daily_pnl : (parseFloat(bot.day_pnl) || 0);
      const capDeployed = Number(bot.capital_deployed || 0);
      const capLimit = Number(bot.capital_limit || 10000);
      const capitalPct = capLimit > 0
        ? Math.min(100, (capDeployed / capLimit) * 100).toFixed(1)
        : 0;
      const statusCss = this._stageStatusCssClass(stageStatus);
      const pnlSign = dailyPnl >= 0 ? "+" : "";
      const pnlClass = dailyPnl >= 0 ? "positive" : "negative";
      const lastAction = bot.last_action || bot.status_text || "Awaiting signals...";

      return `
        <div class="bot-card" style="--bot-color: ${this.esc(bot.color || '#94a3b8')}"
             onclick="window.v2Dashboard.openBotModal('${this.esc(botName)}')">
          <div class="bot-card-header">
            <div class="bot-card-identity">
              <span class="bot-card-icon">${bot.icon || "🤖"}</span>
              <div>
                <div class="bot-card-name">${this.esc(botName)}</div>
                <div class="bot-card-strategy">${this.esc(strategy)}</div>
              </div>
            </div>
            <div class="bot-stage-badge">
              <span class="bot-stage-label">STAGE</span>
              <span class="bot-stage-pill">${this.esc(stageLabel)}</span>
              <span class="bot-stage-status ${statusCss}">${this.esc(stageStatus)}</span>
            </div>
          </div>

          <div class="bot-metrics-row">
            <div class="bot-metric-item">
              <div class="bot-metric-label">Signals</div>
              <div class="bot-metric-value">${signals}</div>
            </div>
            <div class="bot-metric-item">
              <div class="bot-metric-label">Open Pos</div>
              <div class="bot-metric-value">${openPositions}</div>
            </div>
            <div class="bot-metric-item">
              <div class="bot-metric-label">Win Rate</div>
              <div class="bot-metric-value">${winRate}%</div>
            </div>
            <div class="bot-metric-item">
              <div class="bot-metric-label">Day PnL</div>
              <div class="bot-metric-value ${pnlClass}">${pnlSign}₹${Number(dailyPnl).toFixed(2)}</div>
            </div>
          </div>

          <div class="bot-capital-bar-wrap">
            <div class="bot-capital-label">
              <span>Capital Deployed</span>
              <span>₹${Number(capDeployed).toFixed(0)} / ₹${Number(capLimit).toFixed(0)}</span>
            </div>
            <div class="bot-capital-bar">
              <div class="bot-capital-fill" style="width: ${capitalPct}%;"></div>
            </div>
          </div>

          ${lastAction ? `<div class="bot-last-action" title="${this.esc(lastAction)}">▶ ${this.esc(lastAction)}</div>` : ""}
        </div>
      `;
    }).join("");
  }

  patchBotCard(botName, newStatus, lastAction, incrementSignal = false) {
    if (!botName) return;
    const bn = String(botName).toUpperCase();

    // Update cache
    const cached = this.botsCache.find(b => (b.bot || b.bot_name || b.name) === bn);
    if (cached) {
      cached.stage_status = newStatus;
      cached.last_action = lastAction;
      if (incrementSignal) {
        cached.signals_generated = (cached.signals_generated || 0) + 1;
      }
    }

    // Update DOM
    const card = this.elBotGrid
      ? [...this.elBotGrid.querySelectorAll(".bot-card")]
          .find(c => c.querySelector(".bot-card-name")?.textContent === bn)
      : null;
    if (!card) return;

    const badge = card.querySelector(".bot-stage-status");
    if (badge) {
      badge.className = `bot-stage-status ${this._stageStatusCssClass(newStatus)}`;
      badge.textContent = newStatus;
    }

    if (incrementSignal) {
      const sigVal = card.querySelector(".bot-metric-item .bot-metric-value");
      if (sigVal) {
        const cur = parseInt(sigVal.textContent) || 0;
        sigVal.textContent = String(cur + 1);
      }
    }

    const lastActionEl = card.querySelector(".bot-last-action");
    if (lastActionEl) {
      lastActionEl.textContent = `▶ ${lastAction}`;
      lastActionEl.title = lastAction;
    }
  }

  async openBotModal(botName) {
    const headers = {};
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;

    try {
      const res = await fetch(`/api/v2/bots/${botName}`, { headers });
      if (!res.ok) return;
      const bot = await res.json();
      this._renderBotModal(bot);
    } catch {
      // Fallback to cached data
      const cached = this.botsCache.find(b => b.bot === String(botName).toUpperCase());
      if (cached) this._renderBotModal(cached);
    }
  }

  _renderBotModal(bot) {
    document.getElementById("bot-modal-icon").textContent = bot.icon || "🤖";
    document.getElementById("bot-modal-title").textContent = `${bot.bot} — ${bot.strategy}`;
    document.getElementById("bot-modal-subtitle").textContent = bot.stage_status || "IDLE";
    document.getElementById("bot-modal-description").textContent = bot.description || "";

    // Stage progress bar
    const stageBar = document.getElementById("bot-modal-stage-bar");
    const stageOrder = bot.stage_order || [];
    document.getElementById("bot-modal").style.setProperty("--bot-modal-color", bot.color || "var(--cyan)");

    if (stageBar && stageOrder.length) {
      const currentIdx = bot.current_stage_index || 0;
      stageBar.innerHTML = stageOrder.map((sid, i) => {
        const cls = i < currentIdx ? "done" : i === currentIdx ? "active" : "";
        const label = (bot.stage_labels || {})[sid] || sid;
        return `
          <div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; min-width: 30px;">
            <div class="bot-stage-bar-step ${cls}" title="${this.esc(label)}"></div>
            ${i === currentIdx ? `<div class="bot-stage-bar-label" style="color: ${this.esc(bot.color || "var(--cyan)")}; font-weight: 700;">${this.esc(label)}</div>` : ""}
          </div>
        `;
      }).join("");
    }

    // Metrics
    const metricsEl = document.getElementById("bot-modal-metrics");
    if (metricsEl) {
      const pnlClass = (bot.daily_pnl || 0) >= 0 ? "positive" : "negative";
      metricsEl.innerHTML = [
        ["Signals", bot.signals_generated || 0],
        ["AI Evals", bot.ai_evaluations || 0],
        ["AI Approval", `${bot.ai_approval_rate_pct || 0}%`],
        ["Trades Exec", bot.trades_executed || 0],
        ["Open Pos", bot.open_positions || 0],
        ["Win Rate", `${bot.win_rate_pct || 0}%`],
        ["Day PnL", `${(bot.daily_pnl || 0) >= 0 ? "+" : ""}₹${Number(bot.daily_pnl || 0).toFixed(2)}`],
        ["Total PnL", `${(bot.total_pnl || 0) >= 0 ? "+" : ""}₹${Number(bot.total_pnl || 0).toFixed(2)}`],
      ].map(([label, val]) => `
        <div class="modal-metric-chip">
          <div class="modal-metric-label">${this.esc(label)}</div>
          <div class="modal-metric-value">${this.esc(String(val))}</div>
        </div>
      `).join("");
    }

    // Strategy params
    const params = bot.strategy_params || {};
    document.getElementById("bot-modal-params").textContent = JSON.stringify({
      stop_loss: `${params.stop_loss_pct || "—"}%`,
      take_profit: `${params.take_profit_pct || "—"}%`,
      tightened_sl: `${params.tightened_sl_pct || "—"}%`,
      max_positions: params.max_positions || "—",
      trade_amount: `₹${params.default_trade_amount || "—"}`,
      scan_pairs: (params.scan_pairs || []).join(", "),
    }, null, 2);

    // Counters
    const counters = bot.counters || {};
    document.getElementById("bot-modal-counters").textContent = JSON.stringify({
      ai_approved: counters.ai_approved || 0,
      ai_rejected: counters.ai_rejected || 0,
      trades_closed: counters.trades_closed || 0,
      wins: counters.wins || 0,
      losses: counters.losses || 0,
      capital_deployed: `₹${Number(bot.capital_deployed || 0).toFixed(2)}`,
      capital_limit: `₹${Number(bot.capital_limit || 0).toFixed(2)}`,
    }, null, 2);

    // Last action
    document.getElementById("bot-modal-last-action").textContent =
      bot.last_action
        ? `${bot.last_action}\n(${bot.last_action_time || "—"})`
        : "No recent action.";

    document.getElementById("bot-modal").style.display = "flex";
  }

  async pollScanner() {
    const headers = {};
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;
    this.showToast("Scanner Poll Triggered", "Executing market scanner cycle...");
    try {
      const res = await fetch("/api/v2/scanner/poll", { method: "POST", headers });
      if (res.ok) {
        this.showToast("Scanner Complete", "Refreshing evaluation snapshot...");
        setTimeout(() => this.fetchInitialState(), 800);
      }
    } catch (e) {
      console.warn("Poll error:", e);
    }
  }

  renderScannedCoins(coins) {
    if (!this.elScannedCoinsTbody) return;
    if (!coins || !Array.isArray(coins) || coins.length === 0) {
      this.elScannedCoinsTbody.innerHTML = `
        <tr>
          <td colspan="9" style="text-align: center; color: var(--text-dim); padding: 1.5rem;">
            No coin evaluations in latest scan snapshot.
          </td>
        </tr>
      `;
      if (this.elWatchlistBadge) this.elWatchlistBadge.textContent = "0 EVALUATED";
      return;
    }

    this.scannedCoinsCache = coins;
    if (this.elWatchlistBadge) {
      const passed = coins.filter(c => c.status === "PASSED" || c.accepted === true).length;
      this.elWatchlistBadge.textContent = `${coins.length} EVALUATED (${passed} PASSED)`;
    }

    this.elScannedCoinsTbody.innerHTML = coins.map(coin => {
      const isPassed = coin.status === "PASSED" || coin.accepted === true;
      const statusBadgeCls = isPassed ? "positive" : "negative";
      const statusText = isPassed ? "PASSED (>= 85)" : "FILTERED";
      const trendColor = coin.ema_trend === "BULLISH" ? "var(--green)" : coin.ema_trend === "BEARISH" ? "var(--red)" : "var(--text-muted)";
      const mtfBadge = coin.is_mtf_aligned || coin.mtf_alignment === "15m_1h" ? "🟢 15m ✓ / 1h ✓" : "🟡 Not Aligned";
      const scoreColor = coin.confluence_score >= 85 ? "var(--green)" : coin.confluence_score >= 70 ? "var(--amber)" : "var(--text-dim)";
      const rejection = coin.rejection_reason || (isPassed ? "None (Approved)" : "Score < 85 or Gate Veto");

      return `
        <tr style="cursor: pointer;" onclick="window.v2Dashboard.openCoinModal('${this.esc(coin.symbol)}')">
          <td style="font-weight: 700; font-family: var(--font-mono); color: var(--cyan);">
            ${this.esc(coin.pair || coin.symbol)}
          </td>
          <td>₹${Number(coin.price || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
          <td style="color: ${trendColor}; font-weight: 600;">${this.esc(coin.ema_trend || "SIDEWAYS")}</td>
          <td>${Number(coin.rsi || 50).toFixed(1)}</td>
          <td style="font-size: 0.8rem;">${mtfBadge}</td>
          <td style="font-weight: 700; color: ${scoreColor};">${coin.confluence_score}/100</td>
          <td>
            <span class="bot-stage-status ${statusBadgeCls}" style="font-size: 0.7rem; padding: 0.15rem 0.5rem;">
              ${statusText}
            </span>
          </td>
          <td style="font-size: 0.75rem; color: var(--text-muted); max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.esc(rejection)}">
            ${this.esc(rejection)}
          </td>
          <td>
            <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.15rem 0.5rem;" onclick="event.stopPropagation(); window.v2Dashboard.openCoinModal('${this.esc(coin.symbol)}')">
              Inspect
            </button>
          </td>
        </tr>
      `;
    }).join("");
  }

  async openCoinModal(symbol) {
    const modal = document.getElementById("coin-modal");
    if (!modal || !symbol) return;

    const headers = {};
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;

    try {
      const res = await fetch(`/api/v2/scanner/coins/${encodeURIComponent(symbol)}`, { headers });
      if (res.ok) {
        const coin = await res.json();
        this._renderCoinModal(coin);
      } else {
        const cached = this.scannedCoinsCache.find(c => c.symbol === symbol || c.coin === symbol || c.pair === symbol);
        if (cached) this._renderCoinModal(cached);
      }
    } catch (err) {
      const cached = this.scannedCoinsCache.find(c => c.symbol === symbol || c.coin === symbol || c.pair === symbol);
      if (cached) this._renderCoinModal(cached);
    }
  }

  _renderCoinModal(coin) {
    const modal = document.getElementById("coin-modal");
    if (!modal) return;

    document.getElementById("coin-modal-title").textContent = `${coin.pair || coin.symbol} Inspection`;
    document.getElementById("coin-modal-subtitle").textContent = `EVALUATED AT: ${coin.evaluated_at || new Date().toISOString()}`;
    document.getElementById("coin-modal-price").textContent = `₹${Number(coin.price || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
    document.getElementById("coin-modal-score").textContent = `${coin.confluence_score} / 100`;
    
    const statusEl = document.getElementById("coin-modal-status");
    const isPassed = coin.status === "PASSED" || coin.accepted === true;
    statusEl.textContent = isPassed ? "PASSED (CONFLUENCE ✓)" : "REJECTED (GATE VETO)";
    statusEl.style.color = isPassed ? "var(--green)" : "var(--amber)";

    document.getElementById("coin-modal-rsi").textContent = Number(coin.rsi || 50).toFixed(1);

    // Render 4 Layers
    const layersEl = document.getElementById("coin-modal-layers");
    const breakdown = coin.eval_breakdown || {};
    const layers = [
      { name: "Layer 1: Chart Structure", key: "chart", weight: "30%" },
      { name: "Layer 2: Technical Indicators", key: "indicator", weight: "35%" },
      { name: "Layer 3: Market Sentiment", key: "sentiment", weight: "20%" },
      { name: "Layer 4: News & Events", key: "news", weight: "15%" },
    ];

    layersEl.innerHTML = layers.map(l => {
      const data = breakdown[l.key] || {};
      const score = data.score ?? "—";
      const passed = data.passed ? "🟢 PASS" : "🔴 VETO";
      return `
        <div class="metric-chip" style="display: flex; flex-direction: column; gap: 0.25rem;">
          <div style="font-size: 0.7rem; color: var(--text-muted); font-weight: 700;">${l.name} (${l.weight})</div>
          <div style="font-size: 1.1rem; font-weight: 700; color: var(--cyan);">${score} / 100</div>
          <div style="font-size: 0.75rem; font-weight: 600;">${passed}</div>
        </div>
      `;
    }).join("");

    // Rejection reasons
    const reasonsEl = document.getElementById("coin-modal-reasons");
    const reasons = coin.rejection_reasons || (coin.rejection_reason ? [coin.rejection_reason] : []);
    if (reasons.length > 0) {
      reasonsEl.innerHTML = `<ul style="margin: 0; padding-left: 1.25rem;">${reasons.map(r => `<li style="color: var(--amber);">${this.esc(r)}</li>`).join("")}</ul>`;
    } else {
      reasonsEl.innerHTML = `<div style="color: var(--green);">✓ No gate vetoes. Signal qualified for high-conviction pool.</div>`;
    }

    // Raw payload
    document.getElementById("coin-modal-raw").textContent = JSON.stringify(coin, null, 2);

    modal.style.display = "flex";
  }
}

// Exposed globally for inline onclick handlers
function closeBotModal() {
  const m = document.getElementById("bot-modal");
  if (m) m.style.display = "none";
}

document.addEventListener("DOMContentLoaded", () => {
  window.v2Dashboard = new V2DashboardClient();

  // Allow clicking outside bot-modal to close
  const botModal = document.getElementById("bot-modal");
  if (botModal) {
    botModal.addEventListener("click", (e) => {
      if (e.target === botModal) closeBotModal();
    });
  }
});
