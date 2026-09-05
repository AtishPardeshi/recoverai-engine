# RecoverAI — Deterministic Policy / Guardrail Engine & Safe Action Executor

> **Core Security Boundary**: "AI recommendations are advisory. The deterministic Policy Engine is the authority for whether an action may execute."
>
> AI NEVER directly executes. The Action Executor requires an authoritative `PolicyDecision` with `status == "APPROVED"`.

---

## 1. Architecture Overview

RecoverAI enforces a hard security and authority boundary across every recovery lifecycle stage. The machine learning model provides risk probability and root cause intelligence, the AI agent synthesizes these insights into an operational recovery recommendation, but **only the deterministic Policy Engine has authority to approve or reject an action**.

```
                    ┌─────────────────────┐
                    │   ML Risk Model     │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │  AI Recommendation  │
                    │       Agent         │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ POLICY / GUARDRAILS │
                    │   DETERMINISTIC     │
                    └──────────┬──────────┘
                         APPROVED│REJECTED
                               ↓
                    ┌─────────────────────┐
                    │   ACTION EXECUTOR   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ PAYMENT SIMULATOR   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │  RECOVERY OUTCOME   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ REVENUE + AUDIT     │
                    └─────────────────────┘
```

---

## 2. Non-Negotiable Authority Hierarchy

```
SYSTEM STATE
     ↓
POLICY / GUARDRAILS (Deterministic Engine)
     ↓
ACTION EXECUTOR
     ↓
PAYMENT GATEWAY SIMULATOR
```

- **AI is Advisory Only**: The LLM cannot approve its own recommendations, cannot modify policy rules, cannot override retry caps or cooldown periods, cannot override customer opt-outs or dispute holds, and cannot invoke the executor or simulator directly.
- **Zero Execution Authority for AI**: Passing an `AIRecommendationDetail` or raw LLM output directly into `ActionExecutor.execute()` raises an immediate `TypeError` / rejection.
- **100% Deterministic Guardrails**: The Policy Engine contains zero LLM inference, zero randomness, and zero non-deterministic dependencies. For identical input states and configuration, the Policy Engine returns identical decisions.

---

## 3. Policy Configuration (`RecoveryPolicyConfig`)

All operational and safety thresholds are centralized in `RecoveryPolicyConfig`:

```python
class RecoveryPolicyConfig(BaseModel):
    max_automated_retries: int = 2
    min_retry_interval_hours: int = 6
    max_payment_link_attempts: int = 1
    max_recovery_duration_hours: int = 72
    max_messages_per_recovery_case: int = 2
    systemic_incident_threshold: float = 0.25
    policy_version: str = "policy-v1"
```

> [!IMPORTANT]
> **Simulation Control Assumption**: The `systemic_incident_threshold` (default `0.25` or 25% failure spike) is a configurable **simulation control assumption**, NOT an official banking industry standard.

---

## 4. Approved Action Taxonomy

RecoverAI strictly limits operations to 7 approved actions:

| Action | Category | Permitted Automation |
|---|---|---|
| `RETRY_PAYMENT` | Payment | Automated immediate retry (if within limits & cooldown) |
| `DELAYED_RETRY` | Payment | Scheduled retry aligned with banking settlement cycles |
| `SEND_PAYMENT_LINK` | Communication | Single simulated payment link dispatch |
| `SUGGEST_ALTERNATIVE_PAYMENT_METHOD` | Communication | Simulated alternative payment guidance message |
| `SEND_REMINDER` | Communication | Simulated customer reminder notification |
| `ESCALATE_TO_HUMAN` | Administrative | Escalation to operations queue; halts automated retries |
| `STOP_RECOVERY` | Administrative | Terminal cancellation; halts automated workflows |

---

## 5. Controlled Policy Reason Codes

Arbitrary reason strings are prohibited. Decisions are indexed by 18 controlled reason codes:

1. `TRANSACTION_NOT_RECOVERY_ELIGIBLE`
2. `TRANSACTION_ALREADY_CAPTURED`
3. `TRANSACTION_ALREADY_RECOVERED`
4. `TRANSACTION_TERMINAL`
5. `RETRY_LIMIT_EXCEEDED`
6. `RETRY_COOLDOWN_ACTIVE`
7. `PAYMENT_LINK_LIMIT_EXCEEDED`
8. `MESSAGE_LIMIT_EXCEEDED`
9. `RECOVERY_WINDOW_EXCEEDED`
10. `CUSTOMER_OPTED_OUT`
11. `OPEN_DISPUTE`
12. `SYSTEMIC_INCIDENT_ACTIVE`
13. `HUMAN_REVIEW_REQUIRED`
14. `INVALID_ACTION`
15. `MISSING_POLICY_CONTEXT`
16. `RECOVERY_CASE_EXHAUSTED`
17. `ACTION_ALREADY_EXECUTED`
18. `IDEMPOTENCY_CONFLICT`

---

## 6. Deterministic Policy Evaluation Sequence

Policy checks execute in strict, deterministic order:

