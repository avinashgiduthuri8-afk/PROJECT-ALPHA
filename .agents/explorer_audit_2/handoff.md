# Phase 2: Unit Test Coverage on VPS — Handoff Report

## Executive Summary
An exhaustive, read-only audit of the indicator unit test suite for PROJECT-ALPHA was conducted on the remote Linux VPS (`148.113.9.103:20069`) and compared against the local Windows repository.
- The prompt-referenced test file `tests/test_v2_indicators.py` **never existed** in the repository git history. The canonical indicator test suite is `tests/test_indicator_calculations.py` (with supplementary tests in `tests/test_v2_coin_research.py`).
- Executing the test suite via `.venv/bin/pytest` directly fails with `ModuleNotFoundError: No module named 'scanner'` due to `sys.path` not containing the project root.
- Executing via `.venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v` succeeds with **100% pass rate (6/6 passed in 0.71s)**.
- In addition, the 5 pure NumPy indicator tests in `tests/test_v2_coin_research.py` pass 100% (5/5 passed in 1.06s).
- Direct mathematical analysis and empirical VPS verification confirm **zero look-ahead bias** and strict causality across all indicator implementations (EMA, RSI, MACD, Bollinger Bands, ATR, RVOL).
- However, existing test coverage has notable gaps: no existing unit test explicitly validates look-ahead invariance, and warm-up / edge cases are only partially covered.

---

## 1. Observation

### 1.1 Test Suite Identification and Paths
- **Target File `tests/test_v2_indicators.py`**:
  - Local repository search: `find_by_name` across `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA` yielded `0` results.
  - Remote VPS search: `find / -iname '*test_v2*indicator*' 2>/dev/null` yielded `0` results.
  - Remote git history check:
    ```bash
    cd /root/PROJECT-ALPHA && git log --all --full-history -- '**/test_v2_indicators*'
    # Result: Exit code 0, 0 commits found.
    ```
- **Canonical Indicator Test Suite**:
  - Located at `tests/test_indicator_calculations.py` (both locally and on the VPS).
  - Git history confirms it was introduced in commit `69a0a765d0ac29d8cd57240c47ca0f66bdeff115` ("feat: complete V2 pipeline integration and 100% test pass rate") and formatted in commit `06c38625d78e758bb5de7fbcaebff1201226da88`.
  - Secondary indicator tests reside in `tests/test_v2_coin_research.py` (lines 84–136).
- **VPS Deployment Locations**:
  - Active production deployment: `/opt/project-alpha/` (Running service PID 71891: `/opt/project-alpha/.venv/bin/python3 app.py`).
  - Development repository: `/root/PROJECT-ALPHA/`.
  - Both directories are on branch `main` at commit `3b4c616 Phase G: Scanner backtest integration and fixes`.
  - Files `tests/test_indicator_calculations.py` and `scanner/research/indicators.py` are bit-for-bit identical between `/opt/project-alpha` and `/root/PROJECT-ALPHA` (verified via `diff -u`).

---

### 1.2 Test Execution Results on VPS

#### Test Run 1: Direct pytest binary execution
- **Command**:
  ```bash
  cd /opt/project-alpha && .venv/bin/pytest tests/test_indicator_calculations.py -v
  ```
- **Result**: Exit code `2` (collection error).
- **Verbatim Output**:
  ```
  ============================= test session starts ==============================
  platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0 -- /opt/project-alpha/.venv/bin/python3
  cachedir: .pytest_cache
  rootdir: /opt/project-alpha
  plugins: asyncio-1.4.0, anyio-4.15.0
  asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
  collecting ... collected 0 items / 1 error

  ==================================== ERRORS ====================================
  ____________ ERROR collecting tests/test_indicator_calculations.py _____________
  ImportError while importing test module '/opt/project-alpha/tests/test_indicator_calculations.py'.
  Hint: make sure your test modules/packages have valid Python names.
  Traceback:
  /usr/lib/python3.12/importlib/__init__.py:90: in import_module
      return _bootstrap._gcd_import(name[level:], package, level)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  tests/test_indicator_calculations.py:3: in <module>
      from scanner.research.indicators import (
  E   ModuleNotFoundError: No module named 'scanner'
  =========================== short test summary info ============================
  ERROR tests/test_indicator_calculations.py
  !!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
  =============================== 1 error in 0.18s ===============================
  ```

