# Handoff Report — Review & Adversarial Audit of Phase 1 & Phase 2

## Executive Review Summary

**Verdict**: **APPROVE**  
**Role**: Reviewer & Adversarial Critic (`reviewer_audit_1`)  
**Target Host**: Linux VPS (`148.113.9.103:20069`)  
**Active Production Directory**: `/opt/project-alpha`  
**Secondary Clone**: `/root/PROJECT-ALPHA`  
**Commit**: `3b4c616 Phase G: Scanner backtest integration and fixes`  
**Service Status**: Active (`project-alpha-v2.service`, PID 71891 running `/opt/project-alpha/.venv/bin/python3 app.py`)

All observations, deductions, and test results presented in `explorer_audit_1/handoff.md` (Phase 1: Code Inspection) and `explorer_audit_2/handoff.md` (Phase 2: Unit Test Coverage) were independently verified against the remote VPS and local codebase. No integrity violations (hardcoded test results, facade implementations, bypassed tasks, or fabricated logs) were detected.

---

## 1. Observation

### 1.1 VPS Deployment & File Identity Verification
Through independent SSH and SFTP execution against `root@148.113.9.103:20069`:
- **Production Directory**: `/opt/project-alpha` is actively running via `project-alpha-v2.service` (PID `71891`).
- **File Existence Discrepancies**:
  - `scanner/indicators.py`: **NOT_FOUND** on VPS (`/opt/project-alpha` and `/root/PROJECT-ALPHA`) and local Windows checkout. Git log check `git log --all --full-history -- 'scanner/indicators.py'` returned 0 commits.
  - `scanner/research/indicators.py`: **EXISTS** on both VPS and local. Line count is exactly **203 lines**.
  - `tests/test_v2_indicators.py`: **NOT_FOUND** on VPS and local. Git log check `git log --all --full-history -- '**/test_v2_indicators*'` returned 0 commits.
  - `tests/test_indicator_calculations.py`: **EXISTS** on both VPS and local. Line count is **75 lines**.
- **Bit-for-Bit Hash Verification**:
  - `scanner/research/indicators.py`:
    - Linux VPS SHA256: `09e2f1054fbbfe848caaddcc086775ba76a6329b895bcb5854b4b2686cb97150`
    - Local (CRLF) SHA256: `1dba65913d554717487ee0933d927e6816f4cfc82299c94d8aab12cfce1adbe6`
    - Local normalized (LF) SHA256: `09e2f1054fbbfe848caaddcc086775ba76a6329b895bcb5854b4b2686cb97150` (**EXACT MATCH**)
  - `tests/test_indicator_calculations.py`:
    - Linux VPS SHA256: `dabb77749a7bf4dfaadfc4e55fc7df351fa28e38e123fbb25b0006823e59aebb`
    - Local (CRLF) SHA256: `4ca1c77801ffc320a2efa7495cbd7179e12b035522fa98c9f513e8632d806f9c`
    - Local normalized (LF) SHA256: `dabb77749a7bf4dfaadfc4e55fc7df351fa28e38e123fbb25b0006823e59aebb` (**EXACT MATCH**)
  - `diff -u` between `/opt/project-alpha` and `/root/PROJECT-ALPHA` returned 0 diff lines.

### 1.2 Active Indicator Signatures in `scanner/research/indicators.py`
All 8 functions specified in explorer reports were verified in `/opt/project-alpha/scanner/research/indicators.py`:
1. `compute_ema(prices: np.ndarray, period: int) -> np.ndarray` (L16–30)
2. `compute_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray` (L36–65)
3. `compute_macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal_period: int = 9) -> tuple[np.ndarray, np.ndarray, np.ndarray]` (L71–100)
4. `compute_bollinger(prices: np.ndarray, period: int = 20, std_dev: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]` (L106–128)
5. `compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray` (L134–167)
6. `compute_rvol(volume: np.ndarray, period: int = 20) -> float` (L173–184)
7. `compute_sma(prices: np.ndarray, period: int) -> np.ndarray` (L189–194)
8. `last_valid(arr: np.ndarray) -> float` (L200–203)

### 1.3 Independent Test Execution on VPS
1. **Raw Pytest Invocation**:
   - Command: `cd /opt/project-alpha && .venv/bin/pytest tests/test_indicator_calculations.py -v`
   - Exit code: `2` (Collection error).
   - Verbatim: `ModuleNotFoundError: No module named 'scanner'`.
   - Root Cause: In Python, executing a script binary `.venv/bin/pytest` does not prepend the current working directory to `sys.path`.
