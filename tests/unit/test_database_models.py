import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from backend.app.database.session import SessionLocal, Base, engine
from backend.app.models.customer import Customer
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.audit_event import AuditEvent
from backend.app.models.incident import SystemicIncident
from backend.app.models.notification import NotificationLog
from backend.app.schemas.common import TransactionStatusEnum, FailureTypeEnum, RecoveryActionTypeEnum

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_customer_creation_and_constraints():
    db = SessionLocal()
    cust = Customer(
        external_id="CUST-TEST-01",
        name="Test Customer",
        email="test@example.com",
        phone="+919876543210",
        historical_success_rate=0.85,
        total_transaction_value=15000.0,
        successful_payment_count=10,
        failed_payment_count=2,
    )
    db.add(cust)
    db.commit()

    saved = db.query(Customer).filter(Customer.external_id == "CUST-TEST-01").first()
    assert saved is not None
    assert saved.name == "Test Customer"
    assert saved.subscription_status == "ACTIVE"
    db.close()

def test_transaction_creation_and_positive_amount():
    db = SessionLocal()
    cust = Customer(external_id="CUST-TX-01", name="Tx User", historical_success_rate=0.9)
    db.add(cust)
    db.flush()

    tx = Transaction(
        external_id="TX-TEST-001",
        customer_id=cust.id,
        amount=5000.0,
        currency="INR",
        payment_method="CARD",
        status=TransactionStatusEnum.FAILED.value,
        correlation_id="corr-tx-01",
    )
    db.add(tx)
    db.commit()

    saved_tx = db.query(Transaction).filter(Transaction.external_id == "TX-TEST-001").first()
    assert saved_tx is not None
    assert saved_tx.amount == 5000.0
    assert saved_tx.customer.name == "Tx User"
    db.close()

