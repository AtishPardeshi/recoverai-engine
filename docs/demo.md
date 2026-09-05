# RecoverAI — Judge & Developer Walkthrough Demo Guide

This guide provides a comprehensive step-by-step walkthrough to demonstrate the full capabilities of RecoverAI for the Razorpay Ideathon.

---

## 1. Quick Start

### Start Backend
```bash
source .venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive Swagger API documentation is available at: `http://localhost:8000/docs`

### Start Frontend
```bash
cd frontend
npm run dev
```
Open your browser at `http://localhost:5173`.

---

## 2. Walkthrough Steps

### Step 1: Executive KPI Dashboard
- Observe the **Revenue at Risk** ribbon and **Current Scope** indicators.
- Note the clean visual distinction between **Current Batch** performance and **Cumulative Database** all-time records.

### Step 2: Triggering Closed-Loop Batch Recovery
- Click the **"Run Batch Recovery"** button on the dashboard header (default seed `42`).
- The backend evaluates 39 candidate payment failure cases through:
  $$\text{ML Risk} \longrightarrow \text{AI Recommendation} \longrightarrow \text{Policy Guardrails} \longrightarrow \text{Action Executor} \longrightarrow \text{Gateway Simulator}$$

### Step 3: Verified Financial Reconciliation
- Inspect the batch recovery summary cards:
  - **Candidates Evaluated**: `39`
  - **ML Evaluations**: `39`
  - **AI Strategies Generated**: `39`
  - **Policy Approved**: `16`
  - **Policy Rejected (Protected)**: `23`
  - **Actions Executed**: `16`
  - **Successful Recoveries**: `14`
  - **Actual Agent Recovered Revenue**: **₹942,690.56**
  - **Baseline Recovery**: **₹329,941.70**
  - **Incremental Recovered Revenue**: **₹612,748.86**
- Reconcile the invariant: $₹942,690.56 - ₹329,941.70 = ₹612,748.86$.

### Step 4: Analytical Dimension Deep-Dive
- Navigate to the **Analytics** view.
- Toggle between **Current Batch** and **Cumulative DB** scopes:
  - **Failure Taxonomy**: Candidates, Executed Actions, and Recovered Amounts sum exactly to the 39 batch candidates.
  - **Recovery Action Strategy**: See performance breakdown across `DELAYED_RETRY`, `RETRY_PAYMENT`, `SEND_PAYMENT_LINK`, `ESCALATE_TO_HUMAN`.
  - **Payment Methods**: Inspect conversion across `CARD`, `UPI`, `NETBANKING`, and `WALLET`.

### Step 5: Single-Case Deep Dive (`TX-DEMO-001`)
- Open Recovery Cases and inspect customer **Arjun Verma** (`TX-DEMO-001`):
  - Prior History: 17 successful transactions, 2 prior failed payments.
  - Failure Reason: `TEMPORARY_BANK_DECLINE`.
  - ML Recovery Probability: ~0.89.
  - AI Strategy: `DELAYED_RETRY`.
  - Policy Decision: `APPROVED` with cooldown protection.
  - Execution Outcome: `CAPTURED` with ₹4,500.00 recovered revenue.

### Step 6: Immutable Audit Trail
- Click **"View Audit Trail"** on `TX-DEMO-001` to inspect chronological, cryptographically verifiable events (`ML_EVALUATED`, `AI_RECOMMENDED`, `POLICY_EVALUATED`, `ACTION_EXECUTED`, `OUTCOME_RECORDED`).

### Step 7: Idempotency & Re-run Protection
- Click **"Run Batch Recovery"** a second time.
- Verify that terminal states are protected and **zero duplicate recovery revenue** is generated.

---

## 3. Automated Verification Commands
```bash
# Run all 287 automated tests
pytest -v

# Run Python demo script
python scripts/run_demo.py

# Verify frontend build
cd frontend && npm run build
```
