import uuid
import pytest
from sqlalchemy.orm import Session
from backend.app.database.session import SessionLocal, Base, engine
from backend.app.models.customer import Customer
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.audit_event import AuditEvent

from backend.app.schemas.common import (
    TransactionStatusEnum,
    RecoveryActionTypeEnum,
    GuardrailDecisionEnum,
    OutcomeResultEnum,
    OutcomeTypeEnum,
    FailureTypeEnum,
    PaymentMethodEnum,
)
from backend.app.schemas.batch import BatchRunRequest
from backend.app.services.batch_recovery_service import batch_recovery_service
from backend.app.services.analytics_service import analytics_service
from backend.app.services.recovery_service import recovery_service

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_phase8_end_to_end_closed_loop_recovery_pipeline(db: Session):
    """
    SECTION 31 END-TO-END ACCEPTANCE TEST:
    Proves full lifecycle:
    FAILED PAYMENT -> ML -> AI -> POLICY -> EXECUTOR -> SIMULATOR -> ACTUAL RECOVERY -> DATABASE OUTCOME -> REVENUE ANALYTICS -> DASHBOARD METRIC.
    
    Asserts:
    1. actual recovered revenue == persisted successful outcome revenue
    2. incremental revenue == agent recovery - baseline recovery
    3. rerunning the same batch does NOT change revenue.
    """
    # 1. Create a set of fresh failed transactions representing incoming payment failures
    created_cases = []
    for i in range(5):
        cust = Customer(
            id=str(uuid.uuid4()),
            external_id=f"CUST-E2E-{uuid.uuid4().hex[:8]}",
            name=f"E2E Customer {i}",
            historical_success_rate=0.90,
            total_transaction_value=50000.0,
            successful_payment_count=15,
            failed_payment_count=1,
            is_opted_out=False,
            has_open_dispute=False,
        )
        db.add(cust)
        db.flush()

        tx = Transaction(
            id=str(uuid.uuid4()),
            customer_id=cust.id,
            external_id=f"TX-E2E-{uuid.uuid4().hex[:8].upper()}",
            amount=10000.0,
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
            error_description="Gateway connection throttled temporarily",
            error_reason=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
            normalized_failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
            retry_count=0,
        )
        db.add(pf)
        db.flush()

        rc = RecoveryCase(
            id=str(uuid.uuid4()),
            transaction_id=tx.id,
            revenue_at_risk=10000.0,
            recovery_probability=0.85,
            expected_recovery=8500.0,
            priority_score=0.90,
            status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
            retry_count=0,
            message_count=0,
        )
        db.add(rc)
        created_cases.append(rc)

    db.commit()

    # 2. Run deterministic batch recovery (limit=1000, seed=42)
    req = BatchRunRequest(limit=1000, seed=42, dry_run=False)
    summary1 = batch_recovery_service.run_batch(db, req)

    assert summary1.total_candidates >= 1
    assert summary1.ml_evaluated >= 1
    assert summary1.ai_recommended >= 1
    assert summary1.policy_approved >= 1
    assert summary1.actions_executed >= 1

    # 3. Assert Actual Recovered Revenue matches sum of persisted successful outcome records in DB
    db_successful_agent_outcomes = db.query(RecoveryOutcome).filter(
        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
    ).all()
    total_db_recovered = sum(o.recovered_amount for o in db_successful_agent_outcomes)

    dashboard_summary = analytics_service.get_dashboard_summary(db)

    # Core Equality Assertions:
    # 1. Current batch recovered revenue matches batch summary agent recovered revenue
    assert round(dashboard_summary.recovered_revenue, 2) == round(summary1.agent_recovered_revenue, 2)
    # 2. Cumulative database recovered revenue matches total persisted successful outcomes in DB
    assert round(dashboard_summary.cumulative_recovered_revenue, 2) == round(total_db_recovered, 2)

    # 3. Explicit CUMULATIVE scope returns total DB recovered revenue
    cum_summary = analytics_service.get_dashboard_summary(db, scope="CUMULATIVE")
    assert round(cum_summary.recovered_revenue, 2) == round(total_db_recovered, 2)

    # 4. Assert Incremental Revenue = Agent Recovery - Baseline Recovery
    expected_incremental = max(0.0, dashboard_summary.recovered_revenue - dashboard_summary.baseline_recovered_revenue)
    assert round(dashboard_summary.incremental_recovered_revenue, 2) == round(expected_incremental, 2)

    # 5. Assert Idempotent Rerun: running the same batch again must NOT increase cumulative database revenue
    summary2 = batch_recovery_service.run_batch(db, req)
    dashboard_summary_after_rerun = analytics_service.get_dashboard_summary(db)

    # Cumulative total is unchanged (zero duplicate revenue created)
    assert round(dashboard_summary_after_rerun.cumulative_recovered_revenue, 2) == round(dashboard_summary.cumulative_recovered_revenue, 2)
    assert round(dashboard_summary_after_rerun.cumulative_incremental_recovered_revenue, 2) == round(dashboard_summary.cumulative_incremental_recovered_revenue, 2)
    assert summary2.agent_recovered_revenue == 0.0 or summary2.successful_recoveries == 0

    # Batch 1 analytics remains fully intact and unchanged when queried by batch_id
    batch1_summary = analytics_service.get_dashboard_summary(db, batch_id=summary1.batch_id)
    assert round(batch1_summary.recovered_revenue, 2) == round(summary1.agent_recovered_revenue, 2)
    assert round(batch1_summary.incremental_recovered_revenue, 2) == round(summary1.incremental_recovered_revenue, 2)