```
 1. Context Existence Validation (Missing context -> MISSING_POLICY_CONTEXT)
 2. Action Taxonomy Check (Unapproved action -> INVALID_ACTION)
 3. Terminal State Check (CAPTURED/RECOVERED/STOPPED/EXHAUSTED/ESCALATED)
 4. Recovery Eligibility Check (CREATED/AUTHORIZED cannot be recovered)
 5. Recovery Window Duration Check (Elapsed > 72h -> RECOVERY_WINDOW_EXCEEDED)
 6. Customer Opt-Out Check (is_opted_out == True -> CUSTOMER_OPTED_OUT)
 7. Open Dispute Lockout (has_open_dispute == True -> OPEN_DISPUTE)
 8. Systemic Incident Circuit Breaker (Active spike >= 25% -> SYSTEMIC_INCIDENT_ACTIVE)
 9. Human Review Advisory Checks (ML prob < 0.20 or AI conf < 0.40)
10. Retry Limit Check (retry_count >= 2 -> RETRY_LIMIT_EXCEEDED)
11. Retry Cooldown Check (elapsed < 6h -> RETRY_COOLDOWN_ACTIVE)
12. Payment Link Limit Check (count >= 1 -> PAYMENT_LINK_LIMIT_EXCEEDED)
13. Customer Message Limit Check (count >= 2 -> MESSAGE_LIMIT_EXCEEDED)
14. Terminal Action Approval (STOP_RECOVERY, ESCALATE_TO_HUMAN)
15. Return APPROVED Decision with full justification trail
```

---

## 7. Guardrail Rules & Protection Mechanisms

### Retry Limits & Cooldown
- `max_automated_retries = 2`: At 2 retries, automated charging ceases and case status transitions to `RECOVERY_EXHAUSTED`.
- `min_retry_interval_hours = 6`: Subsequent retry attempts require at least 6 hours elapsed since previous attempt.

### Communication & Opt-Out
- `is_opted_out = True`: Blocks all customer communication and payment attempts with `CUSTOMER_OPTED_OUT`. Case transitions to `STOPPED`.
- `max_messages_per_recovery_case = 2`: Prevents customer spamming.

### Dispute / Chargeback Protection
- `has_open_dispute = True`: Completely locks automated retries (`OPEN_DISPUTE`) and routes case to `ESCALATED`.

### Systemic Incident Circuit Breaker
- When an active bank or gateway incident is detected and the failure spike exceeds `0.25`, automated payment attempts (`RETRY_PAYMENT`, `DELAYED_RETRY`, `SEND_PAYMENT_LINK`) are halted to prevent cascading debt or throttling.

### Terminal State Double-Charge Protection
- A transaction in `CAPTURED` or `RECOVERED` status can **NEVER** be charged again.
- Even if a stale policy decision claims approval, the `ActionExecutor` re-verifies live database transaction state and returns `ALREADY_CAPTURED` with zero recovered revenue addition.

---

## 8. Safe Action Executor (`ActionExecutor`)

The `ActionExecutor` manages the execution boundary:

1. **Requires `PolicyDecision`**: Must have `decision == "APPROVED"`. Direct AI recommendations raise `TypeError`.
2. **Idempotency**: Key format `recovery:{case_id}:{action_sequence}`.
   - Exact duplicate request $\rightarrow$ Returns existing cached result (1 execution, 1 outcome).
   - Same key with conflicting action $\rightarrow$ Rejects with HTTP 409 `IDEMPOTENCY_CONFLICT`.
3. **Simulation-Only Adapter (`SimulationActionAdapter`)**:
   - Explicitly flags `simulated = True`.
   - Never communicates with live external gateway/banking APIs, SMS gateways, or mail servers.
4. **Atomic Transactions**:
   - `RecoveryAction`, `RecoveryOutcome`, `Transaction`, `RecoveryCase`, `Customer`, and `AuditEvent` updates occur inside a single SQLAlchemy database transaction with full rollback on exception.

---

## 9. Revenue Accounting Model

RecoverAI enforces strict revenue accounting invariants:

- **Zero Revenue on Recommendation**: Recommendations generate no revenue recognition.
- **Zero Revenue on Failed Interventions**: Failed retries record ₹0 recovered revenue.
- **Revenue Recorded Only on Confirmed Capture**:
  $$\text{Incremental Recovered Revenue} = \text{Recovered Revenue} - \text{Baseline Recovery}$$
- **Baseline vs. Agent Separation**: Baseline organic recoveries (e.g. 35% default) are tracked separately and not attributed to AI revenue creation.

---

## 10. Audit Trail & Traceability

Every event throughout recommendation, policy evaluation, execution, and revenue recording generates a cryptographically traceable `AuditEvent`:

- `POLICY_EVALUATION_STARTED` (`actor_type = POLICY_ENGINE`)
- `POLICY_APPROVED` / `POLICY_REJECTED` (`actor_type = POLICY_ENGINE`)
- `ACTION_EXECUTION_STARTED` (`actor_type = EXECUTOR`)
- `ACTION_EXECUTED` / `ACTION_EXECUTION_FAILED` (`actor_type = EXECUTOR`)
- `ACTION_IDEMPOTENCY_HIT` / `ACTION_IDEMPOTENCY_CONFLICT` (`actor_type = EXECUTOR`)
- `RECOVERY_STATE_CHANGED` (`actor_type = EXECUTOR`)
- `RECOVERY_REVENUE_RECORDED` (`actor_type = EXECUTOR`)

Every audit record retains `correlation_id`, `policy_version`, `agent_version`, `entity_id`, and sanitised payloads. Secrets and model chain-of-thought are strictly excluded.

---

## 11. Known Limitations

1. **Simulation Boundary**: Real-money gateway settlements and carrier messaging are simulated by design to prevent real-world financial or communication side effects.
2. **Single Incident Model**: Systemic incidents are tracked globally per provider in the current schema rather than by micro-BIN routing rules.
