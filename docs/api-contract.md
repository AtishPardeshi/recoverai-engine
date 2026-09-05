# RecoverAI — Authoritative API Contract Specification

**Document Version:** 1.0.0  
**Phase:** 3 — API Contracts  
**Target Systems:** React/TypeScript Frontend $\leftrightarrow$ FastAPI Backend $\leftrightarrow$ Domain / ML / AI / Policy Services $\leftrightarrow$ SQLite / PostgreSQL Database  
**Authoritative Status:** PASS

---

## 1. API Architectural Principles

RecoverAI exposes a strict, deterministic, and type-safe REST API interface built on FastAPI and Pydantic v2. The API is designed with the following core architectural invariants:

1. **Persisted Backend State as Single Source of Truth:**  
   The frontend never computes or overrides financial KPIs, recovery probabilities, expected recoveries, policy validation decisions, transaction states, or execution outcomes. All figures displayed in the UI are persisted backend database records or derived deterministically by backend services.
2. **Deterministic Error Handling:**  
   All error responses follow a single predictable JSON shape. Stack traces are never exposed in production responses.
3. **Decoupled API Contract & Domain Models:**  
   SQLAlchemy ORM models are never directly exposed as API responses. Dedicated Pydantic response and request schemas govern all network boundaries.
4. **Header-Based Idempotency & Repeat-Safety:**  
   State-modifying execution endpoints enforce repeat-safety via the `Idempotency-Key` HTTP header. Duplicate requests return cached results; conflicting payloads with duplicate keys return `409 Conflict`.
5. **Universal Request Correlation:**  
   Every incoming request is tracked with an `X-Correlation-ID` header. If missing, the backend generates one. All downstream execution steps, simulator calls, and `AuditEvent` records preserve this correlation ID.
6. **Financial Precision & Numeric Values:**  
   Monetary amounts are represented as raw decimal/float numbers paired with an ISO currency code (e.g. `{"amount": 12500.00, "currency": "INR"}`). Currency symbols and locale formatting (e.g. `₹12,500`) belong strictly to the frontend UI layer.

---

## 2. Common API Response & Error Conventions

### 2.1 Identifiers & Naming Conventions
All identifiers follow snake_case JSON field naming and standardized prefixes:
- `transaction_id` / `TX-...`
- `recovery_case_id` / `RC-...`
- `action_id` / `ACT-...`
- `recovery_outcome_id` / `OUT-...`
- `event_id` / `EVT-...`
- `correlation_id` / `corr-...`

### 2.2 Standard Error Response Shape
Every 4xx and 5xx error response returns the following standardized JSON structure:

```json
{
  "error": {
    "code": "POLICY_REJECTED",
    "message": "GUARDRAIL_VIOLATION: Cannot execute actions on terminal case in status 'RECOVERED'.",
    "details": {},
    "correlation_id": "corr-f9a8b7c6d5e4"
  }
}
```

#### Standard Error Codes:
| Error Code | HTTP Status | Description |
| :--- | :--- | :--- |
| `VALIDATION_ERROR` | `422 Unprocessable Entity` / `400 Bad Request` | Request payload, enum value, or query parameter failed schema validation. |
| `NOT_FOUND` | `404 Not Found` | Requested recovery case, transaction, or audit resource does not exist. |
| `RECOVERY_NOT_ELIGIBLE` | `400 Bad Request` | Transaction failure type or customer state is not eligible for automated recovery. |
| `ALREADY_RECOVERED` | `400 Bad Request` / `200 OK (Policy Rejection)` | Payment is already captured; duplicate charge execution blocked. |
| `POLICY_REJECTED` | `200 OK (Execution Response)` / `400 Bad Request` | Deterministic policy guardrails rejected the proposed action. |
| `IDEMPOTENCY_CONFLICT` | `409 Conflict` | Idempotency key previously used with conflicting request parameters. |
| `SYSTEMIC_INCIDENT_ACTIVE` | `200 OK (Policy Rejection)` | Bank provider failure rate exceeds circuit breaker threshold. |
| `HUMAN_REVIEW_REQUIRED` | `200 OK (Policy/AI Response)` | Risk flags require human operator intervention before action. |
| `EXECUTION_FAILED` | `500 Internal Server Error` | Execution engine failed during gateway simulation or persistence. |
| `SIMULATOR_ERROR` | `500 Internal Server Error` | Simulated gateway failure during mock execution. |
| `INTERNAL_ERROR` | `500 Internal Server Error` | Unhandled internal exception. |

