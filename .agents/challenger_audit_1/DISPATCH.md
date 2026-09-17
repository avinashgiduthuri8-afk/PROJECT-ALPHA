# Dispatch for challenger_audit_1

## Role
Code-executing Adversarial Verifier (Indicator Calculations Stress & Boundary Verification)

## Working Directory
`c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_1`

## Credentials & VPS Info
- IP: 148.113.9.103, Port: 20069
- User: root, Password: SMT6SiQU2nIUMj0V
- Use paramiko via local python script to execute commands / tests on the Linux VPS.

## Mandatory Reading
1. `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md` (specifically header `## 2026-09-17T08:22:34Z`).
2. `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_3\handoff.md`.

## Objectives
1. Connect to VPS over SSH and adversarially stress-test the indicator functions in `/opt/project-alpha/scanner/research/indicators.py`:
   - **RSI (Phase 3)**: Test extreme inputs (e.g. constant prices, single large spike, monotonic step-down, series length 1..15). Verify overbought (>70) and oversold (<30) invariants hold without exceptions or division by zero.
   - **MACD (Phase 4)**: Construct DataFrame from `compute_macd` on 40 bars. Assert that final values are non-null and `np.allclose(hist, macd - signal, atol=1e-6)` holds for every single valid bar.
   - **EMA50 (Phase 5)**: Test series of length 0, 1, 49, 50, and 100. Verify that <50 bars produce all NaNs, bar 50 (index 49) matches exact SMA arithmetic mean, and bars >=50 produce non-null floats.
   - **Look-ahead / Causality Invariant**: Append future extreme bars and verify that past indicator values remain bit-for-bit identical.
2. Strictly READ-ONLY on codebase (do not modify repository files).
3. Write your findings, code traces, and verdict (`APPROVE` or `REJECT`) to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_1\handoff.md`.
4. Send a message to orchestrator (conversation ID: `7b08aaa8-087c-44c6-8e57-82b8c9ddbd5d`) with verdict and report path.

## 2026-09-17T08:35:29Z
You are challenger_audit_1, a code-executing adversarial verifier for PROJECT-ALPHA.
Your working directory is: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_1`.

You MUST read:
1. `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md` (header `## 2026-09-17T08:22:34Z`).
2. `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_1\DISPATCH.md`.

VPS SSH: 148.113.9.103:20069, root, SMT6SiQU2nIUMj0V
Use paramiko via local Python script on Windows to connect over SSH.
Stress-test and adversarially verify the indicator calculations on the VPS:
- RSI (Phase 3): extreme inputs, boundary cases, constant series.
- MACD (Phase 4): DataFrame format (40, 3), non-null final values, exact identity hist == macd - signal.
- EMA50 (Phase 5): length <50 (all NaNs), length 50 (seed matches exact arithmetic mean), length >=50 (valid values).
- Causality / look-ahead check: verify that adding future bars does not change past indicator outputs.
Strictly read-only on codebase.
Issue a clear verdict: APPROVE or REJECT.
Write your report to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_audit_1\handoff.md`.
Send a message back to orchestrator (ID: 7b08aaa8-087c-44c6-8e57-82b8c9ddbd5d) with your verdict and handoff path.
