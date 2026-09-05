import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.session import SessionLocal, Base, engine
from backend.app.simulator.seed_data import seed_database
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.transaction import Transaction
from backend.app.models.customer import Customer
from backend.app.models.recovery_action import RecoveryAction
from backend.app.schemas.common import (
    TransactionStatusEnum,
    FailureTypeEnum,
    RecoveryActionTypeEnum,
    GuardrailDecisionEnum,
    OutcomeResultEnum,
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_and_seed_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db, n_cases=100)
    finally:
        db.close()
    yield

# 1. Dashboard Summary
def test_1_dashboard_summary():
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["currency"] == "INR"
    assert "metrics" in data
    m = data["metrics"]
    assert "total_payment_volume" in m
    assert "failed_payment_value" in m
    assert "revenue_at_risk" in m
    assert "recovery_eligible" in m
    assert "intervention_value" in m
    assert "recovered_revenue" in m
    assert "incremental_recovered_revenue" in m
    assert "recovery_rate" in m
    assert "active_cases" in m
    assert "successful_recoveries" in m
    assert "total_attempts" in m
    assert "guardrail_compliance_rate" in m
    assert "average_recovery_probability" in m
    assert isinstance(m["total_payment_volume"], (int, float))
    assert 0.0 <= m["recovery_rate"] <= 1.0

# 2. Recovery Case List
def test_2_recovery_case_list():
    resp = client.get("/api/recovery-cases?page=1&page_size=20")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) > 0
    first = items[0]
    assert "id" in first
    assert "recovery_case_id" in first
    assert "revenue_at_risk" in first
    assert "recovery_probability" in first
    assert "priority_score" in first
    assert "status" in first
    assert "transaction" in first
    assert first["transaction"] is not None

# 3. Recovery Case Detail & TX-DEMO-001 Verification
def test_3_recovery_case_detail_demo():
    # Find demo case
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    assert demo_tx is not None
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    assert demo_case is not None
    case_id = demo_case.id
    db.close()

    resp = client.get(f"/api/recovery-cases/{case_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == case_id
    assert data["transaction"]["external_id"] == "TX-DEMO-001"
    assert data["transaction"]["amount"] == 12500.0
    assert data["transaction"]["payment_method"] == "CARD"
    assert 0.0 < data["recovery_probability"] <= 1.0

# 4. Recommendation Endpoint
def test_4_recommendation_endpoint():
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    case_id = demo_case.id
    db.close()

    resp = client.post(f"/api/recovery-cases/{case_id}/recommend")
    assert resp.status_code == 200
    data = resp.json()
    assert data["recovery_case_id"] == case_id
    assert "recommendation" in data
    rec = data["recommendation"]
    assert rec["recommended_action"] == "DELAYED_RETRY"
    assert "confidence" in rec
    assert rec["expected_recovery"] > 10000.0
    assert "ml" in data
    assert 0.0 < data["ml"]["recovery_probability"] <= 1.0

# 5. Recommendation Does NOT Execute Action
def test_5_recommendation_does_not_execute():
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    case_id = demo_case.id
    initial_actions_count = db.query(RecoveryAction).filter(RecoveryAction.recovery_case_id == case_id).count()
    db.close()

    # Call recommend
    resp = client.post(f"/api/recovery-cases/{case_id}/recommend")
    assert resp.status_code == 200

    # Verify state remains unexecuted in DB
    db = SessionLocal()
    case = db.query(RecoveryCase).filter(RecoveryCase.id == case_id).first()
    tx = db.query(Transaction).filter(Transaction.id == case.transaction_id).first()
    actions_count = db.query(RecoveryAction).filter(RecoveryAction.recovery_case_id == case_id).count()
    db.close()

    assert case.status == TransactionStatusEnum.RECOVERY_ELIGIBLE.value
    assert tx.status == TransactionStatusEnum.FAILED.value
    assert actions_count == initial_actions_count

# 6. Execute Endpoint
def test_6_execute_endpoint():
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    case_id = demo_case.id
    db.close()

    resp = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": "test-key-demo-exec-1"},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["recovery_case_id"] == case_id
    assert data["policy"]["approved"] is True
    assert data["action"]["status"] == "EXECUTED"
    assert data["outcome"]["outcome_status"] == "SUCCESS"
    assert data["outcome"]["recovered_amount"] == 12500.0
    assert data["transaction_state"] == "RECOVERED"

# 7. Policy Rejection
def test_7_policy_rejection():
    # Create an opted-out customer and case
    db = SessionLocal()
    cust = Customer(
        id=str(uuid.uuid4()),
        external_id="CUST-OPTED-OUT",
        name="Opted Out User",
        historical_success_rate=0.5,
        total_transaction_value=5000.0,
        successful_payment_count=1,
        failed_payment_count=1,
        is_opted_out=True,
        has_open_dispute=False,
    )
    db.add(cust)
    db.flush()
    tx = Transaction(
        id=str(uuid.uuid4()),
        external_id="TX-OPTED-OUT",
        customer_id=cust.id,
        amount=5000.0,
        currency="INR",
        payment_method="CARD",
        status=TransactionStatusEnum.FAILED.value,
    )
    db.add(tx)
    db.flush()
    case = RecoveryCase(
        id=str(uuid.uuid4()),
        transaction_id=tx.id,
        revenue_at_risk=5000.0,
        recovery_probability=0.5,
        expected_recovery=2500.0,
        priority_score=2500.0,
        status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    db.add(case)
    db.commit()
    case_id = case.id
    db.close()

    resp = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": "test-key-optout-1"},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["policy"]["approved"] is False
    assert "opted out" in data["policy"]["reason_code"]
    assert data["action"]["status"] == "REJECTED"
    assert data["outcome"] is None

# 8. Already Recovered Protection
def test_8_already_recovered_protection():
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    case_id = demo_case.id
    db.close()

    # First execution succeeds
    resp1 = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": "key-exec-first"},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["transaction_state"] == "RECOVERED"

    # Subsequent execution with a new idempotency key on recovered case gets blocked by terminal policy
    resp2 = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": "key-exec-second"},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["policy"]["approved"] is False
    assert "terminal case" in data2["policy"]["reason_code"]

# 9. Duplicate Idempotency Key
def test_9_duplicate_idempotency_key():
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    case_id = demo_case.id
    db.close()

    key = "repeat-safe-key-12345"
    resp1 = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": key},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp1.status_code == 200
    d1 = resp1.json()

    # Re-send identical request with same key
    resp2 = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": key},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d1["action"]["action_id"] == d2["action"]["action_id"]
    assert d1["outcome"]["recovered_amount"] == d2["outcome"]["recovered_amount"]

# 10. Conflicting Idempotency Key
def test_10_conflicting_idempotency_key():
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    case_id = demo_case.id
    db.close()

    key = "conflict-test-key-999"
    # First request
    resp1 = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": key},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp1.status_code == 200

    # Conflicting request: same key, different action
    resp2 = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": key},
        json={"action_type": "SEND_PAYMENT_LINK"},
    )
    assert resp2.status_code == 409
    data = resp2.json()
    assert data["error"]["code"] == "IDEMPOTENCY_CONFLICT"

# 11. Audit Endpoint
def test_11_audit_endpoint():
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    case_id = demo_case.id
    db.close()

    resp = client.get(f"/api/recovery-cases/{case_id}/audit")
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)
    assert len(events) >= 1
    first = events[0]
    assert "event_id" in first
    assert "correlation_id" in first
    assert "entity_id" in first
    assert "event_type" in first
    assert "actor_type" in first

