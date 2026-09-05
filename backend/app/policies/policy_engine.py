from datetime import datetime, timezone, timedelta
from typing import NamedTuple, Any
from backend.app.schemas.common import RecoveryActionTypeEnum, TransactionStatusEnum, GuardrailDecisionEnum
from backend.app.schemas.policy import PolicyDecision, PolicyReasonCode, RecoveryPolicyConfig

class PolicyValidationResult(NamedTuple):
    approved: bool
    decision: GuardrailDecisionEnum
    reason: str
    suggested_status: str | None = None
    reason_code: PolicyReasonCode | None = None

class PolicyEngine:
    """
    Deterministic Safety & Policy Guardrail Engine.
    Enforces strict operational, safety, and compliance boundaries.
    The AI recommends, but ONLY the Deterministic Policy Engine can approve.
    
    The Policy Engine executes 100% deterministic code with NO LLM inference.
    """

    def __init__(self, config: RecoveryPolicyConfig | None = None):
        self.config = config or RecoveryPolicyConfig()

    def evaluate(
        self,
        action: RecoveryActionTypeEnum | str | None,
        case_status: str | None,
        retry_count: int = 0,
        message_count: int = 0,
        payment_link_count: int = 0,
        case_created_at: datetime | None = None,
        last_action_time: datetime | None = None,
        is_opted_out: bool = False,
        has_open_dispute: bool = False,
        is_systemic_incident_active: bool = False,
        failure_spike_rate: float = 0.0,
        ml_probability: float | None = None,
        ai_confidence: float | None = None,
        transaction_amount: float | None = None,
        current_time: datetime | None = None,
    ) -> PolicyDecision:
        """
        Executes strict 15-step deterministic policy evaluation in a defined, invariant order.
        Returns a strict PolicyDecision (APPROVED or REJECTED).
        """
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # 1. Validate Context Exists
        if case_status is None:
            return PolicyDecision(
                decision=GuardrailDecisionEnum.REJECTED,
                action=RecoveryActionTypeEnum.STOP_RECOVERY,
                reason_codes=[PolicyReasonCode.MISSING_POLICY_CONTEXT],
                reasons=["Policy context is missing or incomplete."],
                policy_version=self.config.policy_version,
                evaluated_at=now,
                requires_human_review=True,
            )

        # 2. Validate Action Enum in Approved Taxonomy
        valid_action: RecoveryActionTypeEnum
        try:
            if isinstance(action, RecoveryActionTypeEnum):
                valid_action = action
            elif isinstance(action, str) and action in RecoveryActionTypeEnum.__members__:
                valid_action = RecoveryActionTypeEnum(action)
            else:
                return PolicyDecision(
                    decision=GuardrailDecisionEnum.REJECTED,
                    action=RecoveryActionTypeEnum.STOP_RECOVERY,
                    reason_codes=[PolicyReasonCode.INVALID_ACTION],
                    reasons=[f"Action '{action}' is not in the approved 7-action taxonomy."],
                    policy_version=self.config.policy_version,
                    evaluated_at=now,
                    requires_human_review=True,
                )
        except Exception:
            return PolicyDecision(
                decision=GuardrailDecisionEnum.REJECTED,
                action=RecoveryActionTypeEnum.STOP_RECOVERY,
                reason_codes=[PolicyReasonCode.INVALID_ACTION],
                reasons=[f"Invalid action '{action}'."],
                policy_version=self.config.policy_version,
                evaluated_at=now,
                requires_human_review=True,
            )

        # 3. Check Terminal Transaction & Case States
        if case_status in [
            TransactionStatusEnum.CAPTURED.value,
            TransactionStatusEnum.RECOVERED.value,
            TransactionStatusEnum.STOPPED.value,
            TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
            TransactionStatusEnum.ESCALATED.value,
        ]:
            if case_status == TransactionStatusEnum.CAPTURED.value:
                code = PolicyReasonCode.TRANSACTION_ALREADY_CAPTURED
            elif case_status == TransactionStatusEnum.RECOVERED.value:
                code = PolicyReasonCode.TRANSACTION_ALREADY_RECOVERED
            elif case_status == TransactionStatusEnum.RECOVERY_EXHAUSTED.value:
                code = PolicyReasonCode.RECOVERY_CASE_EXHAUSTED
            else:
                code = PolicyReasonCode.TRANSACTION_TERMINAL

            return PolicyDecision(
                decision=GuardrailDecisionEnum.REJECTED,
                action=valid_action,
                reason_codes=[code],
                reasons=[f"GUARDRAIL_VIOLATION: Cannot execute actions on terminal case in status '{case_status}'. Double charge prevented."],
                policy_version=self.config.policy_version,
                evaluated_at=now,
                suggested_status=case_status,
            )

        # 4. Check Recovery Eligibility
        if case_status in [TransactionStatusEnum.CREATED.value, TransactionStatusEnum.AUTHORIZED.value]:
            return PolicyDecision(
                decision=GuardrailDecisionEnum.REJECTED,
                action=valid_action,
                reason_codes=[PolicyReasonCode.TRANSACTION_NOT_RECOVERY_ELIGIBLE],
                reasons=[f"GUARDRAIL_VIOLATION: Transaction status '{case_status}' is not eligible for recovery."],
                policy_version=self.config.policy_version,
                evaluated_at=now,
            )

        # Normalize timestamps for duration calculations
        if case_created_at:
            if case_created_at.tzinfo is None:
                case_created_at = case_created_at.replace(tzinfo=timezone.utc)
            # 5. Check Maximum Recovery Duration Check (e.g. 72 Hours)
            elapsed_recovery_hours = (now - case_created_at).total_seconds() / 3600.0
            if elapsed_recovery_hours > self.config.max_recovery_duration_hours:
                if valid_action not in [RecoveryActionTypeEnum.ESCALATE_TO_HUMAN, RecoveryActionTypeEnum.STOP_RECOVERY]:
                    return PolicyDecision(
                        decision=GuardrailDecisionEnum.REJECTED,
                        action=valid_action,
                        reason_codes=[PolicyReasonCode.RECOVERY_WINDOW_EXCEEDED],
                        reasons=[
                            f"GUARDRAIL_VIOLATION: Recovery window exceeded maximum duration ({elapsed_recovery_hours:.1f}h > {self.config.max_recovery_duration_hours}h)."
                        ],
                        policy_version=self.config.policy_version,
                        evaluated_at=now,
                        suggested_status=TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
                        requires_human_review=True,
                    )

        # 6. Check Customer Opt-Out Compliance
        if is_opted_out:
            if valid_action != RecoveryActionTypeEnum.STOP_RECOVERY:
                return PolicyDecision(
                    decision=GuardrailDecisionEnum.REJECTED,
                    action=valid_action,
                    reason_codes=[PolicyReasonCode.CUSTOMER_OPTED_OUT],
                    reasons=["GUARDRAIL_VIOLATION: Customer has explicitly opted out of recovery communications and retries."],
                    policy_version=self.config.policy_version,
                    evaluated_at=now,
                    suggested_status=TransactionStatusEnum.STOPPED.value,
                )

        # 7. Check Open Dispute / Chargeback Lockout
        if has_open_dispute:
            if valid_action in [
                RecoveryActionTypeEnum.RETRY_PAYMENT,
                RecoveryActionTypeEnum.DELAYED_RETRY,
                RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
            ]:
                return PolicyDecision(
                    decision=GuardrailDecisionEnum.REJECTED,
                    action=valid_action,
                    reason_codes=[PolicyReasonCode.OPEN_DISPUTE],
                    reasons=["GUARDRAIL_VIOLATION: Active chargeback/dispute lock. Automated charging prohibited."],
                    policy_version=self.config.policy_version,
                    evaluated_at=now,
                    suggested_status=TransactionStatusEnum.ESCALATED.value,
                    requires_human_review=True,
                )

        # 8. Check Systemic Incident Protection (Circuit Breaker)
        incident_triggered = is_systemic_incident_active or (
            failure_spike_rate >= self.config.systemic_incident_threshold
        )
        if incident_triggered:
            if valid_action in [
                RecoveryActionTypeEnum.RETRY_PAYMENT,
                RecoveryActionTypeEnum.DELAYED_RETRY,
                RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
            ]:
                return PolicyDecision(
                    decision=GuardrailDecisionEnum.REJECTED,
                    action=valid_action,
                    reason_codes=[PolicyReasonCode.SYSTEMIC_INCIDENT_ACTIVE],
                    reasons=[
                        f"GUARDRAIL_VIOLATION: Correlated bank failure incident active. Automated retries paused to prevent cascade (spike rate={failure_spike_rate:.2f})."
                    ],
                    policy_version=self.config.policy_version,
                    evaluated_at=now,
                    requires_human_review=True,
                )

        # 9. Human Review Advisory Checks
        human_review_flag = False
        if ml_probability is not None and ml_probability < 0.20:
            human_review_flag = True
        if ai_confidence is not None and ai_confidence < 0.40:
            human_review_flag = True

        # 10. Check Action-Specific Limits: Retries
        if valid_action in [RecoveryActionTypeEnum.RETRY_PAYMENT, RecoveryActionTypeEnum.DELAYED_RETRY]:
            if retry_count >= self.config.max_automated_retries:
                return PolicyDecision(
                    decision=GuardrailDecisionEnum.REJECTED,
                    action=valid_action,
                    reason_codes=[PolicyReasonCode.RETRY_LIMIT_EXCEEDED],
                    reasons=[
                        f"GUARDRAIL_VIOLATION: Max automated retries exceeded ({retry_count}/{self.config.max_automated_retries})."
                    ],
                    policy_version=self.config.policy_version,
                    evaluated_at=now,
                    suggested_status=TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
                )

            # 11. Check Retry Cooldown
            if last_action_time and retry_count > 0:
                if last_action_time.tzinfo is None:
                    last_action_time = last_action_time.replace(tzinfo=timezone.utc)
                elapsed_hrs = (now - last_action_time).total_seconds() / 3600.0
                if elapsed_hrs < self.config.min_retry_interval_hours:
                    return PolicyDecision(
                        decision=GuardrailDecisionEnum.REJECTED,
                        action=valid_action,
                        reason_codes=[PolicyReasonCode.RETRY_COOLDOWN_ACTIVE],
                        reasons=[
                            f"GUARDRAIL_VIOLATION: Retry cooldown active: {elapsed_hrs:.1f}h elapsed < {self.config.min_retry_interval_hours}h required."
                        ],
                        policy_version=self.config.policy_version,
                        evaluated_at=now,
                    )

        # 12. Check Action-Specific Limits: Payment Links
        if valid_action == RecoveryActionTypeEnum.SEND_PAYMENT_LINK:
            if payment_link_count >= self.config.max_payment_link_attempts or message_count >= self.config.max_messages_per_recovery_case:
                return PolicyDecision(
                    decision=GuardrailDecisionEnum.REJECTED,
                    action=valid_action,
                    reason_codes=[PolicyReasonCode.PAYMENT_LINK_LIMIT_EXCEEDED],
                    reasons=[
                        f"Payment link attempt limit reached ({payment_link_count}/{self.config.max_payment_link_attempts})."
                    ],
                    policy_version=self.config.policy_version,
                    evaluated_at=now,
                    suggested_status=TransactionStatusEnum.ESCALATED.value,
                )

        # 13. Check Action-Specific Limits: Communication / Messaging
        if valid_action in [
            RecoveryActionTypeEnum.SEND_REMINDER,
            RecoveryActionTypeEnum.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
        ]:
            if message_count >= self.config.max_messages_per_recovery_case:
                return PolicyDecision(
                    decision=GuardrailDecisionEnum.REJECTED,
                    action=valid_action,
                    reason_codes=[PolicyReasonCode.MESSAGE_LIMIT_EXCEEDED],
                    reasons=[
                        f"Customer communication cap reached ({message_count}/{self.config.max_messages_per_recovery_case})."
                    ],
                    policy_version=self.config.policy_version,
                    evaluated_at=now,
                    suggested_status=TransactionStatusEnum.ESCALATED.value,
                )

        # 14. Terminal Control Actions (STOP_RECOVERY, ESCALATE_TO_HUMAN)
        if valid_action == RecoveryActionTypeEnum.STOP_RECOVERY:
            return PolicyDecision(
                decision=GuardrailDecisionEnum.APPROVED,
                action=valid_action,
                reason_codes=[],
                reasons=["Explicit administrative termination approved."],
                policy_version=self.config.policy_version,
                evaluated_at=now,
                suggested_status=TransactionStatusEnum.STOPPED.value,
            )

        if valid_action == RecoveryActionTypeEnum.ESCALATE_TO_HUMAN:
            return PolicyDecision(
                decision=GuardrailDecisionEnum.APPROVED,
                action=valid_action,
                reason_codes=[],
                reasons=["Escalation to human operator approved."],
                policy_version=self.config.policy_version,
                evaluated_at=now,
                requires_human_review=True,
                suggested_status=TransactionStatusEnum.ESCALATED.value,
            )

        # 15. All Policy Checks Passed -> APPROVED
        return PolicyDecision(
            decision=GuardrailDecisionEnum.APPROVED,
            action=valid_action,
            reason_codes=[],
            reasons=[
                "Retry count below configured maximum",
                "Minimum retry interval satisfied",
                "No active systemic incident",
                "No customer opt-out",
                "No open dispute",
            ],
            policy_version=self.config.policy_version,
            evaluated_at=now,
            requires_human_review=human_review_flag,
            suggested_status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        )

    def validate(
        self,
        action_type: str,
        case_status: str,
        retry_count: int,
        message_count: int,
        case_created_at: datetime,
        last_action_time: datetime | None,
        is_opted_out: bool,
        has_open_dispute: bool,
        is_systemic_incident_active: bool = False,
    ) -> PolicyValidationResult:
        """
        Backwards-compatible wrapper returning PolicyValidationResult.
        """
        decision = self.evaluate(
            action=action_type,
            case_status=case_status,
            retry_count=retry_count,
            message_count=message_count,
            payment_link_count=message_count,
            case_created_at=case_created_at,
            last_action_time=last_action_time,
            is_opted_out=is_opted_out,
            has_open_dispute=has_open_dispute,
            is_systemic_incident_active=is_systemic_incident_active,
        )
        
        reason_str = " | ".join(decision.reasons)
        if decision.is_rejected and decision.reason_codes:
            reason_str = f"GUARDRAIL_VIOLATION: {reason_str}"
        elif decision.is_approved:
            reason_str = f"Policy checks passed (Policy {self.config.policy_version}). {reason_str}"

        return PolicyValidationResult(
            approved=decision.is_approved,
            decision=decision.decision,
            reason=reason_str,
            suggested_status=decision.suggested_status,
            reason_code=decision.reason_codes[0] if decision.reason_codes else None,
        )

policy_engine = PolicyEngine()
