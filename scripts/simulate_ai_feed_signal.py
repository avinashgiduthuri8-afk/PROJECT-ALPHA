#!/usr/bin/env python3
"""
PROJECT-ALPHA V2 — Synthetic Signal Simulator for AI Intelligence & Mission Control Feed.

Emits a synthetic high-conviction signal (Score >= 85) across the internal EventBus
and verifies real-time processing in Gemini Flash / Heuristic AI Evaluator, Dashboard Aggregator,
and WebSocket telemetry stream without live capital risk.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
import httpx
import websockets


async def run_live_simulation(
    base_url: str = "http://127.0.0.1:5001",
    api_key: str = "alpha-dev-key",
    pair: str = "SOL/INR",
    bot_name: str = "STE",
    score: int = 89,
    price: float = 10140.0,
):
    print("=" * 70)
    print("PROJECT-ALPHA V2: AI INTELLIGENCE EVALUATION SIMULATOR")
    print(f"Target: {base_url} | Bot: {bot_name} | Pair: {pair} | Score: {score}/100")
    print("=" * 70)

    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    payload = {
        "pair": pair,
        "bot_name": bot_name,
        "score": score,
        "price": price,
        "suggested_allocation_inr": 200.0,
        "stop_loss": 9980.0,
        "take_profit": 10450.0,
        "regime": "RISK_ON",
        "eval_breakdown": {
            "chart_structure": 28.0,
            "technical_indicators": 32.0,
            "market_sentiment": 16.0,
            "news_events": 13.0,
        },
    }

    # 1. Listen on WebSocket in background task
    ws_url = f"ws://127.0.0.1:5001/ws/v2/feed?api_key={api_key}"
    received_frames = []

    async def ws_listener():
        try:
            async with websockets.connect(ws_url) as ws:
                while True:
                    msg = await ws.recv()
                    frame = json.loads(msg)
                    ftype = frame.get("type")
                    fdata = frame.get("data", {})
                    received_frames.append(frame)
                    if ftype in ("signal.ai_confirmed", "signal.ai_rejected", "signal.generated"):
                        print(f"[WS REAL-TIME FRAME RECEIVED] Type: {ftype}")
                        print(f"   Data: {json.dumps(fdata, indent=2)}")
        except Exception as e:
            pass

    ws_task = asyncio.create_task(ws_listener())
    await asyncio.sleep(0.5)

    # 2. Dispatch Synthetic Signal via REST Endpoint
    async with httpx.AsyncClient(timeout=15.0) as client:
        print(f"\n[EMITTING] Synthetic signal to {base_url}/api/v2/learning/simulate-signal...")
        resp = await client.post(f"{base_url}/api/v2/learning/simulate-signal", json=payload, headers=headers)
        if resp.status_code == 200:
            res_data = resp.json()
            print("\n[AI EVALUATION VERDICT RECEIVED]:")
            print(f"   Signal ID:      {res_data.get('signal_id')}")
            print(f"   Pair / Bot:     {res_data.get('pair')} ({res_data.get('bot_name')})")
            print(f"   Score:          {res_data.get('confluence_score')} / 100")
            print(f"   Recommendation: {res_data.get('ai_recommendation')} (Confidence: {res_data.get('confidence_score')}%)")
            print(f"   Setup Quality:  {res_data.get('setup_quality')}")
            print(f"   AI Model:       {res_data.get('model_name')}")
            print(f"   Supporting:     {res_data.get('supporting_factors')}")
            print(f"   Risk Factors:   {res_data.get('risk_factors')}")
        else:
            print(f"[ERROR] emitting signal: {resp.status_code} -> {resp.text}")

    # Allow WS frames to arrive
    await asyncio.sleep(1.0)
    ws_task.cancel()

    print("\n" + "=" * 70)
    print("SIMULATION VERIFICATION COMPLETE")
    print(f"Total WebSocket Frames Captured: {len(received_frames)}")
    print("Open http://127.0.0.1:5001/?api_key=alpha-dev-key to view the live card.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_live_simulation())
