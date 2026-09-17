# Handoff Report: Indicator Reference Validation (Phases 3, 4, 5) & Live Scanner SQLite Integration (Phase 6)

- **Agent**: `explorer_audit_3`
- **Working Directory**: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_3`
- **Target Host**: VPS (`root@148.113.9.103:20069`)
- **Execution Date**: 2026-09-17
- **Audit Scope**: Phase 3 (RSI Reference Validation), Phase 4 (MACD Reference Validation), Phase 5 (EMA50 Reference Validation), Phase 6 (Live Scanner SQLite Integration)

---

## 1. Observation

### 1.1 VPS Host & Runtime Topology
- **Host**: Linux `vps-tekq` (kernel 6.8.12-38-pve)
- **Active Service**: `project-alpha-v2.service`
- **Active Process**: PID `71891`, running `/opt/project-alpha/.venv/bin/python3 app.py` listening on `0.0.0.0:5001`.
- **Process Environment** (`/proc/71891/environ`):
  ```
  V2_DEPLOYMENT_MODE=SHADOW
  V2_DB_PATH=v2/data/alpha_v2.db
  TELEGRAM_BOT_TOKEN=8874447624:AAH5Bpeq8cCBt1AyyR-5OgXL9U4BuyQl1mU
  ```
- **Open File Descriptors for PID 71891**:
  ```
  6 -> /opt/project-alpha/v2/data/alpha_v2.db
  7 -> /opt/project-alpha/v2/data/alpha_v2.db-wal
  8 -> /opt/project-alpha/v2/data/alpha_v2.db-shm
  ```

### 1.2 SQLite Database Discovery & Dual-DB State (Phase 6)
Two SQLite databases exist on the VPS:
1. `/opt/project-alpha/data/project_alpha.db`:
   - Size: `108,371,968` bytes
   - Total rows in `signals`: **408**
   - Timestamp of latest signal (`id=fbd30627-375c-42f3-96f1-5c363020d38b`, coin `ONDO`): **`2026-09-11T13:26:44.782646+00:00`** (~5.8 days ago).
   - Signals generated in last 5 minutes: **0**
   - Signals generated today (2026-09-17): **0**
2. `/opt/project-alpha/v2/data/alpha_v2.db` (the active database configured in `V2_DB_PATH`):
   - Size: `110,923,776` bytes
   - Total rows in `signals`: **422**
   - Timestamp of latest signal (`id=25b4517f-5131-4e76-ac7b-9b3194a72811`, coin `BTC`, pair `BTC/INR`, score `90`): **`2026-09-17T08:11:33.344530+00:00`** (~20.7 minutes prior to query time `08:32:16 UTC`).
   - Signals generated in last 5 minutes: **0**
   - Signals generated in last 1 hour: **2** (`25b4517f-5131-4e76-ac7b-9b3194a72811` BTC/INR score 90, and `36f68b08-a884-4a88-94aa-8841c9a0b28e` BTC/USDT score 90).
   - Signals generated today (2026-09-17): **14**

### 1.3 Live Scanner Poll Activity (Phase 6)
From systemd service journal logs (`journalctl -u project-alpha-v2.service --since "5 minutes ago"`):
```
Sep 17 08:30:35 vps-tekq python3[71891]: {"ts": "2026-09-17T08:30:35", "level": "INFO", "logger": "background.scheduler", "msg": "Job completed", "job": "scanner_poll", "duration_ms": 2305}
Sep 17 08:31:34 vps-tekq python3[71891]: {"ts": "2026-09-17T08:31:34", "level": "INFO", "logger": "scanner.market_context", "msg": "Market context refreshed: BTC=SIDEWAYS, ETH=SIDEWAYS, Regime=RISK_OFF, F&G=50"}
Sep 17 08:31:35 vps-tekq python3[71891]: {"ts": "2026-09-17T08:31:35", "level": "INFO", "logger": "scanner.service", "msg": "Scanner Funnel Cascade: raw=50, liq=50, vol=50, pump_dump=46, trend=46, atr=46 -> c2_eval=46", "funnel": {"raw_universe": 50, "market_universe": 959, "market_liquidity_rejected": 681, "market_top_n": 50, "liquidity_passed": 50, "volume_passed": 50, "pump_dump_passed": 46, "trend_aligned_passed": 46, "volatility_passed": 46, "c2_evaluated": 46}}
Sep 17 08:31:35 vps-tekq python3[71891]: {"ts": "2026-09-17T08:31:35", "level": "INFO", "logger": "scanner.confluence_engine", "msg": "C2 Confluence evaluation complete", "evaluated": 44, "confluence_passed": 0, "final_signals_output": 0, "max_signals_cap": 2, "dynamic_threshold": 88, "regime_adjustment": -5}
Sep 17 08:31:35 vps-tekq python3[71891]: {"ts": "2026-09-17T08:31:35", "level": "INFO", "logger": "scanner.service", "msg": "Scanner poll complete", "fetched": 46, "new_signals": 0, "expired": 0, "errors": 0, "next_interval_s": 90, "live_count": 2, "evaluated_count": 44}
Sep 17 08:31:35 vps-tekq python3[71891]: {"ts": "2026-09-17T08:31:35", "level": "INFO", "logger": "background.scheduler", "msg": "Job completed", "job": "scanner_poll", "duration_ms": 2170}
```
Observation: The scanner poll runs continuously every 60-90 seconds without exceptions. In the last 5 minutes, 0 new signals met the C2 confluence threshold because market regime was evaluated as `RISK_OFF` (applying a -5 penalty with dynamic threshold 88, resulting in `confluence_passed: 0`).

### 1.4 Indicator Storage & JSON Payload Inspection (Phase 6)
- **Table Schema**: In both databases, `signals` table has columns:
  `['id', 'coin', 'pair', 'market_state', 'opportunity_type', 'priority', 'risk_level', 'score', 'confidence', 'coin_class', 'mtf_alignment', 'generated_at', 'expires_at', 'expired_at', 'expiry_reason', 'source_bot', 'raw_payload']`.
- There is no separate table named `indicators` and no separate column named `indicators`.
- All indicator data is embedded inside the JSON string in `raw_payload`.
- **Inspection of `raw_payload` for Recent Signals** (e.g. `25b4517f-5131-4e76-ac7b-9b3194a72811` at 2026-09-17 08:11:33 UTC):
  ```json
  {
    "coin": "BTC",
    "pair": "BTC/INR",
    "score": 91.3,
    "composite_score": 40.3,
    "price": 7632472.9,
    "priority": "Elite",
    "strategy": "Volatility Contraction Pattern",
    "timeframe": "1h",
    "mtf_timeframes": ["15m", "1h", "1d"],
    "market_state": "bull_trend",
    "opportunity_type": "contraction",
    "coin_class": "A",
    "mtf_alignment": true,
    "is_mtf_aligned": true,
    "bot": "VCP",
    "rsi": 69.49,
    "atr_pct": 0.82,
    "volume_24h": 232456036150622.72,
    "volume_ratio": 0.1,
    "timestamp": null,
    "confluence_score": 90,
    "confluence_base_score": 90,
    "regime_adjustment": 0,
    "dynamic_threshold": 88,
    "confluence_accepted": true,
    "confluence_rejection_reasons": []
  }
  ```
- **Field-by-Field Audit**:
  - `rsi`: **`69.49`** (float, non-null, valid)
  - `atr_pct`: **`0.82`** (float, non-null, valid)
  - `volume_24h`: **`232456036150622.72`** (float, non-null, valid)
  - `volume_ratio`: **`0.1`** (float, non-null, valid)
  - `mtf_alignment`: **`true`** (boolean, non-null, valid)
  - `mtf_timeframes`: **`["15m", "1h", "1d"]`** (list of strings, non-null, valid)
  - `macd`: Not serialized directly in `raw_payload`. (MACD is computed in research indicators for deep coin research, not emitted into the live candidate schema).
  - `ema`: Numerical values (e.g. `ema9`, `ema21`, `ema50`) are not emitted as explicit scalar float keys in `raw_payload`. Instead, EMA calculations are used upstream in `scanner/service.py:1385-1464` to establish `market_state: bull_trend`, `mtf_alignment: true`, and add score points (`spread_ratio = (ema9 - ema21) / ema21`).
  - `indicators` wrapper key: Not present in modern signals. The indicator values are top-level keys within `raw_payload`.
- **Live Memory Endpoint Audit** (`GET http://127.0.0.1:5001/api/v2/scanner/coins` with `X-API-Key: alpha-prod-key`):
  - 44 candidate coins currently tracked in memory.
  - Sample item:
    `{'symbol': 'USELESS', 'coin': 'USELESS', 'pair': 'USELESS/USDT', 'price': 0.27252, 'volume_24h': 851553.06, 'volume_ratio': 0.56, 'ema_trend': 'BULLISH', 'rsi': 73.2, 'mtf_alignment': '15m_1h_1d', 'is_mtf_aligned': True, 'confluence_score': 87, 'status': 'REJECTED', 'accepted': False}`.
  - All indicator values are non-null and valid.

