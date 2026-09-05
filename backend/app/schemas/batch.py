from datetime import datetime, timezone
from pydantic import BaseModel, Field

class BatchRunRequest(BaseModel):
    limit: int = Field(default=500, ge=1, le=5000, description="Max candidate cases to process")
    seed: int = Field(default=42, description="Deterministic random seed for simulator reproducibility")
    dry_run: bool = Field(default=False, description="If true, evaluates policy without executing simulator or mutating DB")

class BatchRunSummary(BaseModel):
    batch_id: str
    status: str = "COMPLETED"
    started_at: datetime
    completed_at: datetime | None = None
    seed: int
    dry_run: bool = False
    total_candidates: int = Field(default=0, ge=0)
    ml_evaluated: int = Field(default=0, ge=0)
    ai_recommended: int = Field(default=0, ge=0)
    policy_approved: int = Field(default=0, ge=0)
    policy_rejected: int = Field(default=0, ge=0)
    actions_executed: int = Field(default=0, ge=0)
    successful_recoveries: int = Field(default=0, ge=0)
    failed_recoveries: int = Field(default=0, ge=0)
    escalated: int = Field(default=0, ge=0)
    stopped: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    baseline_recovered_revenue: float = Field(default=0.0, ge=0.0)
    agent_recovered_revenue: float = Field(default=0.0, ge=0.0)
    incremental_recovered_revenue: float = Field(default=0.0, ge=0.0)
    recovery_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    incremental_lift: float = Field(default=0.0, ge=0.0)
    policy_block_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    execution_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    currency: str = "INR"
    case_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    outcome_ids: list[str] = Field(default_factory=list)

