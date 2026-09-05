import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import relationship
from backend.app.database.session import Base

class PaymentFailure(Base):
    __tablename__ = "payment_failures"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id = Column(String(36), ForeignKey("transactions.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    error_code = Column(String(64), nullable=False)
    error_description = Column(Text, nullable=True)
    error_source = Column(String(64), nullable=True)
    error_step = Column(String(64), nullable=True)
    error_reason = Column(String(64), nullable=True)
    normalized_failure_type = Column(String(64), nullable=False, index=True)  # TEMPORARY_BANK_DECLINE, INSUFFICIENT_FUNDS, BANK_DECLINE, NETWORK_ERROR, EXPIRED_METHOD, INVALID_DETAILS
    retry_count = Column(Integer, default=0, nullable=False)
    correlation_id = Column(String(64), nullable=True, index=True)
    occurred_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    transaction = relationship("Transaction", back_populates="payment_failure")

    __table_args__ = (
        CheckConstraint("retry_count >= 0", name="ck_payment_failure_retry_count"),
        Index("ix_payment_failures_type_date", "normalized_failure_type", "occurred_at"),
    )
