// ── I-04: Cleanup engine helpers ──────────────────────────────────────────
function _relativeTime(date) {
    const diff = Math.round((Date.now() - date.getTime()) / 1000);
    if (diff < 60)    return diff + "s ago";
    if (diff < 3600)  return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
}

function _countdownStr(targetMs) {
    const diff = Math.round((targetMs - Date.now()) / 1000);
    if (diff <= 0) return "Running…";
    const m = Math.floor(diff / 60);
    const s = diff % 60;
    return m + "m " + String(s).padStart(2, "0") + "s";
}

window._nextCleanupTs = null;

// Tick the countdown every second
setInterval(function() {
    const el = document.getElementById("so-next-cleanup");
    if (!el) return;
    if (!window._nextCleanupTs) { el.textContent = "—"; return; }
    el.textContent = _countdownStr(window._nextCleanupTs);
}, 1000);

// Populate the shared CoinDCX datalist once on page load
(async function loadCoinDCXCoins() {
    try {
        const resp = await fetch("/api/supported-coins");
        const data = await resp.json();
        const dl = document.getElementById("coindcx-coins");
        if (!dl || !Array.isArray(data.coins)) return;
        dl.innerHTML = data.coins
            .map(c => `<option value="${c}"></option>`)
            .join("");
    } catch (e) {
        console.warn("[ProjectA] Could not load CoinDCX coin list:", e.message);
    }
})();

// Market Assets link → jump to Watchlist Center
document.addEventListener("DOMContentLoaded", () => {
    const link = document.getElementById("market-assets-link");
    if (link) {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            const target = document.querySelector('.nav-anchor[data-target="watchlist-center"]');
            if (target) target.click();
        });
    }
});

