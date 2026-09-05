import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from backend.app.database.session import get_db, Base, engine
from backend.app.simulator.seed_data import seed_database
from backend.app.models.incident import SystemicIncident

router = APIRouter(prefix="/simulator", tags=["Simulator Controls"])

class IncidentToggleRequest(BaseModel):
    provider_or_bank: str = "HDFC_BANK"
    failure_type: str = "TEMPORARY_BANK_DECLINE"
    active: bool = True
    spike_rate: float = 0.42

@router.post("/reset")
def reset_simulator(db: Session = Depends(get_db)):
    """
    Resets the database tables cleanly.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return {"status": "SUCCESS", "message": "Database reset to clean state"}

@router.post("/seed")
def seed_simulator(
    n_cases: int = Query(1000, ge=10, le=5000),
    seed: int = Query(42, description="Deterministic PRNG seed"),
    db: Session = Depends(get_db),
):
    """
    Seeds 1,000+ realistic cases with fixed random seed and primary demo case (TX-DEMO-001).
    """
    res = seed_database(db, n_cases=n_cases, seed=seed)
    return {
        "status": "SUCCESS",
        "message": f"Seeded {res['total_cases']} synthetic payment cases",
        "details": res,
    }

@router.post("/incident")
def toggle_systemic_incident(
    payload: IncidentToggleRequest,
    db: Session = Depends(get_db),
):
    """
    Toggles a simulated systemic bank outage to demonstrate guardrail circuit-breaker behavior.
    """
    inc = db.query(SystemicIncident).filter(SystemicIncident.provider_or_bank == payload.provider_or_bank).first()
    if payload.active:
        if not inc:
            inc = SystemicIncident(
                id=str(uuid.uuid4()),
                provider_or_bank=payload.provider_or_bank,
                failure_type=payload.failure_type,
                status="ACTIVE",
                spike_rate=payload.spike_rate,
                started_at=datetime.now(timezone.utc),
            )
            db.add(inc)
        else:
            inc.status = "ACTIVE"
            inc.spike_rate = payload.spike_rate
    else:
        if inc:
            inc.status = "RESOLVED"
            inc.resolved_at = datetime.now(timezone.utc)

    db.commit()
    return {
        "status": "SUCCESS",
        "incident_active": payload.active,
        "provider": payload.provider_or_bank,
    }
