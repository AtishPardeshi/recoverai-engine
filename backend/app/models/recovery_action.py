import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Text, DateTime, ForeignKey, Index, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from backend.app.database.session import Base

class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action_id = Column(String(64), unique=True, nullable=False, default=lambda: f"ACT-{uuid.uuid4().hex[:8].upper()}")
    recovery_case_id = Column(String(36), ForeignKey("recovery_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_number = Column(Integer, default=1, nullable=False)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    action_type = Column(String(64), nullable=False)  # RETRY_PAYMENT, DELAYED_RETRY, SEND_PAYMENT_LINK, SUGGEST_ALTERNATIVE_PAYMENT_METHOD, SEND_REMINDER, ESCALATE_TO_HUMAN, STOP_RECOVERY
    status = Column(String(32), nullable=False, default="PENDING", index=True)  # PENDING, EXECUTED, REJECTED, FAILED
    recommendation_reason = Column(Text, nullable=False)
    confidence = Column(Float, default=0.85, nullable=False)
    expected_recovery = Column(Float, default=0.0, nullable=False)
    policy_version = Column(String(32), nullable=False)
    guardrail_decision = Column(String(32), nullable=False)  # APPROVED, REJECTED
    guardrail_reason = Column(Text, nullable=True)
    execution_result = Column(String(64), nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    requested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    approved_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    recovery_case = relationship("RecoveryCase", back_populates="actions")
    outcome = relationship("RecoveryOutcome", back_populates="recovery_action", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("recovery_case_id", "sequence_number", name="uq_case_action_sequence"),
        CheckConstraint("sequence_number >= 1", name="ck_action_sequence_positive"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_action_confidence"),
        CheckConstraint("expected_recovery >= 0.0", name="ck_action_expected_recovery"),
        Index("ix_recovery_actions_case_created", "recovery_case_id", "created_at"),
    )
