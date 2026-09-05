import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.app.database.session import Base

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    notification_id = Column(String(64), unique=True, nullable=False, default=lambda: f"NOTIF-{uuid.uuid4().hex[:8].upper()}")
    recovery_case_id = Column(String(36), ForeignKey("recovery_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)
    channel = Column(String(32), nullable=False)  # EMAIL, SMS, PAYMENT_LINK, REMINDER
    notification_type = Column(String(64), default="RECOVERY_DISPATCH", nullable=False)
    status = Column(String(32), default="DELIVERED", nullable=False)  # QUEUED, DELIVERED, FAILED
    idempotency_key = Column(String(128), unique=True, nullable=False, default=lambda: f"notif:{uuid.uuid4().hex[:12]}", index=True)
    recipient_reference = Column(String(128), nullable=False)
    template_id = Column(String(64), nullable=False)
    metadata_payload = Column(JSON, nullable=True)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    recovery_case = relationship("RecoveryCase", back_populates="notifications")
    customer = relationship("Customer", back_populates="notifications")

    __table_args__ = (
        Index("ix_notification_case_sent", "recovery_case_id", "sent_at"),
    )
