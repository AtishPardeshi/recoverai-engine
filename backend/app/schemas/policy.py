from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from backend.app.schemas.common import RecoveryActionTypeEnum, GuardrailDecisionEnum

class PolicyReasonCode(str, Enum):
    TRANSACTION_NOT_RECOVERY_ELIGIBLE = "TRANSACTION_NOT_RECOVERY_ELIGIBLE"
    TRANSACTION_ALREADY_CAPTURED = "TRANSACTION_ALREADY_CAPTURED"
    TRANSACTION_ALREADY_RECOVERED = "TRANSACTION_ALREADY_RECOVERED"
    TRANSACTION_TERMINAL = "TRANSACTION_TERMINAL"
    RETRY_LIMIT_EXCEEDED = "RETRY_LIMIT_EXCEEDED"
    RETRY_COOLDOWN_ACTIVE = "RETRY_COOLDOWN_ACTIVE"
    PAYMENT_LINK_LIMIT_EXCEEDED = "PAYMENT_LINK_LIMIT_EXCEEDED"
    MESSAGE_LIMIT_EXCEEDED = "MESSAGE_LIMIT_EXCEEDED"
    RECOVERY_WINDOW_EXCEEDED = "RECOVERY_WINDOW_EXCEEDED"
    CUSTOMER_OPTED_OUT = "CUSTOMER_OPTED_OUT"
    OPEN_DISPUTE = "OPEN_DISPUTE"
    SYSTEMIC_INCIDENT_ACTIVE = "SYSTEMIC_INCIDENT_ACTIVE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    INVALID_ACTION = "INVALID_ACTION"
    MISSING_POLICY_CONTEXT = "MISSING_POLICY_CONTEXT"
    RECOVERY_CASE_EXHAUSTED = "RECOVERY_CASE_EXHAUSTED"
    ACTION_ALREADY_EXECUTED = "ACTION_ALREADY_EXECUTED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"

class RecoveryPolicyConfig(BaseModel):
    """
    Centralized Deterministic Policy Configuration.
    
    NOTE ON SYSTEMIC INCIDENT THRESHOLD:
    The systemic incident threshold (default 0.25 = 25% failure spike) is a configurable
    simulation control parameter, NOT a real banking/payment industry standard.
    """
    max_automated_retries: int = 2
    min_retry_interval_hours: int = 6
    max_payment_link_attempts: int = 1
    max_recovery_duration_hours: int = 72
    max_messages_per_recovery_case: int = 2
    systemic_incident_threshold: float = 0.25
    policy_version: str = "policy-v1"

    class Config:
        frozen = True

class PolicyDecision(BaseModel):
    """
    Strict PolicyDecision contract.
    Decision must be strictly APPROVED or REJECTED.
    """
    decision: GuardrailDecisionEnum
    action: RecoveryActionTypeEnum
    reason_codes: list[PolicyReasonCode] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    policy_version: str = "policy-v1"
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    requires_human_review: bool = False
    suggested_status: str | None = None

    @property
    def is_approved(self) -> bool:
        return self.decision == GuardrailDecisionEnum.APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.decision == GuardrailDecisionEnum.REJECTED
