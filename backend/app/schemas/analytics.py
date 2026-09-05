from pydantic import BaseModel, Field
from datetime import datetime, timezone

class RecoveryByDimension(BaseModel):
    category: str
    candidates_count: int = Field(default=0, ge=0)
    attempted_count: int = Field(default=0, ge=0)
    successful_count: int = Field(default=0, ge=0)
    recovery_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    recovered_amount: float = Field(default=0.0, ge=0.0)
    # Extended dimension fields
    at_risk_value: float = Field(default=0.0, ge=0.0)
    eligible_count: int = Field(default=0, ge=0)
    executed_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    baseline_recovered: float = Field(default=0.0, ge=0.0)
    agent_recovered: float = Field(default=0.0, ge=0.0)
    incremental_recovered: float = Field(default=0.0, ge=0.0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    recommended_count: int = Field(default=0, ge=0)
    approved_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    recommended_action_distribution: dict[str, int] = Field(default_factory=dict)
    scope: str = "CURRENT_BATCH"
    batch_id: str | None = None

class PredictedVsActual(BaseModel):
    probability_bucket: str  # e.g. "0.80 - 1.00"
    total_cases: int = Field(default=0, ge=0)
    predicted_expected_revenue: float = Field(default=0.0, ge=0.0)
    actual_recovered_revenue: float = Field(default=0.0, ge=0.0)
    calibration_accuracy: float = Field(default=0.0, ge=0.0)
    average_predicted_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    actual_recovery_rate: float = Field(default=0.0, ge=0.0, le=1.0)

class PredictedVsActualSummary(BaseModel):
    scope: str = "CURRENT_BATCH"
    batch_id: str | None = None
    buckets: list[PredictedVsActual] = Field(default_factory=list)
    total_predicted_revenue: float = Field(default=0.0, ge=0.0)
    total_actual_revenue: float = Field(default=0.0, ge=0.0)
    overall_prediction_to_actual_ratio: float = Field(default=0.0, ge=0.0)
    average_predicted_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_recovery_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    currency: str = "INR"

class IncrementalitySummary(BaseModel):
    scope: str = "CURRENT_BATCH"
    batch_id: str | None = None
    baseline_recovery: float = Field(default=0.0, ge=0.0)
    agent_recovery: float = Field(default=0.0, ge=0.0)
    incremental_recovery: float = Field(default=0.0, ge=0.0)
    baseline_recovered_revenue: float = Field(default=0.0, ge=0.0)
    agent_recovered_revenue: float = Field(default=0.0, ge=0.0)
    incremental_recovered_revenue: float = Field(default=0.0, ge=0.0)
    incremental_lift: float = Field(default=0.0, ge=0.0)
    currency: str = "INR"

class RecoveryFunnelStage(BaseModel):
    stage_name: str
    count: int = Field(ge=0)
    value: float = Field(default=0.0, ge=0.0)
    drop_off_count: int = Field(default=0, ge=0)
    conversion_rate: float = Field(default=0.0, ge=0.0, le=1.0)

class RecoveryFunnelResponse(BaseModel):
    scope: str = "CURRENT_BATCH"
    batch_id: str | None = None
    failed_payments_count: int = Field(ge=0)
    failed_payments_value: float = Field(ge=0.0)
    recovery_eligible_count: int = Field(ge=0)
    recovery_eligible_value: float = Field(ge=0.0)
    ml_high_risk_count: int = Field(ge=0)
    ai_recommended_count: int = Field(ge=0)
    policy_approved_count: int = Field(ge=0)
    action_executed_count: int = Field(ge=0)
    successful_recovery_count: int = Field(ge=0)
    actual_recovered_revenue: float = Field(ge=0.0)
    baseline_recovered_revenue: float = Field(ge=0.0)
    incremental_recovered_revenue: float = Field(ge=0.0)
    overall_conversion_rate: float = Field(ge=0.0, le=1.0)
    stages: list[RecoveryFunnelStage] = Field(default_factory=list)
    currency: str = "INR"

class SystemicIncidentAnalytics(BaseModel):
    incident_type: str
    provider_or_bank: str
    status: str
    failure_spike_rate: float
    affected_transaction_count: int
    affected_payment_value: float
    blocked_automated_retries: int
    threshold: float = 0.25

class AnalyticsResponse(BaseModel):
    scope: str = "CURRENT_BATCH"
    batch_id: str | None = None
    generated_at: str | None = None
    currency: str = "INR"
    by_action: list[RecoveryByDimension] = Field(default_factory=list)
    by_failure_type: list[RecoveryByDimension] = Field(default_factory=list)
    by_payment_method: list[RecoveryByDimension] = Field(default_factory=list)
    funnel: RecoveryFunnelResponse | None = None
    incrementality: IncrementalitySummary
    predicted_vs_actual: list[PredictedVsActual] = Field(default_factory=list)
    predicted_vs_actual_summary: PredictedVsActualSummary | None = None
    systemic_incidents: list[SystemicIncidentAnalytics] = Field(default_factory=list)
    # Direct accessors for backward compatibility
    recovery_by_failure_type: list[RecoveryByDimension] = Field(default_factory=list)
    recovery_by_action: list[RecoveryByDimension] = Field(default_factory=list)
    recovery_by_payment_method: list[RecoveryByDimension] = Field(default_factory=list)
    total_interventions: int = 0
    total_recovered_amount: float = 0.0
    baseline_recovered_amount: float = 0.0
    incremental_recovered_amount: float = 0.0