---

## 3. Enumerated Types (Enums)

The API enforces strict string enums across all endpoints:

```typescript
// Payment Methods
export type PaymentMethod = "CARD" | "UPI" | "NETBANKING" | "WALLET" | "EMANDATE";

// Transaction & Recovery Statuses
export type TransactionStatus =
  | "CREATED"
  | "AUTHORIZED"
  | "CAPTURED"
  | "FAILED"
  | "RECOVERY_ELIGIBLE"
  | "RECOVERY_IN_PROGRESS"
  | "RECOVERED"
  | "RECOVERY_EXHAUSTED"
  | "ESCALATED"
  | "STOPPED";

// Failure Classification Taxonomy
export type FailureType =
  | "TEMPORARY_BANK_DECLINE"
  | "INSUFFICIENT_FUNDS"
  | "BANK_DECLINE"
  | "NETWORK_ERROR"
  | "EXPIRED_METHOD"
  | "INVALID_DETAILS";

// Recovery Interventions
export type RecoveryActionType =
  | "RETRY_PAYMENT"
  | "DELAYED_RETRY"
  | "SEND_PAYMENT_LINK"
  | "SUGGEST_ALTERNATIVE_PAYMENT_METHOD"
  | "SEND_REMINDER"
  | "ESCALATE_TO_HUMAN"
  | "STOP_RECOVERY";

// Guardrail Decision
export type GuardrailDecision = "APPROVED" | "REJECTED";

// Outcome Results
export type OutcomeResult = "SUCCESS" | "FAILURE" | "SKIPPED";

// Outcome Accounting Type
export type OutcomeType = "BASELINE" | "AGENT_RECOVERY";

// Actor Classification
export type ActorType =
  | "SYSTEM"
  | "ML"
  | "AI_AGENT"
  | "POLICY_ENGINE"
  | "EXECUTOR"
  | "SIMULATOR"
  | "HUMAN"
  | "OPERATOR";
```

---

## 4. Authoritative Endpoint Contracts

### 4.1 GET `/api/dashboard/summary`
- **Purpose:** Retrieves real-time aggregated financial KPI metrics calculated directly from database records.
- **Headers:** `X-Correlation-ID` (optional)
- **Query Parameters:** None
- **Response Status:** `200 OK`
- **Recovery Rate Formula:** $\text{recovery\_rate} = \frac{\text{successful\_recoveries}}{\text{total\_cases}}$ (or $0.0$ if $\text{total\_cases} = 0$).

#### Successful Response (`200 OK`):
```json
{
  "currency": "INR",
  "metrics": {
    "total_payment_volume": 2450000.00,
    "failed_payment_value": 345000.00,
    "revenue_at_risk": 185000.00,
    "recovery_eligible": 140000.00,
    "intervention_value": 160000.00,
    "recovered_revenue": 148500.00,
    "baseline_recovered_revenue": 51975.00,
    "incremental_recovered_revenue": 96525.00,
    "recovery_rate": 0.4305,
    "active_cases": 45,
    "successful_recoveries": 43,
    "total_attempts": 68,
    "guardrail_compliance_rate": 0.9412,
    "average_recovery_probability": 0.6840,
    "guardrail_rejections_count": 4,
    "systemic_incidents_active": 0
  },
  "total_payment_volume": 2450000.00,
  "failed_payment_value": 345000.00,
  "revenue_at_risk": 185000.00,
  "recovery_eligible_value": 140000.00,
  "intervention_value": 160000.00,
  "recovered_revenue": 148500.00,
  "baseline_recovered_revenue": 51975.00,
  "incremental_recovered_revenue": 96525.00,
  "recovery_rate": 0.4305,
  "active_cases_count": 45,
  "total_cases_count": 100,
  "successful_recoveries_count": 43,
  "guardrail_rejections_count": 4,
  "systemic_incidents_active": 0
}
```

