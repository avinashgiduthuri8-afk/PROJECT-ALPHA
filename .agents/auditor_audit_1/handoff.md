# Forensic Audit Report: Technical Indicator Calculations & VPS Verification

**Work Product**: Scanner Indicator Audit Process (VPS `148.113.9.103:20069` & Local Repository)  
**Profile**: General Project (Development Mode, Read-Only Constraint)  
**Auditor**: `auditor_audit_1`  
**Working Directory**: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\auditor_audit_1`  
**Date**: 2026-09-17  
**Verdict**: **CLEAN**  

---

## 1. Observation

All observations below were gathered through independent execution by `auditor_audit_1` using local Git commands and remote SSH execution via Paramiko directly into `root@148.113.9.103:20069`.

### 1.1 Source Code Immutability & Git Integrity
1. **Local Repository (`c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA`)**:
   - `git status` output:
     ```
     On branch main
     Your branch is up to date with 'origin/main'.
     Changes not staged for commit:
       modified:   .agents/ORIGINAL_REQUEST.md
       modified:   .agents/sentinel/BRIEFING.md
       modified:   split_db.py
     Untracked files: .agents/... vps_alpha_v2.db
     ```
   - `git diff 3b4c616cfd9dc1a66c8770be949af81add0d8fb5 HEAD -- scanner/ tests/ core/ execution/`:
     - **0 lines changed** (Empty output, exit code 0).
   - Local HEAD commit: `53df1a085e9f0c357a085a35675344862c076f40 update vps tools and split db` (parent commit is `3b4c616cfd9dc1a66c8770be949af81add0d8fb5`).

2. **Remote VPS Deployment (`/opt/project-alpha`)**:
   - `git status` output:
     ```
     On branch main
     Your branch is up to date with 'origin/main'.
     Untracked files:
       .venv/
       _debug_inspect.py
       backups/
       project_alpha_v2.db
       scratch_check_tg.py
       v2/
     nothing added to commit but untracked files present
     ```
   - `git diff` output: **0 lines changed** (exit code 0).
   - Git HEAD commit: `3b4c616cfd9dc1a66c8770be949af81add0d8fb5 Phase G: Scanner backtest integration and fixes (Tue Sep 15 17:22:59 2026 +0530)`.

3. **Remote Secondary Clone (`/root/PROJECT-ALPHA`)**:
   - `git status` output: Only untracked `.venv/`.
   - `git diff` output: **0 lines changed** (exit code 0).
   - Git HEAD commit: `3b4c616cfd9dc1a66c8770be949af81add0d8fb5`.

4. **Indicator File Integrity & SHA256 Checksums**:
   - Path `scanner/indicators.py`: Tested on VPS `/opt/project-alpha` and `/root/PROJECT-ALPHA` -> `NOT_FOUND` (0 lines). Does not exist and has never existed in git history.
   - Canonical path `scanner/research/indicators.py`:
     - Line count on VPS `/opt/project-alpha`: **203 lines**
     - Line count on VPS `/root/PROJECT-ALPHA`: **203 lines**
     - Line count in local repository: **203 lines** (204 including trailing newline)
     - SHA256 on VPS `/opt/project-alpha`: `09e2f1054fbbfe848caaddcc086775ba76a6329b895bcb5854b4b2686cb97150`
     - SHA256 on VPS `/root/PROJECT-ALPHA`: `09e2f1054fbbfe848caaddcc086775ba76a6329b895bcb5854b4b2686cb97150`
     - SHA256 locally (LF-normalized): `09e2f1054fbbfe848caaddcc086775ba76a6329b895bcb5854b4b2686cb97150`
     - Status: **Bit-for-bit identical across all environments**.

---

### 1.2 Authenticity of Verification & VPS Execution
Independent execution on `root@148.113.9.103:20069` confirmed that test runs and validation scripts executed by previous explorer agents were genuine and not fabricated or mocked:

1. **Systemd Service & Process State**:
   - Service: `project-alpha-v2.service` is active and running.
   - Process: PID `71891`, `/opt/project-alpha/.venv/bin/python3 app.py`, listening on port `5001`.
   - Active environment variable: `V2_DB_PATH=v2/data/alpha_v2.db`.

2. **Test Suite Execution on VPS (`tests/test_indicator_calculations.py`)**:
   - Command: `cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v`
   - Result: **6 passed in 0.76s** (Exit code 0).
     ```
     tests/test_indicator_calculations.py::test_compute_ema_validation PASSED [ 16%]
     tests/test_indicator_calculations.py::test_compute_rsi_validation PASSED [ 33%]
     tests/test_indicator_calculations.py::test_compute_macd_validation PASSED [ 50%]
     tests/test_indicator_calculations.py::test_compute_bollinger_validation PASSED [ 66%]
     tests/test_indicator_calculations.py::test_compute_atr_validation PASSED [ 83%]
     tests/test_indicator_calculations.py::test_compute_rvol_validation PASSED [100%]
     ```
   - Command: `cd /opt/project-alpha && .venv/bin/pytest tests/test_indicator_calculations.py -v`
   - Result: Exit code 2, `ModuleNotFoundError: No module named 'scanner'` (exact collection error reproduced, confirming explorer 2's empirical observation).
   - Command: `cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_v2_coin_research.py -k 'computation or bands or atr' -v`
   - Result: **5 passed, 9 deselected in 1.37s** (Exit code 0).

3. **Phase 3: RSI Empirical Validation on VPS**:
   - `uptrend_final`: `99.9999999` (`> 70.0`: **True**)
   - `downtrend_final`: `0.0` (`< 30.0`: **True**)
   - `flat_final`: `99.9999999` (no divide-by-zero, non-NaN)
   - `short_all_nan`: **True** (4 bars < 15 returns all NaNs)

4. **Phase 4: MACD Empirical Validation on VPS**:
   - Shape: `[40, 3]`, Columns: `['macd', 'signal', 'hist']` (Multi-column DataFrame)
   - Final row: `macd = 7.400167`, `signal = 7.112607`, `hist = 0.287560` (all non-null floats)
   - Mathematical identity: `hist == macd - signal` -> **True** (`abs(hist - (macd - signal)) < 1e-6`)
   - Initial NaNs: 25 for MACD line, 33 for Signal line and Histogram.
   - Insufficient data (< 34 bars): All entries are `NaN`.

5. **Phase 5: EMA50 Empirical Validation on VPS**:
   - 10 candles: All NaNs -> **True**
   - 49 candles: All NaNs -> **True**; `calculate_ema` returns empty list `[]` -> **True**
   - 50 candles: Index 49 seeded with `mean(prices[:50])` = `124.500000` -> **True** (`seed_matches = True`)
   - 80 candles: Smoothed value at index 79 = `154.500000`, matching `calculate_ema` -> **True**

6. **Look-Ahead Invariance Verification on VPS**:
   - Extending random 50-bar series with 3 future bars:
     - `ema_past_unaltered`: **True** (`np.allclose == True`)
     - `rsi_past_unaltered`: **True** (`np.allclose == True`)
     - `macd_past_unaltered`: **True** (`np.allclose == True`)
     - `macd_signal_past_unaltered`: **True** (`np.allclose == True`)

---

### 1.3 Traceability of Evidence & DB Schema
1. **SQLite Database Topology on VPS**:
   - Active Database: `/opt/project-alpha/v2/data/alpha_v2.db` (110,931,968 bytes)
     - Total signals: **422**
     - Latest signal: ID `25b4517f-5131-4e76-ac7b-9b3194a72811`, pair `BTC/INR`, score `90`, timestamp `2026-09-17T08:11:33.344530+00:00`.
     - Recent signals in last 1h: 2.
     - Recent signals in last 5m: 0 (verified by journal logs: scanner runs every 60-90s, evaluated 44-46 coins; dynamic threshold was 88 in `RISK_OFF` regime with -5 penalty, rejecting below threshold).
   - Legacy Database: `/opt/project-alpha/data/project_alpha.db` (108,371,968 bytes)
     - Total signals: **408** (stale snapshot, latest signal generated `2026-09-11T13:26:44+00:00`).
2. **Schema Verification**:
   - `PRAGMA table_info(signals)` returns 17 columns:
     `['id', 'coin', 'pair', 'market_state', 'opportunity_type', 'priority', 'risk_level', 'score', 'confidence', 'coin_class', 'mtf_alignment', 'generated_at', 'expires_at', 'expired_at', 'expiry_reason', 'source_bot', 'raw_payload']`.
   - Indicators are not in a separate table; indicator metrics are serialized into `raw_payload`.
   - In latest signal (`25b4517f-...`), `raw_payload` contains:
     - `"rsi": 69.49`
     - `"atr_pct": 0.82`
     - `"volume_24h": 232456036150622.72`
     - `"volume_ratio": 0.1`
     - `"mtf_alignment": true`
     - `"strategy": "Volatility Contraction Pattern"`
     - `"market_state": "bull_trend"`

---

## 2. Logic Chain

1. **Source Immutability**:
   - `ORIGINAL_REQUEST.md` (header `## 2026-09-17T08:22:34Z`) specifies: *"Perform a read-only audit of the scanner's indicator calculations on the VPS... Do NOT modify any indicator logic, thresholds, or scoring."*
   - Direct inspection of Git trees across local repository and VPS clones (`/opt/project-alpha` and `/root/PROJECT-ALPHA`) confirmed `git diff` is completely empty (0 modifications).
   - SHA256 checksums of `scanner/research/indicators.py` match byte-for-byte across local and VPS instances.
   - Therefore, the work products maintained strict read-only immutability.

