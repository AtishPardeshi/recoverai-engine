import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.transaction import Transaction
from backend.app.models.customer import Customer
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.audit_event import AuditEvent
from backend.app.models.notification import NotificationLog
from backend.app.schemas.common import (
    RecoveryActionTypeEnum,
    GuardrailDecisionEnum,
    OutcomeTypeEnum,
    OutcomeResultEnum,
    TransactionStatusEnum,
)
from backend.app.schemas.policy import PolicyDecision, PolicyReasonCode
from backend.app.simulator.gateway_simulator import PaymentGatewaySimulator, simulator as global_simulator
from backend.app.config.config import settings

class ExecutionResult(BaseModel):
    """
    Structured outcome of an executed recovery action.
    """
    action_id: str
    action_type: RecoveryActionTypeEnum
    status: str
    simulated: bool = True
    idempotency_key: str
    sequence_number: int
    outcome_id: str | None = None
    outcome_result: OutcomeResultEnum | None = None
    simulator_result: str | None = None
    recovered_amount: float = 0.0
    baseline_amount: float = 0.0
    incremental_amount: float = 0.0
    currency: str = "INR"
    failure_reason: str | None = None
    provider_reference: str | None = None
    new_case_status: TransactionStatusEnum
    new_transaction_status: TransactionStatusEnum
    audit_event_id: str | None = None
    executed_at: datetime

