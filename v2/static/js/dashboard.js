/**
 * PROJECT-ALPHA V2 Mission Control Dashboard Client
 * Real-time WebSocket streaming with auto-reconnect, 14-stage autonomous pipeline, and REST fallback.
 */

class V2DashboardClient {
  constructor() {
    this.apiKey = localStorage.getItem("v2_api_key") || "";
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
    } catch (err) {
      console.warn("Initial state fetch warning:", err);
    }
  }

  // ── Event Handlers ──────────────────────────────────────────────────────────

  handleEventFrame(frame) {
    const { type, data } = frame;
    this.appendEventRow(type, data);

    if (type === "signal.ai_confirmed" || type === "signal.ai_rejected") {
      this.appendAiCard(data, type === "signal.ai_confirmed");
      const emoji = data.recommendation === "APPROVE" ? "🟢" : data.recommendation === "SCALE_DOWN" ? "🟡" : "🔴";
      this.showToast(`${emoji} AI: ${data.coin || "UNKNOWN"}`, `${data.recommendation} (${data.confidence_score || 0}% Conf)`);
      this.patchStageStatus("ai_intelligence", "ACTIVE", `${data.coin || "COIN"} (${data.confidence_score || 85}%)`);
      this.patchBotCard(data.bot, "AI_EVALUATING", `AI ${type === "signal.ai_confirmed" ? "✓" : "✗"} ${data.coin || ""}`);
    } else if (type === "signal.generated") {
      this.patchStageStatus("signal_engine", "ACTIVE", `${data.coin || "COIN"} (${data.score || 0} pts)`);
      this.patchBotCard(data.bot, "SCANNING", `Signal: ${data.coin || ""}`);
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
      const capitalPct = bot.capital_limit > 0
        ? Math.min(100, (bot.capital_deployed / bot.capital_limit) * 100).toFixed(1)
        : 0;
      const statusCss = this._stageStatusCssClass(bot.stage_status);
      const pnlSign = bot.daily_pnl >= 0 ? "+" : "";
      const pnlClass = bot.daily_pnl >= 0 ? "positive" : "negative";

      return `
        <div class="bot-card" style="--bot-color: ${this.esc(bot.color)}"
             onclick="window.v2Dashboard.openBotModal('${this.esc(bot.bot)}')">
          <div class="bot-card-header">
            <div class="bot-card-identity">
              <span class="bot-card-icon">${bot.icon || "🤖"}</span>
              <div>
                <div class="bot-card-name">${this.esc(bot.bot)}</div>
                <div class="bot-card-strategy">${this.esc(bot.strategy)}</div>
              </div>
            </div>
            <div class="bot-stage-badge">
              <span class="bot-stage-label">STAGE</span>
              <span class="bot-stage-pill">${this.esc(bot.current_stage_label)}</span>
              <span class="bot-stage-status ${statusCss}">${this.esc(bot.stage_status)}</span>
            </div>
          </div>

          <div class="bot-metrics-row">
            <div class="bot-metric-item">
              <div class="bot-metric-label">Signals</div>
              <div class="bot-metric-value">${bot.signals_generated}</div>
            </div>
            <div class="bot-metric-item">
              <div class="bot-metric-label">Open Pos</div>
              <div class="bot-metric-value">${bot.open_positions}</div>
            </div>
            <div class="bot-metric-item">
              <div class="bot-metric-label">Win Rate</div>
              <div class="bot-metric-value">${bot.win_rate_pct}%</div>
            </div>
            <div class="bot-metric-item">
              <div class="bot-metric-label">Day PnL</div>
              <div class="bot-metric-value ${pnlClass}">${pnlSign}₹${Number(bot.daily_pnl).toFixed(2)}</div>
            </div>
          </div>

          <div class="bot-capital-bar-wrap">
            <div class="bot-capital-label">
              <span>Capital Deployed</span>
              <span>₹${Number(bot.capital_deployed).toFixed(0)} / ₹${Number(bot.capital_limit).toFixed(0)}</span>
            </div>
            <div class="bot-capital-bar">
              <div class="bot-capital-fill" style="width: ${capitalPct}%;"></div>
            </div>
          </div>

          ${bot.last_action ? `<div class="bot-last-action" title="${this.esc(bot.last_action)}">▶ ${this.esc(bot.last_action)}</div>` : ""}
        </div>
      `;
    }).join("");
  }

  patchBotCard(botName, newStatus, lastAction) {
    if (!botName) return;
    const bn = String(botName).toUpperCase();

    // Update cache
    const cached = this.botsCache.find(b => b.bot === bn);
    if (cached) {
      cached.stage_status = newStatus;
      cached.last_action = lastAction;
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