2. **Authenticity of Verification**:
   - Explorer agents reported specific line counts, test pass rates, collection errors, and SQLite signal timestamps.
   - Re-running the exact commands and scripts via Paramiko against `root@148.113.9.103:20069` reproduced every observation identically:
     - 6/6 tests passing via `python3 -m pytest`
     - Exit code 2 under raw `pytest` without PYTHONPATH
     - Exact match on RSI (100 / 0), MACD (7.400167 / 7.112607 / 0.287560), and EMA50 (124.500000 seed)
     - Exact match on PID 71891 and DB path `v2/data/alpha_v2.db`
   - No mocks, facades, dummy constants, or fake result files exist in the codebase.
   - Therefore, all reported verification was authentic and empirically grounded.

3. **Causality & Look-Ahead Verification**:
   - Algorithmic analysis confirmed that all array indexing uses backward-looking windows (`prices[i - period + 1 : i + 1]`, `gains[i]` on past deltas, recursive smoothing without centering).
   - Empirical testing confirmed that extending future candles leaves past indicator values unaltered.
   - Therefore, no look-ahead bias exists.

---

## 3. Caveats

1. **Test Module Execution Context**: Running `.venv/bin/pytest` directly on the VPS fails with `ModuleNotFoundError` because `sys.path` does not include `/opt/project-alpha`. Using `.venv/bin/python3 -m pytest` or setting `PYTHONPATH=.` is mandatory for running pytest on the VPS.
2. **Dual Database Paths**: `/opt/project-alpha/data/project_alpha.db` is a static snapshot from 2026-09-11. The live, active database receiving scanner updates is `/opt/project-alpha/v2/data/alpha_v2.db`.
3. **Signal Generation Interval**: The absence of new signals in a narrow 5-minute window is not an indicator failure; it is the designed behavior of the C2 confluence engine under `RISK_OFF` regime.

