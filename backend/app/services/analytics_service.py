from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, case, or_
from backend.app.models.transaction import Transaction
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.incident import SystemicIncident
from backend.app.schemas.dashboard import DashboardSummaryResponse, DashboardMetrics
from backend.app.schemas.analytics import (
    AnalyticsResponse,
    RecoveryByDimension,
    PredictedVsActual,
    PredictedVsActualSummary,
    IncrementalitySummary,
    RecoveryFunnelResponse,
    RecoveryFunnelStage,
    SystemicIncidentAnalytics,
)
from backend.app.schemas.common import (
    TransactionStatusEnum,
    OutcomeResultEnum,
    FailureTypeEnum,
    RecoveryActionTypeEnum,
    PaymentMethodEnum,
)
from backend.app.services.batch_recovery_service import batch_recovery_service

class AnalyticsService:
    """
    Analytics and Closed-Loop Revenue Accounting Engine.
    Supports explicitly scoped analytics:
    1. CURRENT_BATCH (default when batch exists) - isolated strictly to the selected batch's candidates, actions, and outcomes.
    2. CUMULATIVE - aggregated across all historical database records.
    """

    def _resolve_scope(self, db: Session | None = None, batch_id: str | None = None, scope: str | None = None) -> tuple[str, str | None, dict | None]:
        if scope and scope.upper() == "CUMULATIVE":
            return "CUMULATIVE", None, None

        target_batch_id = batch_id or batch_recovery_service.get_latest_batch_id(db)
        if target_batch_id:
            batch_data = batch_recovery_service.get_batch_record(target_batch_id, db)
            if batch_data:
                return "CURRENT_BATCH", target_batch_id, batch_data

        return "CUMULATIVE", None, None

    def get_dashboard_summary(self, db: Session, batch_id: str | None = None, scope: str | None = None) -> DashboardSummaryResponse:
        active_scope, target_batch_id, batch_data = self._resolve_scope(db, batch_id, scope)

        # 1. Cumulative DB Totals (Always calculated for side-by-side presentation)
        cum_tpv = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).scalar() or 0.0
        cum_failed_val = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
            .filter(Transaction.status.in_([
                TransactionStatusEnum.FAILED.value,
                TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
                TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
                TransactionStatusEnum.RECOVERED.value,
                TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
                TransactionStatusEnum.ESCALATED.value,
                TransactionStatusEnum.STOPPED.value,
            ]))
            .scalar() or 0.0
        )
        cum_recovered_rev = (
            db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0))
            .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
            .scalar() or 0.0
        )
        cum_baseline_rev = (
            db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0))
            .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
            .scalar() or 0.0
        )
        cum_incremental_rev = (
            db.query(func.coalesce(func.sum(RecoveryOutcome.incremental_amount), 0.0))
            .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
            .scalar() or 0.0
        )
        cum_total_cases = db.query(RecoveryCase).count()
        cum_successful_recoveries = (
            db.query(RecoveryCase)
            .filter(RecoveryCase.status == TransactionStatusEnum.RECOVERED.value)
            .count()
        )
        systemic_active = (
            db.query(SystemicIncident)
            .filter(SystemicIncident.status == "ACTIVE")
            .count()
        )

        # 2. Scope-Specific Metrics
        if active_scope == "CURRENT_BATCH" and batch_data:
            summary = batch_data["summary"]
            case_ids = batch_data["case_ids"]

            tpv = (
                db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
                .join(RecoveryCase, RecoveryCase.transaction_id == Transaction.id)
                .filter(RecoveryCase.id.in_(case_ids))
                .scalar() or 0.0
            ) if case_ids else 0.0

            failed_val = tpv
            at_risk = (
                db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0))
                .filter(RecoveryCase.id.in_(case_ids))
                .scalar() or 0.0
            ) if case_ids else 0.0
            eligible_val = at_risk
            intervention_val = at_risk if summary.actions_executed > 0 else 0.0

            recovered_rev = summary.agent_recovered_revenue
            baseline_rev = summary.baseline_recovered_revenue
            incremental_rev = summary.incremental_recovered_revenue

            total_cases = summary.total_candidates
            active_cases = summary.total_candidates - summary.successful_recoveries - summary.stopped - summary.escalated
            successful_recoveries = summary.successful_recoveries
            total_attempts = summary.actions_executed + summary.policy_rejected
            guardrail_rejections = summary.policy_rejected
            recovery_rate = summary.recovery_rate
            guardrail_compliance = round((total_attempts - guardrail_rejections) / total_attempts, 4) if total_attempts > 0 else 1.0

            avg_prob = (
                db.query(func.coalesce(func.avg(RecoveryCase.recovery_probability), 0.0))
                .filter(RecoveryCase.id.in_(case_ids))
                .scalar() or 0.0
            ) if case_ids else 0.0
        else:
            active_scope = "CUMULATIVE"
            target_batch_id = None
            tpv = cum_tpv
            failed_val = cum_failed_val
            at_risk = (
                db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0))
                .filter(RecoveryCase.status.in_([
                    TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
                    TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
                ]))
                .scalar() or 0.0
            )
            eligible_val = (
                db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0))
                .filter(RecoveryCase.status == TransactionStatusEnum.RECOVERY_ELIGIBLE.value)
                .scalar() or 0.0
            )
            intervention_val = (
                db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0))
                .join(RecoveryAction, RecoveryAction.recovery_case_id == RecoveryCase.id)
                .distinct()
                .scalar() or 0.0
            )
            recovered_rev = cum_recovered_rev
            baseline_rev = cum_baseline_rev
            incremental_rev = cum_incremental_rev
            total_cases = cum_total_cases
            active_cases = (
                db.query(RecoveryCase)
                .filter(RecoveryCase.status.in_([
                    TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
                    TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
                ]))
                .count()
            )
            successful_recoveries = cum_successful_recoveries
            total_attempts = db.query(RecoveryAction).count()
            guardrail_rejections = (
                db.query(RecoveryAction)
                .filter(RecoveryAction.guardrail_decision == "REJECTED")
                .count()
            )
            recovery_rate = round(successful_recoveries / total_cases, 4) if total_cases > 0 else 0.0
            guardrail_compliance = round((total_attempts - guardrail_rejections) / total_attempts, 4) if total_attempts > 0 else 1.0
            avg_prob = db.query(func.coalesce(func.avg(RecoveryCase.recovery_probability), 0.0)).scalar() or 0.0

        metrics = DashboardMetrics(
            total_payment_volume=round(tpv, 2),
            failed_payment_value=round(failed_val, 2),
            revenue_at_risk=round(at_risk, 2),
            recovery_eligible=round(eligible_val, 2),
            intervention_value=round(intervention_val, 2),
            recovered_revenue=round(recovered_rev, 2),
            baseline_recovered_revenue=round(baseline_rev, 2),
            incremental_recovered_revenue=round(incremental_rev, 2),
            recovery_rate=min(1.0, max(0.0, recovery_rate)),
            active_cases=max(0, active_cases),
            successful_recoveries=successful_recoveries,
            total_attempts=total_attempts,
            guardrail_compliance_rate=min(1.0, max(0.0, guardrail_compliance)),
            average_recovery_probability=round(min(1.0, max(0.0, avg_prob)), 4),
            guardrail_rejections_count=guardrail_rejections,
            systemic_incidents_active=systemic_active,
        )

        return DashboardSummaryResponse(
            currency="INR",
            scope=active_scope,
            batch_id=target_batch_id,
            metrics=metrics,
            total_payment_volume=round(tpv, 2),
            failed_payment_value=round(failed_val, 2),
            revenue_at_risk=round(at_risk, 2),
            recovery_eligible_value=round(eligible_val, 2),
            intervention_value=round(intervention_val, 2),
            recovered_revenue=round(recovered_rev, 2),
            baseline_recovered_revenue=round(baseline_rev, 2),
            incremental_recovered_revenue=round(incremental_rev, 2),
            recovery_rate=min(1.0, max(0.0, recovery_rate)),
            active_cases_count=max(0, active_cases),
            total_cases_count=total_cases,
            successful_recoveries_count=successful_recoveries,
            guardrail_rejections_count=guardrail_rejections,
            systemic_incidents_active=systemic_active,
            cumulative_total_payment_volume=round(cum_tpv, 2),
            cumulative_failed_payment_value=round(cum_failed_val, 2),
            cumulative_recovered_revenue=round(cum_recovered_rev, 2),
            cumulative_baseline_recovered_revenue=round(cum_baseline_rev, 2),
            cumulative_incremental_recovered_revenue=round(cum_incremental_rev, 2),
            cumulative_successful_recoveries_count=cum_successful_recoveries,
            cumulative_total_cases_count=cum_total_cases,
        )

    def get_analytics_by_failure_type(self, db: Session, batch_id: str | None = None, scope: str | None = None) -> list[RecoveryByDimension]:
        active_scope, target_batch_id, batch_data = self._resolve_scope(db, batch_id, scope)
        failure_types = [f.value for f in FailureTypeEnum]
        results = []

        for ft in failure_types:
            if active_scope == "CURRENT_BATCH" and batch_data:
                case_ids = batch_data["case_ids"]
                action_ids = batch_data["action_ids"]
                outcome_ids = batch_data["outcome_ids"]

                if not case_ids:
                    results.append(RecoveryByDimension(
                        category=ft, scope=active_scope, batch_id=target_batch_id
                    ))
                    continue

                candidates_q = (
                    db.query(RecoveryCase)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                    .filter(
                        RecoveryCase.id.in_(case_ids),
                        PaymentFailure.normalized_failure_type == ft,
                    )
                )
                candidates_count = candidates_q.count()
                at_risk = db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0)).filter(
                    RecoveryCase.id.in_([c.id for c in candidates_q.all()])
                ).scalar() or 0.0

                actions_q = (
                    db.query(RecoveryAction)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                    .filter(
                        or_(
                            RecoveryAction.id.in_(action_ids),
                            RecoveryAction.action_id.in_(action_ids),
                            RecoveryAction.recovery_case_id.in_(case_ids),
                        ),
                        PaymentFailure.normalized_failure_type == ft,
                    )
                )
                rec_count = actions_q.count()
                app_count = actions_q.filter(RecoveryAction.guardrail_decision == "APPROVED").count()
                rej_count = actions_q.filter(RecoveryAction.guardrail_decision == "REJECTED").count()
                exec_count = actions_q.filter(RecoveryAction.status == "EXECUTED").count()

                outcomes_q = (
                    db.query(RecoveryOutcome)
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                    .filter(
                        or_(
                            RecoveryOutcome.id.in_(outcome_ids),
                            RecoveryOutcome.recovery_outcome_id.in_(outcome_ids),
                            RecoveryOutcome.recovery_case_id.in_(case_ids),
                        ),
                        PaymentFailure.normalized_failure_type == ft,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                )
                succ_count = outcomes_q.count()
                rec_rev = db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0)).filter(
                    RecoveryOutcome.id.in_([o.id for o in outcomes_q.all()])
                ).scalar() or 0.0
                base_rev = db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0)).filter(
                    RecoveryOutcome.id.in_([o.id for o in outcomes_q.all()])
                ).scalar() or 0.0

            else:
                candidates_q = (
                    db.query(RecoveryCase)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                    .filter(PaymentFailure.normalized_failure_type == ft)
                )
                candidates_count = candidates_q.count()
                at_risk = db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0)).join(
                    Transaction, Transaction.id == RecoveryCase.transaction_id
                ).join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id).filter(
                    PaymentFailure.normalized_failure_type == ft
                ).scalar() or 0.0

                actions_q = (
                    db.query(RecoveryAction)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                    .filter(PaymentFailure.normalized_failure_type == ft)
                )
                rec_count = actions_q.count()
                app_count = actions_q.filter(RecoveryAction.guardrail_decision == "APPROVED").count()
                rej_count = actions_q.filter(RecoveryAction.guardrail_decision == "REJECTED").count()
                exec_count = actions_q.filter(RecoveryAction.status == "EXECUTED").count()

                outcomes_q = (
                    db.query(RecoveryOutcome)
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                    .filter(
                        PaymentFailure.normalized_failure_type == ft,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                )
                succ_count = outcomes_q.count()
                rec_rev = (
                    db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0))
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                    .filter(
                        PaymentFailure.normalized_failure_type == ft,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                    .scalar() or 0.0
                )
                base_rev = (
                    db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0))
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                    .filter(
                        PaymentFailure.normalized_failure_type == ft,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                    .scalar() or 0.0
                )

            inc_rev = max(0.0, rec_rev - base_rev)
            rec_rate = round(succ_count / candidates_count, 4) if candidates_count > 0 else 0.0
            succ_rate = round(succ_count / exec_count, 4) if exec_count > 0 else 0.0

            results.append(RecoveryByDimension(
                category=ft,
                candidates_count=candidates_count,
                attempted_count=exec_count,
                successful_count=succ_count,
                recovery_rate=min(1.0, max(0.0, rec_rate)),
                recovered_amount=round(rec_rev, 2),
                at_risk_value=round(at_risk, 2),
                eligible_count=candidates_count,
                executed_count=exec_count,
                failed_count=max(0, exec_count - succ_count),
                baseline_recovered=round(base_rev, 2),
                agent_recovered=round(rec_rev, 2),
                incremental_recovered=round(inc_rev, 2),
                success_rate=min(1.0, max(0.0, succ_rate)),
                recommended_count=rec_count,
                approved_count=app_count,
                rejected_count=rej_count,
                scope=active_scope,
                batch_id=target_batch_id,
            ))

        return results

    def get_analytics_by_payment_method(self, db: Session, batch_id: str | None = None, scope: str | None = None) -> list[RecoveryByDimension]:
        active_scope, target_batch_id, batch_data = self._resolve_scope(db, batch_id, scope)
        payment_methods = ["CARD", "UPI", "NETBANKING", "WALLET"]
        results = []

        for pm in payment_methods:
            if active_scope == "CURRENT_BATCH" and batch_data:
                case_ids = batch_data["case_ids"]
                action_ids = batch_data["action_ids"]
                outcome_ids = batch_data["outcome_ids"]

                if not case_ids:
                    results.append(RecoveryByDimension(
                        category=pm, scope=active_scope, batch_id=target_batch_id
                    ))
                    continue

                candidates_q = (
                    db.query(RecoveryCase)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .filter(
                        RecoveryCase.id.in_(case_ids),
                        Transaction.payment_method == pm,
                    )
                )
                candidates_count = candidates_q.count()
                at_risk = db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0)).filter(
                    RecoveryCase.id.in_([c.id for c in candidates_q.all()])
                ).scalar() or 0.0

                actions_q = (
                    db.query(RecoveryAction)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .filter(
                        or_(
                            RecoveryAction.id.in_(action_ids),
                            RecoveryAction.action_id.in_(action_ids),
                            RecoveryAction.recovery_case_id.in_(case_ids),
                        ),
                        Transaction.payment_method == pm,
                    )
                )
                exec_count = actions_q.filter(RecoveryAction.status == "EXECUTED").count()

                outcomes_q = (
                    db.query(RecoveryOutcome)
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .filter(
                        or_(
                            RecoveryOutcome.id.in_(outcome_ids),
                            RecoveryOutcome.recovery_outcome_id.in_(outcome_ids),
                            RecoveryOutcome.recovery_case_id.in_(case_ids),
                        ),
                        Transaction.payment_method == pm,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                )
                succ_count = outcomes_q.count()
                rec_rev = db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0)).filter(
                    RecoveryOutcome.id.in_([o.id for o in outcomes_q.all()])
                ).scalar() or 0.0
                base_rev = db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0)).filter(
                    RecoveryOutcome.id.in_([o.id for o in outcomes_q.all()])
                ).scalar() or 0.0

            else:
                candidates_q = (
                    db.query(RecoveryCase)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .filter(Transaction.payment_method == pm)
                )
                candidates_count = candidates_q.count()
                at_risk = db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0)).join(
                    Transaction, Transaction.id == RecoveryCase.transaction_id
                ).filter(Transaction.payment_method == pm).scalar() or 0.0

                actions_q = (
                    db.query(RecoveryAction)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .filter(Transaction.payment_method == pm)
                )
                exec_count = actions_q.filter(RecoveryAction.status == "EXECUTED").count()

                outcomes_q = (
                    db.query(RecoveryOutcome)
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .filter(
                        Transaction.payment_method == pm,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                )
                succ_count = outcomes_q.count()
                rec_rev = (
                    db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0))
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .filter(
                        Transaction.payment_method == pm,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                    .scalar() or 0.0
                )
                base_rev = (
                    db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0))
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .join(RecoveryCase, RecoveryCase.id == RecoveryAction.recovery_case_id)
                    .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
                    .filter(
                        Transaction.payment_method == pm,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                    .scalar() or 0.0
                )

            inc_rev = max(0.0, rec_rev - base_rev)
            rec_rate = round(succ_count / candidates_count, 4) if candidates_count > 0 else 0.0

            results.append(RecoveryByDimension(
                category=pm,
                candidates_count=candidates_count,
                attempted_count=exec_count,
                successful_count=succ_count,
                recovery_rate=min(1.0, max(0.0, rec_rate)),
                recovered_amount=round(rec_rev, 2),
                at_risk_value=round(at_risk, 2),
                eligible_count=candidates_count,
                executed_count=exec_count,
                failed_count=max(0, exec_count - succ_count),
                baseline_recovered=round(base_rev, 2),
                agent_recovered=round(rec_rev, 2),
                incremental_recovered=round(inc_rev, 2),
                success_rate=min(1.0, max(0.0, round(succ_count / exec_count, 4))) if exec_count > 0 else 0.0,
                recommended_count=exec_count,
                approved_count=exec_count,
                rejected_count=0,
                scope=active_scope,
                batch_id=target_batch_id,
            ))

        return results

    def get_analytics_by_action(self, db: Session, batch_id: str | None = None, scope: str | None = None) -> list[RecoveryByDimension]:
        active_scope, target_batch_id, batch_data = self._resolve_scope(db, batch_id, scope)
        actions = [a.value for a in RecoveryActionTypeEnum]
        results = []

        for act in actions:
            if active_scope == "CURRENT_BATCH" and batch_data:
                action_ids = batch_data["action_ids"]
                outcome_ids = batch_data["outcome_ids"]

                if not action_ids:
                    results.append(RecoveryByDimension(
                        category=act, scope=active_scope, batch_id=target_batch_id
                    ))
                    continue

                act_q = db.query(RecoveryAction).filter(
                    or_(
                        RecoveryAction.id.in_(action_ids),
                        RecoveryAction.action_id.in_(action_ids),
                    ),
                    RecoveryAction.action_type == act,
                )
                rec_count = act_q.count()
                app_count = act_q.filter(RecoveryAction.guardrail_decision == "APPROVED").count()
                rej_count = act_q.filter(RecoveryAction.guardrail_decision == "REJECTED").count()
                exec_count = act_q.filter(RecoveryAction.status == "EXECUTED").count()

                out_q = (
                    db.query(RecoveryOutcome)
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .filter(
                        or_(
                            RecoveryOutcome.id.in_(outcome_ids),
                            RecoveryOutcome.recovery_outcome_id.in_(outcome_ids),
                        ),
                        RecoveryAction.action_type == act,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                )
                succ_count = out_q.count()
                rec_rev = db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0)).filter(
                    RecoveryOutcome.id.in_([o.id for o in out_q.all()])
                ).scalar() or 0.0
                base_rev = db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0)).filter(
                    RecoveryOutcome.id.in_([o.id for o in out_q.all()])
                ).scalar() or 0.0

            else:
                act_q = db.query(RecoveryAction).filter(RecoveryAction.action_type == act)
                rec_count = act_q.count()
                app_count = act_q.filter(RecoveryAction.guardrail_decision == "APPROVED").count()
                rej_count = act_q.filter(RecoveryAction.guardrail_decision == "REJECTED").count()
                exec_count = act_q.filter(RecoveryAction.status == "EXECUTED").count()

                out_q = (
                    db.query(RecoveryOutcome)
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .filter(
                        RecoveryAction.action_type == act,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                )
                succ_count = out_q.count()
                rec_rev = (
                    db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0))
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .filter(
                        RecoveryAction.action_type == act,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                    .scalar() or 0.0
                )
                base_rev = (
                    db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0))
                    .join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)
                    .filter(
                        RecoveryAction.action_type == act,
                        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                    )
                    .scalar() or 0.0
                )

            inc_rev = max(0.0, rec_rev - base_rev)
            succ_rate = round(succ_count / exec_count, 4) if exec_count > 0 else 0.0

            results.append(RecoveryByDimension(
                category=act,
                candidates_count=rec_count,
                attempted_count=exec_count,
                successful_count=succ_count,
                recovery_rate=min(1.0, max(0.0, succ_rate)),
                recovered_amount=round(rec_rev, 2),
                at_risk_value=0.0,
                eligible_count=rec_count,
                executed_count=exec_count,
                failed_count=max(0, exec_count - succ_count),
                baseline_recovered=round(base_rev, 2),
                agent_recovered=round(rec_rev, 2),
                incremental_recovered=round(inc_rev, 2),
                success_rate=min(1.0, max(0.0, succ_rate)),
                recommended_count=rec_count,
                approved_count=app_count,
                rejected_count=rej_count,
                scope=active_scope,
                batch_id=target_batch_id,
            ))

        return results

    def get_recovery_funnel(self, db: Session, batch_id: str | None = None, scope: str | None = None) -> RecoveryFunnelResponse:
        active_scope, target_batch_id, batch_data = self._resolve_scope(db, batch_id, scope)

        if active_scope == "CURRENT_BATCH" and batch_data:
            summary = batch_data["summary"]
            case_ids = batch_data["case_ids"]

            failed_count = summary.total_candidates
            failed_value = (
                db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
                .join(RecoveryCase, RecoveryCase.transaction_id == Transaction.id)
                .filter(RecoveryCase.id.in_(case_ids))
                .scalar() or 0.0
            ) if case_ids else 0.0

            eligible_count = summary.total_candidates
            eligible_val = failed_value

            ml_high_risk = (
                db.query(RecoveryCase)
                .filter(
                    RecoveryCase.id.in_(case_ids),
                    RecoveryCase.recovery_probability >= 0.50,
                )
                .count()
            ) if case_ids else 0

            ai_recommended = summary.ai_recommended
            policy_approved = summary.policy_approved
            action_executed = summary.actions_executed
            successful_rec = summary.successful_recoveries

            agent_rec_rev = summary.agent_recovered_revenue
            baseline_rec_rev = summary.baseline_recovered_revenue
            inc_rec_rev = summary.incremental_recovered_revenue
            conv_rate = summary.recovery_rate

        else:
            active_scope = "CUMULATIVE"
            target_batch_id = None
            failed_count = (
                db.query(Transaction)
                .filter(Transaction.status.in_([
                    TransactionStatusEnum.FAILED.value,
                    TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
                    TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
                    TransactionStatusEnum.RECOVERED.value,
                    TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
                    TransactionStatusEnum.ESCALATED.value,
                    TransactionStatusEnum.STOPPED.value,
                ]))
                .count()
            )
            failed_value = (
                db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
                .filter(Transaction.status.in_([
                    TransactionStatusEnum.FAILED.value,
                    TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
                    TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
                    TransactionStatusEnum.RECOVERED.value,
                    TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
                    TransactionStatusEnum.ESCALATED.value,
                    TransactionStatusEnum.STOPPED.value,
                ]))
                .scalar() or 0.0
            )

            eligible_count = db.query(RecoveryCase).count()
            eligible_val = db.query(func.coalesce(func.sum(RecoveryCase.revenue_at_risk), 0.0)).scalar() or 0.0

            ml_high_risk = db.query(RecoveryCase).filter(RecoveryCase.recovery_probability >= 0.50).count()
            ai_recommended = db.query(RecoveryAction).count()
            policy_approved = db.query(RecoveryAction).filter(RecoveryAction.guardrail_decision == "APPROVED").count()
            action_executed = db.query(RecoveryAction).filter(RecoveryAction.status == "EXECUTED").count()

            successful_rec = (
                db.query(RecoveryOutcome)
                .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
                .count()
            )

            agent_rec_rev = (
                db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0))
                .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
                .scalar() or 0.0
            )
            baseline_rec_rev = (
                db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0))
                .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
                .scalar() or 0.0
            )
            inc_rec_rev = (
                db.query(func.coalesce(func.sum(RecoveryOutcome.incremental_amount), 0.0))
                .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
                .scalar() or 0.0
            )
            conv_rate = round(successful_rec / eligible_count, 4) if eligible_count > 0 else 0.0

        stages = [
            RecoveryFunnelStage(stage_name="Failed Payments", count=failed_count, value=round(failed_value, 2), conversion_rate=1.0),
            RecoveryFunnelStage(stage_name="Recovery Eligible", count=eligible_count, value=round(eligible_val, 2), conversion_rate=min(1.0, max(0.0, round(eligible_count / failed_count, 3))) if failed_count > 0 else 0.0),
            RecoveryFunnelStage(stage_name="ML High Recovery Likelihood", count=ml_high_risk, conversion_rate=min(1.0, max(0.0, round(ml_high_risk / eligible_count, 3))) if eligible_count > 0 else 0.0),
            RecoveryFunnelStage(stage_name="AI Recommended", count=ai_recommended, conversion_rate=min(1.0, max(0.0, round(ai_recommended / eligible_count, 3))) if eligible_count > 0 else 0.0),
            RecoveryFunnelStage(stage_name="Policy Approved", count=policy_approved, conversion_rate=min(1.0, max(0.0, round(policy_approved / ai_recommended, 3))) if ai_recommended > 0 else 0.0),
            RecoveryFunnelStage(stage_name="Action Executed", count=action_executed, conversion_rate=min(1.0, max(0.0, round(action_executed / policy_approved, 3))) if policy_approved > 0 else 0.0),
            RecoveryFunnelStage(stage_name="Actual Recovery", count=successful_rec, value=round(agent_rec_rev, 2), conversion_rate=min(1.0, max(0.0, round(successful_rec / action_executed, 3))) if action_executed > 0 else 0.0),
            RecoveryFunnelStage(stage_name="Incremental Lift", count=successful_rec, value=round(inc_rec_rev, 2), conversion_rate=min(1.0, max(0.0, round(inc_rec_rev / agent_rec_rev, 3))) if agent_rec_rev > 0 else 0.0),
        ]

        return RecoveryFunnelResponse(
            scope=active_scope,
            batch_id=target_batch_id,
            failed_payments_count=failed_count,
            failed_payments_value=round(failed_value, 2),
            recovery_eligible_count=eligible_count,
            recovery_eligible_value=round(eligible_val, 2),
            ml_high_risk_count=ml_high_risk,
            ai_recommended_count=ai_recommended,
            policy_approved_count=policy_approved,
            action_executed_count=action_executed,
            successful_recovery_count=successful_rec,
            actual_recovered_revenue=round(agent_rec_rev, 2),
            baseline_recovered_revenue=round(baseline_rec_rev, 2),
            incremental_recovered_revenue=round(inc_rec_rev, 2),
            overall_conversion_rate=min(1.0, max(0.0, conv_rate)),
            stages=stages,
            currency="INR",
        )

    def get_predicted_vs_actual(self, db: Session, batch_id: str | None = None, scope: str | None = None) -> PredictedVsActualSummary:
        active_scope, target_batch_id, batch_data = self._resolve_scope(db, batch_id, scope)
        buckets_def = [
            ("0.00 - 0.30", 0.0, 0.30),
            ("0.30 - 0.60", 0.30, 0.60),
            ("0.60 - 0.80", 0.60, 0.80),
            ("0.80 - 1.00", 0.80, 1.001),
        ]

        buckets_result = []
        tot_pred = 0.0
        tot_act = 0.0
        tot_prob_sum = 0.0
        tot_cases_count = 0
        tot_succ_count = 0

        for name, low, high in buckets_def:
            if active_scope == "CURRENT_BATCH" and batch_data:
                case_ids = batch_data["case_ids"]
                outcome_ids = batch_data["outcome_ids"]

                cases_q = db.query(RecoveryCase).filter(
                    RecoveryCase.id.in_(case_ids),
                    RecoveryCase.recovery_probability >= low,
                    RecoveryCase.recovery_probability < high,
                ) if case_ids else None
                cases = cases_q.all() if cases_q else []

                case_sub_ids = [c.id for c in cases]
                outcomes_q = db.query(RecoveryOutcome).join(
                    RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id
                ).filter(
                    or_(
                        RecoveryOutcome.id.in_(outcome_ids),
                        RecoveryOutcome.recovery_outcome_id.in_(outcome_ids),
                        RecoveryOutcome.recovery_case_id.in_(case_sub_ids),
                    ),
                    RecoveryAction.recovery_case_id.in_(case_sub_ids),
                    RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                ) if case_sub_ids else None
                outcomes = outcomes_q.all() if outcomes_q else []

            else:
                cases = db.query(RecoveryCase).filter(
                    RecoveryCase.recovery_probability >= low,
                    RecoveryCase.recovery_probability < high,
                ).all()

                case_sub_ids = [c.id for c in cases]
                outcomes = db.query(RecoveryOutcome).join(
                    RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id
                ).filter(
                    RecoveryAction.recovery_case_id.in_(case_sub_ids),
                    RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
                ).all() if case_sub_ids else []

            count = len(cases)
            pred_rev = sum(c.expected_recovery for c in cases)
            act_rev = sum(o.recovered_amount for o in outcomes)
            avg_prob = (sum(c.recovery_probability for c in cases) / count) if count > 0 else 0.0
            act_rec_rate = (len(outcomes) / count) if count > 0 else 0.0
            calib = round(act_rev / pred_rev, 3) if pred_rev > 0 else (1.0 if act_rev == 0 and count > 0 else 0.0)

            tot_pred += pred_rev
            tot_act += act_rev
            tot_prob_sum += sum(c.recovery_probability for c in cases)
            tot_cases_count += count
            tot_succ_count += len(outcomes)

            buckets_result.append(PredictedVsActual(
                probability_bucket=name,
                total_cases=count,
                predicted_expected_revenue=round(pred_rev, 2),
                actual_recovered_revenue=round(act_rev, 2),
                calibration_accuracy=min(1.0, max(0.0, calib)),
                average_predicted_probability=round(avg_prob, 3),
                actual_recovery_rate=round(min(1.0, act_rec_rate), 3),
            ))

        ratio = round(tot_act / tot_pred, 3) if tot_pred > 0 else 0.0
        overall_avg_prob = round(tot_prob_sum / tot_cases_count, 3) if tot_cases_count > 0 else 0.0
        overall_rec_rate = round(tot_succ_count / tot_cases_count, 3) if tot_cases_count > 0 else 0.0

        return PredictedVsActualSummary(
            scope=active_scope,
            batch_id=target_batch_id,
            buckets=buckets_result,
            total_predicted_revenue=round(tot_pred, 2),
            total_actual_revenue=round(tot_act, 2),
            overall_prediction_to_actual_ratio=ratio,
            average_predicted_probability=overall_avg_prob,
            overall_recovery_rate=overall_rec_rate,
            currency="INR",
        )

    def get_incrementality_summary(self, db: Session, batch_id: str | None = None, scope: str | None = None) -> IncrementalitySummary:
        active_scope, target_batch_id, batch_data = self._resolve_scope(db, batch_id, scope)

        if active_scope == "CURRENT_BATCH" and batch_data:
            summary = batch_data["summary"]
            agent_rev = summary.agent_recovered_revenue
            base_rev = summary.baseline_recovered_revenue
            inc_rev = summary.incremental_recovered_revenue
            lift = summary.incremental_lift
        else:
            active_scope = "CUMULATIVE"
            target_batch_id = None
            agent_rev = (
                db.query(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0))
                .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
                .scalar() or 0.0
            )
            base_rev = (
                db.query(func.coalesce(func.sum(RecoveryOutcome.baseline_amount), 0.0))
                .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
                .scalar() or 0.0
            )
            inc_rev = (
                db.query(func.coalesce(func.sum(RecoveryOutcome.incremental_amount), 0.0))
                .filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value)
                .scalar() or 0.0
            )
            lift = round(inc_rev / base_rev, 4) if base_rev > 0 else 0.0

        return IncrementalitySummary(
            scope=active_scope,
            batch_id=target_batch_id,
            baseline_recovery=round(base_rev, 2),
            agent_recovery=round(agent_rev, 2),
            incremental_recovery=round(inc_rev, 2),
            baseline_recovered_revenue=round(base_rev, 2),
            agent_recovered_revenue=round(agent_rev, 2),
            incremental_recovered_revenue=round(inc_rev, 2),
            incremental_lift=lift,
            currency="INR",
        )

    def get_systemic_incidents_analytics(self, db: Session) -> list[SystemicIncidentAnalytics]:
        incidents = db.query(SystemicIncident).all()
        results = []
        for inc in incidents:
            txs = (
                db.query(Transaction)
                .join(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
                .filter(PaymentFailure.normalized_failure_type == inc.failure_type)
                .all()
            )
            blocked_retries = (
                db.query(RecoveryAction)
                .filter(
                    RecoveryAction.guardrail_decision == "REJECTED",
                    RecoveryAction.guardrail_reason.ilike("%bank failure incident%")
                )
                .count()
            )
            val = sum(t.amount for t in txs)
            results.append(SystemicIncidentAnalytics(
                incident_type=inc.failure_type,
                provider_or_bank=inc.provider_or_bank,
                status=inc.status,
                failure_spike_rate=inc.spike_rate,
                affected_transaction_count=len(txs),
                affected_payment_value=round(val, 2),
                blocked_automated_retries=blocked_retries,
                threshold=0.25,
            ))
        return results

    def get_recovery_analytics(self, db: Session, batch_id: str | None = None, scope: str | None = None) -> AnalyticsResponse:
        active_scope, target_batch_id, _ = self._resolve_scope(db, batch_id, scope)
        by_failure = self.get_analytics_by_failure_type(db, batch_id=target_batch_id, scope=active_scope)
        by_action = self.get_analytics_by_action(db, batch_id=target_batch_id, scope=active_scope)
        by_method = self.get_analytics_by_payment_method(db, batch_id=target_batch_id, scope=active_scope)
        funnel = self.get_recovery_funnel(db, batch_id=target_batch_id, scope=active_scope)
        pred_act_summary = self.get_predicted_vs_actual(db, batch_id=target_batch_id, scope=active_scope)
        incrementality = self.get_incrementality_summary(db, batch_id=target_batch_id, scope=active_scope)
        systemic = self.get_systemic_incidents_analytics(db)

        total_interventions = sum(a.attempted_count for a in by_action)

        return AnalyticsResponse(
            scope=active_scope,
            batch_id=target_batch_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            currency="INR",
            by_action=by_action,
            by_failure_type=by_failure,
            by_payment_method=by_method,
            funnel=funnel,
            incrementality=incrementality,
            predicted_vs_actual=pred_act_summary.buckets,
            predicted_vs_actual_summary=pred_act_summary,
            systemic_incidents=systemic,
            recovery_by_failure_type=by_failure,
            recovery_by_action=by_action,
            recovery_by_payment_method=by_method,
            total_interventions=total_interventions,
            total_recovered_amount=incrementality.agent_recovered_revenue,
            baseline_recovered_amount=incrementality.baseline_recovered_revenue,
            incremental_recovered_amount=incrementality.incremental_recovered_revenue,
        )

analytics_service = AnalyticsService()
