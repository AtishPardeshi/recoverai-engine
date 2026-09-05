import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Text, DateTime, Index, CheckConstraint
from backend.app.database.session import Base

class SystemicIncident(Base):
    __tablename__ = "systemic_incidents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_id = Column(String(64), unique=True, nullable=False, default=lambda: f"INC-{uuid.uuid4().hex[:8].upper()}")
    provider_or_bank = Column(String(128), nullable=False, index=True)
    failure_type = Column(String(64), nullable=False)
    incident_type = Column(String(64), default="BANK_FAILURE_SPIKE", nullable=False)
    status = Column(String(32), default="ACTIVE", index=True)  # ACTIVE, MITIGATED, RESOLVED
    spike_rate = Column(Float, nullable=False)
    affected_payment_method = Column(String(32), default="CARD", nullable=True)
    affected_gateway = Column(String(64), default="RAZORPAY_GATEWAY", nullable=True)
    reason = Column(Text, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("spike_rate >= 0.0 AND spike_rate <= 1.0", name="ck_incident_spike_rate"),
        Index("ix_incidents_bank_status", "provider_or_bank", "status"),
    )
