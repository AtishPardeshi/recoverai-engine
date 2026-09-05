import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, CheckConstraint, Index
from sqlalchemy.orm import relationship
from backend.app.database.session import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=True)
    historical_success_rate = Column(Float, default=0.0, nullable=False)
    total_transaction_value = Column(Float, default=0.0, nullable=False)
    successful_payment_count = Column(Integer, default=0, nullable=False)
    failed_payment_count = Column(Integer, default=0, nullable=False)
    is_opted_out = Column(Boolean, default=False, nullable=False)
    has_open_dispute = Column(Boolean, default=False, nullable=False)
    subscription_status = Column(String(32), default="ACTIVE", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    transactions = relationship("Transaction", back_populates="customer", cascade="all, delete-orphan")
    notifications = relationship("NotificationLog", back_populates="customer", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("historical_success_rate >= 0.0 AND historical_success_rate <= 1.0", name="ck_customer_success_rate"),
        CheckConstraint("total_transaction_value >= 0.0", name="ck_customer_total_value"),
        CheckConstraint("successful_payment_count >= 0", name="ck_customer_succ_count"),
        CheckConstraint("failed_payment_count >= 0", name="ck_customer_fail_count"),
        Index("ix_customers_optout_dispute", "is_opted_out", "has_open_dispute"),
    )
