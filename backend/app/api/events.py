from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.database.session import get_db
from backend.app.simulator.event_ingestion import ingest_payment_event

router = APIRouter(prefix="/events", tags=["Event Ingestion"])

class EventIngestRequest(BaseModel):
    event_id: str
    event_type: str
    payload: dict[str, Any]
    correlation_id: str | None = None

@router.post("/ingest")
def ingest_event(
    req: EventIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingests payment webhook events with deduplication and automated recovery case generation.
    """
    return ingest_payment_event(
        db=db,
        event_id=req.event_id,
        event_type=req.event_type,
        payload=req.payload,
        correlation_id=req.correlation_id,
    )
