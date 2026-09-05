from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

class AuditEventResponse(BaseModel):
    id: str
    event_id: str
    correlation_id: str
    entity_type: str
    entity_id: str
    event_type: str
    actor_type: str
    input_summary: str | None = None
    recommendation: dict[str, Any] | None = None
    guardrail_result: str | None = None
    execution_result: str | None = None
    recovered_amount: float | None = 0.0
    payload: dict[str, Any] = Field(default_factory=dict)
    policy_version: str | None = None
    agent_version: str | None = None
    created_at: datetime
    timestamp: datetime | None = None

    class Config:
        from_attributes = True

    def __init__(self, **data: Any):
        if "timestamp" not in data or data["timestamp"] is None:
            data["timestamp"] = data.get("created_at")
        super().__init__(**data)

class ActivityFeedItem(BaseModel):
    id: str
    event_id: str | None = None
    event_type: str
    actor_type: str = "SYSTEM"
    title: str
    description: str
    amount: float | None = None
    status: str
    timestamp: datetime
    correlation_id: str