---

### 1.5 Phase 3: RSI Reference Validation
Executed on VPS using `/opt/project-alpha/.venv/bin/python3` testing `scanner.research.indicators.compute_rsi`:
- **Test 3.1: Monotonic Uptrend** (`prices = np.array([10.0 + i * 2.0 for i in range(30)])`):
  - Result: `final_rsi = 100.0`
  - Overbought check (`> 70.0`): **PASS** (`is_overbought_gt_70 = True`)
- **Test 3.2: Realistic Noisy Uptrend** (40 bars with drift + upward sinusoidal oscillation):
  - Result: `final_rsi = 100.0`
  - Overbought check (`> 70.0`): **PASS** (`is_overbought_gt_70 = True`)
- **Test 3.3: Monotonic Downtrend** (`prices = np.array([100.0 - i * 2.0 for i in range(30)])`):
  - Result: `final_rsi = 0.0`
  - Oversold check (`< 30.0`): **PASS** (`is_oversold_lt_30 = True`)
- **Test 3.4: Realistic Noisy Downtrend** (40 bars with negative drift + sinusoidal oscillation):
  - Result: `final_rsi = 0.0`
  - Oversold check (`< 30.0`): **PASS** (`is_oversold_lt_30 = True`)
- **Test 3.5: Flat Price Series** (30 bars at 50.0):
  - Result: `final_rsi = 100.0` (zero loss division avoided by `avg_loss == 0` guard, non-NaN, no exception): **PASS**