---

### 4.2 GET `/api/recovery-cases`
- **Purpose:** Lists recovery cases with priority scoring, status filtering, failure taxonomy filtering, probability bounds, and pagination.
- **Headers:** `X-Correlation-ID` (optional)
- **Query Parameters:**
  - `status`: `Optional[TransactionStatusEnum]`
  - `failure_type`: `Optional[FailureTypeEnum]`
  - `action_type`: `Optional[RecoveryActionTypeEnum]`
  - `payment_method`: `Optional[str]`
  - `min_probability`: `Optional[float]` (range $0.0$ to $1.0$)
  - `max_probability`: `Optional[float]` (range $0.0$ to $1.0$)
  - `search`: `Optional[str]` (filters transaction ID, customer ID, or customer name)
  - `page`: `int = 1` (minimum: 1)
  - `page_size`: `int = 50` (minimum: 1, maximum: 200)
  - `sort_by`: `str = "priority_score"` (`priority_score`, `revenue_at_risk`, `created_at`)
  - `sort_order`: `str = "desc"` (`asc`, `desc`)
- **Ordering Guarantee:** Primary demo case `TX-DEMO-001` is deterministically pinned to the top of the queue when matching active filters.
- **Response Status:** `200 OK`

#### Successful Response (`200 OK`):
```json
[
  {
    "id": "e8a937a0-0453-4889-8dcf-336d39634e42",
    "recovery_case_id": "RC-e8a937a0",
    "transaction_id": "97e68bc6-a94f-4a0b-801b-568eb2a1d355",
    "revenue_at_risk": 12500.00,
    "recovery_probability": 0.87,
    "risk_score": 0.50,
    "priority_score": 10875.00,
    "status": "RECOVERY_ELIGIBLE",
    "recommended_action": "DELAYED_RETRY",
    "root_cause": "TEMPORARY_BANK_DECLINE",
    "expected_recovery": 10875.00,
    "confidence": 0.89,
    "requires_human_review": false,
    "retry_count": 0,
    "message_count": 0,
    "created_at": "2026-09-05T11:45:00Z",
    "updated_at": "2026-09-05T11:45:00Z",
    "transaction": {
      "id": "97e68bc6-a94f-4a0b-801b-568eb2a1d355",
      "external_id": "TX-DEMO-001",
      "customer_id": "c7161476-ba10-449e-b9b2-ff6b0337e3d1",
      "amount": 12500.00,
      "currency": "INR",
      "payment_method": "CARD",
      "status": "FAILED",
      "created_at": "2026-09-05T11:40:00Z",
      "updated_at": "2026-09-05T11:40:00Z",
      "customer": {
        "id": "c7161476-ba10-449e-b9b2-ff6b0337e3d1",
        "external_id": "CUST-1024",
        "name": "Arjun Verma",
        "historical_success_rate": 0.894,
        "total_transaction_value": 212500.00,
        "successful_payment_count": 17,
        "failed_payment_count": 2,
        "is_opted_out": false,
        "has_open_dispute": false,
        "created_at": "2026-06-07T11:40:00Z"
      },
      "payment_failure": {
        "id": "f5e4d3c2-b1a0-4987-6543-210fedcba987",
        "transaction_id": "97e68bc6-a94f-4a0b-801b-568eb2a1d355",
        "error_code": "BAD_REQUEST_PAYMENT_FAILED",
        "error_description": "Issuer bank temporarily throttled card network authorization",
        "error_source": "gateway",
        "error_step": "payment_authorization",
        "error_reason": "TEMPORARY_BANK_DECLINE",
        "normalized_failure_type": "TEMPORARY_BANK_DECLINE",
        "occurred_at": "2026-09-05T11:40:00Z"
      }
    },
    "actions": []
  }
]
```

