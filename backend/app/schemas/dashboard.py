from pydantic import BaseModel, Field

class DashboardMetrics(BaseModel):
    total_payment_volume: float = Field(ge=0.0)
    failed_payment_value: float = Field(ge=0.0)
    revenue_at_risk: float = Field(ge=0.0)
    recovery_eligible: float = Field(ge=0.0)
    intervention_value: float = Field(ge=0.0)
    recovered_revenue: float = Field(ge=0.0)
    baseline_recovered_revenue: float = Field(ge=0.0)
    incremental_recovered_revenue: float = Field(ge=0.0)
    recovery_rate: float = Field(ge=0.0, le=1.0)
    active_cases: int = Field(ge=0)
    successful_recoveries: int = Field(ge=0)
    total_attempts: int = Field(ge=0)
    guardrail_compliance_rate: float = Field(ge=0.0, le=1.0)
    average_recovery_probability: float = Field(ge=0.0, le=1.0)
    guardrail_rejections_count: int = Field(ge=0)
    systemic_incidents_active: int = Field(ge=0)

class DashboardSummaryResponse(BaseModel):
    currency: str = "INR"
    scope: str = "CURRENT_BATCH"
    batch_id: str | None = None
    metrics: DashboardMetrics
    # Direct accessor properties for backward compatibility with frontend
    total_payment_volume: float = 0.0
    failed_payment_value: float = 0.0
    revenue_at_risk: float = 0.0
    recovery_eligible_value: float = 0.0
    intervention_value: float = 0.0
    recovered_revenue: float = 0.0
    baseline_recovered_revenue: float = 0.0
    incremental_recovered_revenue: float = 0.0
    recovery_rate: float = 0.0
    active_cases_count: int = 0
    total_cases_count: int = 0
    successful_recoveries_count: int = 0
    guardrail_rejections_count: int = 0
    systemic_incidents_active: int = 0
    # Cumulative DB Metrics for side-by-side presentation
    cumulative_total_payment_volume: float = 0.0
    cumulative_failed_payment_value: float = 0.0
    cumulative_recovered_revenue: float = 0.0
    cumulative_baseline_recovered_revenue: float = 0.0
    cumulative_incremental_recovered_revenue: float = 0.0
    cumulative_successful_recoveries_count: int = 0
    cumulative_total_cases_count: int = 0
