# RecoverAI Synthetic Dataset & Data Architecture

## Overview
RecoverAI utilizes a deterministic, seed-reproducible synthetic dataset for evaluation and development.

- **Total Historical Population**: 6,984 synthetic transactions across 351 customer profiles.
- **Organic Captured Payments**: 5,274 captured organic payments.
- **Historical Payment Failures**: 1,710 total payment failures.
- **Resolved Training Failures**: 549 historical failure cases with ground-truth resolution (`RECOVERED`: 403, `RECOVERY_EXHAUSTED`: 146).
- **Active / Unresolved Failure Candidates**: 1,161 failures (with 1,000 baseline cases seeded for simulation and evaluation).

## Failure Taxonomy Categories
1. `TEMPORARY_BANK_DECLINE` — Issuer or gateway throttling/timeout.
2. `INSUFFICIENT_FUNDS` — Account balance shortfall.
3. `BANK_DECLINE` — General acquiring/issuing bank rejection.
4. `NETWORK_ERROR` — Socket timeout, packet drop, gateway connection error.
5. `EXPIRED_METHOD` — Expired card or inactive UPI handle.
6. `INVALID_DETAILS` — Incorrect cardholder/VPA parameters.

## Seed Reproducibility
All synthetic data generation is deterministic and keyed on `seed=42` (`v1.0.0`).
