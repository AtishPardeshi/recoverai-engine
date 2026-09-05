# RecoverAI

## AI Revenue Recovery Agent

> "Identify revenue at risk. Understand why payments fail. Recover safely. Measure actual incremental revenue."

Razorpay Ideathon Track 03: **“AI Revenue Recovery: Find revenue that’s slipping away and win it back.”**

---

### Problem

Failed digital payments create significant revenue leakage for merchants and payment platforms. Traditional recovery systems rely on blind, aggressive retries that exhaust customer patience, trigger bank circuit-breakers, spike dispute rates, and degrade customer lifetime value without measuring true business lift.

### Solution

RecoverAI is a full closed-loop, autonomous revenue recovery agent. It combines:

$$\text{Payment Failure} \longrightarrow \text{ML Risk Detection} \longrightarrow \text{AI Recommendation} \longrightarrow \text{Policy Guardrails} \longrightarrow \text{Deterministic Execution} \longrightarrow \text{Simulation} \longrightarrow \text{Actual Revenue Accounting}$$

- **ML Risk Detection**: Supervised Gradient-Boosted Classification (`HistGradientBoostingClassifier`) computing well-calibrated payment recoverability probabilities and risk scores.
- **AI Recommendation Layer**: Multi-modal reasoning agent diagnosing technical root causes (temporary bank declines, insufficient funds, network glitches) and recommending tailored recovery strategies.
- **Deterministic Policy Guardrails**: Hard security boundary with zero LLM execution authority, enforcing terminal-state immutability, customer opt-outs, active dispute blocks, cooldown periods, and systemic incident circuit-breakers.
- **Idempotent Execution Engine**: Enterprise-grade idempotency keys preventing double-charges and race conditions.
- **Payment Gateway Simulator**: Realistic deterministic payment outcome simulator for zero-risk offline evaluation.
- **Closed-Loop Revenue Accounting**: Real-time incrementality tracking that proves actual money recovered versus passive baseline recovery.

### Core Differentiator

Most AI payment solutions stop at predicting probability or generating advice. **RecoverAI demonstrates actual recovered money at batch scale**, persisting execution outcomes and strictly comparing against organic baselines to measure verified **Incremental Recovered Revenue**.

---

## Verified Demo Result

### Current Batch (Batch Execution: `BATCH-0529532396`, Seed: 42)

- **Total Candidates Evaluated**: `39`
- **ML Risk Evaluations**: `39`
- **AI Strategy Recommendations**: `39`
- **Policy Approved**: `16`
- **Policy Rejected (Guardrail Protected)**: `23`
- **Actions Executed**: `16`
- **Successful Recoveries**: `14`

$$\begin{aligned}
\text{Actual Agent Recovered Revenue} &= \mathbf{₹942,690.56} \\
\text{Baseline Recovery} &= \mathbf{₹329,941.70} \\
\text{Incremental Recovered Revenue} &= \mathbf{₹612,748.86}
\end{aligned}$$

$$\text{Formula Invariant: } ₹942,690.56 - ₹329,941.70 = \mathbf{₹612,748.86}$$

---

## Cumulative Database Impact

- **Total Historical Recovery Cases**: `1,000`
- **Cumulative Database Recovered Revenue**: **₹8,985,994.33**
- **Cumulative Baseline Revenue**: **₹3,145,097.98**
- **Cumulative Incremental Revenue**: **₹5,840,896.35**

> [!NOTE]
> *Simulation-based evaluation using deterministic synthetic data.* The cumulative database aggregates 1,000 failure scenarios across cards, UPI, netbanking, and wallets, demonstrating ₹58.41L cumulative incremental recovered revenue in the deterministic simulation.

---

## Architecture & Security Model

```
 ┌──────────────────────┐
 │   Failed Payment     │
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │ ML Feature Pipeline  │ ── 36 features (history, failure codes, amount, velocity)
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │  ML Recovery Model   │ ── ROC-AUC 0.60, PR-AUC 0.83, Expected Recovery Value
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │ AI Recommendation    │ ── Context-aware reasoning (Retry, Payment Link, Alternative)
 └──────────┬───────────┘
            │  (Advisory Only)
            ▼
 ┌────────────────────────────────────────────────────────┐
 │        DETERMINISTIC POLICY / GUARDRAIL ENGINE         │ ◄── HARD SECURITY BOUNDARY
 ├────────────────────────────────────────────────────────┤
 │ • Terminal State Check      • Opt-Out & Dispute Check  │
 │ • Cooldown Period Check     • Max Retries Enforcement  │
 │ • Systemic Incident Breaker • Velocity Rate Limits     │
 └──────────┬─────────────────────────────────────────────┘
            │  (Decision: APPROVED / REJECTED)
            ▼
 ┌──────────────────────┐
 │   Action Executor    │ ── Idempotency Keys (UUIDv5/SHA-256)
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │  Gateway Simulator   │ ── Deterministic multi-stage outcome generation
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │ Database Outcomes    │ ── Persisted RecoveryOutcome (Agent vs Baseline)
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │ Analytics & Dashboard│ ── Scoped Metrics (CURRENT_BATCH vs CUMULATIVE)
 └──────────────────────┘
```