#### Test Run 2: Module-level pytest invocation (`python3 -m pytest`)
- **Command**:
  ```bash
  cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v
  ```
- **Result**: Exit code `0`, **6 passed in 0.71s**.
- **Verbatim Output**:
  ```
  ============================= test session starts ==============================
  platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0 -- /opt/project-alpha/.venv/bin/python3
  cachedir: .pytest_cache
  rootdir: /opt/project-alpha
  plugins: asyncio-1.4.0, anyio-4.15.0
  asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
  collecting ... collected 6 items

  tests/test_indicator_calculations.py::test_compute_ema_validation PASSED [ 16%]
  tests/test_indicator_calculations.py::test_compute_rsi_validation PASSED [ 33%]
  tests/test_indicator_calculations.py::test_compute_macd_validation PASSED [ 50%]
  tests/test_indicator_calculations.py::test_compute_bollinger_validation PASSED [ 66%]
  tests/test_indicator_calculations.py::test_compute_atr_validation PASSED [ 83%]
  tests/test_indicator_calculations.py::test_compute_rvol_validation PASSED [100%]

  ============================== 6 passed in 0.71s ===============================
  ```

#### Test Run 3: Root clone verification (`/root/PROJECT-ALPHA`)
- **Command**:
  ```bash
  cd /root/PROJECT-ALPHA && .venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v
  ```
- **Result**: Exit code `0`, **6 passed in 1.16s**.

#### Test Run 4: Secondary indicator suite (`tests/test_v2_coin_research.py`)
- **Command**:
  ```bash
  cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_v2_coin_research.py -k 'computation or bands or atr' -v
  ```
- **Result**: Exit code `0`, **5 passed, 9 deselected in 1.06s**.
- **Test Cases**:
  - `tests/test_v2_coin_research.py::test_ema_computation`: PASSED
  - `tests/test_v2_coin_research.py::test_rsi_computation`: PASSED
  - `tests/test_v2_coin_research.py::test_macd_computation`: PASSED
  - `tests/test_v2_coin_research.py::test_bollinger_bands`: PASSED
  - `tests/test_v2_coin_research.py::test_atr_and_rvol`: PASSED

---

### 1.3 Individual Test Cases Breakdown in `tests/test_indicator_calculations.py`

| Test Case | Target Function | Invariants & Assertions Tested | Status |
|---|---|---|---|
| `test_compute_ema_validation` | `compute_ema` | 1. Output length equals input length (`len(ema) == len(prices)`)<br>2. First period-1 values are NaN (`assert np.isnan(ema[0])`)<br>3. First valid value at index 4 for period 5 (`assert not np.isnan(ema[4])`)<br>4. Monotonic uptrend response (`assert ema[-1] > ema[4]`)<br>5. Insufficient data edge case: returns all NaNs (`short_prices = [10.0, 11.0]`) | PASSED |
| `test_compute_rsi_validation` | `compute_rsi` | 1. Uptrend response: linear climb over 30 bars yields `last_valid(rsi) >= 90.0`<br>2. Downtrend response: linear drop over 30 bars yields `last_valid(rsi) <= 10.0`<br>3. Zero variance edge case: 30 flat prices yield non-NaN valid number | PASSED |
| `test_compute_macd_validation` | `compute_macd` | Output dimension preservation: `len(macd) == 40`, `len(signal) == 40`, `len(hist) == 40` | PASSED |
| `test_compute_bollinger_validation` | `compute_bollinger` | Mathematical ordering invariant: `last_valid(upper) >= last_valid(mid) >= last_valid(lower)` | PASSED |
| `test_compute_atr_validation` | `compute_atr` | Volatility bounds invariant: `last_valid(atr) > 0.0` for 30 bars with constant range | PASSED |
| `test_compute_rvol_validation` | `compute_rvol` | 1. Ratio calculation: 500 volume spike on 100 baseline yields `rvol == 5.0`<br>2. Insufficient data edge case: `< period + 1` volume bars return default `1.0` | PASSED |

