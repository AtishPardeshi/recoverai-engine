import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, JSON
from backend.app.database.session import Base

class BatchRun(Base):
    """
    Persisted Batch Recovery Run Execution Record.
    Stores durable batch metadata, execution status, counters, and associated IDs
    to allow consistent, process-restart-resilient batch scoped analytics.
    """
    __tablename__ = "batch_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), unique=True, index=True, nullable=False)
    seed = Column(Integer, nullable=True, default=42)
    status = Column(String(32), nullable=False, default="RUNNING")  # RUNNING, COMPLETED, FAILED
    
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    total_candidates = Column(Integer, default=0, nullable=False)
    ml_evaluated = Column(Integer, default=0, nullable=False)
    ai_recommended = Column(Integer, default=0, nullable=False)
    policy_approved = Column(Integer, default=0, nullable=False)
    policy_rejected = Column(Integer, default=0, nullable=False)
    actions_executed = Column(Integer, default=0, nullable=False)
    successful_recoveries = Column(Integer, default=0, nullable=False)
    failed_recoveries = Column(Integer, default=0, nullable=False)
    
    agent_recovered_revenue = Column(Float, default=0.0, nullable=False)
    baseline_recovered_revenue = Column(Float, default=0.0, nullable=False)
    incremental_recovered_revenue = Column(Float, default=0.0, nullable=False)
    
    # Associated entity IDs for exact batch scoping
    case_ids = Column(JSON, nullable=True, default=list)
    action_ids = Column(JSON, nullable=True, default=list)
    outcome_ids = Column(JSON, nullable=True, default=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "seed": self.seed,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_candidates": self.total_candidates,
            "ml_evaluated": self.ml_evaluated,
            "ai_recommended": self.ai_recommended,
            "policy_approved": self.policy_approved,
            "policy_rejected": self.policy_rejected,
            "actions_executed": self.actions_executed,
            "successful_recoveries": self.successful_recoveries,
            "failed_recoveries": self.failed_recoveries,
            "agent_recovered_revenue": round(self.agent_recovered_revenue, 2),
            "baseline_recovered_revenue": round(self.baseline_recovered_revenue, 2),
            "incremental_recovered_revenue": round(self.incremental_recovered_revenue, 2),
            "case_ids": self.case_ids or [],
            "action_ids": self.action_ids or [],
            "outcome_ids": self.outcome_ids or [],
        }
