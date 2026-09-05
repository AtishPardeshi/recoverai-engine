# RecoverAI — AI Revenue Recovery Agent

### Razorpay Ideathon — AI Revenue Recovery
> "Identify revenue at risk. Understand why payments fail. Recover safely. Measure actual incremental revenue."

---

## Problem
Failed digital payments create substantial revenue leakage for online businesses and merchants. Traditional recovery systems rely on static, blind retries that retry without understanding failure context, customer history, recovery probability, or operational constraints. This leads to customer fatigue, issuer throttling, elevated dispute rates, and negative customer lifetime value without measuring true incremental recovery.

## Solution
**RecoverAI** is a closed-loop, autonomous revenue recovery agent. It identifies revenue at risk, predicts recovery likelihood, diagnoses failure context, recommends a bounded recovery strategy, checks it through deterministic policy guardrails, executes it safely in simulation, observes the actual outcome, and measures verified incremental revenue recovered.

---

## Core Pipeline

```
Failed Payment
       ↓
ML Risk Detection
       ↓
AI Root Cause & Recommendation
       ↓
Deterministic Policy Guardrail Engine  ◄── HARD SECURITY BOUNDARY
       ↓
Safe Action Executor (Idempotent)
       ↓
Payment Gateway Simulator
       ↓
Actual Recovery Outcome (Persisted)
       ↓
Revenue Accounting (Agent vs Baseline)
       ↓
Executive Analytics Dashboard
```

---

## Authority & Security Model

- **ML Model**: Prediction only (Recovery Probability, Expected Recovery Value).
- **AI Agent**: Recommendation only (Context-aware Root Cause Diagnosis & Strategic Action).
- **Policy Engine**: Authoritative safety gate (Customer Opt-outs, Open Disputes, Cooldowns, Retries, Circuit Breakers).
- **Action Executor**: Execution only after deterministic policy approval with SHA-256 idempotency keys.
- **Payment Simulator**: Deterministic payment outcome simulation for zero-risk validation.
- **Revenue Accounting**: Revenue derives strictly from persisted successful `CAPTURED` outcomes — never from ML probability estimates.

---

## Business Impact

> [!NOTE]
> **Deterministic Simulation Results**: The figures below represent verified offline evaluation on deterministic synthetic data using `seed 42`. They demonstrate the autonomous recovery architecture and are not live Razorpay production metrics.

### Current Batch Verification (`BATCH-0529532396`, Seed: 42)
- **Total Candidates Evaluated**: `39`
- **Policy-Approved Actions**: `16`
- **Policy-Rejected (Guardrail Protected)**: `23`
- **Actions Executed**: `16`
- **Successful Recoveries**: `14`
- **Agent Recovered Revenue**: **₹942,690.56**
- **Baseline Organic Recovery**: **₹329,941.70**
- **Incremental Recovered Revenue**: **₹612,748.86**

$$\text{Incremental Revenue} = \text{Agent Recovered Revenue} - \text{Baseline Recovery}$$
$$₹942,690.56 - ₹329,941.70 = \mathbf{₹612,748.86}$$

### Cumulative Database Impact
- **Total Historical Cases**: `1,000`
- **Cumulative Recovered Revenue**: **₹8,985,994.33**
- **Cumulative Baseline Revenue**: **₹3,145,097.98**
- **Cumulative Incremental Revenue**: **₹5,840,896.35**

---

## Key Features

- **ML Recovery-Risk Prediction**: Supervised gradient boosting (`HistGradientBoostingClassifier`) with 36 engineered customer, transaction, and velocity features.
- **AI Contextual Recommendation**: Multi-factor root cause diagnosis selecting from 7 bounded recovery actions (`RETRY_PAYMENT`, `DELAYED_RETRY`, `SEND_PAYMENT_LINK`, `REQUEST_ALTERNATIVE_METHOD`, `OFFER_ALTERNATIVE_PAYMENT_METHOD`, `CUSTOMER_SUPPORT_ESCALATION`, `DO_NOT_RECOVER`).
- **Root-Cause Taxonomy**: Automated categorization across temporary bank declines, insufficient funds, network glitches, expired instruments, and invalid credentials.
- **Deterministic Policy Engine**: Comprehensive safety rules enforcing cooldown windows, retry ceilings, customer opt-outs, and active dispute blocks.
- **Systemic-Incident Circuit Breaker**: Real-time detection of bank/gateway outages that automatically suspends retries to prevent cascade failures.
- **Idempotent Action Execution**: Enterprise-grade idempotency keys ensuring repeat execution safety.
- **Terminal-State Protection**: Guaranteed ₹0.00 duplicate charges on already terminal or captured transactions.
- **Baseline vs. Agent Accounting**: Direct comparison against organic recovery baselines to isolate true AI lift.
- **Batch Processing Engine**: High-throughput batch processing with persistent `BatchRun` database records.
- **Scoped Analytics**: Dynamic toggling between `CURRENT_BATCH` and `CUMULATIVE` database metrics.
- **Immutable Audit Trail**: Append-only event store capturing every ML inference, AI recommendation, policy decision, and gateway response.
- **Interactive Executive Dashboard**: Modern React/Tailwind frontend with real-time KPI metrics, conversion funnel, and calibration charts.

