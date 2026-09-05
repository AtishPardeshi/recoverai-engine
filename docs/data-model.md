# RecoverAI: Persistent Domain Data Model Specification

**Project:** RecoverAI — Autonomous AI Revenue Recovery Platform  
**Hackathon Track:** Razorpay Ideathon Track 03: AI Revenue Recovery  
**Version:** 1.0.0  
**Phase:** Phase 2 — Domain Data Model + Database Layer  

---

## 1. Entity Overview & Architecture Boundaries

RecoverAI implements nine persistent domain entities designed for high-concurrency payment recovery, deterministic policy guardrails, revenue accounting, and full auditability:

1. **`Customer`**: Merchant customer profile, historical payment track record, and compliance opt-out state.
2. **`Transaction`**: Canonical financial payment attempt and current lifecycle state.
3. **`PaymentFailure`**: Root cause gateway decline details, step, reason, and normalized taxonomy.
4. **`RecoveryCase`**: Active/resolved recovery lifecycle context bound 1:1 to a failed transaction.
5. **`RecoveryAction`**: Immutable record of every planned, approved, or rejected recovery intervention.
6. **`RecoveryOutcome`**: Verified financial outcome recording baseline vs. incremental recovered revenue.
7. **`AuditEvent`**: Chronological, integrity-verifiable audit ledger capturing all decision and execution events.
8. **`SystemicIncident`**: Provider/bank outage circuit-breaker trigger protecting against retry cascades.
9. **`NotificationLog`**: Record of simulated multi-channel customer communications (`EMAIL`, `SMS`, `PAYMENT_LINK`, `REMINDER`).

---

## 2. Entity-Relationship Diagram (Mermaid)

```mermaid
erDiagram
    CUSTOMER ||--o{ TRANSACTION : "initiates"
    CUSTOMER ||--o{ NOTIFICATION_LOG : "receives"
    TRANSACTION ||--o| PAYMENT_FAILURE : "experiences (1:1)"
    TRANSACTION ||--o| RECOVERY_CASE : "generates (1:1)"
    TRANSACTION ||--o{ RECOVERY_OUTCOME : "settles"
    RECOVERY_CASE ||--o{ RECOVERY_ACTION : "triggers"
    RECOVERY_CASE ||--o{ RECOVERY_OUTCOME : "accrues"
    RECOVERY_CASE ||--o{ NOTIFICATION_LOG : "dispatches"
    RECOVERY_ACTION ||--o| RECOVERY_OUTCOME : "results in (1:1)"

    CUSTOMER {
        string id PK
        string external_id UK
        string name
        string email
        string phone
        float historical_success_rate
        float total_transaction_value
        int successful_payment_count
        int failed_payment_count
        boolean is_opted_out
        boolean has_open_dispute
        string subscription_status
        datetime created_at
        datetime updated_at
    }

    TRANSACTION {
        string id PK
        string external_id UK
        string customer_id FK
        float amount
        string currency
        string payment_method
        string status
        string correlation_id
        datetime created_at
        datetime updated_at
    }

    PAYMENT_FAILURE {
        string id PK
        string transaction_id FK, UK
        string error_code
        string error_description
        string error_source
        string error_step
        string error_reason
        string normalized_failure_type
        int retry_count
        string correlation_id
        datetime occurred_at
    }

    RECOVERY_CASE {
        string id PK
        string recovery_case_id UK
        string transaction_id FK, UK
        float revenue_at_risk
        float recovery_probability
        float risk_score
        float priority_score
        string status
        string recommended_action
        string root_cause
        float expected_recovery
        float confidence
        boolean requires_human_review
        int retry_count
        int message_count
        datetime opened_at
        datetime closed_at
        string correlation_id
        datetime created_at
        datetime updated_at
    }

    RECOVERY_ACTION {
        string id PK
        string action_id UK
        string recovery_case_id FK
        int sequence_number
        string idempotency_key UK
        string action_type
        string status
        string recommendation_reason
        float confidence
        float expected_recovery
        string policy_version
        string guardrail_decision
        string guardrail_reason
        string execution_result
        string correlation_id
        datetime requested_at
        datetime approved_at
        datetime executed_at
        datetime created_at
    }

    RECOVERY_OUTCOME {
        string id PK
        string recovery_outcome_id UK
        string recovery_case_id FK
        string recovery_action_id FK, UK
        string transaction_id FK
        string outcome_type
        string result
        float recovered_amount
        float baseline_amount
        float incremental_amount
        string simulator_result
        string failure_reason
        json metadata_payload
        string correlation_id
        datetime occurred_at
    }

    AUDIT_EVENT {
        string id PK
        string event_id UK
        string correlation_id
        string entity_type
        string entity_id
        string event_type
        string actor_type
        text input_summary
        json recommendation
        string guardrail_result
        string execution_result
        float recovered_amount
        json payload
        string policy_version
        string agent_version
        string previous_event_hash
        string event_hash
        datetime created_at
    }

    SYSTEMIC_INCIDENT {
        string id PK
        string incident_id UK
        string provider_or_bank
        string failure_type
        string incident_type
        string status
        float spike_rate
        string affected_payment_method
        string affected_gateway
        text reason
        string correlation_id
        datetime started_at
        datetime resolved_at
    }

    NOTIFICATION_LOG {
        string id PK
        string notification_id UK
        string recovery_case_id FK
        string customer_id FK
        string channel
        string notification_type
        string status
        string idempotency_key UK
        string recipient_reference
        string template_id
        json metadata_payload
        datetime sent_at
    }
```