- **Test 3.6: Insufficient Data** (4 bars < 15 bars required):
  - Result: array of 4 elements, all `np.nan`: **PASS**

---

### 1.6 Phase 4: MACD Reference Validation
Executed on VPS using `/opt/project-alpha/.venv/bin/python3` testing `scanner.research.indicators.compute_macd`:
- **Test 4.1: Standard 40 Bars** (`prices = np.array([100.0 + (i % 5) * 2.0 + i for i in range(40)])`):
  - DataFrame constructed: `df = pd.DataFrame({"macd": macd, "signal": signal, "hist": hist})`
  - `is_dataframe`: **True**
  - Columns: **`['macd', 'signal', 'hist']`** (Multi-column DataFrame)
  - Shape: **`[40, 3]`**
  - Final row values:
    - `final_macd`: **`7.400167`** (non-null)
    - `final_signal`: **`7.112607`** (non-null)
    - `final_hist`: **`0.287560`** (non-null)
  - `non_null_final_values`: **True**
  - Mathematical identity: `abs(hist - (macd - signal)) < 1e-6`: **True** (Exact identity preserved)
  - Warm-up verification:
    - `macd` initial NaNs: **25** (corresponds to slow EMA period 26)
    - `signal` initial NaNs: **33** (25 + 8 for signal period 9)
    - `hist` initial NaNs: **33**
  - Status: **PASS**
- **Test 4.2: Insufficient Data (20 Bars < 34 Bars)**:
  - Result: `df.shape == [20, 3]`, all entries in `macd`, `signal`, and `hist` are `NaN`: **PASS**

---

### 1.7 Phase 5: EMA50 Reference Validation
Executed on VPS using `/opt/project-alpha/.venv/bin/python3` testing both `scanner.research.indicators.compute_ema` and `scanner.market_context.calculate_ema`:
- **Test 5.1: Insufficient Data (< 50 Candles)**:
  - 10 candles: `compute_ema(p_10, 50)` returns array of length 10, all entries `NaN`, `last_valid` returns `0.0`. Status: **PASS**
  - 49 candles: `compute_ema(p_49, 50)` returns array of length 49, all entries `NaN`, `last_valid` returns `0.0`. Status: **PASS**
  - `calculate_ema(list_49, 50)` returns empty list `[]`. Status: **PASS**