---

## Razorpay Conceptual Boundary

> **Disclaimer**: This project is a simulation-first prototype built for the Razorpay Ideathon Track 03. It operates on a local sandbox database and deterministic payment gateway simulator. It does not initiate real banking transactions or connect to private production Razorpay APIs.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 1. Backend Setup
```bash
# Clone the repository
git clone https://github.com/<your-username>/RecoverAI.git
cd RecoverAI

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend API server (FastAPI + Uvicorn)
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be available at: `http://localhost:8000/docs`

### 2. Frontend Setup
```bash
# In a new terminal window
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```
Dashboard will be available at: `http://localhost:5173`

---

## 60–90 Second Demo Flow

1. **Open Dashboard**: Navigate to `http://localhost:5173` to view real-time Revenue at Risk and recovery KPIs.
2. **Review Failed Payment Queue**: Inspect incoming payment failure cases across UPI, Cards, Netbanking, and Wallets.
3. **Inspect Case `TX-DEMO-001`**: Click on the showcase transaction for Arjun Verma (₹12,500 decline).
4. **Inspect ML Risk Score**: View the 87% predicted recovery probability derived from historical customer success patterns.
5. **Inspect AI Recommendation**: Review the recommended `DELAYED_RETRY` strategy and contextual root-cause explanation.
6. **Verify Policy Decision**: See the deterministic policy check pass (no dispute, cooldown satisfied).
7. **Execute Recovery**: Click **"Execute Recovery"** and observe the simulated `CAPTURED` outcome.
8. **Verify Recovered Revenue**: Confirm revenue accounting updates from persisted database records.
9. **Run Batch Recovery**: Click **"Run Batch Recovery"** in the top navigation bar.
10. **Analyze Current Batch**: Observe the 39 evaluated candidates, 16 policy approvals, 14 captures, and **₹612,748.86** incremental revenue.
11. **Toggle Cumulative Scope**: Switch the analytics selector to **"Cumulative DB"** to view aggregate metrics across 1,000 cases.
12. **Inspect Failure Taxonomy**: Review recovery breakdown across failure types and payment methods in the interactive charts.
13. **Simulate Systemic Outage**: Click **"Simulate HDFC Outage"** and verify that policy guardrails immediately block automated retries.
14. **Inspect Audit Trail**: Navigate to the Audit tab to view the tamper-evident chronological event log.

---

## Testing & Quality Assurance

RecoverAI includes an automated test suite covering unit tests, integration contracts, security invariants, batch persistence, and end-to-end acceptance:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run complete pytest test suite
pytest -v
```

### Test Results
- **Pytest**: `287 passed, 1 skipped in ~48s`
- **Frontend Build**: `tsc -b && vite build` (0 TypeScript errors, 0 build warnings)
- **Key Test Suites**:
  - `test_phase5_ml_pipeline.py`: Feature engineering, model evaluation, calibration checks.
  - `test_phase6_ai_agent.py`: Advisory boundary, schema validation, fallback provider.
  - `test_phase7_policy_and_executor.py`: Policy guardrails, cooldowns, dispute blocking, idempotency.
  - `test_phase8_batch_and_analytics.py`: Closed-loop batch lifecycle, scope isolation, revenue accounting.
  - `test_phase8_batch_persistence_and_restart.py`: Process restart durability for `BatchRun` records.
  - `test_phase8_e2e_acceptance.py`: End-to-end failed payment to captured revenue lifecycle.

---

## Machine Learning Disclosure

> The ML recovery risk model is evaluated on a synthetic payments dataset with a holdout set. Its performance metrics demonstrate the end-to-end feature pipeline, probability calibration, and integration with the policy engine rather than production-level fraud or recovery benchmarks.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
