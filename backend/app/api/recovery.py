import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from backend.app.database.session import get_db
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.transaction import Transaction
from backend.app.models.customer import Customer
from backend.app.models.payment_failure import PaymentFailure
from backend.app.schemas.common import (
    PaginatedResponse,
    PaginationMetadata,
    TransactionStatusEnum,
    FailureTypeEnum,
    RecoveryActionTypeEnum,
)
from backend.app.schemas.recovery import (
    RecoveryCaseResponse,
    AIRecommendationResponse,
    RecoveryExecuteRequest,
    RecoveryExecuteResponse,
)
from backend.app.schemas.batch import BatchRunRequest, BatchRunSummary
from backend.app.schemas.audit import AuditEventResponse
from backend.app.services.recovery_service import recovery_service
from backend.app.services.batch_recovery_service import batch_recovery_service
from backend.app.audit.audit_service import audit_service

router = APIRouter(prefix="/recovery-cases", tags=["Recovery Cases"])
batch_router = APIRouter(prefix="/recovery", tags=["Batch Recovery"])

@router.get("", response_model=list[RecoveryCaseResponse])
def list_recovery_cases(
    status: Optional[TransactionStatusEnum] = Query(None, description="Filter by transaction status"),
    failure_type: Optional[FailureTypeEnum] = Query(None, description="Filter by failure type"),
    action_type: Optional[RecoveryActionTypeEnum] = Query(None, description="Filter by recommended action"),
    payment_method: Optional[str] = Query(None, description="Filter by payment method"),
    min_probability: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum recovery probability"),
    max_probability: Optional[float] = Query(None, ge=0.0, le=1.0, description="Maximum recovery probability"),
    search: Optional[str] = Query(None, description="Search by transaction ID, customer ID, or customer name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = Query("priority_score", description="Sort field (priority_score, created_at, revenue_at_risk)"),
    sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    db: Session = Depends(get_db),
):
    """
    Lists recovery cases with rich filtering, search, and priority sorting.
    """
    query = (
        db.query(RecoveryCase)
        .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
        .join(Customer, Customer.id == Transaction.customer_id)
        .outerjoin(PaymentFailure, PaymentFailure.transaction_id == Transaction.id)
        .options(
            joinedload(RecoveryCase.transaction).joinedload(Transaction.customer),
            joinedload(RecoveryCase.transaction).joinedload(Transaction.payment_failure),
            joinedload(RecoveryCase.actions),
        )
    )

    if status:
        query = query.filter(RecoveryCase.status == status.value)

    if payment_method:
        query = query.filter(Transaction.payment_method == payment_method)

    if failure_type:
        query = query.filter(PaymentFailure.normalized_failure_type == failure_type.value)

    if min_probability is not None:
        query = query.filter(RecoveryCase.recovery_probability >= min_probability)

    if max_probability is not None:
        query = query.filter(RecoveryCase.recovery_probability <= max_probability)

    if search:
        s = f"%{search}%"
        query = query.filter(
            (Transaction.external_id.ilike(s)) |
            (Customer.external_id.ilike(s)) |
            (Customer.name.ilike(s))
        )

    # Sorting
    if sort_by == "priority_score":
        order_col = RecoveryCase.priority_score
    elif sort_by == "revenue_at_risk":
        order_col = RecoveryCase.revenue_at_risk
    else:
        order_col = RecoveryCase.created_at

    if sort_order.lower() == "asc":
        query = query.order_by((Transaction.external_id == "TX-DEMO-001").desc(), order_col.asc())
    else:
        query = query.order_by((Transaction.external_id == "TX-DEMO-001").desc(), order_col.desc())

    offset = (page - 1) * page_size
    cases = query.offset(offset).limit(page_size).all()
    return cases

@router.get("/{case_id}", response_model=RecoveryCaseResponse)
def get_recovery_case(case_id: str, db: Session = Depends(get_db)):
    """
    Retrieves detailed case context including customer health, transaction failure, and attempts.
    """
    case = (
        db.query(RecoveryCase)
        .options(
            joinedload(RecoveryCase.transaction).joinedload(Transaction.customer),
            joinedload(RecoveryCase.transaction).joinedload(Transaction.payment_failure),
            joinedload(RecoveryCase.actions),
        )
        .filter((RecoveryCase.id == case_id) | (RecoveryCase.recovery_case_id == case_id))
        .first()
    )
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Recovery case '{case_id}' was not found.",
                    "details": {"case_id": case_id},
                }
            },
        )
    return case

@router.post("/{case_id}/recommend", response_model=AIRecommendationResponse)
def get_ai_recommendation(
    case_id: str,
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
):
    """
    Generates structured AI recommendation combining root cause intelligence, ML probability, and safety context.
    Does NOT execute payment actions.
    """
    correlation_id = x_correlation_id or f"corr-rec-{uuid.uuid4().hex[:8]}"
    return recovery_service.get_recommendation(db, case_id, correlation_id=correlation_id)

@router.post("/{case_id}/execute", response_model=RecoveryExecuteResponse)
def execute_recovery_action(
    case_id: str,
    payload: RecoveryExecuteRequest = RecoveryExecuteRequest(),
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
):
    """
    Executes recovery intervention strictly through deterministic Policy Guardrail Engine and Gateway Simulator.
    Supports repeat-safe Idempotency-Key header.
    """
    correlation_id = x_correlation_id or f"corr-exec-{uuid.uuid4().hex[:8]}"
    return recovery_service.execute_recovery(
        db=db,
        case_id=case_id,
        action_type_override=payload.action_type,
        override_reason=payload.override_reason,
        idempotency_key_header=idempotency_key_header,
        correlation_id=correlation_id,
    )

@router.get("/{case_id}/audit", response_model=list[AuditEventResponse])
def get_case_audit_trail(case_id: str, db: Session = Depends(get_db)):
    """
    Retrieves chronological, integrity-verifiable audit events for the specific recovery case.
    """
    return audit_service.get_case_audit_trail(db, case_id)

@router.post("/batch-run", response_model=BatchRunSummary)
def run_batch_recovery_cases(
    payload: BatchRunRequest = BatchRunRequest(),
    db: Session = Depends(get_db),
):
    """
    Runs deterministic batch recovery across eligible failed payment cases.
    """
    return batch_recovery_service.run_batch(db, payload)

@batch_router.post("/batch-run", response_model=BatchRunSummary)
def run_batch_recovery(
    payload: BatchRunRequest = BatchRunRequest(),
    db: Session = Depends(get_db),
):
    """
    Runs deterministic batch recovery across eligible failed payment cases.
    """
    return batch_recovery_service.run_batch(db, payload)

@batch_router.get("/batch-history", response_model=list[BatchRunSummary])
def get_batch_history(db: Session = Depends(get_db)):
    """
    Retrieves execution history of past batch runs.
    """
    return batch_recovery_service.get_history(db)

@batch_router.get("/batches", response_model=list[BatchRunSummary])
def list_batches(db: Session = Depends(get_db)):
    """
    Lists persisted batch recovery runs, sorted newest first.
    """
    return batch_recovery_service.get_history(db)

@batch_router.get("/batches/{batch_id}", response_model=BatchRunSummary)
def get_batch_by_id(batch_id: str, db: Session = Depends(get_db)):
    """
    Retrieves details for a specific batch run.
    """
    rec = batch_recovery_service.get_batch_record(batch_id, db)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch {batch_id} not found")
    return rec["summary"]

