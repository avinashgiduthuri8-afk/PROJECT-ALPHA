---
name: Legacy safety-test compatibility
description: How to handle older tests that still refer to removed wallet and micro-order ceilings
---

Retired wallet and per-bot micro-order ceilings may remain as empty compatibility exports while production validation uses the configured shared pool and ₹200 minimum.

**Why:** Older imported tests and consumers can fail during collection when names disappear, but restoring fixed ceilings would contradict the V2 safety contract and create misleading operator telemetry.

**How to apply:** Keep compatibility symbols inert, update stale tests toward the current contract, and do not reintroduce hard-coded cap enforcement merely to satisfy legacy assertions.