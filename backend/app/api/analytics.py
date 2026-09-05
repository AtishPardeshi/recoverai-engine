from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.database.session import get_db
from backend.app.schemas.analytics import (
    AnalyticsResponse,
    RecoveryByDimension,
    PredictedVsActualSummary,
    IncrementalitySummary,
    RecoveryFunnelResponse,
    SystemicIncidentAnalytics,
)
from backend.app.schemas.audit import ActivityFeedItem
from backend.app.services.analytics_service import analytics_service
from backend.app.audit.audit_service import audit_service

router = APIRouter(tags=["Analytics & Activity"])


@router.get("/analytics/recovery", response_model=AnalyticsResponse)
def get_recovery_analytics(
    batch_id: str | None = Query(None, description="Optional batch ID to scope analytics to"),
    scope: str | None = Query(None, description="Scope filter ('CURRENT_BATCH' or 'CUMULATIVE')"),
    db: Session = Depends(get_db),
):
    """
    Returns comprehensive recovery performance metrics, incrementality, funnel, and breakdowns.
    """
    return analytics_service.get_recovery_analytics(db, batch_id=batch_id, scope=scope)


@router.get("/analytics/recovery/by-failure-type", response_model=list[RecoveryByDimension])
def get_analytics_by_failure_type(
    batch_id: str | None = Query(None, description="Optional batch ID to scope analytics to"),
    scope: str | None = Query(None, description="Scope filter ('CURRENT_BATCH' or 'CUMULATIVE')"),
    db: Session = Depends(get_db),
):
    """
    Returns recovery performance metrics grouped by failure type.
    """
    return analytics_service.get_analytics_by_failure_type(db, batch_id=batch_id, scope=scope)


@router.get("/analytics/recovery/by-payment-method", response_model=list[RecoveryByDimension])
def get_analytics_by_payment_method(
    batch_id: str | None = Query(None, description="Optional batch ID to scope analytics to"),
    scope: str | None = Query(None, description="Scope filter ('CURRENT_BATCH' or 'CUMULATIVE')"),
    db: Session = Depends(get_db),
):
    """
    Returns recovery performance metrics grouped by payment method (CARD, UPI, NETBANKING, WALLET).
    """
    return analytics_service.get_analytics_by_payment_method(db, batch_id=batch_id, scope=scope)


@router.get("/analytics/recovery/by-action", response_model=list[RecoveryByDimension])
def get_analytics_by_action(
    batch_id: str | None = Query(None, description="Optional batch ID to scope analytics to"),
    scope: str | None = Query(None, description="Scope filter ('CURRENT_BATCH' or 'CUMULATIVE')"),
    db: Session = Depends(get_db),
):
    """
    Returns recovery performance metrics grouped by recovery action type.
    """
    return analytics_service.get_analytics_by_action(db, batch_id=batch_id, scope=scope)


@router.get("/analytics/recovery/funnel", response_model=RecoveryFunnelResponse)
def get_recovery_funnel(
    batch_id: str | None = Query(None, description="Optional batch ID to scope analytics to"),
    scope: str | None = Query(None, description="Scope filter ('CURRENT_BATCH' or 'CUMULATIVE')"),
    db: Session = Depends(get_db),
):
    """
    Returns closed-loop recovery funnel from failed payments to incremental revenue.
    """
    return analytics_service.get_recovery_funnel(db, batch_id=batch_id, scope=scope)


@router.get("/analytics/recovery/predicted-vs-actual", response_model=PredictedVsActualSummary)
def get_predicted_vs_actual(
    batch_id: str | None = Query(None, description="Optional batch ID to scope analytics to"),
    scope: str | None = Query(None, description="Scope filter ('CURRENT_BATCH' or 'CUMULATIVE')"),
    db: Session = Depends(get_db),
):
    """
    Returns comparison between ML predicted probability / expected recovery and actual recovered revenue.
    """
    return analytics_service.get_predicted_vs_actual(db, batch_id=batch_id, scope=scope)


@router.get("/analytics/recovery/incrementality", response_model=IncrementalitySummary)
def get_incrementality_summary(
    batch_id: str | None = Query(None, description="Optional batch ID to scope analytics to"),
    scope: str | None = Query(None, description="Scope filter ('CURRENT_BATCH' or 'CUMULATIVE')"),
    db: Session = Depends(get_db),
):
    """
    Returns baseline vs agent recovery revenue and calculated incremental lift.
    """
    return analytics_service.get_incrementality_summary(db, batch_id=batch_id, scope=scope)


@router.get("/analytics/recovery/systemic-incidents", response_model=list[SystemicIncidentAnalytics])
def get_systemic_incidents_analytics(db: Session = Depends(get_db)):
    """
    Returns systemic bank/provider incident metrics and blocked retry statistics.
    """
    return analytics_service.get_systemic_incidents_analytics(db)


@router.get("/activity", response_model=list[ActivityFeedItem])
def get_activity_feed(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Returns real-time database-backed activity feed of recovery events.
    """
    return audit_service.get_activity_feed(db, limit=limit)