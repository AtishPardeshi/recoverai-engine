import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import relationship
from backend.app.database.session import Base

class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recovery_case_id = Column(String(64), unique=True, nullable=False, default=lambda: f"CASE-{uuid.uuid4().hex[:8].upper()}")
    transaction_id = Column(String(36), ForeignKey("transactions.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    revenue_at_risk = Column(Float, nullable=False)
    recovery_probability = Column(Float, nullable=False)
    risk_score = Column(Float, default=0.5, nullable=False)
    priority_score = Column(Float, nullable=False)
    status = Column(String(32), nullable=False, default="RECOVERY_ELIGIBLE", index=True)
    recommended_action = Column(String(64), nullable=True)
    root_cause = Column(String(64), nullable=True)
    expected_recovery = Column(Float, nullable=False)
    confidence = Column(Float, default=0.85, nullable=False)
    requires_human_review = Column(Boolean, default=False, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    message_count = Column(Integer, default=0, nullable=False)
    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    closed_at = Column(DateTime, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    transaction = relationship("Transaction", back_populates="recovery_case")
    actions = relationship("RecoveryAction", back_populates="recovery_case", cascade="all, delete-orphan", order_by="RecoveryAction.sequence_number")
    outcomes = relationship("RecoveryOutcome", back_populates="recovery_case", cascade="all, delete-orphan")
    notifications = relationship("NotificationLog", back_populates="recovery_case", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("revenue_at_risk >= 0.0", name="ck_case_revenue_at_risk"),
        CheckConstraint("expected_recovery >= 0.0", name="ck_case_expected_recovery"),
        CheckConstraint("recovery_probability >= 0.0 AND recovery_probability <= 1.0", name="ck_case_recovery_probability"),
        CheckConstraint("risk_score >= 0.0 AND risk_score <= 1.0", name="ck_case_risk_score"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_case_confidence"),
        CheckConstraint("retry_count >= 0", name="ck_case_retry_count"),
        CheckConstraint("message_count >= 0", name="ck_case_message_count"),
        Index("ix_recovery_cases_priority", "priority_score"),
        Index("ix_recovery_cases_status_created", "status", "created_at"),
    )
