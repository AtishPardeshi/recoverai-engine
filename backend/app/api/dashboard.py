from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.database.session import get_db
from backend.app.schemas.dashboard import DashboardSummaryResponse
from backend.app.services.analytics_service import analytics_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    batch_id: str | None = Query(None, description="Optional batch ID to scope summary metrics to"),
    scope: str | None = Query(None, description="Scope filter ('CURRENT_BATCH' or 'CUMULATIVE')"),
    db: Session = Depends(get_db),
):
    """
    Returns financial KPI metrics calculated directly from database records, scoped to current batch or cumulative DB.
    """
    return analytics_service.get_dashboard_summary(db, batch_id=batch_id, scope=scope)