---

### 4.3 GET `/api/recovery-cases/{id}`
- **Purpose:** Retrieves complete case context, customer profile, failure telemetry, prior actions, and outcomes.
- **Path Parameter:** `id` (UUID or `recovery_case_id`)
- **Headers:** `X-Correlation-ID` (optional)
- **Response Status:** `200 OK` (or `404 Not Found`)

---

### 4.4 POST `/api/recovery-cases/{id}/recommend`
- **Purpose:** Generates a structured AI recommendation combining root-cause diagnosis, ML recovery probability, risk flags, and suggested action.  
  **INVARIANT:** This endpoint NEVER executes financial interventions or modifies payment balances.
- **Path Parameter:** `id` (UUID or `recovery_case_id`)
- **Headers:** `X-Correlation-ID` (optional)
- **Request Body:** None required
- **Response Status:** `200 OK` (or `404 Not Found`)

#### Successful Response (`200 OK`):
```json
{
  "recovery_case_id": "e8a937a0-0453-4889-8dcf-336d39634e42",
  "recommendation": {
    "recommended_action": "DELAYED_RETRY",
    "root_cause": "TEMPORARY_BANK_DECLINE",
    "reason": "Customer Arjun Verma has high reliability (89.4% success over 17 payments). Issuer bank experienced transient card network throttling. A 6-hour delayed retry avoids throttling window with 87% projected recovery.",
    "confidence": 0.89,
    "expected_recovery": 10875.00,
    "risk_flags": [],
    "requires_human_review": false
  },
  "ml": {
    "recovery_probability": 0.87,
    "risk_score": 0.50,
    "priority_score": 10875.00
  },
  "correlation_id": "corr-rec-a1b2c3d4",
  "recommended_action": "DELAYED_RETRY",
  "root_cause": "TEMPORARY_BANK_DECLINE",
  "reason": "Customer Arjun Verma has high reliability (89.4% success over 17 payments). Issuer bank experienced transient card network throttling. A 6-hour delayed retry avoids throttling window with 87% projected recovery.",
  "confidence": 0.89,
  "expected_recovery": 10875.00,
  "risk_flags": [],
  "requires_human_review": false,
  "recovery_probability": 0.87,
  "risk_score": 0.50
}
```

---

### 4.5 POST `/api/recovery-cases/{id}/execute`
- **Purpose:** Executes a recovery intervention strictly through the Deterministic Policy Guardrail Engine and Gateway Simulator.
- **Authority Chain:**
  $$\text{AI/Operator Proposed Action} \longrightarrow \text{Policy Guardrail Engine (11 Checks)} \longrightarrow \text{Gateway Simulator} \longrightarrow \text{Outcome \& Ledger Persistence} \longrightarrow \text{AuditEvent Logging}$$
- **Headers:**
  - `Idempotency-Key`: `string` (required for repeat-safe execution, e.g. `rec-exec-tx-demo-001-attempt-1`)
  - `X-Correlation-ID`: `string` (optional)
- **Request Body:**
  ```json
  {
    "action_type": "DELAYED_RETRY",
    "override_reason": null
  }
  ```
- **Response Status Codes:**
  - `200 OK`: Intervention processed (either executed or safely rejected by policy guardrail).
  - `404 Not Found`: Recovery case does not exist.
  - `409 Conflict`: Idempotency key previously submitted with conflicting action parameters.
  - `422 Unprocessable Entity`: Invalid enum or payload structure.