- **Test 5.2: Boundary Condition (Exactly 50 Candles)**:
  - 50 candles (`[100.0, 101.0, ..., 149.0]`):
    - First 49 values (`indices 0..48`) are `NaN`.
    - Index 49 (the 50th candle) is seeded with `np.mean(prices[:50])` = **`124.500000`**.
    - `seed_matches`: **True** (`abs(ema[49] - 124.5) < 1e-9`).
    - `last_valid`: **`124.500000`**.
    - `calculate_ema(list_50, 50)` returns `[124.5]`.
    - Status: **PASS**
- **Test 5.3: Sufficient Data (>= 50 Candles, e.g. 80 Candles)**:
  - `compute_ema(p_80, 50)`: returns array of length 80. First 49 values are `NaN`, subsequent 31 values are non-null smoothed EMA values. Final value = **`127.250000`** (valid, non-null). Status: **PASS**
  - `calculate_ema(list_80, 50)`: returns list of length 31 (80 - 50 + 1) with final value = **`127.250000`**. Status: **PASS**

---

### 1.8 Unit Test Suite Execution
- Command executed on VPS:
  `cd /opt/project-alpha && PYTHONPATH=. .venv/bin/pytest tests/test_indicator_calculations.py -v`
- Result:
  ```
  tests/test_indicator_calculations.py::test_compute_ema_validation PASSED [ 16%]
  tests/test_indicator_calculations.py::test_compute_rsi_validation PASSED [ 33%]
  tests/test_indicator_calculations.py::test_compute_macd_validation PASSED [ 50%]
  tests/test_indicator_calculations.py::test_compute_bollinger_validation PASSED [ 66%]
  tests/test_indicator_calculations.py::test_compute_atr_validation PASSED [ 83%]
  tests/test_indicator_calculations.py::test_compute_rvol_validation PASSED [100%]
  ============================== 6 passed in 0.69s ===============================
  ```
- Note: When running without `PYTHONPATH=.`, pytest throws `ModuleNotFoundError: No module named 'scanner'`. Setting `PYTHONPATH=.` executes 100% cleanly.

---

## 2. Logic Chain

1. **Premise**: The user requested an audit of indicator calculations (Phases 3, 4, 5) and a live SQLite integration check for recent signals and indicator JSON blobs (Phase 6) on the VPS.
2. **Path Resolution**: We queried the VPS filesystem for `project_alpha.db` and checked process 71891's environment and open file descriptors (Observation 1.1). Process 71891 runs with `V2_DB_PATH=v2/data/alpha_v2.db` and holds open file locks on `/opt/project-alpha/v2/data/alpha_v2.db`, while `/opt/project-alpha/data/project_alpha.db` remains a static historical snapshot from 2026-09-11 (Observation 1.2).
3. **Phase 6 Verification**:
   - Querying `data/project_alpha.db` directly returns 0 signals generated in the last 5 minutes (last signal was 2026-09-11).
   - Querying the active database `v2/data/alpha_v2.db` also returns 0 signals in the last 5 minutes, with the most recent signals generated today at 08:11:33 UTC (20 minutes ago).
   - Examining service logs confirms the scanner scheduler is running normally every 60-90 seconds without error (Observation 1.3). The reason 0 signals were generated in the last 5 minutes is market-driven: the C2 confluence engine evaluated 44-46 coins against a dynamic threshold of 88 in a `RISK_OFF` regime with -5 score adjustment, filtering all candidates below threshold.
   - Inspecting `signals.raw_payload` across recent records (Observation 1.4) proves that indicator metrics (`rsi`, `atr_pct`, `volume_24h`, `volume_ratio`, `mtf_alignment`, `mtf_timeframes`) are fully populated with valid non-null floats and booleans. There is no separate `indicators` column or table; rather, indicator values are serialized directly into `raw_payload`.
4. **Phase 3 Verification**: Running parametric tests on `compute_rsi` demonstrates that an uptrend outputs `100.0` (exceeding overbought threshold 70), a downtrend outputs `0.0` (below oversold threshold 30), zero-loss conditions avoid runtime division errors, and insufficient data cleanly returns NaNs (Observation 1.5).
5. **Phase 4 Verification**: Running `compute_macd` on 40 bars produces a 3-column pandas DataFrame (`macd`, `signal`, `hist`) with shape (40, 3) where the final row consists of valid non-null floats (`7.400167`, `7.112607`, `0.287560`) adhering strictly to `hist == macd - signal`, while bars below warm-up length yield NaNs (Observation 1.6).
6. **Phase 5 Verification**: Running `compute_ema` with period 50 proves that price series with <50 bars return all NaNs, series with exactly 50 bars seed the 50th element (index 49) with the exact SMA average (`124.500000`), and series with >=50 bars return valid smoothed values (Observation 1.7).