---

### 1.4 Empirical Verification of Look-Ahead, Warm-Up, and Edge Cases on VPS
An automated diagnostic script (`.agents/explorer_audit_2/audit_indicators_vps.py`) was executed on the VPS using `/opt/project-alpha/.venv/bin/python3` against `scanner.research.indicators`.

- **Verbatim Output**:
  ```
  === LOOK-AHEAD CAUSALITY CHECK ===
  EMA causal: True
  RSI causal: True
  Bollinger causal: True
  ATR causal: True
  MACD line causal: True
  MACD signal causal: True

  === WARM-UP CHECK ===
  EMA(10) nan count: 9 (expected 9)
  RSI(14) nan count: 14 (expected 14)
  BB(20) nan count: 19 (expected 19)
  ATR(14) nan count: 14 (expected 14)
  MACD line nan count: 25 (expected 25)
  MACD signal nan count: 33 (expected 33)

  === EDGE CASES CHECK ===
  Empty array EMA: []
  Single value EMA: [nan]
  Zero variance RVOL (all 0 vol): 1.0
  Zero volume handled safely: True
  ```

---

## 2. Logic Chain

1. **Test Suite Mapping**:
   - *Premise*: The audit instructions specified executing `tests/test_v2_indicators.py`.
   - *Observation*: Neither the working copy nor git history contained `tests/test_v2_indicators.py`. Grep and file inspections revealed `tests/test_indicator_calculations.py` testing the exact indicator module `scanner.research.indicators`.
   - *Deduction*: `tests/test_indicator_calculations.py` is the actual, canonical test suite intended for indicator unit test coverage in V2.

2. **Root Cause of Pytest Failure**:
   - *Observation*: Invoking `.venv/bin/pytest tests/test_indicator_calculations.py` failed with `ModuleNotFoundError: No module named 'scanner'`.
   - *Observation*: Invoking `.venv/bin/python3 -m pytest tests/test_indicator_calculations.py` succeeded with 100% pass rate.
   - *Deduction*: When `pytest` is invoked directly from the virtual environment without an installed editable package (`pip install -e .`) or an explicit `PYTHONPATH`, Python does not add the current working directory (`/opt/project-alpha`) to `sys.path`. Using `python3 -m pytest` automatically prepends `cwd` to `sys.path`.

3. **Look-Ahead Bias Assessment**:
   - *Observation*: Code inspection of `scanner/research/indicators.py` revealed:
     - `compute_ema`: Iterates forward in time `for i in range(period, len(prices)): result[i] = prices[i] * k + result[i - 1] * (1.0 - k)`.
     - `compute_rsi`: Iterates forward in time updating `avg_gain` and `avg_loss` with current `deltas[i]`.
     - `compute_macd`: Combines causal EMAs (`ema_fast - ema_slow`), and signal EMA is computed on causal MACD.
     - `compute_bollinger`: Computes mean and standard deviation on backward sliding window `prices[i - period + 1 : i + 1]`.
     - `compute_atr`: Computes True Range using current high/low and previous close, smoothed with backward Wilder recursion.
     - `compute_rvol`: Compares the latest bar `volume[-1]` against historical bars `volume[-(period + 1) : -1]`.
   - *Empirical Check*: Appending 3 future bars to a 50-bar price series resulted in zero difference (`np.allclose == True`) across all past 50 indicator values.
   - *Deduction*: The indicator algorithms are mathematically causal and free of look-ahead leakage. However, **none** of the existing automated unit tests in `tests/test_indicator_calculations.py` or `tests/test_v2_coin_research.py` test for look-ahead bias or enforce future data invariance.

4. **Warm-Up Period Assessment**:
   - *Observation*: `compute_ema` seeds at `period - 1` and produces `period - 1` NaNs. `compute_rsi` seeds after `period` deltas and produces `period` NaNs. `compute_bollinger` produces `period - 1` NaNs. `compute_atr` produces `period` NaNs. `compute_macd` produces `slow - 1` NaNs for MACD line and `(slow - 1) + (signal_period - 1)` NaNs for signal line.
   - *Test Audit*: Only `test_compute_ema_validation` checks warm-up NaNs (`assert np.isnan(ema[0])` and `assert not np.isnan(ema[4])`). The tests for RSI, MACD, Bollinger, and ATR do not assert the presence of NaN values during the warm-up period.