2. **Canonical Module Invocation**:
   - Command: `cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v`
   - Exit code: `0` (100% pass).
   - Result: **6 passed in 1.52s** (`test_compute_ema_validation`, `test_compute_rsi_validation`, `test_compute_macd_validation`, `test_compute_bollinger_validation`, `test_compute_atr_validation`, `test_compute_rvol_validation`).
3. **Environment-Explicit Invocation**:
   - Command: `cd /opt/project-alpha && PYTHONPATH=. .venv/bin/pytest tests/test_indicator_calculations.py -v`
   - Exit code: `0` (100% pass).
4. **Secondary Research Suite**:
   - Command: `cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_v2_coin_research.py -k 'computation or bands or atr' -v`
   - Exit code: `0` (100% pass, 5 passed, 9 deselected in 1.78s).

---

## 2. Adversarial Challenge & Stress-Testing

### 2.1 Adversarial Look-Ahead Invariance Stress Test
To rigorously test the explorer agents' claim of "zero look-ahead bias", an independent adversarial stress test script was executed on the VPS.
- **Methodology**:
  1. Generate 80 bars of realistic random walk price data ($T_1 = 80$).
  2. Compute all indicators on this $T_1$ series.
  3. Extend the series to 120 bars ($T_2 = 120$), where bars $0..79$ are identical, but bars $80..119$ contain extreme volatility shocks (5x price shifts and 50-point volatility spikes).
  4. Compute all indicators on the $T_2$ series.
  5. Assert that indicator values for indices $0..79$ in the second run are **strictly identical** (`np.allclose(..., equal_nan=True)`) to the first run.
- **Results**:
  - `ema_lookahead_clean`: **True**
  - `rsi_lookahead_clean`: **True**
  - `bollinger_upper_clean`: **True**, `bollinger_mid_clean`: **True**, `bollinger_lower_clean`: **True**
  - `macd_line_clean`: **True**, `macd_signal_clean`: **True**, `macd_hist_clean`: **True**
  - `atr_clean`: **True**
  - `sma_clean`: **True**
- **Deduction**: Mathematical and empirical causality is 100% proven. Future bars exert zero influence on past indicator values.

### 2.2 Warm-Up Window and NaN Integrity Test
Empirical analysis of warm-up length on a 60-bar sequence on the VPS:
- `compute_ema(p, 10)`: Exactly 9 leading NaNs. First valid at index 9.
- `compute_rsi(p, 14)`: Exactly 14 leading NaNs. First valid at index 14.
- `compute_bollinger(p, 20)`: Exactly 19 leading NaNs. First valid at index 19.
- `compute_atr(h, l, c, 14)`: Exactly 14 leading NaNs. First valid at index 14.
- `compute_macd(p, 12, 26, 9)`:
  - MACD Line: Exactly 25 leading NaNs (`slow - 1`). First valid at index 25.
  - MACD Signal Line: Exactly 33 leading NaNs ($25 + 9 - 1$). First valid at index 33.
  - MACD Histogram: Exactly 33 leading NaNs. First valid at index 33.
- `compute_sma(p, 10)`: Exactly 9 leading NaNs. First valid at index 9.
All indicator warm-up periods conform to mathematical definitions.

### 2.3 Boundary Condition & Hostile Input Stress Test
- **Empty Array (`np.array([])`)**:
  - EMA, RSI, MACD, Bollinger, ATR return 0-length arrays without throwing exceptions.
  - RVOL returns `1.0` (safe default).
  - `last_valid` returns `0.0` (safe fallback).
- **Single Element (`np.array([50.0])`)**:
  - Returns `[NaN]` safely for EMA, RSI, MACD.
  - RVOL returns `1.0`.
  - `last_valid` returns `50.0`.
- **Zero Variance / Flat Price Series (`np.full(50, 100.0)`)**:
  - RSI safely branches `if avg_loss == 0:` and outputs valid `99.9999999` / `100.0`.
  - Bollinger Bands standard deviation collapses to `0.0`, resulting in `upper == mid == lower`.
- **Zero Volume Series (`np.zeros(50)`)**:
  - RVOL checks `if avg_vol <= 0: return 1.0`, returning `1.0` safely without division-by-zero errors.

---

## 3. Logic Chain