### Safety Principles & Invariants:
1. **AI has ZERO direct execution authority**: The AI agent is advisory only. All executions require deterministic Policy Engine validation.
2. **Strict Financial Accounting**: Predictions are never counted as revenue. Actual revenue derives strictly from persisted successful `RecoveryOutcome` records (`CAPTURED`).
3. **Idempotency & Re-run Safety**: Processing terminal cases produces **₹0.00 duplicate revenue**.

---

## Visual Previews

Screenshots are available in [docs/images/](docs/images/):
- **Executive Dashboard**: `docs/images/dashboard.png`
- **Batch Recovery Execution**: `docs/images/batch-recovery.png`
- **Failure Taxonomy & Analytics**: `docs/images/analytics.png`
- **Case Audit Trail**: `docs/images/audit-trail.png`

---

## Step-by-Step Demo Flow

Follow this 14-step flow to experience the full end-to-end recovery pipeline:

1. **Start the Application**: Run the FastAPI backend on port 8000 and the Vite frontend on port 5173.
2. **Open the Dashboard**: Navigate to `http://localhost:5173`.
3. **Inspect Revenue at Risk**: Observe live revenue at risk across active failed transactions.
4. **Trigger Batch Recovery**: Click **"Run Batch Recovery"** with default seed `42`.
5. **Watch ML Risk Detection**: 39 candidate payment failures evaluated with calibrated recovery probabilities.
6. **Review AI Recommendations**: View recommended actions (`DELAYED_RETRY`, `SEND_PAYMENT_LINK`, `RETRY_PAYMENT`).
7. **Inspect Policy Guardrails**: Observe 23 actions safely rejected to protect customers (opt-outs, disputes, rate limits).
8. **Verify Executed Actions**: 16 actions safely dispatched to the payment simulator.
9. **Inspect Successful Recoveries**: 14 payments successfully captured.
10. **Verify Batch Recovered Revenue**: Reconcile **₹942,690.56** actual agent recovered revenue on the batch card.
11. **Verify Incremental Revenue**: Confirm **₹612,748.86** incremental lift ($\text{Agent} - \text{Baseline}$).
12. **Deep-Dive into Transaction `TX-DEMO-001`**: Inspect rich customer profile, risk scores, and the immutable audit trail.
13. **Switch Analytics Scope**: Toggle between **Current Batch** and **Cumulative DB** to view segregated analytical tables.
14. **Test Rerun Idempotency**: Re-run the batch again and verify that **₹0.00 additional revenue** is created.

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### Local Development Setup

#### 1. Backend Setup
```bash
# Navigate to project root
cd recoverai

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend API documentation available at: `http://localhost:8000/docs`

#### 2. Frontend Setup
```bash
# Open new terminal
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

Frontend application available at: `http://localhost:5173`

---

## Running Tests & Verification

### Backend Automated Test Suite
```bash
# Run all 287 automated unit and integration tests
pytest -v
```

### Frontend Build & Typecheck
```bash
cd frontend
npm run build
```

---

## API Reference

### Recovery Endpoints
- `POST /api/recovery/batch-run`: Run deterministic bulk recovery batch.
- `GET /api/recovery/batches`: List persisted batch runs.
- `GET /api/recovery/batches/{batch_id}`: Retrieve details for a specific batch run.
- `GET /api/recovery-cases`: Filter and search recovery cases.
- `GET /api/recovery-cases/{case_id}`: Inspect single case with ML context.
- `POST /api/recovery-cases/{case_id}/execute`: Execute recovery action with idempotency key.
- `GET /api/recovery-cases/{case_id}/audit`: Retrieve immutable audit events.

### Analytics Endpoints (Scoped: `scope=CURRENT_BATCH` or `scope=CUMULATIVE`)
- `GET /api/analytics/summary?batch_id=<id>&scope=<scope>`: Executive KPI summary.
- `GET /api/analytics/recovery/by-failure-type`: Failure taxonomy breakdown.
- `GET /api/analytics/recovery/by-payment-method`: Payment method breakdown.
- `GET /api/analytics/recovery/by-action`: Action strategy performance.
- `GET /api/analytics/recovery/funnel`: Conversion funnel stages.
- `GET /api/analytics/recovery/predicted-vs-actual`: Calibration and accuracy metrics.

---

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
