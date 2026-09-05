import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.transaction import Transaction
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.incident import SystemicIncident
from backend.app.models.audit_event import AuditEvent
from backend.app.models.batch_run import BatchRun
from backend.app.schemas.common import (
    TransactionStatusEnum,
    RecoveryActionTypeEnum,
    GuardrailDecisionEnum,
    OutcomeResultEnum,
)
from backend.app.schemas.batch import BatchRunRequest, BatchRunSummary
from backend.app.services.ml_risk_service import ml_risk_service
from backend.app.agent.ai_agent import ai_agent
from backend.app.policies.policy_engine import policy_engine
from backend.app.executor.action_executor import action_executor
from backend.app.simulator.gateway_simulator import simulator
from backend.app.config.config import settings

class BatchRecoveryService:
    """
    Deterministic Batch Recovery Engine.
    Coordinates closed-loop bulk recovery over persisted failure cases:
    Candidate Selection -> ML Risk -> AI Recommendation -> Policy Engine -> Executor -> Simulator -> Outcome Persistence -> Revenue Accounting.
    Persists durable BatchRun records to database for restart-resilient analytics.
    """

    def __init__(self):
        self.history: list[BatchRunSummary] = []
        self.batch_records: dict[str, dict] = {}

    def get_history(self, db: Session | None = None) -> list[BatchRunSummary]:
        if db:
            try:
                db_runs = db.query(BatchRun).order_by(desc(BatchRun.started_at)).all()
                if db_runs:
                    return [
                        BatchRunSummary(
                            batch_id=r.batch_id,
                            status=r.status,
                            started_at=r.started_at,
                            completed_at=r.completed_at,
                            seed=r.seed or 42,
                            dry_run=False,
                            total_candidates=r.total_candidates,
                            ml_evaluated=r.ml_evaluated,
                            ai_recommended=r.ai_recommended,
                            policy_approved=r.policy_approved,
                            policy_rejected=r.policy_rejected,
                            actions_executed=r.actions_executed,
                            successful_recoveries=r.successful_recoveries,
                            failed_recoveries=r.failed_recoveries,
                            baseline_recovered_revenue=round(r.baseline_recovered_revenue, 2),
                            agent_recovered_revenue=round(r.agent_recovered_revenue, 2),
                            incremental_recovered_revenue=round(r.incremental_recovered_revenue, 2),
                            recovery_rate=round(r.successful_recoveries / r.total_candidates, 4) if r.total_candidates > 0 else 0.0,
                            incremental_lift=round(r.incremental_recovered_revenue / r.baseline_recovered_revenue, 4) if r.baseline_recovered_revenue > 0 else 0.0,
                            policy_block_rate=round(r.policy_rejected / r.total_candidates, 4) if r.total_candidates > 0 else 0.0,
                            execution_success_rate=round(r.successful_recoveries / r.actions_executed, 4) if r.actions_executed > 0 else 0.0,
                            currency="INR",
                            case_ids=r.case_ids or [],
                            action_ids=r.action_ids or [],
                            outcome_ids=r.outcome_ids or [],
                        )
                        for r in db_runs
                    ]
            except Exception:
                pass
        return list(reversed(self.history))

    def get_batch_record(self, batch_id: str, db: Session | None = None) -> dict | None:
        if batch_id in self.batch_records:
            return self.batch_records[batch_id]

        if db:
            try:
                r = db.query(BatchRun).filter(BatchRun.batch_id == batch_id).first()
                if r:
                    summary = BatchRunSummary(
                        batch_id=r.batch_id,
                        status=r.status,
                        started_at=r.started_at,
                        completed_at=r.completed_at,
                        seed=r.seed or 42,
                        dry_run=False,
                        total_candidates=r.total_candidates,
                        ml_evaluated=r.ml_evaluated,
                        ai_recommended=r.ai_recommended,
                        policy_approved=r.policy_approved,
                        policy_rejected=r.policy_rejected,
                        actions_executed=r.actions_executed,
                        successful_recoveries=r.successful_recoveries,
                        failed_recoveries=r.failed_recoveries,
                        baseline_recovered_revenue=round(r.baseline_recovered_revenue, 2),
                        agent_recovered_revenue=round(r.agent_recovered_revenue, 2),
                        incremental_recovered_revenue=round(r.incremental_recovered_revenue, 2),
                        recovery_rate=round(r.successful_recoveries / r.total_candidates, 4) if r.total_candidates > 0 else 0.0,
                        incremental_lift=round(r.incremental_recovered_revenue / r.baseline_recovered_revenue, 4) if r.baseline_recovered_revenue > 0 else 0.0,
                        policy_block_rate=round(r.policy_rejected / r.total_candidates, 4) if r.total_candidates > 0 else 0.0,
                        execution_success_rate=round(r.successful_recoveries / r.actions_executed, 4) if r.actions_executed > 0 else 0.0,
                        currency="INR",
                        case_ids=r.case_ids or [],
                        action_ids=r.action_ids or [],
                        outcome_ids=r.outcome_ids or [],
                    )
                    record = {
                        "batch_id": r.batch_id,
                        "case_ids": r.case_ids or [],
                        "action_ids": r.action_ids or [],
                        "outcome_ids": r.outcome_ids or [],
                        "summary": summary,
                    }
                    self.batch_records[batch_id] = record
                    return record
            except Exception:
                pass
        return None

    def get_latest_batch_id(self, db: Session | None = None) -> str | None:
        if self.history:
            return self.history[-1].batch_id
        if db:
            try:
                r = db.query(BatchRun).order_by(desc(BatchRun.started_at)).first()
                if r:
                    return r.batch_id
            except Exception:
                pass
        return None

    def get_latest_batch_summary(self, db: Session | None = None) -> BatchRunSummary | None:
        if self.history:
            return self.history[-1]
        if db:
            history = self.get_history(db)
            if history:
                return history[0]
        return None

    def run_batch(self, db: Session, request: BatchRunRequest) -> BatchRunSummary:
        batch_id = f"BATCH-{uuid.uuid4().hex[:10].upper()}"
        started_at = datetime.now(timezone.utc)

        # 1. Reseed Simulator for Deterministic Reproducibility
        simulator.reseed(request.seed)

        # 2. Select Eligible Candidates (Exclude terminal states)
        terminal_statuses = [
            TransactionStatusEnum.CAPTURED.value,
            TransactionStatusEnum.RECOVERED.value,
            TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
            TransactionStatusEnum.ESCALATED.value,
            TransactionStatusEnum.STOPPED.value,
        ]

        candidates = (
            db.query(RecoveryCase)
            .filter(
                RecoveryCase.status.in_([
                    TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
                    TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
                ]),
                ~RecoveryCase.status.in_(terminal_statuses)
            )
            .order_by(desc(RecoveryCase.priority_score), desc(RecoveryCase.created_at))
            .limit(request.limit)
            .all()
        )

        batch_case_ids: list[str] = [case.id for case in candidates]
        batch_action_ids: list[str] = []
        batch_outcome_ids: list[str] = []

        total_candidates = len(candidates)
        ml_evaluated = 0
        ai_recommended = 0
        policy_approved = 0
        policy_rejected = 0
        actions_executed = 0
        successful_recoveries = 0
        failed_recoveries = 0
        escalated = 0
        stopped = 0
        skipped = 0

        baseline_recovered_revenue = 0.0
        agent_recovered_revenue = 0.0
        incremental_recovered_revenue = 0.0

        batch_run = None
        if not request.dry_run:
            batch_run = BatchRun(
                id=str(uuid.uuid4()),
                batch_id=batch_id,
                seed=request.seed,
                status="RUNNING",
                started_at=started_at,
                total_candidates=total_candidates,
                case_ids=batch_case_ids,
                action_ids=[],
                outcome_ids=[],
            )
            db.add(batch_run)
            db.commit()

        # Query active systemic incident
        active_inc = db.query(SystemicIncident).filter(SystemicIncident.status == "ACTIVE").first()
        incident_active = active_inc is not None
        failure_spike_rate = 0.40 if incident_active else 0.0

        for case in candidates:
            tx = case.transaction
            if not tx or tx.status in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value]:
                continue

            cust = tx.customer
            fail = tx.payment_failure
            corr_id = f"corr-{batch_id[:8].lower()}-{case.id[:6]}"
            now = datetime.now(timezone.utc)

            # STEP 1 & 2: ML Risk Evaluation
            ml_eval = ml_risk_service.predict_risk_for_case(db, case)
            ml_evaluated += 1
            case.recovery_probability = ml_eval.recovery_probability
            case.expected_recovery = ml_eval.expected_recovery
            case.priority_score = ml_eval.priority_score
            case.risk_score = ml_eval.risk_score
            case.root_cause = ml_eval.root_cause

            # STEP 3 & 4: AI Recommendation
            ai_context = {
                "transaction_amount": tx.amount,
                "payment_method": tx.payment_method,
                "failure_type": fail.normalized_failure_type if fail else "TEMPORARY_BANK_DECLINE",
                "error_description": fail.error_description if fail else None,
                "customer_name": cust.name if cust else "Unknown",
                "customer_success_rate": cust.historical_success_rate if cust else 0.5,
                "customer_success_count": cust.successful_payment_count if cust else 0,
                "customer_failed_count": cust.failed_payment_count if cust else 0,
                "retry_count": case.retry_count,
                "message_count": case.message_count,
                "recovery_probability": ml_eval.recovery_probability,
                "expected_recovery": ml_eval.expected_recovery,
                "priority_score": ml_eval.priority_score,
                "root_cause": ml_eval.root_cause,
                "recoverability_class": ml_eval.recoverability_class,
                "is_opted_out": cust.is_opted_out if cust else False,
                "has_open_dispute": cust.has_open_dispute if cust else False,
                "is_systemic_incident": incident_active,
            }

            detail, agent_meta = ai_agent.recommend_with_metadata(ai_context)
            ai_recommended += 1
            case.recommended_action = detail.recommended_action.value
            case.confidence = detail.confidence
            case.requires_human_review = detail.requires_human_review

            # Last action timestamp
            last_act = (
                db.query(RecoveryAction)
                .filter(RecoveryAction.recovery_case_id == case.id)
                .order_by(RecoveryAction.created_at.desc())
                .first()
            )
            last_action_time = last_act.created_at if last_act else None

            # STEP 5: Policy Engine Evaluation
            policy_decision = policy_engine.evaluate(
                action=detail.recommended_action,
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
                ai_confidence=detail.confidence,
                transaction_amount=tx.amount,
                current_time=now,
            )

            # STEP 6: Policy Rejection Handling
            if policy_decision.is_rejected:
                policy_rejected += 1
                if not request.dry_run:
                    action_seq = len(case.actions) + 1
                    idemp_key = f"recovery:{case.id}:{action_seq}"
                    
                    rej_action = RecoveryAction(
                        id=str(uuid.uuid4()),
                        action_id=f"ACT-{uuid.uuid4().hex[:8].upper()}",
                        recovery_case_id=case.id,
                        sequence_number=action_seq,
                        idempotency_key=idemp_key,
                        action_type=policy_decision.action.value,
                        recommendation_reason=detail.reason,
                        confidence=detail.confidence,
                        expected_recovery=detail.expected_recovery,
                        policy_version=policy_decision.policy_version,
                        guardrail_decision=GuardrailDecisionEnum.REJECTED.value,
                        guardrail_reason=" | ".join(policy_decision.reasons),
                        status="REJECTED",
                        correlation_id=corr_id,
                        created_at=now,
                        executed_at=None,
                    )
                    db.add(rej_action)
                    batch_action_ids.append(rej_action.id)

                    if policy_decision.suggested_status:
                        case.status = policy_decision.suggested_status
                        tx.status = policy_decision.suggested_status
                        if policy_decision.suggested_status == TransactionStatusEnum.STOPPED.value:
                            stopped += 1
                        elif policy_decision.suggested_status == TransactionStatusEnum.ESCALATED.value:
                            escalated += 1

                    db.commit()
                continue

            # STEP 7: Policy Approved -> Execute via Action Executor
            policy_approved += 1

            if not request.dry_run:
                action_seq = len(case.actions) + 1
                idemp_key = f"recovery:{case.id}:{action_seq}"

                try:
                    exec_res = action_executor.execute(
                        db=db,
                        recovery_case=case,
                        policy_decision=policy_decision,
                        idempotency_key=idemp_key,
                        correlation_id=corr_id,
                    )
                    actions_executed += 1
                    batch_action_ids.append(exec_res.action_id)
                    if exec_res.outcome_id:
                        batch_outcome_ids.append(exec_res.outcome_id)

                    if exec_res.outcome_result == OutcomeResultEnum.SUCCESS:
                        successful_recoveries += 1
                        agent_recovered_revenue += exec_res.recovered_amount
                        baseline_recovered_revenue += exec_res.baseline_amount
                        incremental_recovered_revenue += exec_res.incremental_amount
                    elif exec_res.outcome_result == OutcomeResultEnum.FAILURE:
                        failed_recoveries += 1
                    elif exec_res.outcome_result == OutcomeResultEnum.SKIPPED:
                        skipped += 1
                        if exec_res.action_type == RecoveryActionTypeEnum.ESCALATE_TO_HUMAN:
                            escalated += 1
                        elif exec_res.action_type == RecoveryActionTypeEnum.STOP_RECOVERY:
                            stopped += 1

                except Exception as e:
                    # In case of idempotency conflict or execution error, continue gracefully
                    failed_recoveries += 1

        completed_at = datetime.now(timezone.utc)

        # Derived metrics with zero-denominator safety
        rec_rate = round(successful_recoveries / total_candidates, 4) if total_candidates > 0 else 0.0
        inc_lift = round(incremental_recovered_revenue / baseline_recovered_revenue, 4) if baseline_recovered_revenue > 0 else 0.0
        block_rate = round(policy_rejected / total_candidates, 4) if total_candidates > 0 else 0.0
        exec_rate = round(successful_recoveries / actions_executed, 4) if actions_executed > 0 else 0.0

        summary = BatchRunSummary(
            batch_id=batch_id,
            status="COMPLETED",
            started_at=started_at,
            completed_at=completed_at,
            seed=request.seed,
            dry_run=request.dry_run,
            total_candidates=total_candidates,
            ml_evaluated=ml_evaluated,
            ai_recommended=ai_recommended,
            policy_approved=policy_approved,
            policy_rejected=policy_rejected,
            actions_executed=actions_executed,
            successful_recoveries=successful_recoveries,
            failed_recoveries=failed_recoveries,
            escalated=escalated,
            stopped=stopped,
            skipped=skipped,
            baseline_recovered_revenue=round(baseline_recovered_revenue, 2),
            agent_recovered_revenue=round(agent_recovered_revenue, 2),
            incremental_recovered_revenue=round(incremental_recovered_revenue, 2),
            recovery_rate=rec_rate,
            incremental_lift=inc_lift,
            policy_block_rate=block_rate,
            execution_success_rate=exec_rate,
            currency="INR",
            case_ids=batch_case_ids,
            action_ids=batch_action_ids,
            outcome_ids=batch_outcome_ids,
        )

        if not request.dry_run and batch_run is not None:
            batch_run.status = "COMPLETED"
            batch_run.completed_at = completed_at
            batch_run.ml_evaluated = ml_evaluated
            batch_run.ai_recommended = ai_recommended
            batch_run.policy_approved = policy_approved
            batch_run.policy_rejected = policy_rejected
            batch_run.actions_executed = actions_executed
            batch_run.successful_recoveries = successful_recoveries
            batch_run.failed_recoveries = failed_recoveries
            batch_run.agent_recovered_revenue = round(agent_recovered_revenue, 2)
            batch_run.baseline_recovered_revenue = round(baseline_recovered_revenue, 2)
            batch_run.incremental_recovered_revenue = round(incremental_recovered_revenue, 2)
            batch_run.case_ids = batch_case_ids
            batch_run.action_ids = batch_action_ids
            batch_run.outcome_ids = batch_outcome_ids
            db.commit()

        self.history.append(summary)
        self.batch_records[batch_id] = {
            "batch_id": batch_id,
            "case_ids": batch_case_ids,
            "action_ids": batch_action_ids,
            "outcome_ids": batch_outcome_ids,
            "summary": summary,
        }
        return summary

batch_recovery_service = BatchRecoveryService()