#### Successful Execution Response (`200 OK`):
```json
{
  "recovery_case_id": "e8a937a0-0453-4889-8dcf-336d39634e42",
  "action": {
    "action_id": "ACT-84F7C19D",
    "action_type": "DELAYED_RETRY",
    "status": "EXECUTED"
  },
  "policy": {
    "approved": true,
    "reason_code": "Policy checks passed (Policy v1.2.0). Within retry limits, cooldowns, and safety thresholds.",
    "violations": [],
    "policy_version": "v1.2.0"
  },
  "outcome": {
    "outcome_type": "AGENT_RECOVERY",
    "outcome_status": "SUCCESS",
    "recovered_amount": 12500.00,
    "baseline_amount": 4375.00,
    "incremental_amount": 8125.00,
    "currency": "INR",
    "simulator_reference": "sim_pay_8a9b0c1d2e3f"
  },
  "transaction_state": "RECOVERED",
  "correlation_id": "corr-exec-99a8b7c6"
}
```

#### Guardrail-Rejected Response (`200 OK` with Policy Rejection):
```json
{
  "recovery_case_id": "e8a937a0-0453-4889-8dcf-336d39634e42",
  "action": {
    "action_id": "ACT-12A34B56",
    "action_type": "DELAYED_RETRY",
    "status": "REJECTED"
  },
  "policy": {
    "approved": false,
    "reason_code": "GUARDRAIL_VIOLATION: Customer has explicitly opted out of recovery communications and retries.",
    "violations": [
      "GUARDRAIL_VIOLATION: Customer has explicitly opted out of recovery communications and retries."
    ],
    "policy_version": "v1.2.0"
  },
  "outcome": null,
  "transaction_state": "STOPPED",
  "correlation_id": "corr-exec-11223344"
}
```

---

### 4.6 GET `/api/recovery-cases/{id}/audit`
- **Purpose:** Retrieves chronological, integrity-verifiable audit events for the specific recovery case.
- **Path Parameter:** `id` (UUID or `recovery_case_id`)
- **Headers:** `X-Correlation-ID` (optional)
- **Response Status:** `200 OK`

#### Successful Response (`200 OK`):
```json
[
  {
    "id": "3b2c1a0f-9e8d-7c6b-5a4f-3e2d1c0b9a8f",
    "event_id": "EVT-87654321ABCD",
    "correlation_id": "corr-exec-99a8b7c6",
    "entity_type": "RECOVERY_ACTION",
    "entity_id": "ACT-84F7C19D",
    "event_type": "ACTION_EXECUTED",
    "actor_type": "EXECUTOR",
    "input_summary": null,
    "recommendation": null,
    "guardrail_result": "APPROVED",
    "execution_result": "SUCCESS",
    "recovered_amount": 12500.00,
    "payload": {
      "case_id": "e8a937a0-0453-4889-8dcf-336d39634e42",
      "action_type": "DELAYED_RETRY",
      "guardrail_status": "APPROVED",
      "outcome_result": "SUCCESS",
      "recovered_amount": 12500.00,
      "simulator_result": "CAPTURED",
      "new_status": "RECOVERED"
    },
    "policy_version": "v1.2.0",
    "agent_version": "v1.0.0",
    "created_at": "2026-09-05T11:46:00Z",
    "timestamp": "2026-09-05T11:46:00Z"
  }
]
```

---

### 4.7 GET `/api/analytics/recovery`
- **Purpose:** Returns comprehensive multi-dimensional recovery analytics, incrementality benchmarks, and probability calibration buckets.
- **Headers:** `X-Correlation-ID` (optional)
- **Response Status:** `200 OK`