document.addEventListener("DOMContentLoaded", () => {
    // 1. Core Config State Payload Bridge Unpacking Pipeline
    const stateEngineData = JSON.parse(document.getElementById("dashboard-state-payload-json").textContent);

    // 2. Sidebar Dropdown Menu Toggle Engine
    const dropdownToggles = document.querySelectorAll(".nav-dropdown-toggle");
    dropdownToggles.forEach(toggle => {
        toggle.addEventListener("click", () => {
            const menuId = "menu-" + toggle.getAttribute("data-menu");
            const menu = document.getElementById(menuId);
            const isHidden = menu.classList.contains("view-hidden");
            // Close all other menus
            document.querySelectorAll(".nav-dropdown-menu").forEach(m => {
                if (m.id !== menuId) m.classList.add("view-hidden");
            });
            document.querySelectorAll(".nav-dropdown-toggle").forEach(t => {
                if (t !== toggle) t.classList.remove("active");
            });
            // Toggle current
            if (isHidden) {
                menu.classList.remove("view-hidden");
                toggle.classList.add("active");
            } else {
                menu.classList.add("view-hidden");
                toggle.classList.remove("active");
            }
        });
    });

    // 3. Multi-Module Navigation Tab Switch Engine (SPA View Layer Pipeline)
    const sidebarAnchors = document.querySelectorAll(".nav-anchor");
    const layoutViews = document.querySelectorAll(".spa-view-layer");

    sidebarAnchors.forEach(anchor => {
        anchor.addEventListener("click", (event) => {
            event.preventDefault();
            sidebarAnchors.forEach(el => el.classList.remove("active"));
            layoutViews.forEach(el => el.classList.add("view-hidden"));

            anchor.classList.add("active");
            const structuralTargetId = anchor.getAttribute("data-target");
            document.getElementById(structuralTargetId).classList.remove("view-hidden");
        });
    });

    // 3. Alerts Popover Floating Panel Component Overlay Toggles Handles
    const dropdownTrigger = document.getElementById("alert-dropdown-btn");
    const popoverOverlay = document.getElementById("alerts-popup-overlay");

    dropdownTrigger.addEventListener("click", (e) => {
        e.stopPropagation();
        popoverOverlay.classList.toggle("view-hidden");
    });

    document.addEventListener("click", (e) => {
        if (!popoverOverlay.classList.contains("view-hidden") && !popoverOverlay.contains(e.target)) {
            popoverOverlay.classList.add("view-hidden");
        }
    });

    // 4. Color Framework Application Core Theme Inversion Routine
    const themeControlBtn = document.getElementById("global-theme-toggle");
    const documentHtmlElement = document.documentElement;

    // I-02: Theme Persistence — restore saved theme on page load
    const savedTheme = localStorage.getItem("pa-theme");
    if (savedTheme && (savedTheme === "dark" || savedTheme === "light")) {
        documentHtmlElement.setAttribute("data-theme", savedTheme);
    }

    themeControlBtn.addEventListener("click", () => {
        const currentlyActiveTheme = documentHtmlElement.getAttribute("data-theme");
        const inverseCalculatedTheme = currentlyActiveTheme === "dark" ? "light" : "dark";
        documentHtmlElement.setAttribute("data-theme", inverseCalculatedTheme);
        localStorage.setItem("pa-theme", inverseCalculatedTheme); // I-02: persist
        // Re-compile Graphic Widget options colors parameters dynamically
        refreshDashboardCharts(inverseCalculatedTheme);
    });

    // 5. Global Chart.js Subsystem Processing Loops Configuration Matrix
    let runtimeChartHandles = {};

    function initializeAllDashboardWidgets(themeContext) {
        if (typeof Chart === "undefined") {
            console.warn("Chart.js unavailable");
            return;
        }

        const isDarkThemeActive = themeContext === "dark";
        const gridBorderColor = isDarkThemeActive ? "#172033" : "#E2E8F0";
        const labelTextColor = isDarkThemeActive ? "#F4F5F7" : "#0F172A";

        // Setup 1: Home Dashboard Pie Configuration Widget
        const ctxHomePie = document.getElementById("homePieChart").getContext("2d");
        runtimeChartHandles.homePie = new Chart(ctxHomePie, {
            type: "doughnut",
            data: {
                labels: stateEngineData.charts.distribution.labels,
                datasets: [{
                    data: stateEngineData.charts.distribution.data,
                    backgroundColor: ["#3B82F6", "#F59E0B", "#EF4444"],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom", labels: { color: labelTextColor, font: { family: "Inter", size: 10 } } } }
            }
        });

        // Setup 2: Home Dashboard Market Conditions Strength Gauge Widget
        const ctxHomeGauge = document.getElementById("homeGaugeChart").getContext("2d");
        const innerStrengthDataValue = stateEngineData.market_state.market_strength;
        runtimeChartHandles.homeGauge = new Chart(ctxHomeGauge, {
            type: "doughnut",
            data: {
                datasets: [{
                    data: [innerStrengthDataValue, 100 - innerStrengthDataValue],
                    backgroundColor: ["#10B981", isDarkThemeActive ? "#172033" : "#E2E8F0"],
                    circumference: 180,
                    rotation: 270,
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "85%",
                plugins: { tooltip: { enabled: false }, legend: { display: false } }
            }
        });

        // Setup 3: Home Dashboard Historical Run Engine Breakouts Line Widget
        const ctxHomeLine = document.getElementById("homeLineChart").getContext("2d");
        runtimeChartHandles.homeLine = new Chart(ctxHomeLine, {
            type: "line",
            data: {
                labels: stateEngineData.charts.daily_signals.labels,
                datasets: [{
                    data: stateEngineData.charts.daily_signals.data,
                    borderColor: "#3B82F6",
                    backgroundColor: "rgba(59, 130, 246, 0.03)",
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { color: gridBorderColor }, ticks: { color: labelTextColor } },
                    y: { grid: { color: gridBorderColor }, ticks: { color: labelTextColor } }
                },
                plugins: { legend: { display: false } }
            }
        });

        // Setup 4: Portfolio Allocation Weight Matrix Pie Widget
        const ctxPortfolioPie = document.getElementById("portfolioPieChart").getContext("2d");
        runtimeChartHandles.portfolioPie = new Chart(ctxPortfolioPie, {
            type: "pie",
            data: {
                labels: stateEngineData.charts.asset_allocation.labels,
                datasets: [{
                    data: stateEngineData.charts.asset_allocation.data,
                    backgroundColor: ["#3B82F6", "#10B981", "#F59E0B", "#64748B"],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom", labels: { color: labelTextColor, font: { family: "Inter", size: 10 } } } }
            }
        });

        // Setup 5: Portfolio Compound Value Equity Growth Curve Line Widget
        const ctxPortfolioLine = document.getElementById("portfolioGrowthLineChart").getContext("2d");
        runtimeChartHandles.portfolioLine = new Chart(ctxPortfolioLine, {
            type: "line",
            data: {
                labels: stateEngineData.charts.portfolio_growth.labels,
                datasets: [{
                    data: stateEngineData.charts.portfolio_growth.data,
                    borderColor: "#10B981",
                    backgroundColor: "rgba(16, 185, 129, 0.03)",
                    fill: true,
                    tension: 0.2,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { color: gridBorderColor }, ticks: { color: labelTextColor } },
                    y: { grid: { color: gridBorderColor }, ticks: { color: labelTextColor } }
                },
                plugins: { legend: { display: false } }
            }
        });

        // Setup 6: VGX Virtual Balance Equity Curve — area line chart
        const vgxEquity = stateEngineData.vgx_overview && stateEngineData.vgx_overview.equity_curve
            ? stateEngineData.vgx_overview.equity_curve
            : { labels: ["Start"], data: [1000000] };

        const ctxVgxEquity = document.getElementById("vgxEquityChart");
        if (ctxVgxEquity) {
            runtimeChartHandles.vgxEquity = new Chart(ctxVgxEquity.getContext("2d"), {
                type: "line",
                data: {
                    labels: vgxEquity.labels,
                    datasets: [{
                        label: "Virtual Balance (₹)",
                        data: vgxEquity.data,
                        borderColor: "#3B82F6",
                        backgroundColor: "rgba(59, 130, 246, 0.08)",
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2.5,
                        pointRadius: vgxEquity.data.length > 30 ? 0 : 3,
                        pointHoverRadius: 5,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    scales: {
                        x: {
                            grid: { color: gridBorderColor },
                            ticks: {
                                color: labelTextColor,
                                maxTicksLimit: 8,
                                maxRotation: 0,
                                font: { size: 10 }
                            }
                        },
                        y: {
                            grid: { color: gridBorderColor },
                            ticks: {
                                color: labelTextColor,
                                font: { size: 10 },
                                callback: v => "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })
                            }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => "₹" + Number(ctx.parsed.y).toLocaleString("en-IN", { maximumFractionDigits: 2 })
                            }
                        }
                    }
                }
            });
        }

        // Setup 7: VGX Win / Loss Distribution — bar chart
        const vgxWL = stateEngineData.vgx_overview && stateEngineData.vgx_overview.win_loss_chart
            ? stateEngineData.vgx_overview.win_loss_chart
            : { labels: ["Wins", "Losses"], data: [0, 0] };

        const ctxVgxWL = document.getElementById("vgxWinLossChart");
        if (ctxVgxWL) {
            runtimeChartHandles.vgxWinLoss = new Chart(ctxVgxWL.getContext("2d"), {
                type: "bar",
                data: {
                    labels: vgxWL.labels,
                    datasets: [{
                        data: vgxWL.data,
                        backgroundColor: ["rgba(16, 185, 129, 0.75)", "rgba(239, 68, 68, 0.75)"],
                        borderColor:     ["#10B981", "#EF4444"],
                        borderWidth: 1.5,
                        borderRadius: 6,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { color: gridBorderColor }, ticks: { color: labelTextColor } },
                        y: {
                            grid: { color: gridBorderColor },
                            ticks: { color: labelTextColor, precision: 0 },
                            beginAtZero: true
                        }
                    },
                    plugins: { legend: { display: false } }
                }
            });
        }
    }

    function refreshDashboardCharts(themeContext) {
        Object.keys(runtimeChartHandles).forEach(key => {
            if (runtimeChartHandles[key]) runtimeChartHandles[key].destroy();
        });
        initializeAllDashboardWidgets(themeContext);
    }

    // Default system initialization trace run (uses current theme)
    const initialTheme = documentHtmlElement.getAttribute("data-theme") || "dark";
    initializeAllDashboardWidgets(initialTheme);

    // ═══════════════════════════════════════════════════════════════════════
    // I-05: Score Settings Persistence  +  I-01: Refresh Interval Config
    // ═══════════════════════════════════════════════════════════════════════
    const riskSelect = document.getElementById("settings-risk-profile");
    const refreshSelect = document.getElementById("settings-refresh-interval");
    const saveSettingsBtn = document.getElementById("settings-save-btn");

    // Load saved settings
    if (localStorage.getItem("pa-risk-profile")) {
        riskSelect.value = localStorage.getItem("pa-risk-profile");
    }
    if (localStorage.getItem("pa-refresh-interval")) {
        refreshSelect.value = localStorage.getItem("pa-refresh-interval");
    }

    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener("click", () => {
            localStorage.setItem("pa-risk-profile", riskSelect.value);
            localStorage.setItem("pa-refresh-interval", refreshSelect.value);
            // Show brief confirmation
            const originalText = saveSettingsBtn.textContent;
            saveSettingsBtn.textContent = "Saved ✓";
            saveSettingsBtn.style.backgroundColor = "var(--color-green)";
            setTimeout(() => {
                saveSettingsBtn.textContent = originalText;
                saveSettingsBtn.style.backgroundColor = "";
            }, 1500);
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // 6. Live Data Refresh Engine — replaces window.location.reload()
    //    Fetches /api/v1/state every 10s and patches only the changed DOM nodes
    //    and Chart.js datasets. No page reload. No flicker. No chart destruction.
    //    I-01: Refresh interval is configurable via settings
    // ─────────────────────────────────────────────────────────────────────────

    // Helper: find a metric-card by its h5 label text, return its value node (h2 or h3)
    function findCardValueNode(labelText) {
        const cards = document.querySelectorAll(".metric-card h5");
        for (const h5 of cards) {
            if (h5.textContent.trim() === labelText) {
                return h5.parentElement.querySelector("h2, h3");
            }
        }
        return null;
    }

    // Helper: find a card's footer <span class="text-white"> node by card label
    function findCardFooterSpan(labelText) {
        const cards = document.querySelectorAll(".metric-card h5");
        for (const h5 of cards) {
            if (h5.textContent.trim() === labelText) {
                return h5.parentElement.querySelector(".card-footer-metric .text-white");
            }
        }
        return null;
    }

    // Helper: update a Chart.js handle's labels and first dataset data in place
    function patchChart(handle, labels, data) {
        if (!handle) return;
        handle.data.labels = labels;
        handle.data.datasets[0].data = data;
        handle.update("none");   // "none" = skip animation for live updates
    }

    // Helper: update gauge chart (two-segment) and its readout digit text
    function patchGauge(handle, strength) {
        if (!handle) return;
        handle.data.datasets[0].data = [strength, 100 - strength];
        handle.update("none");
        const readout = document.querySelector(".gauge-readout-digits");
        if (readout) readout.textContent = strength + "%";
    }

    // Return a human-readable relative age string (e.g. "4m ago", "2h ago")
    function timeAgo(isoString) {
        if (!isoString) return "—";
        try {
            const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
            if (diff < 0)    return "just now";
            if (diff < 60)   return diff + "s ago";
            if (diff < 3600) return Math.floor(diff / 60) + "m ago";
            if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
            return Math.floor(diff / 86400) + "d ago";
        } catch (e) { return "—"; }
    }

    // Helper: rebuild the signals table tbody from fresh recent_signals array
    function patchSignalTable(signals) {
        const scannerView = document.getElementById("scanner-view");
        if (!scannerView) return;
        const tbody = scannerView.querySelector("table tbody");
        if (!tbody) return;

        if (!signals || signals.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;opacity:0.5;">No active signals</td></tr>';
            return;
        }

        tbody.innerHTML = signals.map(trace => `
            <tr>
                <td><strong>${trace.coin || ""}</strong></td>
                <td>${trace.category || ""}</td>
                <td>${trace.score || 0}</td>
                <td>${trace.signal_price || 0}</td>
                <td>${trace.market || "INR"}</td>
                <td>${trace.timestamp || ""}</td>
                <td>${trace.market_state || ""}</td>
                <td style="color:var(--text-muted);font-size:0.85em;white-space:nowrap;">${timeAgo(trace.timestamp)}</td>
            </tr>
        `).join("");
    }

    async function refreshDashboardData() {
        try {
            const response = await fetch("/api/v1/state");
            if (!response.ok) return;   // silently skip on non-200; retry next interval
            const data = await response.json();

            // ── Scanner stat cards (home view + scanner view) ──────────────
            const marketCount = document.getElementById("market-assets-count");
            if (marketCount) marketCount.textContent = data.scanner_overview.coins_scanned || 0;

            const footerScan = findCardFooterSpan("Scanner Processing Efficiency Matrix");
            if (footerScan) footerScan.textContent = data.scanner_overview.last_scan_time || "LIVE";

            const eliteNode  = document.getElementById("so-elite-signals")  || findCardValueNode("Elite Signals");
            const highNode   = document.getElementById("so-high-signals")   || findCardValueNode("High Signals");
            const mediumNode = document.getElementById("so-medium-signals") || findCardValueNode("Medium Signals");
            if (eliteNode)  eliteNode.textContent  = data.scanner_overview.elite_signals  || 0;
            if (highNode)   highNode.textContent   = data.scanner_overview.high_signals   || 0;
            if (mediumNode) mediumNode.textContent = data.scanner_overview.medium_signals || 0;

            // ── I-04: Cleanup engine stat cards ───────────────────────────
            const activeNode   = document.getElementById("so-active-signals");
            const expiredNode  = document.getElementById("so-expired-signals");
            const lastCleanEl  = document.getElementById("so-last-cleanup");
            const nextCleanEl  = document.getElementById("so-next-cleanup");

            if (activeNode)  activeNode.textContent  = data.scanner_overview.active_signals  || 0;
            if (expiredNode) expiredNode.textContent = data.scanner_overview.expired_signals || 0;

            if (lastCleanEl) {
                const lct = data.scanner_overview.last_cleanup_time;
                if (lct) {
                    try {
                        const ago = _relativeTime(new Date(lct));
                        lastCleanEl.textContent = ago;
                    } catch(e) { lastCleanEl.textContent = "—"; }
                } else {
                    lastCleanEl.textContent = "Pending";
                }
            }

            // Store next cleanup ISO time for countdown ticker
            if (data.scanner_overview.next_cleanup_time) {
                window._nextCleanupTs = new Date(data.scanner_overview.next_cleanup_time).getTime();
            }

            // ── I-05: Health monitor card ────────────────────────────────
            if (data.scanner_overview) {
                const apiStatus = document.getElementById("sh-api-status");
                if (apiStatus) {
                    apiStatus.textContent = data.scanner_overview.api_status || "ONLINE";
                    apiStatus.className = "text-" + (data.scanner_overview.health_color || "green");
                }
                const hScore = document.getElementById("sh-health-score");
                if (hScore) {
                    hScore.textContent = (data.scanner_overview.health_score || 100) + "%";
                    hScore.className = "text-" + (data.scanner_overview.health_color || "green");
                }
                const tScan = document.getElementById("sh-total-scans");
                if (tScan) tScan.textContent = data.scanner_overview.total_scans || 0;
                const fScan = document.getElementById("sh-failed-scans");
                if (fScan) fScan.textContent = data.scanner_overview.failed_scans || 0;
                const cFail = document.getElementById("sh-consecutive-failures");
                if (cFail) cFail.textContent = data.scanner_overview.consecutive_failures || 0;
                const sDur = document.getElementById("sh-scan-duration");
                if (sDur) sDur.textContent = (data.scanner_overview.scan_duration_ms || 0) + " ms";
                const mStat = document.getElementById("sh-market-status");
                if (mStat) mStat.textContent = data.scanner_overview.current_market_status || "ACTIVE";
                const lScan = document.getElementById("sh-last-scan");
                if (lScan && data.scanner_overview.last_successful_scan) {
                    lScan.textContent = timeAgo(data.scanner_overview.last_successful_scan);
                }
                // I-07: Recovery card
                const rTime = document.getElementById("sh-restart-time");
                if (rTime) rTime.textContent = data.scanner_overview.last_restart_time || "—";
                const rSig = document.getElementById("sh-recovered-signals");
                if (rSig) rSig.textContent = data.scanner_overview.recovered_signals || 0;
                const rStat = document.getElementById("sh-recovery-status");
                if (rStat) {
                    rStat.textContent = data.scanner_overview.recovery_status || "SUCCESS";
                    rStat.className = (data.scanner_overview.recovery_status === "SUCCESS" ? "text-green" : "text-red");
                }
            }

            // ── Alerts badge ───────────────────────────────────────────────
            const alertBadge = document.querySelector(".alert-counter-badge");
            if (alertBadge) alertBadge.textContent = (data.notifications || []).length;

            // ── Charts: distribution doughnut ──────────────────────────────
            if (data.charts && data.charts.distribution) {
                patchChart(
                    runtimeChartHandles.homePie,
                    data.charts.distribution.labels,
                    data.charts.distribution.data
                );
            }

            // ── Charts: gauge + readout digit ─────────────────────────────
            if (data.market_state) {
                patchGauge(
                    runtimeChartHandles.homeGauge,
                    data.market_state.market_strength || 0
                );
            }

            // ── Charts: daily signals line ─────────────────────────────────
            if (data.charts && data.charts.daily_signals) {
                patchChart(
                    runtimeChartHandles.homeLine,
                    data.charts.daily_signals.labels,
                    data.charts.daily_signals.data
                );
            }

            // ── Charts: asset allocation pie ───────────────────────────────
            if (data.charts && data.charts.asset_allocation) {
                patchChart(
                    runtimeChartHandles.portfolioPie,
                    data.charts.asset_allocation.labels,
                    data.charts.asset_allocation.data
                );
            }

            // ── Charts: portfolio growth line ──────────────────────────────
            if (data.charts && data.charts.portfolio_growth) {
                patchChart(
                    runtimeChartHandles.portfolioLine,
                    data.charts.portfolio_growth.labels,
                    data.charts.portfolio_growth.data
                );
            }

            // ── VGX equity curve ───────────────────────────────────────────
            if (data.vgx_overview && data.vgx_overview.equity_curve) {
                patchChart(
                    runtimeChartHandles.vgxEquity,
                    data.vgx_overview.equity_curve.labels,
                    data.vgx_overview.equity_curve.data
                );
            }

            // ── VGX win/loss bar chart ─────────────────────────────────────
            if (data.vgx_overview && data.vgx_overview.win_loss_chart) {
                patchChart(
                    runtimeChartHandles.vgxWinLoss,
                    data.vgx_overview.win_loss_chart.labels,
                    data.vgx_overview.win_loss_chart.data
                );
            }

            // ── VGX stat cards (vgx-view) ──────────────────────────────────
            const vgxBalNode = findCardValueNode("Virtual Balance");
            if (vgxBalNode && data.vgx_overview) {
                vgxBalNode.textContent = "₹" + Number(data.vgx_overview.virtual_balance).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }
            const vgxWrNode = findCardValueNode("Win Rate");
            if (vgxWrNode && data.vgx_overview) {
                vgxWrNode.textContent = data.vgx_overview.win_rate + "%";
            }

            // ── Signal table rows ──────────────────────────────────────────
            patchSignalTable(data.recent_signals || []);

            // ── Scanner watchlist count ────────────────────────────────────
            if (data.scanner_overview) {
                const scannerWlCount = document.getElementById("scanner-watchlist-count");
                if (scannerWlCount) scannerWlCount.textContent = data.scanner_overview.coins_scanned || 0;
            }

            // ── Performance Tracker cards ──────────────────────────────────
            if (data.performance_stats) {
                const ps = data.performance_stats;
                const totalNode = findCardValueNode("Total Signals");
                if (totalNode) totalNode.textContent = ps.total_signals || 0;
                const winNode = findCardValueNode("Winning Signals");
                if (winNode) winNode.textContent = ps.winning_signals || 0;
                const lossNode = findCardValueNode("Losing Signals");
                if (lossNode) lossNode.textContent = ps.losing_signals || 0;
                const wrNode = findCardValueNode("Win Rate %");
                if (wrNode) {
                    wrNode.textContent = (ps.win_rate_pct || 0) + "%";
                    wrNode.className = (ps.win_rate_pct >= 50 ? "text-green" : "text-red") + " h2";
                }
                const avgNode = findCardValueNode("Average Return %");
                if (avgNode) {
                    avgNode.textContent = (ps.avg_return_pct || 0) + "%";
                    avgNode.className = (ps.avg_return_pct >= 0 ? "text-green" : "text-red") + " h2";
                }
                const bestNode = findCardValueNode("Best Signal");
                if (bestNode && ps.best_signal) {
                    bestNode.textContent = (ps.best_signal.coin || "—") + " " + (ps.best_signal.return_pct || 0) + "%";
                }
                const worstNode = findCardValueNode("Worst Signal");
                if (worstNode && ps.worst_signal) {
                    worstNode.textContent = (ps.worst_signal.coin || "—") + " " + (ps.worst_signal.return_pct || 0) + "%";
                }
            }

            // ── Performance Tracker table ────────────────────────────────
            if (data.performance_signals) {
                const tbody = document.getElementById("performance-table-body");
                if (tbody) {
                    const sigs = data.performance_signals;
                    if (!sigs || sigs.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="11" class="text-muted">No evaluated signals yet — signals will appear as 1H/4H/24H/3D/7D horizons mature.</td></tr>';
                    } else {
                        tbody.innerHTML = sigs.map(s => {
                            const color = pct => pct >= 0 ? 'text-green' : 'text-red';
                            const badge = s.result === 'WIN' ? 'signal-type-elite' : 'color-indicator-error';
                            return `<tr>
                                <td><strong>${s.coin || ""}</strong></td>
                                <td class="text-muted text-sm">${s.timestamp || ""}</td>
                                <td>${s.signal_price || 0}</td>
                                <td>${s.current_price || 0}</td>
                                <td class="${color(s['1h_pct'])}">${s['1h_pct']}%</td>
                                <td class="${color(s['4h_pct'])}">${s['4h_pct']}%</td>
                                <td class="${color(s['24h_pct'])}">${s['24h_pct']}%</td>
                                <td class="${color(s['3d_pct'])}">${s['3d_pct']}%</td>
                                <td class="${color(s['7d_pct'])}">${s['7d_pct']}%</td>
                                <td class="${color(s.return_pct)}">${s.return_pct}%</td>
                                <td><span class="row-badge-pill ${badge}">${s.result}</span></td>
                            </tr>`;
                        }).join("");
                    }
                }
            }

            // ── Signal History cards ──────────────────────────────────────
            if (data.signal_history_stats) {
                const hs = data.signal_history_stats;
                const totalNode = findCardValueNode("History Signals");
                if (totalNode) totalNode.textContent = hs.total || 0;
                const winNode = findCardValueNode("Winners");
                if (winNode) winNode.textContent = hs.winners || 0;
                const lossNode = findCardValueNode("Losers");
                if (lossNode) lossNode.textContent = hs.losers || 0;
                const wrNode = findCardValueNode("Win Rate %");
                if (wrNode) {
                    wrNode.textContent = (hs.win_rate_pct || 0) + "%";
                    wrNode.className = (hs.win_rate_pct >= 50 ? "text-green" : "text-red") + " h2";
                }
                const avgNode = findCardValueNode("Avg Return %");
                if (avgNode) {
                    avgNode.textContent = (hs.avg_return_pct || 0) + "%";
                    avgNode.className = (hs.avg_return_pct >= 0 ? "text-green" : "text-red") + " h2";
                }
                const recNode = findCardValueNode("Records");
                if (recNode) recNode.textContent = hs.total || 0;
                const countLabel = document.getElementById("sh-count-label");
                if (countLabel && data.signal_history) countLabel.textContent = (data.signal_history.length || 0) + " records";
            }

            // ── Signal History table ──────────────────────────────────────
            if (data.signal_history) {
                const tbody = document.getElementById("signal-history-table-body");
                if (tbody) {
                    const all = data.signal_history || [];
                    let filtered = all;
                    const filterVal = document.getElementById("sh-filter")?.value || "ALL";
                    const searchVal = (document.getElementById("sh-search")?.value || "").trim().toUpperCase();
                    if (filterVal !== "ALL") {
                        filtered = filtered.filter(s => s.result === filterVal);
                    }
                    if (searchVal) {
                        filtered = filtered.filter(s => (s.coin || "").toUpperCase().includes(searchVal));
                    }
                    const sortVal = document.getElementById("sh-sort")?.value || "newest";
                    if (sortVal === "newest") {
                        filtered.sort((a, b) => (b.timestamp || "").localeCompare(a.timestamp || ""));
                    } else if (sortVal === "oldest") {
                        filtered.sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));
                    } else if (sortVal === "return") {
                        filtered.sort((a, b) => (b.return_pct || 0) - (a.return_pct || 0));
                    } else if (sortVal === "worst") {
                        filtered.sort((a, b) => (a.return_pct || 0) - (b.return_pct || 0));
                    }
                    if (filtered.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="12" class="text-muted">No history matches the current filter.</td></tr>';
                    } else {
                        tbody.innerHTML = filtered.map(s => {
                            const color = pct => pct >= 0 ? 'text-green' : 'text-red';
                            const badge = s.result === 'WIN' ? 'signal-type-elite' : 'color-indicator-error';
                            return `<tr>
                                <td><strong>${s.coin || ""}</strong></td>
                                <td class="text-muted text-sm">${s.timestamp || ""}</td>
                                <td>${s.score || 0}</td>
                                <td>${s.tier || ""}</td>
                                <td>${s.signal_price || 0}</td>
                                <td class="${color(s['1h_pct'])}">${s['1h_pct']}%</td>
                                <td class="${color(s['4h_pct'])}">${s['4h_pct']}%</td>
                                <td class="${color(s['24h_pct'])}">${s['24h_pct']}%</td>
                                <td class="${color(s['3d_pct'])}">${s['3d_pct']}%</td>
                                <td class="${color(s['7d_pct'])}">${s['7d_pct']}%</td>
                                <td class="${color(s.return_pct)}">${s.return_pct}%</td>
                                <td><span class="row-badge-pill ${badge}">${s.result}</span></td>
                            </tr>`;
                        }).join("");
                    }
                }
            }

            // ── Coin Performance cards ───────────────────────────────────
            if (data.coin_performance_stats) {
                const cps = data.coin_performance_stats;
                const ctNode = findCardValueNode("Coins Tracked");
                if (ctNode) ctNode.textContent = cps.coins_tracked || 0;
                const tsNode = findCardValueNode("Total Signals");
                if (tsNode) tsNode.textContent = cps.total_signals || 0;
                const winNode = findCardValueNode("Winning Signals");
                if (winNode) winNode.textContent = cps.winning_signals || 0;
                const lossNode = findCardValueNode("Losing Signals");
                if (lossNode) lossNode.textContent = cps.losing_signals || 0;
                const wrNode = findCardValueNode("Win Rate %");
                if (wrNode) {
                    wrNode.textContent = (cps.win_rate_pct || 0) + "%";
                    wrNode.className = (cps.win_rate_pct >= 50 ? "text-green" : "text-red") + " h2";
                }
                const recNode = findCardValueNode("Records");
                if (recNode) recNode.textContent = cps.coins_tracked || 0;
                const countLabel = document.getElementById("cp-count-label");
                if (countLabel && data.coin_performance_data) countLabel.textContent = (data.coin_performance_data.length || 0) + " coins";
            }

            // ── Coin Performance table ───────────────────────────────────
            if (data.coin_performance_data) {
                const tbody = document.getElementById("coin-performance-table-body");
                if (tbody) {
                    let rows = data.coin_performance_data || [];
                    const searchVal = (document.getElementById("cp-search")?.value || "").trim().toUpperCase();
                    if (searchVal) {
                        rows = rows.filter(r => (r.coin || "").toUpperCase().includes(searchVal));
                    }
                    const sortVal = document.getElementById("cp-sort")?.value || "winrate";
                    if (sortVal === "winrate") {
                        rows.sort((a, b) => (b.win_rate_pct || 0) - (a.win_rate_pct || 0));
                    } else if (sortVal === "signals") {
                        rows.sort((a, b) => (b.total_signals || 0) - (a.total_signals || 0));
                    } else if (sortVal === "best") {
                        rows.sort((a, b) => (b.best_return_pct || 0) - (a.best_return_pct || 0));
                    } else if (sortVal === "worst") {
                        rows.sort((a, b) => (a.worst_return_pct || 0) - (b.worst_return_pct || 0));
                    }
                    if (rows.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="9" class="text-muted">No coin data matches the current filter.</td></tr>';
                    } else {
                        tbody.innerHTML = rows.map(r => {
                            const color = pct => pct >= 0 ? 'text-green' : 'text-red';
                            return `<tr>
                                <td><strong>${r.coin || ""}</strong></td>
                                <td>${r.total_signals || 0}</td>
                                <td class="text-green">${r.winning_signals || 0}</td>
                                <td class="text-red">${r.losing_signals || 0}</td>
                                <td class="${color(r.win_rate_pct)}">${r.win_rate_pct}%</td>
                                <td class="${color(r.avg_return_pct)}">${r.avg_return_pct}%</td>
                                <td class="text-green">${r.best_return_pct}%</td>
                                <td class="text-red">${r.worst_return_pct}%</td>
                                <td class="text-muted text-sm">${r.last_signal_time || "—"}</td>
                            </tr>`;
                        }).join("");
                    }
                }
            }

        } catch (err) {
            // Network error or JSON parse failure — skip silently, retry next interval
            console.warn("[ProjectA] Dashboard refresh failed:", err.message);
        }
    }

    // I-01: Auto-refresh live data using configurable interval — no page reload
    function getRefreshIntervalMs() {
        const raw = localStorage.getItem("pa-refresh-interval");
        const ms = raw ? parseInt(raw, 10) : 10000;
        return (ms > 0) ? ms : 0;
    }
    const refreshIntervalId = setInterval(refreshDashboardData, getRefreshIntervalMs());
    // If user changes interval to >0, restart the interval
    if (refreshSelect) {
        refreshSelect.addEventListener("change", () => {
            const newMs = parseInt(refreshSelect.value, 10);
            if (newMs > 0) {
                clearInterval(refreshIntervalId);
                setInterval(refreshDashboardData, newMs);
                localStorage.setItem("pa-refresh-interval", newMs);
            }
        });
    }

    // ═══════════════════════════════════════════════════════════════
    //  Signal History — interactive filter / sort / search
    // ═══════════════════════════════════════════════════════════════
    const shSearch = document.getElementById("sh-search");
    const shFilter = document.getElementById("sh-filter");
    const shSort   = document.getElementById("sh-sort");
    function attachHistoryListeners() {
        if (!shSearch || !shFilter || !shSort) return;
        const rerender = () => refreshDashboardData();
        shSearch.addEventListener("input", rerender);
        shFilter.addEventListener("change", rerender);
        shSort.addEventListener("change", rerender);
    }
    attachHistoryListeners();

    // ═══════════════════════════════════════════════════════════════
    //  Coin Performance — interactive search / sort
    // ═══════════════════════════════════════════════════════════════
    const cpSearch = document.getElementById("cp-search");
    const cpSort   = document.getElementById("cp-sort");
    function attachCoinPerformanceListeners() {
        if (!cpSearch || !cpSort) return;
        const rerender = () => refreshDashboardData();
        cpSearch.addEventListener("input", rerender);
        cpSort.addEventListener("change", rerender);
    }
    attachCoinPerformanceListeners();

    // ═══════════════════════════════════════════════════════════════
    //  Watchlist Center — Add / Remove Coins
    // ═══════════════════════════════════════════════════════════════

    // I-08: Manual refresh scanner
    window.refreshScanner = async function() {
        const msg = document.getElementById("scanner-refresh-msg");
        if (msg) { msg.style.display = "none"; msg.textContent = ""; msg.style.color = "#ff4444"; }
        try {
            const resp = await fetch("/api/scanner/refresh", { method: "POST" });
            const data = await resp.json();
            if (data.success) {
                if (msg) {
                    msg.textContent = "Scanner Updated Successfully";
                    msg.style.color = "#44ff44";
                    msg.style.display = "block";
                    setTimeout(() => { msg.style.display = "none"; }, 3000);
                }
                refreshDashboardData();
            } else {
                if (msg) {
                    msg.textContent = "Scanner Refresh Failed";
                    msg.style.display = "block";
                    setTimeout(() => { msg.style.display = "none"; }, 5000);
                }
            }
        } catch (e) {
            if (msg) {
                msg.textContent = "Scanner Refresh Failed";
                msg.style.display = "block";
                setTimeout(() => { msg.style.display = "none"; }, 5000);
            }
        }
    };

    window.addCoin = async function() {
        const input = document.getElementById("scanner-add-input");
        const errorDiv = document.getElementById("scanner-add-error");
        const coin = input.value.trim().toUpperCase();

        if (errorDiv) { errorDiv.style.display = "none"; errorDiv.textContent = ""; }
        if (!coin) {
            if (errorDiv) { errorDiv.textContent = "Enter a coin symbol"; errorDiv.style.display = "block"; }
            return;
        }

        try {
            const resp = await fetch("/api/watchlist/add", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({coin}),
            });
            const data = await resp.json();
            if (data.success) {
                input.value = "";
                if (errorDiv) { errorDiv.style.display = "none"; errorDiv.textContent = ""; }
                refreshWatchlistTable();
            } else {
                const msg = data.error || "Add failed";
                if (errorDiv) {
                    errorDiv.textContent = msg;
                    errorDiv.style.display = "block";
                    setTimeout(() => { errorDiv.style.display = "none"; errorDiv.textContent = ""; }, 5000);
                }
            }
        } catch (e) {
            if (errorDiv) {
                errorDiv.textContent = "Network error — please try again";
                errorDiv.style.display = "block";
                setTimeout(() => { errorDiv.style.display = "none"; }, 5000);
            }
        }
    };

    window.removeCoin = async function(coin) {
        if (!confirm("Remove " + coin + " from Scanner Watchlist?")) return;
        try {
            const resp = await fetch("/api/watchlist/remove", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({coin}),
            });
            const data = await resp.json();
            if (data.success) {
                refreshWatchlistTable();
            } else {
                alert("Remove failed: " + (data.error || "unknown"));
            }
        } catch (e) {
            alert("Network error: " + e.message);
        }
    };

    // Wire up remove buttons via event delegation
    document.addEventListener("click", function(e) {
        const btn = e.target.closest(".btn-remove-coin");
        if (!btn) return;
        const coin = btn.dataset.coin;
        if (coin) removeCoin(coin);
    });

    async function refreshWatchlistTable() {
        try {
            const resp = await fetch("/api/watchlist");
            const data = await resp.json();
            const coins = data.coins || [];
            const countNode = document.getElementById("scanner-coin-count");
            if (countNode) countNode.textContent = coins.length;
            const tbody = document.getElementById("scanner-coin-table");
            if (!tbody) return;
            tbody.innerHTML = coins.length === 0
                ? '<tr><td colspan="2" class="text-muted">No coins</td></tr>'
                : coins.map(c => '<tr><td><strong>' + c + '/INR</strong></td><td><button class="btn-remove-coin" data-coin="' + c + '">REMOVE</button></td></tr>').join("");
            const totalNode = document.getElementById("total-coin-count");
            if (totalNode) totalNode.textContent = coins.length;
        } catch (err) {
            console.warn("[ProjectA] Watchlist refresh failed:", err.message);
        }
    }
});
