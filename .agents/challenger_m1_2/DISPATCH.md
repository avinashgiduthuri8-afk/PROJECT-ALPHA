# DISPATCH: Challenger 2 for Milestone 1

**Working Directory**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\challenger_m1_2
**Original Request**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\ORIGINAL_REQUEST.md
**Project Plan**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\PROJECT.md
**Worker Handoff**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\worker_m1\handoff.md
**Project Workspace**: c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA

## Mission
Adversarially challenge dynamic equity, mark-to-market calculations, and shared capital invariants:
1. Verify that dynamic total equity formula $\text{Cash} + \text{MTM} - \text{Friction}$ accurately handles positive/negative unrealized PnL, multiple coins with varying tick sizes, and zero-cash states.
2. Verify that shared capital pool constraints (no negative pool, ₹200 minimum notional enforcement) remain strictly unviolated.
3. Verify that restarting the server twice in succession preserves idempotency of hydration without multiplying position counts or capital.
4. Report your empirical findings and confirmation verdict (`CONFIRMED` or `DISCONFIRMED`) in `handoff.md` and send a message to parent.