# 12. Analytics Endpoint
def test_12_analytics_endpoint():
    resp = client.get("/api/analytics/recovery")
    assert resp.status_code == 200
    data = resp.json()
    assert data["currency"] == "INR"
    assert "by_action" in data
    assert "by_failure_type" in data
    assert "by_payment_method" in data
    assert "incrementality" in data
    assert "predicted_vs_actual" in data
    inc = data["incrementality"]
    assert "baseline_recovery" in inc
    assert "agent_recovery" in inc
    assert "incremental_recovery" in inc

# 13. Activity Endpoint
def test_13_activity_endpoint():
    resp = client.get("/api/activity?limit=25")
    assert resp.status_code == 200
    feed = resp.json()
    assert isinstance(feed, list)
    assert len(feed) > 0
    item = feed[0]
    assert "id" in item
    assert "event_type" in item
    assert "title" in item
    assert "description" in item
    assert "status" in item
    assert "timestamp" in item
    assert "correlation_id" in item

# 14. Simulator Reset
def test_14_simulator_reset():
    resp = client.post("/api/simulator/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    # Verify tables are clean
    db = SessionLocal()
    assert db.query(RecoveryCase).count() == 0
    db.close()

# 15. Simulator Seed
def test_15_simulator_seed():
    resp = client.post("/api/simulator/seed?n_cases=50")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert "details" in data
    details = data["details"]
    assert details["transactions_created"] >= 50
    assert details["recovery_cases_created"] == 50
    assert details["demo_case_id"] == "TX-DEMO-001"
    assert details["seed_version"] == "v1.0.0"

# 16. Invalid Enum Validation
def test_16_invalid_enum():
    resp = client.get("/api/recovery-cases?status=INVALID_STATUS_VALUE")
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in data["error"]

# 17. Invalid Pagination
def test_17_invalid_pagination():
    # Page must be >= 1
    resp1 = client.get("/api/recovery-cases?page=0")
    assert resp1.status_code == 422
    assert resp1.json()["error"]["code"] == "VALIDATION_ERROR"

    # Page size > 200
    resp2 = client.get("/api/recovery-cases?page_size=500")
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "VALIDATION_ERROR"

# 18. Missing Recovery Case
def test_18_missing_recovery_case():
    resp = client.get("/api/recovery-cases/non-existent-case-id-12345")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "not found" in data["error"]["message"]

# 19. Correlation ID Propagation
def test_19_correlation_id_propagation():
    custom_corr_id = "corr-test-custom-12345678"
    resp = client.get("/api/dashboard/summary", headers={"X-Correlation-ID": custom_corr_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Correlation-ID") == custom_corr_id

# 20. Common Error Response Shape
def test_20_common_error_response_shape():
    resp = client.get("/api/recovery-cases/missing-case-id")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    err = body["error"]
    assert "code" in err
    assert "message" in err
    assert "details" in err
    assert "correlation_id" in err
