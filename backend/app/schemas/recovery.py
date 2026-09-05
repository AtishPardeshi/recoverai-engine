from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from backend.app.schemas.common import (
    RecoveryActionTypeEnum,
    GuardrailDecisionEnum,
    OutcomeTypeEnum,
    OutcomeResultEnum,
    TransactionStatusEnum,
)
from backend.app.schemas.transaction import TransactionResponse

class AgentMetadata(BaseModel):
    agent_version: str = "recovery-agent-v1"
    prompt_version: str = "prompt-v1"
    provider: str = "fallback"
    model_name: str = "deterministic-rule-agent"
    prediction_source: str = "fallback"
    recommendation_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AIRecommendationDetail(BaseModel):
    recommended_action: RecoveryActionTypeEnum
    root_cause: str
    reason: str = Field(..., max_length=500)
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_recovery: float = Field(..., ge=0.0)
    risk_flags: list[str] = Field(default_factory=list)
    requires_human_review: bool = False

    class Config:
        extra = "forbid"

class MLRiskContext(BaseModel):
    recovery_probability: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    expected_recovery: float = Field(default=0.0, ge=0.0)
    priority_score: float = Field(ge=0.0)
    model_version: str = "recovery-risk-v1"
    feature_version: str = "features-v1"
    prediction_source: str = "trained_model"
    confidence: float = 0.85

class RootCauseContext(BaseModel):
    root_cause: str
    explanation: str
    recoverability_class: str = "HIGH"
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)

class AIRecommendationResponse(BaseModel):
    case_id: str | None = None
    recovery_case_id: str
    transaction_id: str | None = None
    recommendation: AIRecommendationDetail
    ai_recommendation: AIRecommendationDetail | None = None
    ml: MLRiskContext
    ml_context: MLRiskContext | None = None
    root_cause_context: RootCauseContext | None = None
    agent_metadata: AgentMetadata | None = None
    correlation_id: str
    # Direct accessors for backward compatibility
    recommended_action: RecoveryActionTypeEnum | None = None
    root_cause: str | None = None
    reason: str | None = None
    confidence: float | None = None
    expected_recovery: float | None = None
    risk_flags: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    recovery_probability: float | None = None
    risk_score: float | None = None


class RecoveryOutcomeResponse(BaseModel):
    id: str
    recovery_outcome_id: str
    recovery_case_id: str
    recovery_action_id: str | None = None
    transaction_id: str
    outcome_type: OutcomeTypeEnum
    result: OutcomeResultEnum
    recovered_amount: float = Field(ge=0.0)
    baseline_amount: float = Field(ge=0.0)
    incremental_amount: float = Field(ge=0.0)
    currency: str = "INR"
    simulator_result: str
    failure_reason: str | None = None
    metadata_payload: dict[str, Any] | None = None
    occurred_at: datetime

    class Config:
        from_attributes = True

class RecoveryActionResponse(BaseModel):
    id: str
    action_id: str
    recovery_case_id: str
    sequence_number: int
    idempotency_key: str
    action_type: RecoveryActionTypeEnum
    recommendation_reason: str
    confidence: float
    expected_recovery: float
    policy_version: str
    guardrail_decision: GuardrailDecisionEnum
    guardrail_reason: str | None = None
    status: str
    created_at: datetime
    executed_at: datetime | None = None
    outcome: RecoveryOutcomeResponse | None = None

    class Config:
        from_attributes = True

class RecoveryCaseResponse(BaseModel):
    id: str
    recovery_case_id: str
    transaction_id: str
    revenue_at_risk: float
    recovery_probability: float
    risk_score: float = 0.5
    priority_score: float
    status: TransactionStatusEnum
    recommended_action: str | None = None
    root_cause: str | None = None
    expected_recovery: float
    confidence: float = 0.85
    requires_human_review: bool = False
    retry_count: int
    message_count: int
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    correlation_id: str | None = None
    created_at: datetime
    updated_at: datetime
    transaction: TransactionResponse | None = None
    actions: list[RecoveryActionResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True

class RecoveryExecuteRequest(BaseModel):
    action_type: RecoveryActionTypeEnum | None = None
    override_reason: str | None = None

class ActionSummary(BaseModel):
    action_id: str
    action_type: RecoveryActionTypeEnum
    status: str

class ExecutionSummary(BaseModel):
    status: str
    simulated: bool = True
    idempotency_key: str | None = None
    action_id: str | None = None
    action_type: RecoveryActionTypeEnum | None = None

class PolicySummary(BaseModel):
    approved: bool
    decision: GuardrailDecisionEnum = GuardrailDecisionEnum.APPROVED
    action: RecoveryActionTypeEnum | None = None
    reason_code: str
    reason_codes: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    policy_version: str = "policy-v1"

class OutcomeSummary(BaseModel):
    outcome_type: OutcomeTypeEnum = OutcomeTypeEnum.AGENT_RECOVERY
    outcome_status: OutcomeResultEnum = OutcomeResultEnum.SUCCESS
    status: str | None = None
    recovered_amount: float = 0.0
    baseline_amount: float = 0.0
    incremental_amount: float = 0.0
    currency: str = "INR"
    simulator_reference: str | None = None

class RecoveryExecuteResponse(BaseModel):
    case_id: str | None = None
    recovery_case_id: str
    action: ActionSummary | None = None
    policy: PolicySummary
    execution: ExecutionSummary | None = None
    outcome: OutcomeSummary | None = None
    transaction_state: TransactionStatusEnum
    correlation_id: str
    # Compatibility accessors
    execution_id: str | None = None
    transaction_id: str | None = None
    action_type: RecoveryActionTypeEnum | None = None
    guardrail_status: GuardrailDecisionEnum | None = None
    guardrail_reason: str | None = None
    execution_status: str | None = None
    outcome_result: OutcomeResultEnum | None = None
    recovered_amount: float = 0.0
    simulator_reference: str | None = None
    new_case_status: TransactionStatusEnum | None = None
    audit_event_id: str | None = None
    executed_at: datetime | None = None

