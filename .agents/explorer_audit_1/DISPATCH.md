# Dispatch for explorer_audit_1

## Task
Phase 1: Code Inspection of `scanner/indicators.py` and `scanner/research/indicators.py` on the VPS.

## Working Directory
`c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_1`

## Credentials & VPS Info
- IP: 148.113.9.103, Port: 20069
- User: root, Password: SMT6SiQU2nIUMj0V
- Use paramiko via local python script if running commands on VPS.

## Instructions
1. First read `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md` (specifically header `## 2026-09-17T08:22:34Z`).
2. Discover where the project is deployed on the VPS (e.g. `/root/PROJECT-ALPHA`, `/root/alpha`, or check running processes / systemd service `systemctl status alpha` or similar).
3. Inspect `scanner/indicators.py` and `scanner/research/indicators.py` on the VPS (and compare with local copies):
   - Report exact line counts for both files on the VPS.
   - List all active indicator function signatures (RSI, MACD, EMA, Bollinger Bands, ATR, Volume indicators).
   - Perform a thorough static scan of both indicator files for any forward-looking / look-ahead data leakage patterns (e.g. `shift(-1)`, `iloc[i+1]`, rolling calculations with future offsets, using `close` before candle completion if applicable, centering rolling windows `center=True`, etc.).
4. Strictly READ-ONLY. Do not modify any code.
5. Write your detailed findings and evidence to `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_1\handoff.md`.
6. Send a message to orchestrator with summary and path to handoff.md.

## 2026-09-17T08:25:54Z
You are explorer_audit_1, a read-only exploration agent for PROJECT-ALPHA.
Your working directory is: `c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\explorer_audit_1`.
Your objective is Phase 1: Code Inspection of `scanner/indicators.py` and `scanner/research/indicators.py` on the VPS.
VPS SSH Details: Host: 148.113.9.103, Port: 20069, User: root, Password: SMT6SiQU2nIUMj0V