---

## 3. Entity Definitions & Database Constraints

### 3.1 `customers`
- **Primary Key**: `id` VARCHAR(36)
- **Unique Keys**: `external_id` VARCHAR(64)
- **Check Constraints**:
  - `historical_success_rate >= 0.0 AND historical_success_rate <= 1.0`
  - `total_transaction_value >= 0.0`
  - `successful_payment_count >= 0`
  - `failed_payment_count >= 0`
- **Indexes**: `ix_customers_optout_dispute (is_opted_out, has_open_dispute)`

### 3.2 `transactions`
- **Primary Key**: `id` VARCHAR(36)
- **Unique Keys**: `external_id` VARCHAR(64)
- **Foreign Keys**: `customer_id -> customers.id` (ON DELETE CASCADE)
- **Check Constraints**: `amount >= 0.0`
- **Indexes**:
  - `ix_transactions_status_created (status, created_at)`
  - `ix_transactions_customer_created (customer_id, created_at)`

### 3.3 `payment_failures`
- **Primary Key**: `id` VARCHAR(36)
- **Unique & Foreign Key**: `transaction_id -> transactions.id` (ON DELETE CASCADE, UNIQUE)
- **Check Constraints**: `retry_count >= 0`
- **Indexes**: `ix_payment_failures_type_date (normalized_failure_type, occurred_at)`

### 3.4 `recovery_cases`
- **Primary Key**: `id` VARCHAR(36)
- **Unique Keys**: `recovery_case_id` VARCHAR(64), `transaction_id` VARCHAR(36) (UNIQUE FK)
- **Foreign Keys**: `transaction_id -> transactions.id` (ON DELETE CASCADE)
- **Check Constraints**:
  - `revenue_at_risk >= 0.0`
  - `expected_recovery >= 0.0`
  - `recovery_probability >= 0.0 AND recovery_probability <= 1.0`
  - `risk_score >= 0.0 AND risk_score <= 1.0`
  - `confidence >= 0.0 AND confidence <= 1.0`
  - `retry_count >= 0`, `message_count >= 0`
- **Indexes**:
  - `ix_recovery_cases_priority (priority_score)`
  - `ix_recovery_cases_status_created (status, created_at)`