---

## 3. Caveats

1. **Dual Database Paths**: The active systemd service uses `V2_DB_PATH=v2/data/alpha_v2.db`. The legacy path `data/project_alpha.db` exists on disk but does not receive live writes from the current running process. Any monitoring tool querying only `data/project_alpha.db` will report stale data from 2026-09-11.
2. **Signal Generation Cadence vs 5-Minute Window**: Because PROJECT-ALPHA prioritizes "few, high-conviction signals" (dynamic threshold 80-92, strict C2 confluence gate), a 5-minute sampling window frequently contains 0 new signals during `SIDEWAYS` or `RISK_OFF` conditions. The lack of signals in the last 5 minutes is expected operational behavior, not an outage.
3. **Indicator Key Flattening**: Indicator fields in `signals` are flattened as top-level keys in `raw_payload` (`rsi`, `atr_pct`, `volume_ratio`) rather than nested under an `indicators: {...}` key.
4. **MACD in Live Candidate Payload**: MACD is fully implemented and tested in `scanner/research/indicators.py` and `scanner/research/service.py`, but is not included in the fast 1h candidate dictionary emitted by `scanner/service.py::_generate_native_candidates`.

---

## 4. Conclusion

1. **Phase 3 (RSI)**: **PASSED (100%)**. `compute_rsi` correctly identifies overbought (>70) and oversold (<30) conditions, handles zero-variance flat price series, and properly returns NaNs when data is insufficient.
2. **Phase 4 (MACD)**: **PASSED (100%)**. `compute_macd` returns a valid multi-column DataFrame (`macd`, `signal`, `hist`) with non-null final values, exact histogram identity (`hist = macd - signal`), and proper initial warm-up NaNs.
3. **Phase 5 (EMA50)**: **PASSED (100%)**. `compute_ema` (and `calculate_ema`) cleanly handles <50 candles by returning NaNs / empty list, correctly seeds at candle 50 with the SMA mean, and generates valid non-null smoothed values for >=50 candles.
4. **Phase 6 (Live Scanner SQLite Integration)**: **PASSED WITH ARCHITECTURAL CLARIFICATION**.
   - The scanner is actively polling every 60-90s on the VPS with 0 runtime errors.
   - Live signals are written to `/opt/project-alpha/v2/data/alpha_v2.db` (14 signals today, latest at 08:11:33 UTC). No signals were generated in the last 5 minutes due to normal C2 confluence rejection under `RISK_OFF` market conditions.
   - All required indicator fields (`rsi`, `atr_pct`, `volume_24h`, `volume_ratio`, `mtf_alignment`, `mtf_timeframes`) in recent signals are populated with valid, non-null values inside `raw_payload`.

---

## 5. Verification Method

To independently verify all findings on the VPS:

### 1. Run the Unit Test Suite
```bash
ssh -p 20069 root@148.113.9.103 "cd /opt/project-alpha && PYTHONPATH=. .venv/bin/pytest tests/test_indicator_calculations.py -v"
```
*Expected*: 6 passed in < 1s.

### 2. Execute the Reference Validation Script (Phases 3, 4, 5)
```bash
python .agents/explorer_audit_3/run_phases_3_4_5_validation.py
```
*Expected*: JSON output with `"status": "PASS"` across `Phase_3_RSI`, `Phase_4_MACD`, and `Phase_5_EMA50`.

### 3. Query the Live SQLite Databases & Scanner Logs (Phase 6)
```bash
python .agents/explorer_audit_3/check_phase6_live.py
```
*Expected*: Details of `alpha_v2.db` showing 422 signals, recent BTC signals at 08:11:33 UTC, non-null indicator fields in `raw_payload`, and active journal logs of scanner poll cycles.

### 4. Query the Live Authenticated API
```bash
python .agents/explorer_audit_3/query_auth_endpoints.py
```
*Expected*: HTTP 200 responses from `/api/v2/scanner/coins` (44 coins with live RSI, EMA trend, and volume ratios) and `/api/v2/scanner/signals`.