def test_one_recovery_case_per_transaction_invariant():
    db = SessionLocal()
    cust = Customer(external_id="CUST-DUP-01", name="Dup User")
    db.add(cust)
    db.flush()

    tx = Transaction(
        external_id="TX-DUP-001",
        customer_id=cust.id,
        amount=10000.0,
        currency="INR",
        payment_method="UPI",
        status=TransactionStatusEnum.FAILED.value,
    )
    db.add(tx)
    db.flush()

    # Case 1
    case1 = RecoveryCase(
        transaction_id=tx.id,
        revenue_at_risk=10000.0,
        recovery_probability=0.75,
        risk_score=0.25,
        priority_score=7500.0,
        expected_recovery=7500.0,
        confidence=0.8,
        status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    db.add(case1)
    db.commit()

    # Case 2 on SAME transaction -> Must fail unique constraint
    case2 = RecoveryCase(
        transaction_id=tx.id,
        revenue_at_risk=10000.0,
        recovery_probability=0.75,
        risk_score=0.25,
        priority_score=7500.0,
        expected_recovery=7500.0,
        confidence=0.8,
        status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    db.add(case2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()

def test_recovery_action_sequence_and_idempotency_uniqueness():
    db = SessionLocal()
    cust = Customer(external_id="CUST-ACT-01", name="Action User")
    db.add(cust)
    db.flush()

    tx = Transaction(
        external_id="TX-ACT-001",
        customer_id=cust.id,
        amount=2500.0,
        currency="INR",
        payment_method="CARD",
        status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
    )
    db.add(tx)
    db.flush()

    case = RecoveryCase(
        transaction_id=tx.id,
        revenue_at_risk=2500.0,
        recovery_probability=0.8,
        priority_score=2000.0,
        expected_recovery=2000.0,
        status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
    )
    db.add(case)
    db.flush()

    # Action 1
    action1 = RecoveryAction(
        recovery_case_id=case.id,
        sequence_number=1,
        idempotency_key=f"recovery:{case.id}:1",
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        recommendation_reason="Transient decline",
        confidence=0.85,
        expected_recovery=2000.0,
        policy_version="v1.2.0",
        guardrail_decision="APPROVED",
        status="EXECUTED",
    )
    db.add(action1)
    db.commit()

    # Duplicate idempotency key -> Must fail
    action_dup_key = RecoveryAction(
        recovery_case_id=case.id,
        sequence_number=2,
        idempotency_key=f"recovery:{case.id}:1",  # Same key
        action_type=RecoveryActionTypeEnum.RETRY_PAYMENT.value,
        recommendation_reason="Retry",
        confidence=0.85,
        expected_recovery=2000.0,
        policy_version="v1.2.0",
        guardrail_decision="APPROVED",
        status="EXECUTED",
    )
    db.add(action_dup_key)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Duplicate sequence number -> Must fail
    action_dup_seq = RecoveryAction(
        recovery_case_id=case.id,
        sequence_number=1,  # Same sequence number 1
        idempotency_key=f"recovery:{case.id}:2",
        action_type=RecoveryActionTypeEnum.RETRY_PAYMENT.value,
        recommendation_reason="Retry",
        confidence=0.85,
        expected_recovery=2000.0,
        policy_version="v1.2.0",
        guardrail_decision="APPROVED",
        status="EXECUTED",
    )
    db.add(action_dup_seq)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()

def test_recovery_outcome_baseline_and_agent_separation():
    db = SessionLocal()
    cust = Customer(external_id="CUST-OUT-01", name="Outcome User")
    db.add(cust)
    db.flush()

    tx = Transaction(
        external_id="TX-OUT-001",
        customer_id=cust.id,
        amount=12500.0,
        currency="INR",
        payment_method="CARD",
        status=TransactionStatusEnum.RECOVERED.value,
    )
    db.add(tx)
    db.flush()

    case = RecoveryCase(
        transaction_id=tx.id,
        revenue_at_risk=12500.0,
        recovery_probability=0.87,
        priority_score=12500.0,
        expected_recovery=10875.0,
        status=TransactionStatusEnum.RECOVERED.value,
    )
    db.add(case)
    db.flush()

    action = RecoveryAction(
        recovery_case_id=case.id,
        sequence_number=1,
        idempotency_key=f"recovery:{case.id}:1",
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        recommendation_reason="Demo recovery",
        confidence=0.87,
        expected_recovery=10875.0,
        policy_version="v1.2.0",
        guardrail_decision="APPROVED",
        status="EXECUTED",
    )
    db.add(action)
    db.flush()

    # Agent Recovery Outcome
    agent_outcome = RecoveryOutcome(
        recovery_case_id=case.id,
        recovery_action_id=action.id,
        transaction_id=tx.id,
        outcome_type="AGENT_RECOVERY",
        result="SUCCESS",
        recovered_amount=12500.0,
        baseline_amount=4375.0,
        incremental_amount=8125.0,
        simulator_result="CAPTURED",
    )
    db.add(agent_outcome)
    db.commit()

    saved_out = db.query(RecoveryOutcome).filter(RecoveryOutcome.recovery_action_id == action.id).first()
    assert saved_out is not None
    assert saved_out.outcome_type == "AGENT_RECOVERY"
    assert saved_out.incremental_amount == saved_out.recovered_amount - saved_out.baseline_amount
    db.close()

def test_audit_event_uniqueness():
    db = SessionLocal()
    evt1 = AuditEvent(
        event_id="EVT-UNIQUE-001",
        correlation_id="corr-audit-01",
        entity_type="RECOVERY_CASE",
        entity_id="CASE-1",
        event_type="REVENUE_RISK_DETECTED",
        actor_type="SYSTEM",
        payload={"amount": 5000},
    )
    db.add(evt1)
    db.commit()

    # Duplicate event_id -> Must fail
    evt2 = AuditEvent(
        event_id="EVT-UNIQUE-001",
        correlation_id="corr-audit-02",
        entity_type="RECOVERY_CASE",
        entity_id="CASE-2",
        event_type="ACTION_EXECUTED",
        actor_type="AI_AGENT",
        payload={"amount": 5000},
    )
    db.add(evt2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()

def test_systemic_incident_and_notification_log():
    db = SessionLocal()
    cust = Customer(external_id="CUST-NOTIF-01", name="Notif User")
    db.add(cust)
    db.flush()

    tx = Transaction(
        external_id="TX-NOTIF-001",
        customer_id=cust.id,
        amount=3000.0,
        currency="INR",
        payment_method="CARD",
        status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    db.add(tx)
    db.flush()

    case = RecoveryCase(
        transaction_id=tx.id,
        revenue_at_risk=3000.0,
        recovery_probability=0.7,
        priority_score=2100.0,
        expected_recovery=2100.0,
        status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    db.add(case)
    db.flush()

    # Systemic Incident
    inc = SystemicIncident(
        provider_or_bank="HDFC_BANK",
        failure_type="TEMPORARY_BANK_DECLINE",
        status="ACTIVE",
        spike_rate=0.45,
    )
    db.add(inc)

    # Notification Log
    notif = NotificationLog(
        recovery_case_id=case.id,
        customer_id=cust.id,
        channel="SMS",
        recipient_reference="+919876543210",
        template_id="tpl_delayed_retry",
        idempotency_key="notif:case:1",
    )
    db.add(notif)
    db.commit()

    saved_inc = db.query(SystemicIncident).filter(SystemicIncident.provider_or_bank == "HDFC_BANK").first()
    assert saved_inc is not None
    assert saved_inc.status == "ACTIVE"

    saved_notif = db.query(NotificationLog).filter(NotificationLog.recovery_case_id == case.id).first()
    assert saved_notif is not None
    assert saved_notif.customer.name == "Notif User"
    db.close()