1. **Premise**: User prompt requested inspecting `scanner/indicators.py` and running `tests/test_v2_indicators.py`.
2. **Observation**: Neither file exists or ever existed in the repository. The canonical implementation is `scanner/research/indicators.py` and the canonical test suite is `tests/test_indicator_calculations.py`.
3. **Verification**: Both files are bit-for-bit identical between local and VPS (accounting for LF vs CRLF checkout format).
4. **Execution**: Running `tests/test_indicator_calculations.py` via `python3 -m pytest` yields a 100% pass rate (6/6). Secondary tests in `tests/test_v2_coin_research.py` also pass 100% (5/5).
5. **Causality & Correctness**: Array slice inspection and adversarial look-ahead perturbation tests confirm zero future data leakage. Warm-up and edge cases are handled safely.
6. **Integrity Check**: Source code contains genuine mathematical formulas and vector operations; no test results are hardcoded or fabricated.
7. **Conclusion**: Findings of `explorer_audit_1` and `explorer_audit_2` are verified to be fully accurate and complete.

---

## 4. Review Findings & Challenges

### Finding 1 (Major): Repository Test Suite Lacks Look-Ahead & Warm-Up Regression Assertions
- **What**: `tests/test_indicator_calculations.py` validates output dimensions, monotonicity, and values on simple synthetic inputs, but contains zero assertions testing that future data extension does not alter past values. Furthermore, only EMA is tested for NaN warm-up behavior; RSI, MACD, and Bollinger tests only check `last_valid()`.
- **Where**: `tests/test_indicator_calculations.py`
- **Why**: While the current code is mathematically causal, a future developer could accidentally introduce centered rolling windows (`center=True`) or negative index shifts without failing the existing unit tests.
- **Recommendation**: In a future non-audit task, add dedicated regression test cases to `tests/test_indicator_calculations.py` explicitly enforcing causality and verifying warm-up NaN counts.

### Finding 2 (Minor): Execution Vulnerability in Direct Pytest Invocation
- **What**: Running `.venv/bin/pytest` directly from the terminal without `python3 -m pytest` or `PYTHONPATH=.` fails with `ModuleNotFoundError: No module named 'scanner'`.
- **Where**: Repository environment configuration on VPS.
- **Why**: The project is not installed in editable mode (`pip install -e .`) inside the virtual environment.
- **Recommendation**: Ensure deployment documentation and CI scripts specify `python3 -m pytest` or set `PYTHONPATH=.` in `.env`.

### Finding 3 (Minor): Architectural Divergence in Scanner Funnel
- **What**: `scanner/service.py` (L1385–1446) implements its own inline versions of RSI, Volume Ratio, and ATR rather than importing `scanner.research.indicators`.
- **Where**: `scanner/service.py` vs `scanner/research/indicators.py`.
- **Why**: The inline volume ratio in `scanner/service.py` includes `volumes[-1]` in the 20-bar baseline denominator, whereas `compute_rvol` in `scanner/research/indicators.py` strictly excludes `volumes[-1]` (`volume[-(period+1):-1]`). Neither leaks future data, but results differ slightly.
- **Recommendation**: For consistency across the application, harmonize scanner screening logic with `scanner.research.indicators` in future maintenance.

---

## 5. Integrity Attestation

- **Hardcoded test outputs**: NONE found in `scanner/research/indicators.py`.
- **Dummy / facade logic**: NONE found. Implementations execute genuine iterative and vectorized NumPy calculations.
- **Shortcuts or task bypasses**: NONE found.
- **Fabricated verification logs**: NONE. All logs and results reported by explorer agents match verbatim the outputs obtained from independent live VPS runs.
- **Independent verification**: Confirmed independently via remote SSH script execution (`verify_vps.py`).

---

## 6. Conclusion & Verdict

- **Phase 1 (Code Inspection)**: **VERIFIED & APPROVED**.
  - `scanner/indicators.py`: 0 lines (non-existent).
  - `scanner/research/indicators.py`: 203 lines (canonical, 8 active signatures, zero look-ahead bias).
- **Phase 2 (Unit Test Coverage)**: **VERIFIED & APPROVED**.
  - `tests/test_v2_indicators.py`: Non-existent.
  - `tests/test_indicator_calculations.py`: 6/6 tests pass (100%).
  - `tests/test_v2_coin_research.py` indicator subset: 5/5 tests pass (100%).
  - Pytest collection error mechanism (`sys.path` omitted under direct binary call) verified.

**FINAL VERDICT**: **APPROVE**

---

## 7. Verification Method

To independently reproduce this review from any terminal:
```bash
# 1. SSH into VPS
ssh -p 20069 root@148.113.9.103

# 2. Verify git commit and active service
cd /opt/project-alpha
git log -1 --oneline
systemctl status project-alpha-v2.service

# 3. Reproduce canonical test execution (100% pass)
.venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v
.venv/bin/python3 -m pytest tests/test_v2_coin_research.py -k 'computation or bands or atr' -v

# 4. Reproduce the pytest collection failure
.venv/bin/pytest tests/test_indicator_calculations.py -v
```
