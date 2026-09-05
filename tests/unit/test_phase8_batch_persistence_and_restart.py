import uuid
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.database.session import SessionLocal, Base, engine
from backend.app.main import app
from backend.app.models.batch_run import BatchRun
from backend.app.models.customer import Customer
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.schemas.common import TransactionStatusEnum, FailureTypeEnum, PaymentMethodEnum
from backend.app.schemas.batch import BatchRunRequest
from backend.app.services.batch_recovery_service import BatchRecoveryService, batch_recovery_service
from backend.app.services.analytics_service import AnalyticsService, analytics_service

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client():
    return TestClient(app)

def test_batch_run_persists_to_database_and_survives_restart(db: Session):
    """
    SECTION 6 RESTART TEST:
    1. Run batch.
    2. Persist BatchRun in database.
    3. Clear in-memory service state.
    4. Recreate analytics service.
    5. Query the same batch.
    6. Verify CURRENT_BATCH analytics still work from database.
    """
    # 1. Create candidate cases
    created_cases = []
    for i in range(3):
        cust = Customer(
            id=str(uuid.uuid4()),
            external_id=f"CUST-PERSIST-{uuid.uuid4().hex[:8]}",
            name=f"Persist Customer {i}",
            historical_success_rate=0.85,
            total_transaction_value=30000.0,
            successful_payment_count=8,
            failed_payment_count=1,
            is_opted_out=False,
            has_open_dispute=False,
        )
        db.add(cust)
        db.flush()

        tx = Transaction(
            id=str(uuid.uuid4()),
            customer_id=cust.id,
            external_id=f"TX-PERSIST-{uuid.uuid4().hex[:8].upper()}",
            amount=8000.0,
            currency="INR",
            payment_method=PaymentMethodEnum.CARD.value,
            status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        )
        db.add(tx)
        db.flush()

        pf = PaymentFailure(
            id=str(uuid.uuid4()),
            transaction_id=tx.id,
            error_code="BANK_THROTTLED",
            error_description="Gateway timeout",
            error_reason=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
            normalized_failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
            retry_count=0,
        )
        db.add(pf)
        db.flush()

        rc = RecoveryCase(
            id=str(uuid.uuid4()),
            transaction_id=tx.id,
            revenue_at_risk=8000.0,
            recovery_probability=0.80,
            expected_recovery=6400.0,
            priority_score=0.85,
            status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
            retry_count=0,
            message_count=0,
        )
        db.add(rc)
        created_cases.append(rc)
    db.commit()

    # 2. Run batch recovery
    req = BatchRunRequest(limit=3, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    batch_id = summary.batch_id

    # 3. Verify BatchRun is persisted in DB
    db_batch = db.query(BatchRun).filter(BatchRun.batch_id == batch_id).first()
    assert db_batch is not None
    assert db_batch.status == "COMPLETED"
    assert db_batch.total_candidates == summary.total_candidates
    assert round(db_batch.agent_recovered_revenue, 2) == round(summary.agent_recovered_revenue, 2)

    # 4. SIMULATE SERVICE RESTART: Wipe in-memory caches completely
    batch_recovery_service.history.clear()
    batch_recovery_service.batch_records.clear()
    assert len(batch_recovery_service.history) == 0
    assert len(batch_recovery_service.batch_records) == 0

    # 5. Create fresh AnalyticsService instance (zero in-memory state)
    fresh_analytics = AnalyticsService()
    fresh_summary = fresh_analytics.get_dashboard_summary(db, batch_id=batch_id, scope="CURRENT_BATCH")

    # 6. Verify CURRENT_BATCH analytics still resolves flawlessly from DB persistence
    assert fresh_summary.scope == "CURRENT_BATCH"
    assert fresh_summary.batch_id == batch_id
    assert fresh_summary.total_cases_count == summary.total_candidates
    assert round(fresh_summary.recovered_revenue, 2) == round(summary.agent_recovered_revenue, 2)
    assert round(fresh_summary.incremental_recovered_revenue, 2) == round(summary.incremental_recovered_revenue, 2)

    # Breakdown queries also resolve correctly
    ft = fresh_analytics.get_analytics_by_failure_type(db, batch_id=batch_id, scope="CURRENT_BATCH")
    assert sum(x.candidates_count for x in ft) == summary.total_candidates

def test_batch_history_and_by_id_api_endpoints(client: TestClient, db: Session):
    """
    SECTION 7 BATCH HISTORY API TEST:
    Tests GET /api/recovery/batches and GET /api/recovery/batches/{batch_id}
    """
    # 1. Run batch to ensure at least one batch exists
    req = BatchRunRequest(limit=2, seed=42, dry_run=False)
    batch_recovery_service.run_batch(db, req)

    # 2. Test GET /api/recovery/batches
    res = client.get("/api/recovery/batches")
    assert res.status_code == 200
    batches = res.json()
    assert isinstance(batches, list)
    assert len(batches) >= 1
    latest_batch = batches[0]
    assert "batch_id" in latest_batch
    assert "agent_recovered_revenue" in latest_batch
    assert "status" in latest_batch

    # 3. Test GET /api/recovery/batches/{batch_id}
    batch_id = latest_batch["batch_id"]
    res_single = client.get(f"/api/recovery/batches/{batch_id}")
    assert res_single.status_code == 200
    single_batch = res_single.json()
    assert single_batch["batch_id"] == batch_id
    assert single_batch["status"] == "COMPLETED"

    # 4. Test 404 on non-existent batch
    res_404 = client.get("/api/recovery/batches/NON-EXISTENT-BATCH")
    assert res_404.status_code == 404
