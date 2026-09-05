import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Text, JSON, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import relationship
from backend.app.database.session import Base

class RecoveryOutcome(Base):
    __tablename__ = "recovery_outcomes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recovery_outcome_id = Column(String(64), unique=True, nullable=False, default=lambda: f"OUT-{uuid.uuid4().hex[:8].upper()}")
    recovery_case_id = Column(String(36), ForeignKey("recovery_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    recovery_action_id = Column(String(36), ForeignKey("recovery_actions.id", ondelete="CASCADE"), unique=True, nullable=True, index=True)
    transaction_id = Column(String(36), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    outcome_type = Column(String(32), nullable=False, default="AGENT_RECOVERY", index=True)  # BASELINE, AGENT_RECOVERY
    result = Column(String(32), nullable=False, index=True)  # SUCCESS, FAILURE, SKIPPED
    recovered_amount = Column(Float, default=0.0, nullable=False)
    baseline_amount = Column(Float, default=0.0, nullable=False)
    incremental_amount = Column(Float, default=0.0, nullable=False)
    simulator_result = Column(String(64), nullable=False)
    failure_reason = Column(Text, nullable=True)
    metadata_payload = Column(JSON, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    occurred_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    recovery_action = relationship("RecoveryAction", back_populates="outcome")
    recovery_case = relationship("RecoveryCase", back_populates="outcomes")
    transaction = relationship("Transaction", back_populates="recovery_outcomes")

    __table_args__ = (
        CheckConstraint("recovered_amount >= 0.0", name="ck_outcome_recovered_amount"),
        CheckConstraint("baseline_amount >= 0.0", name="ck_outcome_baseline_amount"),
        CheckConstraint("incremental_amount >= 0.0", name="ck_outcome_incremental_amount"),
        Index("ix_recovery_outcomes_result_date", "result", "occurred_at"),
        Index("ix_recovery_outcomes_type_occurred", "outcome_type", "occurred_at"),
    )