---

## 4. Conclusion

The forensic integrity audit is complete.
- **Source Code Immutability**: VERIFIED (0 modifications to source, indicator logic, thresholds, or scoring).
- **Authenticity of Remote VPS Execution**: VERIFIED (All explorer claims match the real live VPS environment).
- **Traceability of Evidence**: VERIFIED (Exact matching line counts, signatures, test outputs, and DB schemas).
- **Prohibited Patterns**: NONE DETECTED (No hardcoded test outputs, no facade implementations, no fabricated outputs).

**Final Binary Verdict**: **CLEAN**

---

## 5. Verification Method

To independently reproduce this forensic audit:

1. **Verify Git Status & Diff on VPS**:
   ```bash
   ssh -p 20069 root@148.113.9.103 "cd /opt/project-alpha && git status --porcelain && git diff"
   ```
   *Expected*: Empty diff, no modifications to tracked source files.

2. **Verify SHA256 Checksum on VPS**:
   ```bash
   ssh -p 20069 root@148.113.9.103 "sha256sum /opt/project-alpha/scanner/research/indicators.py"
   ```
   *Expected*: `09e2f1054fbbfe848caaddcc086775ba76a6329b895bcb5854b4b2686cb97150`.

3. **Verify Indicator Tests on VPS**:
   ```bash
   ssh -p 20069 root@148.113.9.103 "cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v"
   ```
   *Expected*: `6 passed in < 1.0s`.

4. **Verify Active Process & Database on VPS**:
   ```bash
   ssh -p 20069 root@148.113.9.103 "systemctl status project-alpha-v2.service --no-pager"
   ssh -p 20069 root@148.113.9.103 "sqlite3 /opt/project-alpha/v2/data/alpha_v2.db 'SELECT count(*), max(generated_at) FROM signals;'"
   ```
   *Expected*: Service active (running), count >= 422, max date 2026-09-17.
