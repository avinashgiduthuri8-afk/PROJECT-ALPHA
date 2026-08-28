/**
 * PROJECT-ALPHA V2 Mission Control Dashboard Client
 * Real-time WebSocket streaming with auto-reconnect and REST state fallback.
 */

class V2DashboardClient {
  constructor() {
    this.apiKey = localStorage.getItem("v2_api_key") || "";
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.pollInterval = null;

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

      this.ws.onclose = (event) => {
        this.updateConnectionStatus(false, "Disconnected");
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.updateConnectionStatus(false, "Connection Error");
      };
    } catch (err) {
      this.updateConnectionStatus(false, "WS Init Error");
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts++;
    setTimeout(() => {
      this.connectWebSocket();
    }, delay);
  }

  updateConnectionStatus(connected, text) {
    if (!this.elConnPill) return;
    if (connected) {
      this.elConnPill.className = "connection-pill connected";
      this.elConnText.textContent = text || "WS Live";
    } else {
      this.elConnPill.className = "connection-pill disconnected";
      this.elConnText.textContent = text || "Offline";
    }
  }

  // ── REST API Overview & Health ──────────────────────────────────────────────

  async fetchInitialState() {
    try {
      const headers = this.apiKey ? { "X-API-Key": this.apiKey } : {};
      
      // 1. Fetch Overview
      const res = await fetch("/api/v2/dashboard/overview", { headers });
      if (res.ok) {
        const data = await res.json();
        this.renderOverview(data);
      }

      // 2. Fetch Health
      const hRes = await fetch("/api/v2/monitoring/health", { headers });
      if (hRes.ok) {
        const hData = await hRes.json();
        this.renderHealthMatrix(hData.services || {});
      }

      // 3. Fetch Positions
      const pRes = await fetch("/api/v2/trading/positions", { headers });
      if (pRes.ok) {
        const pData = await pRes.json();
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
    } else if (type === "portfolio.updated") {
      this.renderPortfolio(data);
    } else if (type === "position.opened" || type === "position.closed") {
      this.fetchInitialState(); // Refresh positions
      this.showToast(`⚡ Position Event`, `${data.bot || "Bot"}: ${data.coin || ""} (${type})`);
    } else if (type === "circuit_breaker.triggered") {
      this.showToast("🚨 CIRCUIT BREAKER TRIPPED", data.reason || "Drawdown limit reached");
      if (this.elBreakerStatus) {
        this.elBreakerStatus.textContent = "TRIPPED";
        this.elBreakerStatus.style.color = "var(--red)";
      }
    } else if (type === "divergence.detected") {
      this.appendDivergenceLog(data);
    }
  }

  // ── Rendering Functions ─────────────────────────────────────────────────────

  renderOverview(data) {
    if (data.portfolio) this.renderPortfolio(data.portfolio);
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
      this.elPositionsTbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 1.5rem;">No open positions</td></tr>`;
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
}

document.addEventListener("DOMContentLoaded", () => {
  window.v2Dashboard = new V2DashboardClient();
});