5. **Edge Case Handling Assessment**:
   - *Observation*: Handled edge cases:
     - Short series for EMA: `if len(prices) < period: return result` (returns array of NaNs). Tested in unit tests.
     - Short series for RVOL: `if len(volume) < period + 1: return 1.0`. Tested in unit tests.
     - Zero variance for RSI: `if avg_loss == 0: result[period] = 100.0`. Tested in unit tests.
     - Zero volume for RVOL: `if avg_vol <= 0: return 1.0`. Handled in code, verified empirically.
   - *Untested Edge Cases in Test Suite*: Empty arrays (`len == 0`), single-bar arrays (`len == 1`), zero/negative price values, and insufficient data for MACD, Bollinger, and ATR.

---

## 3. Caveats
- **Test File Naming**: The file `tests/test_v2_indicators.py` cited in the prompt does not exist; all findings are based on `tests/test_indicator_calculations.py` and `tests/test_v2_coin_research.py`.
- **Look-ahead Test Omission**: While indicator logic is proven mathematically causal, no regression test exists in the repository to prevent a future contributor from inadvertently introducing look-ahead bias (e.g., centering rolling windows or using `.shift(-1)`).
- **Service Integration**: This audit covers unit test execution and indicator calculation logic. Evaluation of live DB signals and scanner runtime integration belongs to subsequent audit phases.

---

## 4. Conclusion
1. The indicator test suite for PROJECT-ALPHA is located at `tests/test_indicator_calculations.py`.
2. All **6 unit tests in `tests/test_indicator_calculations.py` pass 100%** on the VPS when executed with `.venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v`.
3. All **5 pure NumPy indicator tests in `tests/test_v2_coin_research.py` also pass 100%**.
4. Executing pytest via the raw binary `.venv/bin/pytest` will fail with `ModuleNotFoundError: No module named 'scanner'` unless `PYTHONPATH=.` or `python3 -m pytest` is used.
5. All indicator implementations in `scanner/research/indicators.py` are strictly causal with **zero look-ahead bias** and proper warm-up NaN handling.
6. The test suite currently lacks explicit assertions for look-ahead bias and has partial coverage for warm-up and edge cases.

---

## 5. Verification Method

### Command 1: Run Canonical Indicator Test Suite on VPS
```bash
# Connect to VPS and run within production directory
ssh -p 20069 root@148.113.9.103 "cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v"
```
- **Expected Output**:
  - `collected 6 items`
  - `tests/test_indicator_calculations.py::test_compute_ema_validation PASSED`
  - `tests/test_indicator_calculations.py::test_compute_rsi_validation PASSED`
  - `tests/test_indicator_calculations.py::test_compute_macd_validation PASSED`
  - `tests/test_indicator_calculations.py::test_compute_bollinger_validation PASSED`
  - `tests/test_indicator_calculations.py::test_compute_atr_validation PASSED`
  - `tests/test_indicator_calculations.py::test_compute_rvol_validation PASSED`
  - `6 passed in < 1.5s`

### Command 2: Run Research Indicator Subset on VPS
```bash
ssh -p 20069 root@148.113.9.103 "cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_v2_coin_research.py -k 'computation or bands or atr' -v"
```
- **Expected Output**: `5 passed, 9 deselected in < 2.0s`.

### Command 3: Reproduce the ModuleNotFoundError Collection Failure
```bash
ssh -p 20069 root@148.113.9.103 "cd /opt/project-alpha && .venv/bin/pytest tests/test_indicator_calculations.py -v"
```
- **Expected Output**: Exit code 2, `ModuleNotFoundError: No module named 'scanner'`.

### Invalidation Conditions
- Any test failure in `tests/test_indicator_calculations.py`.
- Any non-zero difference when extending future bars in causality checks.
- Changes to `scanner/research/indicators.py` that alter smoothing formulas or window centering.
