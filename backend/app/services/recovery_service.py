import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.transaction import Transaction
from backend.app.models.customer import Customer
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.audit_event import AuditEvent
from backend.app.models.incident import SystemicIncident
from backend.app.models.notification import NotificationLog
from backend.app.schemas.common import (
    TransactionStatusEnum,
    RecoveryActionTypeEnum,
    GuardrailDecisionEnum,
    OutcomeTypeEnum,
    OutcomeResultEnum,
)
from backend.app.schemas.recovery import (
    AIRecommendationResponse,
    AIRecommendationDetail,
    MLRiskContext,
    RecoveryExecuteResponse,
    ActionSummary,
    PolicySummary,
    OutcomeSummary,
    ExecutionSummary,
)
from backend.app.schemas.policy import PolicyDecision, PolicyReasonCode
from backend.app.agent.ai_agent import ai_agent
from backend.app.policies.policy_engine import policy_engine
from backend.app.executor.action_executor import action_executor, ActionExecutor
from backend.app.simulator.gateway_simulator import simulator
from backend.app.config.config import settings

class RecoveryService:
    """
    Coordinates end-to-end recovery lifecycle:
    AI Recommendation -> Guardrail Validation -> Simulator Execution -> Outcome Persistence -> Audit Logging.
    """

    def get_recommendation(
        self,
        db: Session,
        case_id: str,
        correlation_id: str | None = None,
    ) -> AIRecommendationResponse:
        corr_id = correlation_id or f"corr-rec-{uuid.uuid4().hex[:8]}"
        case = (
            db.query(RecoveryCase)
            .filter((RecoveryCase.id == case_id) | (RecoveryCase.recovery_case_id == case_id))
            .first()
        )
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Recovery case '{case_id}' was not found.",
                        "correlation_id": corr_id,
                    }
                },
            )

        tx = case.transaction
        cust = tx.customer
        fail = tx.payment_failure

        # 1. Evaluate real ML risk intelligence from trained HistGradientBoostingClassifier
        from backend.app.services.ml_risk_service import ml_risk_service
        from backend.app.schemas.recovery import RootCauseContext
        ml_eval = ml_risk_service.predict_risk_for_case(db, case)

        # Update case ML fields dynamically
        case.recovery_probability = ml_eval.recovery_probability
        case.expected_recovery = ml_eval.expected_recovery
        case.priority_score = ml_eval.priority_score
        case.risk_score = ml_eval.risk_score
        case.root_cause = ml_eval.root_cause

        # Check systemic incident
        active_inc = db.query(SystemicIncident).filter(SystemicIncident.status == "ACTIVE").first()

        # Build unified context for AI recommendation agent
        ai_context = {
            "transaction_amount": tx.amount,
            "payment_method": tx.payment_method,
            "failure_type": fail.normalized_failure_type if fail else "TEMPORARY_BANK_DECLINE",
            "error_description": fail.error_description if fail else None,
            "customer_name": cust.name,
            "customer_success_rate": cust.historical_success_rate,
            "customer_success_count": cust.successful_payment_count,
            "customer_failed_count": cust.failed_payment_count,
            "retry_count": case.retry_count,
            "message_count": case.message_count,
            "recovery_probability": ml_eval.recovery_probability,
            "expected_recovery": ml_eval.expected_recovery,
            "priority_score": ml_eval.priority_score,
            "root_cause": ml_eval.root_cause,
            "recoverability_class": ml_eval.recoverability_class,
            "is_opted_out": cust.is_opted_out,
            "has_open_dispute": cust.has_open_dispute,
            "is_systemic_incident": (active_inc is not None),
        }

        detail, agent_meta = ai_agent.recommend_with_metadata(ai_context)

        # Update recommended action on case in background if needed
        case.recommended_action = detail.recommended_action.value
        case.confidence = detail.confidence
        case.requires_human_review = detail.requires_human_review

        ml_ctx = MLRiskContext(
            recovery_probability=ml_eval.recovery_probability,
            risk_score=ml_eval.risk_score,
            expected_recovery=ml_eval.expected_recovery,
            priority_score=ml_eval.priority_score,
            model_version=ml_eval.model_version,
            feature_version=ml_eval.feature_version,
            prediction_source=ml_eval.prediction_source,
            confidence=ml_eval.confidence,
        )

        root_cause_ctx = RootCauseContext(
            root_cause=ml_eval.root_cause,
            explanation=ml_eval.root_cause_explanation,
            recoverability_class=ml_eval.recoverability_class,
            confidence=ml_eval.confidence,
        )

        # 2. Persist AI recommendation audit trail event
        audit_event = AuditEvent(
            id=str(uuid.uuid4()),
            event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
            correlation_id=corr_id,
            event_type="AI_RECOMMENDATION_CREATED",
            entity_type="RECOVERY_CASE",
            entity_id=case.id,
            actor_type="AI",
            agent_version=agent_meta.agent_version,
            policy_version=settings.POLICY_VERSION,
            recommendation=detail.model_dump(mode="json"),
            payload={
                "transaction_id": tx.external_id or tx.id,
                "recommendation": detail.model_dump(mode="json"),
                "ml_context": ml_ctx.model_dump(mode="json"),
                "agent_metadata": agent_meta.model_dump(mode="json"),
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit_event)
        db.commit()



        return AIRecommendationResponse(
            case_id=case.id,
            recovery_case_id=case.id,
            transaction_id=tx.external_id or tx.id,
            recommendation=detail,
            ai_recommendation=detail,
            ml=ml_ctx,
            ml_context=ml_ctx,
            root_cause_context=root_cause_ctx,
            agent_metadata=agent_meta,
            correlation_id=corr_id,
            # Backward compatibility fields
            recommended_action=detail.recommended_action,
            root_cause=detail.root_cause,
            reason=detail.reason,
            confidence=detail.confidence,
            expected_recovery=detail.expected_recovery,
            risk_flags=detail.risk_flags,
            requires_human_review=detail.requires_human_review,
            recovery_probability=ml_eval.recovery_probability,
            risk_score=ml_eval.risk_score,
        )


    def execute_recovery(
        self,
        db: Session,
        case_id: str,
        action_type_override: RecoveryActionTypeEnum | None = None,
        override_reason: str | None = None,
        idempotency_key_header: str | None = None,
        correlation_id: str | None = None,
    ) -> RecoveryExecuteResponse:
        corr_id = correlation_id or f"corr-exec-{uuid.uuid4().hex[:10]}"
        case = (
            db.query(RecoveryCase)
            .filter((RecoveryCase.id == case_id) | (RecoveryCase.recovery_case_id == case_id))
            .first()
        )
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Recovery case '{case_id}' was not found.",
                        "correlation_id": corr_id,
                    }
                },
            )

        tx = case.transaction
        cust = tx.customer if tx else None
        now = datetime.now(timezone.utc)

        # 1. Obtain AI Recommendation or use operator override
        rec_resp = self.get_recommendation(db, case_id, correlation_id=corr_id)
        chosen_action = (
            action_type_override
            if action_type_override
            else rec_resp.recommendation.recommended_action
        )
        rec_reason = override_reason if override_reason else rec_resp.recommendation.reason

        # 2. Query Systemic Incidents
        active_inc = db.query(SystemicIncident).filter(SystemicIncident.status == "ACTIVE").first()
        incident_active = active_inc is not None
        failure_spike_rate = 0.40 if incident_active else 0.0

        # Find last action timestamp
        last_action = (
            db.query(RecoveryAction)
            .filter(RecoveryAction.recovery_case_id == case.id)
            .order_by(RecoveryAction.created_at.desc())
            .first()
        )
        last_action_time = last_action.created_at if last_action else None

        # Build sequence number and default idempotency key
        action_seq = len(case.actions) + 1
        idempotency_key = idempotency_key_header or f"recovery:{case.id}:{action_seq}"

        # 3. Idempotency Check: Existing action with identical key
        existing_action = db.query(RecoveryAction).filter(RecoveryAction.idempotency_key == idempotency_key).first()
        if existing_action:
            # Check for conflict: same key with different action parameters
            action_val = chosen_action.value if hasattr(chosen_action, "value") else str(chosen_action)
            if existing_action.action_type != action_val:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "IDEMPOTENCY_CONFLICT",
                            "message": f"Idempotency key '{idempotency_key}' was previously used for a different action '{existing_action.action_type}'.",
                            "correlation_id": corr_id,
                        }
                    },
                )

            # Return cached idempotent result
            out = existing_action.outcome
            is_appr = (existing_action.guardrail_decision == GuardrailDecisionEnum.APPROVED.value)
            return RecoveryExecuteResponse(
                case_id=case.id,
                recovery_case_id=case.id,
                action=ActionSummary(
                    action_id=existing_action.action_id,
                    action_type=RecoveryActionTypeEnum(existing_action.action_type),
                    status=existing_action.status,
                ),
                policy=PolicySummary(
                    approved=is_appr,
                    decision=GuardrailDecisionEnum.APPROVED if is_appr else GuardrailDecisionEnum.REJECTED,
                    action=RecoveryActionTypeEnum(existing_action.action_type),
                    reason_code=existing_action.guardrail_reason or ("APPROVED" if is_appr else "REJECTED"),
                    reason_codes=[],
                    reasons=[existing_action.guardrail_reason] if existing_action.guardrail_reason else [],
                    violations=[existing_action.guardrail_reason] if not is_appr and existing_action.guardrail_reason else [],
                    policy_version=existing_action.policy_version,
                ),
                execution=ExecutionSummary(
                    status=existing_action.status,
                    simulated=True,
                    idempotency_key=existing_action.idempotency_key,
                    action_id=existing_action.action_id,
                    action_type=RecoveryActionTypeEnum(existing_action.action_type),
                ) if is_appr else None,
                outcome=OutcomeSummary(
                    outcome_type=OutcomeTypeEnum(out.outcome_type) if out else OutcomeTypeEnum.AGENT_RECOVERY,
                    outcome_status=OutcomeResultEnum(out.result) if out else OutcomeResultEnum.FAILURE,
                    status=out.simulator_result if out else None,
                    recovered_amount=out.recovered_amount if out else 0.0,
                    baseline_amount=out.baseline_amount if out else 0.0,
                    incremental_amount=out.incremental_amount if out else 0.0,
                    currency="INR",
                    simulator_reference=out.simulator_result if out else None,
                ) if out else None,
                transaction_state=TransactionStatusEnum(case.status),
                correlation_id=corr_id,
                execution_id=existing_action.id,
                transaction_id=tx.id if tx else None,
                action_type=RecoveryActionTypeEnum(existing_action.action_type),
                guardrail_status=GuardrailDecisionEnum(existing_action.guardrail_decision),
                guardrail_reason=existing_action.guardrail_reason or "",
                execution_status=existing_action.status,
                outcome_result=OutcomeResultEnum(out.result) if out else None,
                recovered_amount=out.recovered_amount if out else 0.0,
                simulator_reference=out.simulator_result if out else None,
                new_case_status=TransactionStatusEnum(case.status),
                executed_at=existing_action.executed_at or now,
            )

        # 4. Audit Policy Evaluation Start
        start_eval_audit = AuditEvent(
            id=str(uuid.uuid4()),
            event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
            correlation_id=corr_id,
            entity_type="POLICY_GUARDRAIL",
            entity_id=case.id,
            event_type="POLICY_EVALUATION_STARTED",
            actor_type="POLICY_ENGINE",
            payload={
                "case_id": case.id,
                "action": chosen_action.value if hasattr(chosen_action, "value") else str(chosen_action),
                "retry_count": case.retry_count,
                "message_count": case.message_count,
            },
            policy_version=settings.POLICY_VERSION,
            agent_version=settings.AGENT_VERSION,
            created_at=now,
        )
        db.add(start_eval_audit)
        db.commit()

        # 5. Strict Deterministic Policy Evaluation
        policy_decision = policy_engine.evaluate(
            action=chosen_action,
            case_status=case.status,
            retry_count=case.retry_count,
            message_count=case.message_count,
            payment_link_count=case.message_count,
            case_created_at=case.created_at,
            last_action_time=last_action_time,
            is_opted_out=cust.is_opted_out if cust else False,
            has_open_dispute=cust.has_open_dispute if cust else False,
            is_systemic_incident_active=incident_active,
            failure_spike_rate=failure_spike_rate,
            ml_probability=case.recovery_probability,
            ai_confidence=rec_resp.recommendation.confidence,
            transaction_amount=tx.amount if tx else None,
            current_time=now,
        )

        # 6. Handle Policy Rejection
        if policy_decision.is_rejected:
            # Audit rejection
            rej_audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                correlation_id=corr_id,
                entity_type="POLICY_GUARDRAIL",
                entity_id=case.id,
                event_type="POLICY_REJECTED",
                actor_type="POLICY_ENGINE",
                guardrail_result="REJECTED",
                payload={
                    "case_id": case.id,
                    "action": policy_decision.action.value,
                    "reason_codes": [rc.value for rc in policy_decision.reason_codes],
                    "reasons": policy_decision.reasons,
                    "suggested_status": policy_decision.suggested_status,
                },
                policy_version=policy_decision.policy_version,
                agent_version=settings.AGENT_VERSION,
                created_at=now,
            )
            db.add(rej_audit)

            # Persist rejected action record
            rec_action = RecoveryAction(
                id=str(uuid.uuid4()),
                action_id=f"ACT-{uuid.uuid4().hex[:8].upper()}",
                recovery_case_id=case.id,
                sequence_number=action_seq,
                idempotency_key=idempotency_key,
                action_type=policy_decision.action.value,
                recommendation_reason=rec_reason,
                confidence=rec_resp.recommendation.confidence,
                expected_recovery=rec_resp.recommendation.expected_recovery,
                policy_version=policy_decision.policy_version,
                guardrail_decision=GuardrailDecisionEnum.REJECTED.value,
                guardrail_reason=" | ".join(policy_decision.reasons),
                status="REJECTED",
                correlation_id=corr_id,
                created_at=now,
                executed_at=None,
            )
            db.add(rec_action)

            # Update status if policy suggests transition
            if policy_decision.suggested_status:
                case.status = policy_decision.suggested_status
                if tx:
                    tx.status = policy_decision.suggested_status
            case.updated_at = now
            if tx:
                tx.updated_at = now
            db.commit()

            primary_reason_str = " | ".join(policy_decision.reasons) if policy_decision.reasons else (
                policy_decision.reason_codes[0].value if policy_decision.reason_codes else "POLICY_REJECTED"
            )

            return RecoveryExecuteResponse(
                case_id=case.id,
                recovery_case_id=case.id,
                action=ActionSummary(
                    action_id=rec_action.action_id,
                    action_type=policy_decision.action,
                    status="REJECTED",
                ),
                policy=PolicySummary(
                    approved=False,
                    decision=GuardrailDecisionEnum.REJECTED,
                    action=policy_decision.action,
                    reason_code=primary_reason_str,
                    reason_codes=[rc.value for rc in policy_decision.reason_codes],
                    reasons=policy_decision.reasons,
                    violations=policy_decision.reasons,
                    policy_version=policy_decision.policy_version,
                ),
                execution=None,
                outcome=None,
                transaction_state=TransactionStatusEnum(case.status),
                correlation_id=corr_id,
                execution_id=rec_action.id,
                transaction_id=tx.id if tx else None,
                action_type=policy_decision.action,
                guardrail_status=GuardrailDecisionEnum.REJECTED,
                guardrail_reason=" | ".join(policy_decision.reasons),
                execution_status="REJECTED",
                outcome_result=None,
                recovered_amount=0.0,
                simulator_reference=None,
                new_case_status=TransactionStatusEnum(case.status),
                audit_event_id=rej_audit.id,
                executed_at=now,
            )

        # 7. Policy Approved -> Record POLICY_APPROVED Audit & Execute via ActionExecutor
        appr_audit = AuditEvent(
            id=str(uuid.uuid4()),
            event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
            correlation_id=corr_id,
            entity_type="POLICY_GUARDRAIL",
            entity_id=case.id,
            event_type="POLICY_APPROVED",
            actor_type="POLICY_ENGINE",
            guardrail_result="APPROVED",
            payload={
                "case_id": case.id,
                "action": policy_decision.action.value,
                "reasons": policy_decision.reasons,
            },
            policy_version=policy_decision.policy_version,
            agent_version=settings.AGENT_VERSION,
            created_at=now,
        )
        db.add(appr_audit)
        db.commit()

        # Delegate execution strictly through ActionExecutor
        exec_res = action_executor.execute(
            db=db,
            recovery_case=case,
            policy_decision=policy_decision,
            idempotency_key=idempotency_key,
            correlation_id=corr_id,
        )

        approval_reason_str = " | ".join(policy_decision.reasons) if policy_decision.reasons else "APPROVED"

        return RecoveryExecuteResponse(
            case_id=case.id,
            recovery_case_id=case.id,
            action=ActionSummary(
                action_id=exec_res.action_id,
                action_type=exec_res.action_type,
                status=exec_res.status,
            ),
            policy=PolicySummary(
                approved=True,
                decision=GuardrailDecisionEnum.APPROVED,
                action=policy_decision.action,
                reason_code=approval_reason_str,
                reason_codes=[rc.value for rc in policy_decision.reason_codes],
                reasons=policy_decision.reasons,
                violations=[],
                policy_version=policy_decision.policy_version,
            ),
            execution=ExecutionSummary(
                status=exec_res.status,
                simulated=exec_res.simulated,
                idempotency_key=exec_res.idempotency_key,
                action_id=exec_res.action_id,
                action_type=exec_res.action_type,
            ),
            outcome=OutcomeSummary(
                outcome_type=OutcomeTypeEnum.AGENT_RECOVERY,
                outcome_status=exec_res.outcome_result or OutcomeResultEnum.SUCCESS,
                status=exec_res.simulator_result,
                recovered_amount=exec_res.recovered_amount,
                baseline_amount=exec_res.baseline_amount,
                incremental_amount=exec_res.incremental_amount,
                currency=exec_res.currency,
                simulator_reference=exec_res.provider_reference,
            ),
            transaction_state=exec_res.new_case_status,
            correlation_id=corr_id,
            execution_id=exec_res.action_id,
            transaction_id=tx.id if tx else None,
            action_type=exec_res.action_type,
            guardrail_status=GuardrailDecisionEnum.APPROVED,
            guardrail_reason=" | ".join(policy_decision.reasons),
            execution_status=exec_res.status,
            outcome_result=exec_res.outcome_result,
            recovered_amount=exec_res.recovered_amount,
            simulator_reference=exec_res.provider_reference,
            new_case_status=exec_res.new_case_status,
            audit_event_id=exec_res.audit_event_id,
            executed_at=exec_res.executed_at,
        )

recovery_service = RecoveryService()

