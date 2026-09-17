# Handoff Report — Phase 1: Code Inspection of Technical Indicators

## 1. Observation

### 1.1 VPS Deployment & Project Location
Using a local Python script executing Paramiko over SSH to `root@148.113.9.103:20069`:
- **Active Service Location**: `/opt/project-alpha`
  - Systemd service file: `/etc/systemd/system/project-alpha-v2.service`
  - `WorkingDirectory=/opt/project-alpha`
  - `ExecStart=/opt/project-alpha/.venv/bin/python3 app.py`
  - Running process: PID `71891`, `/opt/project-alpha/.venv/bin/python3 app.py`
  - Git commit: `3b4c616` (*Phase G: Scanner backtest integration and fixes*)
- **Secondary Repository Clone**: `/root/PROJECT-ALPHA`
  - Also present on the VPS at git commit `3b4c616`.

### 1.2 Indicator File Existence & Line Counts
Commands executed on the VPS:
- `test -f /opt/project-alpha/scanner/indicators.py && echo EXISTS || echo NOT_FOUND` -> `NOT_FOUND`
- `test -f /root/PROJECT-ALPHA/scanner/indicators.py && echo EXISTS || echo NOT_FOUND` -> `NOT_FOUND`
- `test -f /opt/project-alpha/scanner/research/indicators.py && wc -l /opt/project-alpha/scanner/research/indicators.py` -> `203 /opt/project-alpha/scanner/research/indicators.py`
- `test -f /root/PROJECT-ALPHA/scanner/research/indicators.py && wc -l /root/PROJECT-ALPHA/scanner/research/indicators.py` -> `203 /root/PROJECT-ALPHA/scanner/research/indicators.py`
- Git history check: `git -C /opt/project-alpha log --all --full-history -- 'scanner/indicators.py'` returned empty. `scanner/indicators.py` has never existed as a distinct file in the repository. The canonical technical indicators module is `scanner/research/indicators.py`.

Comparison with local repository (`c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA`):
- Local `scanner/indicators.py`: Non-existent.
- Local `scanner/research/indicators.py`: Exactly 203 lines (204 including trailing newline), 7036 bytes.
- Byte-by-byte comparison between VPS (`/opt/project-alpha/scanner/research/indicators.py`) and local: Exact string match is `True` (0 diff lines).

### 1.3 Active Indicator Function Signatures
In `/opt/project-alpha/scanner/research/indicators.py`:

| # | Indicator / Utility | Function Signature | Defined at Lines |
|---|---|---|---|
| 1 | Exponential Moving Average (EMA) | `compute_ema(prices: np.ndarray, period: int) -> np.ndarray` | L16–30 |
| 2 | Relative Strength Index (RSI) | `compute_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray` | L36–65 |
| 3 | Moving Average Convergence Divergence (MACD) | `compute_macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal_period: int = 9) -> tuple[np.ndarray, np.ndarray, np.ndarray]` | L71–100 |
| 4 | Bollinger Bands | `compute_bollinger(prices: np.ndarray, period: int = 20, std_dev: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]` | L106–128 |
| 5 | Average True Range (ATR) | `compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray` | L134–167 |
| 6 | Relative Volume (RVOL) | `compute_rvol(volume: np.ndarray, period: int = 20) -> float` | L173–184 |
| 7 | Simple Moving Average (SMA) | `compute_sma(prices: np.ndarray, period: int) -> np.ndarray` | L189–194 |
| 8 | Safe Last Non-NaN Extractor | `last_valid(arr: np.ndarray) -> float` | L200–203 |

Auxiliary indicator functions found elsewhere in `scanner/`:
- In `scanner/market_context.py` (L21–30): `calculate_ema(prices: list[float], period: int) -> list[float]`
- In `scanner/service.py` (L1385–1446): Inline calculations for RSI (L1390–1402), Volume Ratio (L1403–1408), and ATR (L1440–1446) for scanner funnel scoring.

### 1.4 Static Scan for Look-Ahead Bias & Data Leakage
Executed searches across `/opt/project-alpha/scanner/` and locally:
- `grep -rnE 'shift|iloc|center' /opt/project-alpha/scanner/` -> 0 results.
- Line-by-line inspection of array slicing and indexing in `scanner/research/indicators.py`:
  - **EMA** (`compute_ema`): Seeding uses `prices[:period]` (indices `0` to `period - 1`). Iterative loop `for i in range(period, len(prices))` calculates `result[i] = prices[i] * k + result[i - 1] * (1.0 - k)`. Uses only price at `i` and prior EMA. No future indexing.
  - **RSI** (`compute_rsi`): `deltas = np.diff(prices)`. Seed average uses `gains[:period]` (deltas up to `period - 1`, corresponding to prices up to index `period`). Loop `for i in range(period, len(deltas))` computes `result[i + 1]` using `gains[i]`, which is `prices[i + 1] - prices[i]`. Strictly backward-looking. No future candle is observed.
  - **MACD** (`compute_macd`): Slices `macd[first_valid:]` forward from index `first_valid`. Evaluates EMA over the valid historical series. Assigns back via `signal[first_valid:] = valid_signal`. Strictly causal.
  - **Bollinger Bands** (`compute_bollinger`): Window slice is `prices[i - period + 1 : i + 1]`. For index `i`, slice stops at `i + 1` (non-inclusive of `i + 1`, meaning it includes exactly index `i` as the last bar). Trailing window only. No centering (`center=False`).
  - **ATR** (`compute_atr`): `tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))`. Uses current high/low and previous close. Seed uses `tr[1 : period + 1]`. Recursive smoothing uses `tr[i]` and `result[i - 1]`. Standard Wilder formulation without look-ahead.
  - **RVOL** (`compute_rvol`): Baseline average uses `volume[-(period + 1) : -1]`, strictly excluding the latest bar `volume[-1]`. Spike ratio divides `volume[-1]` by this trailing baseline.
  - **SMA** (`compute_sma`): Trailing slice `prices[i - period + 1 : i + 1]`. Strictly backward-looking.

