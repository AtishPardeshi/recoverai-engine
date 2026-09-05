import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import relationship
from backend.app.database.session import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id = Column(String(64), unique=True, nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="INR", nullable=False)
    payment_method = Column(String(32), nullable=False)  # CARD, UPI, NETBANKING, WALLET, EMANDATE
    status = Column(String(32), nullable=False, default="CREATED", index=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    customer = relationship("Customer", back_populates="transactions")
    payment_failure = relationship("PaymentFailure", back_populates="transaction", uselist=False, cascade="all, delete-orphan")
    recovery_case = relationship("RecoveryCase", back_populates="transaction", uselist=False, cascade="all, delete-orphan")
    recovery_outcomes = relationship("RecoveryOutcome", back_populates="transaction", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("amount >= 0.0", name="ck_transaction_amount_positive"),
        Index("ix_transactions_status_created", "status", "created_at"),
        Index("ix_transactions_customer_created", "customer_id", "created_at"),
    )
