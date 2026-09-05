# RecoverAI Automation & Verification Scripts

This directory contains utility scripts for database seeding, demo execution, and pipeline verification.

## Available Scripts

### `run_demo.py`
Executes an end-to-end deterministic batch recovery demonstration on the local database:
1. Resets and seeds synthetic transaction dataset (`seed=42`).
2. Runs batch recovery with candidate selection (39 candidates).
3. Evaluates ML risk, AI recommendation, policy guardrails, execution, and simulator outcomes.
4. Prints batch vs cumulative financial metrics with exact reconciliation invariants.
5. Re-runs the batch to verify idempotency and zero duplicate revenue creation.

```bash
python scripts/run_demo.py
```