class SimulationActionAdapter:
    """
    Simulation Adapter for Safe Action Execution.
    Guarantees that ALL operations remain strictly within the simulation environment.
    
    SAFETY RULE: NEVER makes live calls to Razorpay APIs, bank APIs, SMS, email, WhatsApp, or voice.
    """

    def __init__(self, simulator: PaymentGatewaySimulator | None = None):
        self.simulator = simulator or global_simulator

    def execute_simulated_action(
        self,
        transaction: Transaction,
        recovery_case: RecoveryCase,
        action_type: RecoveryActionTypeEnum,
        attempt_number: int,
        is_demo_tx: bool = False,
        is_already_recovered: bool = False,
    ) -> dict[str, Any]:
        """
        Routes the approved action to the appropriate simulation subsystem.
        """
        cust = transaction.customer
        fail = transaction.payment_failure

        # Payment retries
        if action_type in [RecoveryActionTypeEnum.RETRY_PAYMENT, RecoveryActionTypeEnum.DELAYED_RETRY]:
            sim_res = self.simulator.simulate_execution(
                transaction_amount=transaction.amount,
                payment_method=transaction.payment_method,
                failure_type=fail.normalized_failure_type if fail else "TEMPORARY_BANK_DECLINE",
                action_type=action_type.value,
                attempt_number=attempt_number,
                customer_success_rate=cust.historical_success_rate if cust else 0.5,
                is_demo_tx=is_demo_tx,
                is_already_recovered=is_already_recovered,
                transaction_id=transaction.id,
            )
            sim_res["simulated"] = True
            return sim_res

        # Communication actions (simulated only)
        elif action_type in [
            RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
            RecoveryActionTypeEnum.SEND_REMINDER,
            RecoveryActionTypeEnum.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
        ]:
            ref_id = f"sim_comm_{uuid.uuid4().hex[:12]}"
            sim_res = self.simulator.simulate_execution(
                transaction_amount=transaction.amount,
                payment_method=transaction.payment_method,
                failure_type=fail.normalized_failure_type if fail else "TEMPORARY_BANK_DECLINE",
                action_type=action_type.value,
                attempt_number=attempt_number,
                customer_success_rate=cust.historical_success_rate if cust else 0.5,
                is_demo_tx=is_demo_tx,
                is_already_recovered=is_already_recovered,
                transaction_id=transaction.id,
            )
            sim_res["simulated"] = True
            sim_res["provider_reference"] = ref_id
            return sim_res

        # Terminal control actions
        elif action_type == RecoveryActionTypeEnum.STOP_RECOVERY:
            return {
                "success": False,
                "result": OutcomeResultEnum.SKIPPED.value,
                "simulator_result": "RECOVERY_STOPPED",
                "transaction_id": transaction.id,
                "recovered_amount": 0.0,
                "currency": "INR",
                "failure_reason": "Recovery terminated by policy or administrative command",
                "provider_reference": f"sim_stop_{uuid.uuid4().hex[:8]}",
                "reason_code": "STOPPED",
                "simulated": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        elif action_type == RecoveryActionTypeEnum.ESCALATE_TO_HUMAN:
            return {
                "success": False,
                "result": OutcomeResultEnum.SKIPPED.value,
                "simulator_result": "ESCALATED_TO_HUMAN",
                "transaction_id": transaction.id,
                "recovered_amount": 0.0,
                "currency": "INR",
                "failure_reason": "Escalated for human operator review and manual handling",
                "provider_reference": f"sim_esc_{uuid.uuid4().hex[:8]}",
                "reason_code": "ESCALATED",
                "simulated": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        else:
            raise ValueError(f"Unsupported action type: {action_type}")

class ActionExecutor:
    """
    Deterministic Action Executor with Hard Security Boundary.
    
    NON-NEGOTIABLE SAFETY RULES:
    1. AI has ZERO direct execution authority.
    2. The executor strictly requires an authoritative PolicyDecision with decision == APPROVED.
    3. Stale policy decisions and race conditions are guarded by re-checking database transaction state.
    4. Idempotency is enforced using database uniqueness keys.
    5. Execution is atomic and strictly simulation-only.
    """

    def __init__(self, adapter: SimulationActionAdapter | None = None):
        self.adapter = adapter or SimulationActionAdapter()

    def execute(
        self,
        db: Session,
        recovery_case: RecoveryCase,
        policy_decision: PolicyDecision,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> ExecutionResult:
        """
        Executes an approved recovery action inside a controlled database transaction.
        """
        corr_id = correlation_id or f"corr-exec-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)

        # 1. HARD SECURITY CHECK: Require PolicyDecision instance (Reject raw AI recommendations)
        if not isinstance(policy_decision, PolicyDecision):
            raise TypeError(
                f"ActionExecutor strictly requires an authoritative PolicyDecision instance, got {type(policy_decision).__name__}. Direct AI execution is forbidden."
            )

        # 2. HARD SECURITY CHECK: Verify policy approval
        if not policy_decision.is_approved:
            raise ValueError(
                f"ActionExecutor cannot execute unapproved policy decision (decision={policy_decision.decision.value}, reasons={policy_decision.reasons})."
            )

        tx = recovery_case.transaction
        cust = tx.customer if tx else None

        # 3. SAFETY CHECK: Re-verify transaction and case existence
        if not tx:
            raise ValueError(f"Recovery case '{recovery_case.id}' has no associated transaction.")

        # 4. SAFETY CHECK: Stale Policy Decision & Terminal State Protection
        # Protect against race conditions if transaction became captured/recovered after policy evaluation
        is_already_terminal = (
            tx.status in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value]
            or recovery_case.status in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value]
        )

        action_type = policy_decision.action
        action_seq = len(recovery_case.actions) + 1
        key = idempotency_key or f"recovery:{recovery_case.id}:{action_seq}"

        # 5. IDEMPOTENCY CHECK
        existing_action = db.query(RecoveryAction).filter(RecoveryAction.idempotency_key == key).first()
        if existing_action:
            # Check for conflict: same key used for different action
            if existing_action.action_type != action_type.value:
                # Audit idempotency conflict
                conflict_audit = AuditEvent(
                    id=str(uuid.uuid4()),
                    event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                    correlation_id=corr_id,
                    entity_type="RECOVERY_ACTION",
                    entity_id=existing_action.id,
                    event_type="ACTION_IDEMPOTENCY_CONFLICT",
                    actor_type="EXECUTOR",
                    guardrail_result="REJECTED",
                    payload={
                        "case_id": recovery_case.id,
                        "idempotency_key": key,
                        "existing_action": existing_action.action_type,
                        "attempted_action": action_type.value,
                    },
                    policy_version=policy_decision.policy_version,
                    agent_version=settings.AGENT_VERSION,
                    created_at=now,
                )
                db.add(conflict_audit)
                db.commit()

                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "IDEMPOTENCY_CONFLICT",
                            "message": f"Idempotency key '{key}' was previously used for action '{existing_action.action_type}', cannot execute '{action_type.value}'.",
                            "correlation_id": corr_id,
                        }
                    },
                )

            # Audit idempotency hit
            idempotent_hit_audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                correlation_id=corr_id,
                entity_type="RECOVERY_ACTION",
                entity_id=existing_action.id,
                event_type="ACTION_IDEMPOTENCY_HIT",
                actor_type="EXECUTOR",
                guardrail_result="APPROVED",
                payload={"case_id": recovery_case.id, "idempotency_key": key, "action_type": action_type.value},
                policy_version=policy_decision.policy_version,
                agent_version=settings.AGENT_VERSION,
                created_at=now,
            )
            db.add(idempotent_hit_audit)
            db.commit()

            # Return cached execution result
            out = existing_action.outcome
            return ExecutionResult(
                action_id=existing_action.action_id,
                action_type=RecoveryActionTypeEnum(existing_action.action_type),
                status=existing_action.status,
                simulated=True,
                idempotency_key=key,
                sequence_number=existing_action.sequence_number,
                outcome_id=out.recovery_outcome_id if out else None,
                outcome_result=OutcomeResultEnum(out.result) if out else OutcomeResultEnum.FAILURE,
                simulator_result=out.simulator_result if out else None,
                recovered_amount=out.recovered_amount if out else 0.0,
                baseline_amount=out.baseline_amount if out else 0.0,
                incremental_amount=out.incremental_amount if out else 0.0,
                currency="INR",
                failure_reason=out.failure_reason if out else None,
                provider_reference=out.simulator_result if out else None,
                new_case_status=TransactionStatusEnum(recovery_case.status),
                new_transaction_status=TransactionStatusEnum(tx.status),
                audit_event_id=idempotent_hit_audit.id,
                executed_at=existing_action.executed_at or now,
            )

        # 6. ATOMIC TRANSACTION EXECUTION
        try:
            # Audit start of execution
            start_audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                correlation_id=corr_id,
                entity_type="RECOVERY_ACTION",
                entity_id=recovery_case.id,
                event_type="ACTION_EXECUTION_STARTED",
                actor_type="EXECUTOR",
                policy_version=policy_decision.policy_version,
                agent_version=settings.AGENT_VERSION,
                payload={"case_id": recovery_case.id, "action_type": action_type.value, "idempotency_key": key},
                created_at=now,
            )
            db.add(start_audit)

            # Create RecoveryAction
            rec_action = RecoveryAction(
                id=str(uuid.uuid4()),
                action_id=f"ACT-{uuid.uuid4().hex[:8].upper()}",
                recovery_case_id=recovery_case.id,
                sequence_number=action_seq,
                idempotency_key=key,
                action_type=action_type.value,
                recommendation_reason=" | ".join(policy_decision.reasons),
                confidence=recovery_case.confidence or 0.85,
                expected_recovery=recovery_case.expected_recovery or 0.0,
                policy_version=policy_decision.policy_version,
                guardrail_decision=GuardrailDecisionEnum.APPROVED.value,
                guardrail_reason=" | ".join(policy_decision.reasons),
                status="EXECUTED",
                correlation_id=corr_id,
                created_at=now,
                executed_at=now,
            )
            db.add(rec_action)
            db.flush()

            # Execute via Simulation Adapter
            is_demo_tx = (tx.external_id == "TX-DEMO-001")
            sim_out = self.adapter.execute_simulated_action(
                transaction=tx,
                recovery_case=recovery_case,
                action_type=action_type,
                attempt_number=recovery_case.retry_count + 1,
                is_demo_tx=is_demo_tx,
                is_already_recovered=is_already_terminal,
            )

            outcome_result = sim_out["result"]
            recovered_amt = sim_out["recovered_amount"]
            baseline_amt = round(recovered_amt * 0.35, 2)
            incremental_amt = round(recovered_amt - baseline_amt, 2)

            # Persist Outcome
            outcome = RecoveryOutcome(
                id=str(uuid.uuid4()),
                recovery_outcome_id=f"OUT-{uuid.uuid4().hex[:8].upper()}",
                recovery_case_id=recovery_case.id,
                recovery_action_id=rec_action.id,
                transaction_id=tx.id,
                outcome_type=OutcomeTypeEnum.AGENT_RECOVERY.value,
                result=outcome_result,
                recovered_amount=recovered_amt,
                baseline_amount=baseline_amt,
                incremental_amount=incremental_amt,
                simulator_result=sim_out["simulator_result"],
                failure_reason=sim_out.get("failure_reason"),
                metadata_payload=sim_out,
                correlation_id=corr_id,
                occurred_at=now,
            )
            db.add(outcome)

            # Update Case & Transaction State
            if action_type in [RecoveryActionTypeEnum.RETRY_PAYMENT, RecoveryActionTypeEnum.DELAYED_RETRY]:
                recovery_case.retry_count += 1
            elif action_type in [
                RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
                RecoveryActionTypeEnum.SEND_REMINDER,
                RecoveryActionTypeEnum.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
            ]:
                recovery_case.message_count += 1
                if cust:
                    notif = NotificationLog(
                        id=str(uuid.uuid4()),
                        recovery_case_id=recovery_case.id,
                        customer_id=cust.id,
                        channel="PAYMENT_LINK" if action_type == RecoveryActionTypeEnum.SEND_PAYMENT_LINK else "SMS",
                        recipient_reference=f"cust_{cust.external_id}",
                        template_id=f"tpl_{action_type.value.lower()}",
                        status="DELIVERED",
                        sent_at=now,
                    )
                    db.add(notif)

            old_status = recovery_case.status
            if outcome_result == OutcomeResultEnum.SUCCESS.value:
                recovery_case.status = TransactionStatusEnum.RECOVERED.value
                tx.status = TransactionStatusEnum.RECOVERED.value
                if cust:
                    cust.successful_payment_count += 1
                recovery_case.closed_at = now
            elif outcome_result == OutcomeResultEnum.SKIPPED.value:
                if action_type == RecoveryActionTypeEnum.STOP_RECOVERY:
                    recovery_case.status = TransactionStatusEnum.STOPPED.value
                    tx.status = TransactionStatusEnum.STOPPED.value
                elif action_type == RecoveryActionTypeEnum.ESCALATE_TO_HUMAN:
                    recovery_case.status = TransactionStatusEnum.ESCALATED.value
                    tx.status = TransactionStatusEnum.ESCALATED.value
                recovery_case.closed_at = now
            else:
                if recovery_case.retry_count >= settings.MAX_AUTOMATED_RETRIES:
                    recovery_case.status = TransactionStatusEnum.RECOVERY_EXHAUSTED.value
                    tx.status = TransactionStatusEnum.RECOVERY_EXHAUSTED.value
                    recovery_case.closed_at = now
                else:
                    recovery_case.status = TransactionStatusEnum.RECOVERY_IN_PROGRESS.value
                    tx.status = TransactionStatusEnum.RECOVERY_IN_PROGRESS.value

            recovery_case.updated_at = now
            tx.updated_at = now

            # Audit State Change
            if recovery_case.status != old_status:
                state_audit = AuditEvent(
                    id=str(uuid.uuid4()),
                    event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                    correlation_id=corr_id,
                    entity_type="RECOVERY_CASE",
                    entity_id=recovery_case.id,
                    event_type="RECOVERY_STATE_CHANGED",
                    actor_type="EXECUTOR",
                    guardrail_result="APPROVED",
                    payload={
                        "case_id": recovery_case.id,
                        "old_status": old_status,
                        "new_status": recovery_case.status,
                    },
                    policy_version=policy_decision.policy_version,
                    agent_version=settings.AGENT_VERSION,
                    created_at=now,
                )
                db.add(state_audit)

            # Audit Revenue Recording if recovered > 0
            if recovered_amt > 0:
                rev_audit = AuditEvent(
                    id=str(uuid.uuid4()),
                    event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                    correlation_id=corr_id,
                    entity_type="TRANSACTION",
                    entity_id=tx.id,
                    event_type="RECOVERY_REVENUE_RECORDED",
                    actor_type="EXECUTOR",
                    recovered_amount=recovered_amt,
                    payload={
                        "case_id": recovery_case.id,
                        "transaction_id": tx.id,
                        "recovered_amount": recovered_amt,
                        "baseline_amount": baseline_amt,
                        "incremental_amount": incremental_amt,
                        "currency": "INR",
                    },
                    policy_version=policy_decision.policy_version,
                    agent_version=settings.AGENT_VERSION,
                    created_at=now,
                )
                db.add(rev_audit)

            # Audit Execution Complete
            exec_audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                correlation_id=corr_id,
                entity_type="RECOVERY_ACTION",
                entity_id=rec_action.id,
                event_type="ACTION_EXECUTED",
                actor_type="EXECUTOR",
                guardrail_result="APPROVED",
                execution_result=outcome_result,
                recovered_amount=recovered_amt,
                payload={
                    "case_id": recovery_case.id,
                    "transaction_id": tx.id,
                    "action_type": action_type.value,
                    "outcome_result": outcome_result,
                    "recovered_amount": recovered_amt,
                    "simulator_result": sim_out["simulator_result"],
                    "new_status": recovery_case.status,
                },
                policy_version=policy_decision.policy_version,
                agent_version=settings.AGENT_VERSION,
                created_at=now,
            )
            db.add(exec_audit)

            db.commit()

            return ExecutionResult(
                action_id=rec_action.action_id,
                action_type=action_type,
                status="EXECUTED",
                simulated=True,
                idempotency_key=key,
                sequence_number=action_seq,
                outcome_id=outcome.recovery_outcome_id,
                outcome_result=OutcomeResultEnum(outcome_result),
                simulator_result=sim_out["simulator_result"],
                recovered_amount=recovered_amt,
                baseline_amount=baseline_amt,
                incremental_amount=incremental_amt,
                currency="INR",
                failure_reason=sim_out.get("failure_reason"),
                provider_reference=sim_out.get("provider_reference"),
                new_case_status=TransactionStatusEnum(recovery_case.status),
                new_transaction_status=TransactionStatusEnum(tx.status),
                audit_event_id=exec_audit.id,
                executed_at=now,
            )

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            fail_audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                correlation_id=corr_id,
                entity_type="RECOVERY_CASE",
                entity_id=recovery_case.id,
                event_type="ACTION_EXECUTION_FAILED",
                actor_type="EXECUTOR",
                payload={"case_id": recovery_case.id, "error": str(e)},
                policy_version=policy_decision.policy_version,
                agent_version=settings.AGENT_VERSION,
                created_at=now,
            )
            db.add(fail_audit)
            db.commit()
            raise

action_executor = ActionExecutor()
