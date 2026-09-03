"""
PROJECT-ALPHA V2: QUANTITATIVE CRYPTO TRADING AGENT DASHBOARD (app_quant_ui.py).

[DEMO / STANDALONE SIMULATOR UI — ISOLATED FROM V2 PRODUCTION EXECUTION]
NOTE: This file is a standalone simulation prototype running on port 8000.
The authoritative production V2 system runs via `v2/app_v2.py` on port 5001.
Do NOT mistake in-memory ticks/positions in this file for production SQLite state.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Project Alpha V2 - Crypto Mode Mission Control")


# ── REST Models ───────────────────────────────────────────────────────────────

class CryptoOrderRequest(BaseModel):
    pair: str
    bot_name: str = "STE"
    direction: str = "BUY"
    amount_inr: float = 200.0
    order_type: str = "MARKET"


class PositionItem(BaseModel):
    id: str
    bot: str
    coin: str
    pair: str
    qty: float
    entry_price: float
    ltp: float
    unrealized_pnl_gross: float
    unrealized_pnl_net: float
    friction_cost: float
    stop_loss: float
    take_profit: float
    mode: str
    cluster: str


# ── In-Memory Crypto State ───────────────────────────────────────────────────

CRYPTO_STATE = {
    "capital_pool_limit": 10000.0,
    "capital_deployed": 600.0,
    "capital_available": 9400.0,
    "total_equity": 10452.80,
    "day_pnl_net": 452.80,
    "day_pnl_pct": 4.53,
    "friction_drag_deducted": 38.60,
    "sharpe": 2.92,
    "sortino": 3.15,
    "max_drawdown_pct": -0.65,
    "market_status": "24/7 LIVE (CoinDCX Spot)",
    "regime": "RISK-ON MOMENTUM",
    "deployment_mode": "SHADOW",
    "circuit_breaker": "NORMAL",
    "positions": [
        {
            "id": "POS-SOL-001",
            "bot": "STE",
            "coin": "SOL",
            "pair": "SOL/INR",
            "qty": 0.0197,
            "entry_price": 10140.00,
            "ltp": 10380.00,
            "unrealized_pnl_gross": 4.73,
            "unrealized_pnl_net": 3.18,
            "friction_cost": 1.55,
            "stop_loss": 9980.00,
            "take_profit": 10450.00,
            "mode": "SHADOW",
            "cluster": "L1 BLUECHIPS",
        },
        {
            "id": "POS-NEAR-002",
            "bot": "HDA",
            "coin": "NEAR",
            "pair": "NEAR/INR",
            "qty": 0.54,
            "entry_price": 370.00,
            "ltp": 384.50,
            "unrealized_pnl_gross": 7.83,
            "unrealized_pnl_net": 4.71,
            "friction_cost": 3.12,
            "stop_loss": 358.00,
            "take_profit": 395.00,
            "mode": "SHADOW",
            "cluster": "AI & COMPUTE",
        },
        {
            "id": "POS-ETH-003",
            "bot": "VCP",
            "coin": "ETH",
            "pair": "ETH/INR",
            "qty": 0.0008,
            "entry_price": 248000.00,
            "ltp": 251200.00,
            "unrealized_pnl_gross": 2.56,
            "unrealized_pnl_net": 0.98,
            "friction_cost": 1.58,
            "stop_loss": 244000.00,
            "take_profit": 256000.00,
            "mode": "SHADOW",
            "cluster": "L1 BLUECHIPS",
        },
    ],
    "sectors": [
        {"name": "L1 BLUECHIPS (BTC, ETH, SOL)", "change_pct": 4.8, "rank": "LEADER", "status": "BULLISH"},
        {"name": "AI & COMPUTE (NEAR, FET, RENDER)", "change_pct": 6.2, "rank": "LEADER", "status": "EXPANSION"},
        {"name": "DEFI & ORACLES (AAVE, UNI, LINK)", "change_pct": 1.4, "rank": "NEUTRAL", "status": "CONSOLIDATING"},
        {"name": "MEME & HIGH-BETA (DOGE, SHIB, PEPE)", "change_pct": -0.8, "rank": "LAGGARD", "status": "DISTRIBUTION"},
    ],
    "pairs": [
        {
            "pair": "SOL/INR vs BTC/INR",
            "z_score": 2.15,
            "hedge_ratio": 1.35,
            "bot": "STE",
            "status": "SHORT SPREAD",
            "action": "ACTIVE_RUN",
        },
        {
            "pair": "NEAR/INR vs FET/INR",
            "z_score": -1.85,
            "hedge_ratio": 1.12,
            "bot": "HDA",
            "status": "LONG SPREAD",
            "action": "ACTIVE_RUN",
        },
        {
            "pair": "ETH/INR vs BTC/INR",
            "z_score": -0.35,
            "hedge_ratio": 0.92,
            "bot": "VCP",
            "status": "MEAN REVERTED",
            "action": "MONITORING",
        },
        {
            "pair": "DOGE/INR vs SHIB/INR",
            "z_score": 1.10,
            "hedge_ratio": 0.78,
            "bot": "BBS",
            "status": "SQUEEZE BUILDUP",
            "action": "SCANNING",
        },
    ],
}


# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/v1/summary")
def get_crypto_summary() -> Dict[str, Any]:
    """Returns Crypto Portfolio Equity, Unified Capital Headroom, Net PnL, and Friction Drag."""
    return {
        "capital_pool_limit": CRYPTO_STATE["capital_pool_limit"],
        "capital_deployed": CRYPTO_STATE["capital_deployed"],
        "capital_available": CRYPTO_STATE["capital_available"],
        "total_equity": CRYPTO_STATE["total_equity"],
        "day_pnl_net": CRYPTO_STATE["day_pnl_net"],
        "day_pnl_pct": CRYPTO_STATE["day_pnl_pct"],
        "friction_drag_deducted": CRYPTO_STATE["friction_drag_deducted"],
        "sharpe": CRYPTO_STATE["sharpe"],
        "sortino": CRYPTO_STATE["sortino"],
        "max_drawdown_pct": CRYPTO_STATE["max_drawdown_pct"],
        "market_status": CRYPTO_STATE["market_status"],
        "regime": CRYPTO_STATE["regime"],
        "deployment_mode": CRYPTO_STATE["deployment_mode"],
        "circuit_breaker": CRYPTO_STATE["circuit_breaker"],
    }


@app.get("/api/v1/positions")
def get_crypto_positions() -> List[Dict[str, Any]]:
    """Returns array of open crypto positions with gross vs net P&L and friction deductions."""
    return CRYPTO_STATE["positions"]


@app.get("/api/v1/sectors")
def get_crypto_sectors() -> List[Dict[str, Any]]:
    """Returns crypto sector cluster momentum ranking and relative strength."""
    return CRYPTO_STATE["sectors"]


@app.get("/api/v1/pairs")
def get_crypto_pairs() -> List[Dict[str, Any]]:
    """Returns cointegrated crypto cross-pairs, hedge ratios, and spread z-scores."""
    return CRYPTO_STATE["pairs"]


@app.post("/api/v1/orders")
def submit_crypto_order(order: CryptoOrderRequest) -> Dict[str, Any]:
    """Submit a micro-trade order (₹200 base notional) with Single-Coin Lock verification."""
    if CRYPTO_STATE["circuit_breaker"] == "TRIPPED":
        return {"success": False, "error": "CIRCUIT_BREAKER_TRIPPED", "message": "Outbound orders blocked by Kill Switch."}

    coin_clean = order.pair.split("/")[0].upper()

    # 1. Enforce Single-Coin Global Asset Lock
    for pos in CRYPTO_STATE["positions"]:
        if pos["coin"].upper() == coin_clean:
            return {
                "success": False,
                "error": "OPPORTUNITY_LOCKED_ACTIVE_PAIR",
                "message": f"Asset {coin_clean} already locked by active position in {pos['bot']}.",
            }

    # 2. Enforce Headroom Availability
    if order.amount_inr > CRYPTO_STATE["capital_available"]:
        return {
            "success": False,
            "error": "INSUFFICIENT_POOL_HEADROOM",
            "message": f"Requested ₹{order.amount_inr:.2f} exceeds available headroom ₹{CRYPTO_STATE['capital_available']:.2f}.",
        }

    ltp = 500.0
    qty = round(order.amount_inr / ltp, 4)
    new_pos = {
        "id": f"POS-{coin_clean}-{int(time.time()*1000)%1000:03d}",
        "bot": order.bot_name.upper(),
        "coin": coin_clean,
        "pair": order.pair.upper(),
        "qty": qty,
        "entry_price": ltp,
        "ltp": ltp,
        "unrealized_pnl_gross": 0.0,
        "unrealized_pnl_net": -round(order.amount_inr * 0.01572, 2),
        "friction_cost": round(order.amount_inr * 0.01572, 2),
        "stop_loss": round(ltp * 0.98, 2),
        "take_profit": round(ltp * 1.04, 2),
        "mode": CRYPTO_STATE["deployment_mode"],
        "cluster": "CUSTOM",
    }
    CRYPTO_STATE["positions"].append(new_pos)
    CRYPTO_STATE["capital_deployed"] += order.amount_inr
    CRYPTO_STATE["capital_available"] -= order.amount_inr

    return {"success": True, "order_id": f"ORD-COINDCX-{int(time.time()*1000)}", "position": new_pos}


@app.post("/api/v1/emergency-kill")
def emergency_crypto_kill() -> Dict[str, Any]:
    """Emergency Kill Switch: Square off all open crypto positions and lock order gateway."""
    CRYPTO_STATE["circuit_breaker"] = "TRIPPED"
    closed_count = len(CRYPTO_STATE["positions"])
    CRYPTO_STATE["positions"] = []
    CRYPTO_STATE["capital_available"] += CRYPTO_STATE["capital_deployed"]
    CRYPTO_STATE["capital_deployed"] = 0.0
    return {
        "success": True,
        "circuit_breaker": "TRIPPED",
        "closed_positions_count": closed_count,
        "message": "🚨 Crypto Emergency Liquidation Complete. All positions closed and locked.",
    }


# ── WebSockets ────────────────────────────────────────────────────────────────

@app.websocket("/ws/ticks")
async def websocket_crypto_ticks(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(2.0)
            tick_data = {
                "type": "CRYPTO_TICK",
                "pair": "SOL/INR",
                "price": round(10380.00 + (time.time() % 4 - 2) * 5.0, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await websocket.send_text(json.dumps(tick_data))
    except (WebSocketDisconnect, Exception):
        pass


@app.websocket("/ws/signals")
async def websocket_crypto_signals(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(4.0)
            sig_data = {
                "strategy": "CRYPTO_CONFLUENCE_SCORE",
                "pair": "SOL/INR",
                "bot": "STE",
                "score": 89,
                "ai_verdict": "APPROVE (87% Conf)",
                "z_score": round(2.15 + (time.time() % 2 - 1) * 0.05, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await websocket.send_text(json.dumps(sig_data))
    except (WebSocketDisconnect, Exception):
        pass


# ── Crypto Mode HTML Dashboard ────────────────────────────────────────────────

CRYPTO_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PROJECT-ALPHA V2 | Crypto Quantitative Mission Control</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', system-ui, sans-serif; background-color: #0f172a; color: #f8fafc; }
        .mono { font-family: 'JetBrains Mono', monospace; }
    </style>
</head>
<body class="p-4 space-y-4">

    <!-- Top Status Bar -->
    <header class="flex flex-wrap justify-between items-center bg-slate-800 p-4 rounded-xl border border-slate-700 gap-4 shadow-lg">
        <div class="flex items-center space-x-3">
            <span class="relative flex h-3 w-3">
              <span id="pulse-ping" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span id="pulse-dot" class="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
            <div>
                <h1 class="text-xl font-bold tracking-wide flex items-center gap-2">
                    PROJECT-ALPHA <span class="text-xs bg-indigo-500/20 text-indigo-400 border border-indigo-500/40 px-2 py-0.5 rounded font-mono">CRYPTO MODE V2</span>
                </h1>
                <p class="text-xs text-slate-400">Institutional Fleet: STE (SuperTrend) | HDA (Absorption) | VCP (Contraction) | BBS (Squeeze)</p>
            </div>
        </div>
        <div class="flex flex-wrap items-center gap-6 mono text-sm">
            <div>MARKET: <span class="text-emerald-400 font-bold">24/7 SPOT CRYPTO</span></div>
            <div>POOL: <span class="font-bold text-slate-200">₹10,000</span> <span class="text-xs text-slate-400">(₹200 micro-alloc)</span></div>
            <div>FRICTION: <span class="text-amber-400 font-bold">1.572%</span> <span class="text-[10px] text-slate-400">(TDS+GST+Fee)</span></div>
            <button onclick="triggerEmergencyKill()" class="bg-red-600 hover:bg-red-700 text-white text-xs px-3.5 py-2 rounded-lg font-bold uppercase transition flex items-center gap-1.5 shadow-lg shadow-red-900/30">
                🚨 Emergency Kill
            </button>
        </div>
    </header>

    <!-- Key Metrics Row -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
            <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Crypto Equity</div>
            <div id="metric-equity" class="text-2xl font-bold mono text-emerald-400 mt-1">₹10,452.80</div>
            <div class="text-xs text-emerald-400 mt-1 flex items-center gap-1">
                <span>▲</span> +4.53% Net Realized (Post-Tax)
            </div>
        </div>
        <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
            <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Available Capital Headroom</div>
            <div id="metric-avail" class="text-2xl font-bold mono text-indigo-400 mt-1">₹9,400.00</div>
            <div class="text-xs text-slate-400 mt-1">Deployed: ₹600.00 across 3 bots</div>
        </div>
        <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
            <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Sharpe & Sortino Ratio</div>
            <div id="metric-sharpe" class="text-2xl font-bold mono text-indigo-400 mt-1">2.92</div>
            <div class="text-xs text-slate-400 mt-1">Sortino: 3.15 | Net Profit Factor: 2.14</div>
        </div>
        <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
            <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Friction Drag Deducted</div>
            <div id="metric-friction" class="text-2xl font-bold mono text-amber-400 mt-1">-₹38.60</div>
            <div class="text-xs text-slate-400 mt-1">Exact 1.572% Statutory Accounting</div>
        </div>
    </div>

    <!-- Main Topology 3-Column Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-4">

        <!-- Column 1: Crypto Sector Heatmap & Pairs (3 Cols) -->
        <div class="lg:col-span-3 space-y-4">
            <!-- Crypto Sector Clusters -->
            <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 space-y-3">
                <div class="flex justify-between items-center">
                    <h2 class="text-xs font-bold text-slate-300 uppercase tracking-wider">Crypto Sector Clusters</h2>
                    <span class="text-[10px] text-indigo-400 mono">RS-Momentum</span>
                </div>
                <div id="sector-list" class="space-y-2 text-xs mono">
                    <div class="flex justify-between items-center p-2.5 bg-slate-900/70 rounded-lg border border-slate-700/50">
                        <span>L1 BLUECHIPS (SOL, BTC, ETH)</span>
                        <span class="text-emerald-400 font-bold">+4.8% [LEADER]</span>
                    </div>
                    <div class="flex justify-between items-center p-2.5 bg-slate-900/70 rounded-lg border border-slate-700/50">
                        <span>AI & COMPUTE (NEAR, FET, RNDR)</span>
                        <span class="text-emerald-400 font-bold">+6.2% [LEADER]</span>
                    </div>
                    <div class="flex justify-between items-center p-2.5 bg-slate-900/70 rounded-lg border border-slate-700/50">
                        <span>DEFI & ORACLES (AAVE, UNI, LINK)</span>
                        <span class="text-slate-300 font-bold">+1.4% [NEUTRAL]</span>
                    </div>
                    <div class="flex justify-between items-center p-2.5 bg-slate-900/70 rounded-lg border border-slate-700/50">
                        <span>MEME / HIGH-BETA (DOGE, SHIB)</span>
                        <span class="text-red-400 font-bold">-0.8% [LAGGARD]</span>
                    </div>
                </div>
            </div>

            <!-- Cointegrated Crypto Pairs Monitor -->
            <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 space-y-3">
                <div class="flex justify-between items-center">
                    <h2 class="text-xs font-bold text-slate-300 uppercase tracking-wider">Crypto Pairs Spread Monitor</h2>
                    <span class="text-[10px] text-emerald-400 mono">Cointegration</span>
                </div>
                <div class="space-y-2 text-xs mono">
                    <div class="p-3 bg-slate-900/70 rounded-lg border border-indigo-500/40">
                        <div class="flex justify-between font-bold">
                            <span>SOL/INR vs BTC/INR</span>
                            <span class="text-amber-400 font-bold">z = +2.15</span>
                        </div>
                        <div class="text-[11px] text-slate-400 mt-1">Bot: <span class="text-indigo-400 font-bold">STE</span> | Hedge: 1.35 | <span class="text-amber-300">ACTIVE RUN</span></div>
                    </div>
                    <div class="p-3 bg-slate-900/70 rounded-lg border border-emerald-500/40">
                        <div class="flex justify-between font-bold">
                            <span>NEAR/INR vs FET/INR</span>
                            <span class="text-emerald-400 font-bold">z = -1.85</span>
                        </div>
                        <div class="text-[11px] text-slate-400 mt-1">Bot: <span class="text-emerald-400 font-bold">HDA</span> | Hedge: 1.12 | <span class="text-emerald-300">ACTIVE RUN</span></div>
                    </div>
                    <div class="p-3 bg-slate-900/70 rounded-lg border border-slate-700/50">
                        <div class="flex justify-between font-bold">
                            <span>ETH/INR vs BTC/INR</span>
                            <span class="text-slate-400">z = -0.35</span>
                        </div>
                        <div class="text-[11px] text-slate-400 mt-1">Bot: <span class="text-blue-400 font-bold">VCP</span> | Hedge: 0.92 | <span class="text-slate-300">HOLD</span></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Column 2: Crypto Charting & Confluence Engine (6 Cols) -->
        <div class="lg:col-span-6 bg-slate-800 p-4 rounded-xl border border-slate-700 space-y-4 flex flex-col justify-between">
            <div class="flex flex-wrap justify-between items-center gap-2">
                <div>
                    <h2 class="text-xs font-bold text-slate-300 uppercase tracking-wider">Crypto Cross-Spread Z-Score & Statistical Bands</h2>
                    <p class="text-[11px] text-slate-400">Active Pair: SOL/INR vs BTC/INR (Confluence Quality Score: 89/100)</p>
                </div>
                <div class="flex items-center gap-2 mono text-xs">
                    <span class="px-2 py-0.5 bg-emerald-500/20 text-emerald-300 rounded border border-emerald-500/30">AI: APPROVE (87%)</span>
                    <span class="px-2 py-0.5 bg-indigo-500/20 text-indigo-300 rounded border border-indigo-500/30">Gemini 2.5 Flash</span>
                </div>
            </div>
            <div class="h-80 w-full">
                <canvas id="cryptoZscoreChart"></canvas>
            </div>
            <div class="grid grid-cols-3 gap-2 pt-2 text-center text-xs mono border-t border-slate-700">
                <div class="p-2 bg-slate-900/60 rounded">
                    <span class="text-slate-400 block text-[10px]">UPPER ENTRY (+2.0z)</span>
                    <span class="text-red-400 font-bold">SHORT SPREAD</span>
                </div>
                <div class="p-2 bg-slate-900/60 rounded">
                    <span class="text-slate-400 block text-[10px]">CURRENT SPREAD</span>
                    <span class="text-amber-400 font-bold">+2.15z (ACTIVE)</span>
                </div>
                <div class="p-2 bg-slate-900/60 rounded">
                    <span class="text-slate-400 block text-[10px]">LOWER ENTRY (-2.0z)</span>
                    <span class="text-emerald-400 font-bold">LONG SPREAD</span>
                </div>
            </div>
        </div>

        <!-- Column 3: Crypto Order Ticket & RMS Risk Gauges (3 Cols) -->
        <div class="lg:col-span-3 space-y-4">
            <!-- Crypto Order Ticket -->
            <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 space-y-3">
                <h2 class="text-xs font-bold text-slate-300 uppercase tracking-wider">⚡ CoinDCX Micro-Execution Ticket</h2>
                <form id="crypto-order-form" onsubmit="handleCryptoOrderSubmit(event)" class="space-y-2.5 text-xs">
                    <div>
                        <label class="text-slate-400 block mb-1">Coin / Pair</label>
                        <select id="crypto-pair" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-slate-200 mono">
                            <option value="SOL/INR">SOL/INR (Solana)</option>
                            <option value="BTC/INR">BTC/INR (Bitcoin)</option>
                            <option value="ETH/INR">ETH/INR (Ethereum)</option>
                            <option value="NEAR/INR">NEAR/INR (Near Protocol)</option>
                            <option value="DOGE/INR">DOGE/INR (Dogecoin)</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1">Strategy Fleet Archetype</label>
                        <select id="crypto-bot" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-slate-200 mono">
                            <option value="STE">STE - SuperTrend Momentum</option>
                            <option value="HDA">HDA - High-Delivery Absorption</option>
                            <option value="VCP">VCP - Volatility Contraction Pattern</option>
                            <option value="BBS">BBS - Bollinger-Keltner Squeeze</option>
                        </select>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="text-slate-400 block mb-1">Order Allocation</label>
                            <input id="crypto-amount" type="number" value="200" min="100" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-slate-200 mono" title="Minimum INR 100">
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1">Direction</label>
                            <select id="crypto-direction" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-slate-200 mono">
                                <option value="BUY">BUY</option>
                                <option value="SELL">SELL</option>
                            </select>
                        </div>
                    </div>
                    <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-lg uppercase tracking-wider transition text-xs shadow-md shadow-indigo-900/30">
                        🚀 Dispatch Micro-Order
                    </button>
                </form>
            </div>

            <!-- Crypto RMS Boundaries -->
            <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 space-y-3">
                <h2 class="text-xs font-bold text-slate-300 uppercase tracking-wider">🛡 Crypto RMS Guard</h2>
                <div class="space-y-2 text-xs mono">
                    <div>
                        <div class="flex justify-between text-slate-400 mb-1">
                            <span>Single-Coin Global Lock</span>
                            <span class="text-emerald-400 font-bold">1 / 1 Pos Max</span>
                        </div>
                        <div class="w-full bg-slate-900 rounded-full h-1.5">
                            <div class="bg-emerald-500 h-1.5 rounded-full" style="width: 100%"></div>
                        </div>
                    </div>
                    <div>
                        <div class="flex justify-between text-slate-400 mb-1">
                            <span>Pool Headroom (₹10,000 Cap)</span>
                            <span class="text-indigo-400 font-bold">₹600 / ₹10,000 (6%)</span>
                        </div>
                        <div class="w-full bg-slate-900 rounded-full h-1.5">
                            <div class="bg-indigo-500 h-1.5 rounded-full" style="width: 6%"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Live Crypto Positions & Trade Audit Table -->
    <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 space-y-3">
        <div class="flex justify-between items-center">
            <h2 class="text-xs font-bold text-slate-300 uppercase tracking-wider">📜 Live Crypto Positions (Net of 1.572% Statutory Friction)</h2>
            <span class="text-xs text-slate-400 mono">Active Positions: <span id="pos-count" class="text-emerald-400 font-bold">3</span></span>
        </div>
        <div class="overflow-x-auto">
            <table class="w-full text-left text-xs mono">
                <thead class="bg-slate-900 text-slate-400 uppercase">
                    <tr>
                        <th class="p-3">Position / Bot</th>
                        <th class="p-3">Coin / Pair</th>
                        <th class="p-3">Quantity</th>
                        <th class="p-3">Avg Entry</th>
                        <th class="p-3">LTP</th>
                        <th class="p-3">Gross P&L</th>
                        <th class="p-3">Friction (1.572%)</th>
                        <th class="p-3">Net P&L</th>
                        <th class="p-3">Mode</th>
                        <th class="p-3 text-right">Action</th>
                    </tr>
                </thead>
                <tbody id="crypto-positions-tbody" class="divide-y divide-slate-700">
                    <tr class="hover:bg-slate-700/50">
                        <td class="p-3 font-bold"><span class="px-2 py-0.5 bg-indigo-500/20 text-indigo-300 rounded border border-indigo-500/40">STE</span> POS-SOL-001</td>
                        <td class="p-3 font-bold text-slate-200">SOL/INR</td>
                        <td class="p-3">0.0197</td>
                        <td class="p-3">₹10,140.00</td>
                        <td class="p-3">₹10,380.00</td>
                        <td class="p-3 text-emerald-400 font-bold">+₹4.73</td>
                        <td class="p-3 text-amber-400">-₹1.55</td>
                        <td class="p-3 text-emerald-400 font-bold">+₹3.18</td>
                        <td class="p-3"><span class="px-2 py-0.5 bg-slate-900 rounded text-slate-400">SHADOW</span></td>
                        <td class="p-3 text-right"><button onclick="closeCryptoPosition('SOL/INR')" class="bg-slate-700 hover:bg-red-600 px-2.5 py-1 rounded text-slate-200 hover:text-white transition">Close</button></td>
                    </tr>
                    <tr class="hover:bg-slate-700/50">
                        <td class="p-3 font-bold"><span class="px-2 py-0.5 bg-emerald-500/20 text-emerald-300 rounded border border-emerald-500/40">HDA</span> POS-NEAR-002</td>
                        <td class="p-3 font-bold text-slate-200">NEAR/INR</td>
                        <td class="p-3">0.5400</td>
                        <td class="p-3">₹370.00</td>
                        <td class="p-3">₹384.50</td>
                        <td class="p-3 text-emerald-400 font-bold">+₹7.83</td>
                        <td class="p-3 text-amber-400">-₹3.12</td>
                        <td class="p-3 text-emerald-400 font-bold">+₹4.71</td>
                        <td class="p-3"><span class="px-2 py-0.5 bg-slate-900 rounded text-slate-400">SHADOW</span></td>
                        <td class="p-3 text-right"><button onclick="closeCryptoPosition('NEAR/INR')" class="bg-slate-700 hover:bg-red-600 px-2.5 py-1 rounded text-slate-200 hover:text-white transition">Close</button></td>
                    </tr>
                    <tr class="hover:bg-slate-700/50">
                        <td class="p-3 font-bold"><span class="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded border border-blue-500/40">VCP</span> POS-ETH-003</td>
                        <td class="p-3 font-bold text-slate-200">ETH/INR</td>
                        <td class="p-3">0.0008</td>
                        <td class="p-3">₹2,48,000.00</td>
                        <td class="p-3">₹2,51,200.00</td>
                        <td class="p-3 text-emerald-400 font-bold">+₹2.56</td>
                        <td class="p-3 text-amber-400">-₹1.58</td>
                        <td class="p-3 text-emerald-400 font-bold">+₹0.98</td>
                        <td class="p-3"><span class="px-2 py-0.5 bg-slate-900 rounded text-slate-400">SHADOW</span></td>
                        <td class="p-3 text-right"><button onclick="closeCryptoPosition('ETH/INR')" class="bg-slate-700 hover:bg-red-600 px-2.5 py-1 rounded text-slate-200 hover:text-white transition">Close</button></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Chart.js Cross-Crypto Spread Z-Score
        const ctx = document.getElementById('cryptoZscoreChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: Array.from({length: 30}, (_, i) => `T-${30 - i}`),
                datasets: [
                    {
                        label: 'SOL/INR vs BTC/INR Spread Z-Score',
                        data: [0.1, 0.4, 0.8, 1.2, 1.5, 1.9, 2.15, 1.8, 1.4, 0.9, 0.5, 0.1, -0.4, -0.9, -1.5, -2.1, -1.8, -1.2, -0.6, 0.0, 0.3, 0.7, 1.1, 1.6, 2.05, 1.7, 1.2, 0.6, 0.2, 2.15],
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.12)',
                        borderWidth: 2.5,
                        tension: 0.25,
                        fill: true,
                        pointRadius: 2
                    },
                    {
                        label: 'Upper Entry Threshold (+2.0z)',
                        data: Array(30).fill(2.0),
                        borderColor: '#ef4444',
                        borderDash: [4, 4],
                        borderWidth: 1.5,
                        pointRadius: 0,
                        fill: false
                    },
                    {
                        label: 'Lower Entry Threshold (-2.0z)',
                        data: Array(30).fill(-2.0),
                        borderColor: '#10b981',
                        borderDash: [4, 4],
                        borderWidth: 1.5,
                        pointRadius: 0,
                        fill: false
                    },
                    {
                        label: 'Equilibrium (0.0z)',
                        data: Array(30).fill(0.0),
                        borderColor: '#475569',
                        borderDash: [2, 2],
                        borderWidth: 1,
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 11 } }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } },
                        grid: { color: '#334155' }
                    },
                    y: {
                        ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } },
                        grid: { color: '#334155' },
                        suggestedMin: -3.0,
                        suggestedMax: 3.0
                    }
                }
            }
        });

        // Emergency Crypto Kill Switch
        async function triggerEmergencyKill() {
            if (!confirm("🚨 WARNING: Execute Emergency Crypto Liquidation across all bot positions?")) {
                return;
            }
            try {
                const res = await fetch("/api/v1/emergency-kill", { method: "POST" });
                const data = await res.json();
                if (data.success) {
                    document.getElementById("pulse-dot").className = "relative inline-flex rounded-full h-3 w-3 bg-red-500";
                    document.getElementById("pulse-ping").className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75";
                    document.getElementById("crypto-positions-tbody").innerHTML = `
                        <tr>
                            <td colspan="10" class="p-4 text-center text-red-400 font-bold">
                                🚨 ALL CRYPTO POSITIONS SQUARED OFF VIA EMERGENCY KILL SWITCH
                            </td>
                        </tr>
                    `;
                    document.getElementById("pos-count").innerText = "0";
                    alert(data.message);
                }
            } catch (err) {
                alert("Error executing kill switch: " + err);
            }
        }

        // Crypto Order Submit with RMS Feedback
        async function handleCryptoOrderSubmit(e) {
            e.preventDefault();
            const pair = document.getElementById("crypto-pair").value;
            const bot_name = document.getElementById("crypto-bot").value;
            const amount_inr = parseFloat(document.getElementById("crypto-amount").value);
            const direction = document.getElementById("crypto-direction").value;

            try {
                const res = await fetch("/api/v1/orders", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ pair, bot_name, amount_inr, direction })
                });
                const data = await res.json();
                if (data.success) {
                    alert(`✅ Micro-Order Dispatched: ${direction} ${pair} (₹${amount_inr}) [Bot: ${bot_name}]`);
                    location.reload();
                } else {
                    alert("❌ Order Blocked by RMS: " + (data.message || data.error));
                }
            } catch (err) {
                alert("Order error: " + err);
            }
        }

        // Close Individual Position
        function closeCryptoPosition(pair) {
            if (confirm(`Square off active crypto position for ${pair}?`)) {
                alert(`Square-off fill executed for ${pair}. Net P&L credited to unified pool.`);
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def read_crypto_dashboard():
    import os
    tmpl_path = os.path.join(os.path.dirname(__file__), "dashboard", "templates", "dashboard.html")
    if os.path.exists(tmpl_path):
        with open(tmpl_path, "r", encoding="utf-8") as f:
            return f.read()
    return CRYPTO_HTML_TEMPLATE


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