### 3.5 `recovery_actions`
- **Primary Key**: `id` VARCHAR(36)
- **Unique Keys**: `action_id` VARCHAR(64), `idempotency_key` VARCHAR(128)
- **Compound Unique Key**: `(recovery_case_id, sequence_number)`
- **Foreign Keys**: `recovery_case_id -> recovery_cases.id` (ON DELETE CASCADE)
- **Check Constraints**:
  - `sequence_number >= 1`
  - `confidence >= 0.0 AND confidence <= 1.0`
  - `expected_recovery >= 0.0`
- **Indexes**: `ix_recovery_actions_case_created (recovery_case_id, created_at)`

### 3.6 `recovery_outcomes`
- **Primary Key**: `id` VARCHAR(36)
- **Unique Keys**: `recovery_outcome_id` VARCHAR(64), `recovery_action_id` VARCHAR(36) (UNIQUE FK, nullable for baseline)
- **Foreign Keys**:
  - `recovery_case_id -> recovery_cases.id` (ON DELETE CASCADE)
  - `transaction_id -> transactions.id` (ON DELETE CASCADE)
- **Check Constraints**:
  - `recovered_amount >= 0.0`
  - `baseline_amount >= 0.0`
  - `incremental_amount >= 0.0`
- **Indexes**:
  - `ix_recovery_outcomes_result_date (result, occurred_at)`
  - `ix_recovery_outcomes_type_occurred (outcome_type, occurred_at)`

### 3.7 `audit_events`
- **Primary Key**: `id` VARCHAR(36)
- **Unique Keys**: `event_id` VARCHAR(64)
- **Indexes**:
  - `ix_audit_events_correlation (correlation_id)`
  - `ix_audit_events_entity (entity_type, entity_id)`
  - `ix_audit_events_type_created (event_type, created_at)`

### 3.8 `systemic_incidents`
- **Primary Key**: `id` VARCHAR(36)
- **Unique Keys**: `incident_id` VARCHAR(64)
- **Check Constraints**: `spike_rate >= 0.0 AND spike_rate <= 1.0`
- **Indexes**: `ix_incidents_bank_status (provider_or_bank, status)`

### 3.9 `notification_logs`
- **Primary Key**: `id` VARCHAR(36)
- **Unique Keys**: `notification_id` VARCHAR(64), `idempotency_key` VARCHAR(128)
- **Foreign Keys**:
  - `recovery_case_id -> recovery_cases.id` (ON DELETE CASCADE)
  - `customer_id -> customers.id` (ON DELETE CASCADE)
- **Indexes**: `ix_notification_case_sent (recovery_case_id, sent_at)`

---

## 4. Critical Invariants Enforced

1. **One Transaction $\to$ At Most One Recovery Case**:
   - Enforced by `UNIQUE(transaction_id)` on `recovery_cases`.
   - Prevents parallel conflicting recovery workflows for the same payment.
2. **Action Sequence & Idempotency Uniqueness**:
   - Enforced by `UNIQUE(recovery_case_id, sequence_number)` and `UNIQUE(idempotency_key)`.
3. **Monetary Non-Negativity**:
   - All `amount`, `revenue_at_risk`, `recovered_amount`, `baseline_amount`, and `incremental_amount` fields enforce `CHECK (value >= 0.0)`.
4. **Probability & Confidence Range Invariants**:
   - All probability and confidence scores enforce `CHECK (value >= 0.0 AND value <= 1.0)`.
5. **Revenue Accounting Separation**:
   - `RecoveryOutcome` explicitly tags outcomes as `BASELINE` or `AGENT_RECOVERY` to calculate `INCREMENTAL_RECOVERED_REVENUE = AGENT_RECOVERY - BASELINE_RECOVERY`.

---

## 5. Session Management & Database Initialization

- **Session Local**: Managed via `backend/app/database/session.py` with SQLAlchemy 2.0 scoped generator `get_db()`.
- **Dialect Compatibility**:
  - Local default: SQLite with foreign keys and `check_same_thread=False`.
  - Production ready: Fully compatible with PostgreSQL connection strings (`DATABASE_URL=postgresql://user:pass@host:5432/dbname`).
- **Initialization**: Managed safely via `Base.metadata.create_all(bind=engine)` during FastAPI lifespan startup.