---

## 2. Logic Chain

1. **Observation 1.1 & 1.2** show that the production deployment on the VPS is located at `/opt/project-alpha`, matching git commit `3b4c616`. A second clone exists at `/root/PROJECT-ALPHA`.
2. **Observation 1.2** demonstrates that `scanner/indicators.py` does not exist on the VPS or locally, and has never existed in git history. The dispatch request's reference to `scanner/indicators.py` is a common naming assumption for the actual technical indicators file located at `scanner/research/indicators.py`.
3. **Observation 1.2** confirms that `/opt/project-alpha/scanner/research/indicators.py` and local `scanner/research/indicators.py` are 100% identical byte-for-byte, both containing exactly 203 lines.
4. **Observation 1.3** enumerates all 8 functions in `scanner/research/indicators.py`, covering RSI, MACD, EMA, Bollinger Bands, ATR, RVOL, SMA, and `last_valid`.
5. **Observation 1.4** verifies through both regex search and explicit index tracing that no look-ahead operations (`shift(-1)`, `iloc[i+1]`, `center=True`, or indexing past `i`) exist in the indicator codebase.
6. Furthermore, unit tests on the VPS (`tests/test_indicator_calculations.py` with 6 passed tests, and `tests/test_v2_coin_research.py` with 14 passed tests) confirm numerical stability, correct handling of insufficient warm-up periods (returning NaNs or empty lists), and deterministic execution on the VPS Python 3.12 environment.

---

## 3. Caveats

- **File Path Discrepancy**: `scanner/indicators.py` does not exist; all indicator calculations reside in `scanner/research/indicators.py`. Downstream audit phases (Phase 2–7) must import from `scanner.research.indicators`.
- **Inline Scanner Logic**: In `scanner/service.py` (L1381–1446), the scanner funnel uses standalone inline implementations of RSI, ATR, and Volume Ratio rather than directly calling `scanner.research.indicators`. In particular, the inline volume ratio calculates `sum(volumes[-20:]) / 20`, which includes the current bar `volumes[-1]` in the denominator, whereas `compute_rvol` in `scanner/research/indicators.py` strictly excludes `volume[-1]` from the baseline denominator. Both implementations are non-anticipating (no lookahead), but downstream phases should note this subtle distinction.
- **Warm-Up Periods**: Indicators require a minimum warm-up length (`period` for EMA/SMA, `period + 1` for RSI/ATR, `slow + signal_period` for MACD). If candle series are shorter than required, the functions return arrays of NaNs. The caller must verify `~np.isnan(result[-1])` or use `last_valid()` before triggering trade logic.

---

## 4. Conclusion

- **Audit Status**: PASSED.
- **Line Counts**:
  - `scanner/indicators.py`: Does not exist (0 lines).
  - `scanner/research/indicators.py`: 203 lines on VPS (`/opt/project-alpha`), 203 lines in `/root/PROJECT-ALPHA`, and 203 lines locally.
- **Look-Ahead Bias**: Clean. No forward-looking data leakage, no future indexing, no centered rolling windows. All indicators strictly use trailing causal price data.
- **Read-Only Preservation**: Completely preserved. No files were modified, created, or deleted in the VPS or local project source tree.

---

## 5. Verification Method

To independently reproduce and verify this inspection:

1. Connect to VPS via SSH:
   ```bash
   ssh -p 20069 root@148.113.9.103
   ```
2. Verify project location and service:
   ```bash
   systemctl status project-alpha-v2.service
   ls -la /opt/project-alpha/scanner/research/indicators.py
   wc -l /opt/project-alpha/scanner/research/indicators.py
   ```
3. Run the indicator test suites on the VPS:
   ```bash
   cd /opt/project-alpha
   PYTHONPATH=. .venv/bin/pytest tests/test_indicator_calculations.py -v
   PYTHONPATH=. .venv/bin/pytest tests/test_v2_coin_research.py -v
   ```
4. Verify absence of look-ahead keywords across `scanner/`:
   ```bash
   grep -rnE 'shift|iloc|center' /opt/project-alpha/scanner/
   ```
