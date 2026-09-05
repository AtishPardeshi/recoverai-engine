import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Text, JSON, DateTime, Index
from backend.app.database.session import Base

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(64), unique=True, nullable=False, default=lambda: f"EVT-{uuid.uuid4().hex[:12].upper()}", index=True)
    correlation_id = Column(String(64), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)  # TRANSACTION, RECOVERY_CASE, RECOVERY_ACTION, POLICY_GUARDRAIL, SIMULATOR
    entity_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)  # REVENUE_RISK_DETECTED, RECOMMENDATION_GENERATED, GUARDRAIL_EVALUATED, ACTION_EXECUTED, OUTCOME_RECORDED, etc.
    actor_type = Column(String(32), nullable=False)  # SYSTEM, ML, AI, POLICY_ENGINE, EXECUTOR, SIMULATOR, HUMAN
    input_summary = Column(Text, nullable=True)
    recommendation = Column(JSON, nullable=True)
    guardrail_result = Column(String(64), nullable=True)
    execution_result = Column(String(64), nullable=True)
    recovered_amount = Column(Float, default=0.0, nullable=True)
    payload = Column(JSON, nullable=False)
    policy_version = Column(String(32), nullable=True)
    agent_version = Column(String(32), nullable=True)
    previous_event_hash = Column(String(64), nullable=True)
    event_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index("ix_audit_events_correlation", "correlation_id"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_type_created", "event_type", "created_at"),
    )