#### Successful Response (`200 OK`):
```json
{
  "currency": "INR",
  "by_action": [
    {
      "category": "DELAYED_RETRY",
      "attempted_count": 32,
      "successful_count": 28,
      "recovery_rate": 0.875,
      "recovered_amount": 98500.00
    }
  ],
  "by_failure_type": [
    {
      "category": "TEMPORARY_BANK_DECLINE",
      "attempted_count": 35,
      "successful_count": 30,
      "recovery_rate": 0.857,
      "recovered_amount": 105000.00
    }
  ],
  "by_payment_method": [
    {
      "category": "CARD",
      "attempted_count": 40,
      "successful_count": 32,
      "recovery_rate": 0.800,
      "recovered_amount": 112000.00
    }
  ],
  "incrementality": {
    "baseline_recovery": 51975.00,
    "agent_recovery": 148500.00,
    "incremental_recovery": 96525.00
  },
  "predicted_vs_actual": [
    {
      "probability_bucket": "0.80 - 1.00",
      "total_cases": 28,
      "predicted_expected_revenue": 102000.00,
      "actual_recovered_revenue": 98500.00,
      "calibration_accuracy": 0.965
    }
  ],
  "total_interventions": 68,
  "total_recovered_amount": 148500.00,
  "baseline_recovered_amount": 51975.00,
  "incremental_recovered_amount": 96525.00
}
```

---

### 4.8 GET `/api/activity`
- **Purpose:** Returns real-time database-backed activity feed of audit events with pagination limits.
- **Query Parameters:**
  - `limit`: `int = 30` (minimum: 1, maximum: 100)
- **Headers:** `X-Correlation-ID` (optional)
- **Response Status:** `200 OK`

---

### 4.9 POST `/api/simulator/reset`
- **Purpose:** Resets database tables cleanly for test/demo environments.
- **Response Status:** `200 OK`
- **Response Body:** `{"status": "SUCCESS", "message": "Database reset to clean state"}`

---

### 4.10 POST `/api/simulator/seed`
- **Purpose:** Seeds 1,000+ realistic synthetic transactions and cases with deterministic seed and primary demo case (`TX-DEMO-001`).
- **Query Parameters:**
  - `n_cases`: `int = 1000` (minimum: 10, maximum: 5000)
- **Response Status:** `200 OK`
- **Response Body:**
  ```json
  {
    "status": "SUCCESS",
    "message": "Seeded 1000 synthetic payment cases",
    "details": {
      "transactions_created": 1000,
      "failures_created": 1000,
      "recovery_cases_created": 1000,
      "demo_case_id": "TX-DEMO-001",
      "seed_version": "v1.0.0",
      "total_cases": 1000,
      "historical_recovered": 542,
      "demo_tx_seeded": true
    }
  }
  ```

---

## 5. Demonstration Case Invariant: `TX-DEMO-001`

The primary demonstration transaction satisfies the following immutable invariants across all layers:

| Property | Value | Origin |
| :--- | :--- | :--- |
| **Transaction ID** | `TX-DEMO-001` | Seed Database / Ingestion |
| **Customer ID** | `CUST-1024` (`Arjun Verma`) | Domain Customer Record |
| **Amount** | `₹12,500.00` | Persisted Database Column |
| **Payment Method** | `CARD` | Payment Transaction |
| **Failure Reason** | `TEMPORARY_BANK_DECLINE` | Issuer Network Telemetry |
| **Customer History** | 17 Successes, 2 Failures (89.4% reliability) | Domain Profile |
| **Predicted Probability** | $\approx 87\%$ (`0.87`) | ML Recovery Model Pipeline |
| **Recommended Action** | `DELAYED_RETRY` | AI Decision Agent |
| **Expected Recovery** | $\approx ₹10,875.00$ ($₹12,500 \times 0.87$) | ML Pipeline Calculation |
| **Execution Policy** | `APPROVED` | Deterministic Policy Engine |
| **Recovered Revenue** | `₹12,500.00` | Gateway Simulator |
| **Incremental Revenue** | `₹8,125.00` ($₹12,500 - ₹4,375$ baseline) | Revenue Accounting Ledger |
