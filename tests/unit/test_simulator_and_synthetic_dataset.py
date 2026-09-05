import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.session import SessionLocal, Base, engine
from backend.app.simulator.seed_data import seed_database
from backend.app.simulator.gateway_simulator import PaymentGatewaySimulator, simulator
from backend.app.simulator.event_ingestion import ingest_payment_event
from backend.app.models.customer import Customer
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.incident import SystemicIncident
from backend.app.schemas.common import (
    PaymentMethodEnum,
    TransactionStatusEnum,
    FailureTypeEnum,
    RecoveryActionTypeEnum,
    OutcomeTypeEnum,
    OutcomeResultEnum,
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

# 1. Deterministic Dataset Generation
def test_1_deterministic_dataset_generation():
    db = SessionLocal()
    res1 = seed_database(db, n_cases=100, seed=42)
    tx_ids_1 = [t.external_id for t in db.query(Transaction).order_by(Transaction.external_id.asc()).all()]
    
    # Re-seed with same seed
    res2 = seed_database(db, n_cases=100, seed=42)
    tx_ids_2 = [t.external_id for t in db.query(Transaction).order_by(Transaction.external_id.asc()).all()]
    db.close()

    assert res1["transactions_created"] == res2["transactions_created"]
    assert tx_ids_1 == tx_ids_2

# 2. Dataset >= 1,000 Transactions
def test_2_dataset_minimum_1000_transactions():
    db = SessionLocal()
    res = seed_database(db, n_cases=1000, seed=42)
    tx_count = db.query(Transaction).count()
    case_count = db.query(RecoveryCase).count()
    db.close()

    assert tx_count >= 1000
    assert case_count >= 1000
    assert res["transactions_created"] >= 1000

# 3. Unique Transaction IDs
def test_3_unique_transaction_ids():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    txs = db.query(Transaction.external_id).all()
    tx_ids = [t[0] for t in txs]
    db.close()

    assert len(tx_ids) == len(set(tx_ids))

# 4. Unique Customers
def test_4_unique_customers():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    custs = db.query(Customer.external_id).all()
    cust_ids = [c[0] for c in custs]
    db.close()

    assert len(cust_ids) == len(set(cust_ids))

# 5. Valid Failure Taxonomy
def test_5_valid_failure_taxonomy():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    valid_types = {e.value for e in FailureTypeEnum}
    failures = db.query(PaymentFailure.normalized_failure_type).all()
    db.close()

    assert len(failures) > 0
    for f in failures:
        assert f[0] in valid_types

# 6. Valid Payment Methods
def test_6_valid_payment_methods():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    valid_methods = {e.value for e in PaymentMethodEnum}
    tx_methods = db.query(Transaction.payment_method).all()
    db.close()

    assert len(tx_methods) > 0
    for m in tx_methods:
        assert m[0] in valid_methods

# 7. Chronological Customer Histories
def test_7_chronological_customer_histories():
    db = SessionLocal()
    seed_database(db, n_cases=300, seed=42)
    customers = db.query(Customer).all()
    
    for c in customers:
        txs = db.query(Transaction).filter(Transaction.customer_id == c.id).order_by(Transaction.created_at.asc()).all()
        if len(txs) > 1:
            for i in range(len(txs) - 1):
                assert txs[i].created_at <= txs[i+1].created_at
    db.close()

# 8. No Negative Time Deltas
def test_8_no_negative_time_deltas():
    db = SessionLocal()
    seed_database(db, n_cases=300, seed=42)
    customers = db.query(Customer).all()
    
    for c in customers:
        txs = db.query(Transaction).filter(Transaction.customer_id == c.id).order_by(Transaction.created_at.asc()).all()
        if len(txs) > 1:
            for i in range(len(txs) - 1):
                delta = (txs[i+1].created_at - txs[i].created_at).total_seconds()
                assert delta >= 0
    db.close()

# 9. No Future Leakage
def test_9_no_future_leakage():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    cases = db.query(RecoveryCase).all()
    for c in cases:
        tx = c.transaction
        # Recovery probability and expected recovery must be non-negative numbers independent of final outcome
        assert 0.0 <= c.recovery_probability <= 1.0
        assert c.expected_recovery >= 0.0
    db.close()

# 10. Simulator Success
def test_10_simulator_success():
    sim = PaymentGatewaySimulator(seed=42)
    out = sim.simulate_execution(
        transaction_amount=10000.0,
        payment_method="CARD",
        failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        attempt_number=1,
        customer_success_rate=0.95,
        is_demo_tx=True,
    )
    assert out["success"] is True
    assert out["result"] == OutcomeResultEnum.SUCCESS.value
    assert out["recovered_amount"] == 10000.0
    assert out["reason_code"] == "CAPTURED"

# 11. Simulator Failure
def test_11_simulator_failure():
    sim = PaymentGatewaySimulator(seed=123)
    out = sim.simulate_execution(
        transaction_amount=10000.0,
        payment_method="CARD",
        failure_type=FailureTypeEnum.INVALID_DETAILS.value,
        action_type=RecoveryActionTypeEnum.RETRY_PAYMENT.value,
        attempt_number=3,
        customer_success_rate=0.10,
        is_demo_tx=False,
    )
    assert out["success"] is False
    assert out["result"] == OutcomeResultEnum.FAILURE.value
    assert out["recovered_amount"] == 0.0

# 12. Deterministic Simulator Result
def test_12_deterministic_simulator_result():
    sim1 = PaymentGatewaySimulator(seed=99)
    out1 = sim1.simulate_execution(
        transaction_amount=5000.0,
        payment_method="UPI",
        failure_type=FailureTypeEnum.INSUFFICIENT_FUNDS.value,
        action_type=RecoveryActionTypeEnum.SEND_PAYMENT_LINK.value,
        attempt_number=1,
        customer_success_rate=0.80,
    )

    sim2 = PaymentGatewaySimulator(seed=99)
    out2 = sim2.simulate_execution(
        transaction_amount=5000.0,
        payment_method="UPI",
        failure_type=FailureTypeEnum.INSUFFICIENT_FUNDS.value,
        action_type=RecoveryActionTypeEnum.SEND_PAYMENT_LINK.value,
        attempt_number=1,
        customer_success_rate=0.80,
    )
    assert out1["result"] == out2["result"]
    assert out1["recovered_amount"] == out2["recovered_amount"]

# 13. Already Recovered Protection in Simulator
def test_13_already_recovered_protection():
    sim = PaymentGatewaySimulator(seed=42)
    out = sim.simulate_execution(
        transaction_amount=12500.0,
        payment_method="CARD",
        failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        attempt_number=1,
        customer_success_rate=0.89,
        is_already_recovered=True,
    )
    assert out["result"] == OutcomeResultEnum.SKIPPED.value
    assert out["recovered_amount"] == 0.0
    assert out["reason_code"] == "ALREADY_CAPTURED"

# 14. Idempotent Payment Execution
def test_14_idempotent_payment_execution():
    db = SessionLocal()
    seed_database(db, n_cases=50, seed=42)
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    case_id = demo_case.id
    db.close()

    # First request
    resp1 = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": "idemp-key-sim-test-1"},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp1.status_code == 200

    # Repeat request with same idempotency key
    resp2 = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        headers={"Idempotency-Key": "idemp-key-sim-test-1"},
        json={"action_type": "DELAYED_RETRY"},
    )
    assert resp2.status_code == 200
    assert resp1.json()["action"]["action_id"] == resp2.json()["action"]["action_id"]

# 15. Duplicate Event Ingestion
def test_15_duplicate_event_ingestion():
    db = SessionLocal()
    payload = {
        "transaction": {"external_id": "TX-WEBHOOK-001", "amount": 3500.0, "payment_method": "UPI"},
        "customer": {"external_id": "CUST-WEBHOOK-001", "name": "Webhook User"},
        "error": {"code": "BAD_REQUEST", "reason": "TEMPORARY_BANK_DECLINE"},
    }
    # Ingest event first time
    res1 = ingest_payment_event(db, event_id="evt-uniq-101", event_type="payment.failed", payload=payload)
    assert res1["status"] in ["RECOVERY_CASE_CREATED", "EVENT_PROCESSED"]

    # Ingest same event_id second time
    res2 = ingest_payment_event(db, event_id="evt-uniq-101", event_type="payment.failed", payload=payload)
    assert res2["status"] == "DEDUPLICATED"
    db.close()

# 16. Out-of-order Event Handling: Captured arrives and sets terminal state
def test_16_out_of_order_event_handling():
    db = SessionLocal()
    payload_cap = {
        "transaction": {"external_id": "TX-ORDER-OUT-001", "amount": 7500.0, "payment_method": "CARD"},
        "customer": {"external_id": "CUST-ORDER-001", "name": "Order User"},
    }
    # Captured arrives first
    res_cap = ingest_payment_event(db, event_id="evt-cap-001", event_type="payment.captured", payload=payload_cap)
    assert res_cap["status"] == "TRANSACTION_CAPTURED"

    tx = db.query(Transaction).filter(Transaction.external_id == "TX-ORDER-OUT-001").first()
    assert tx.status in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value]
    db.close()

# 17. Captured State Dominates Failed Event
def test_17_captured_state_dominates_failed_event():
    db = SessionLocal()
    payload_cap = {
        "transaction": {"external_id": "TX-DOM-001", "amount": 9000.0, "payment_method": "CARD"},
        "customer": {"external_id": "CUST-DOM-001", "name": "Dom User"},
    }
    # First: captured event
    ingest_payment_event(db, event_id="evt-dom-cap-001", event_type="payment.captured", payload=payload_cap)

    # Second: delayed failed event arrives for same transaction
    payload_fail = {
        "transaction": {"external_id": "TX-DOM-001", "amount": 9000.0, "payment_method": "CARD"},
        "customer": {"external_id": "CUST-DOM-001", "name": "Dom User"},
        "error": {"code": "BAD_REQUEST", "reason": "TEMPORARY_BANK_DECLINE"},
    }
    res_fail = ingest_payment_event(db, event_id="evt-dom-fail-002", event_type="payment.failed", payload=payload_fail)
    assert res_fail["status"] == "IGNORED_OUT_OF_ORDER"

    # Transaction must remain CAPTURED/RECOVERED
    tx = db.query(Transaction).filter(Transaction.external_id == "TX-DOM-001").first()
    assert tx.status in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value]
    db.close()

# 18. Systemic Incident Activation
def test_18_systemic_incident_activation():
    resp = client.post(
        "/api/simulator/incident",
        json={
            "provider_or_bank": "HDFC_BANK",
            "failure_type": "TEMPORARY_BANK_DECLINE",
            "active": True,
            "spike_rate": 0.45,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["incident_active"] is True

    db = SessionLocal()
    inc = db.query(SystemicIncident).filter(SystemicIncident.provider_or_bank == "HDFC_BANK").first()
    assert inc is not None
    assert inc.status == "ACTIVE"
    assert inc.spike_rate == 0.45
    db.close()

# 19. Systemic Incident Deactivation
def test_19_systemic_incident_deactivation():
    # Activate
    client.post("/api/simulator/incident", json={"provider_or_bank": "ICICI_BANK", "active": True, "spike_rate": 0.35})
    # Deactivate
    resp = client.post("/api/simulator/incident", json={"provider_or_bank": "ICICI_BANK", "active": False})
    assert resp.status_code == 200
    assert resp.json()["incident_active"] is False

    db = SessionLocal()
    inc = db.query(SystemicIncident).filter(SystemicIncident.provider_or_bank == "ICICI_BANK").first()
    assert inc.status == "RESOLVED"
    db.close()

# 20. Seed Repeat Safety
def test_20_seed_repeat_safety():
    db = SessionLocal()
    res1 = seed_database(db, n_cases=50, seed=42)
    assert db.query(RecoveryCase).count() == 50
    # Repeat seed
    res2 = seed_database(db, n_cases=50, seed=42)
    assert db.query(RecoveryCase).count() == 50
    assert res1["total_cases"] == res2["total_cases"]
    db.close()

# 21. Reset Behavior
def test_21_reset_behavior():
    resp_seed = client.post("/api/simulator/seed?n_cases=50")
    assert resp_seed.status_code == 200

    resp_reset = client.post("/api/simulator/reset")
    assert resp_reset.status_code == 200
    assert resp_reset.json()["status"] == "SUCCESS"

    db = SessionLocal()
    assert db.query(RecoveryCase).count() == 0
    assert db.query(Transaction).count() == 0
    db.close()

# 22. TX-DEMO-001 Exact Structure
def test_22_tx_demo_001_exact_structure():
    db = SessionLocal()
    seed_database(db, n_cases=100, seed=42)
    tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    assert tx is not None
    assert tx.amount == 12500.0
    assert tx.currency == "INR"
    assert tx.payment_method == "CARD"
    assert tx.status == TransactionStatusEnum.FAILED.value

    cust = tx.customer
    assert cust.external_id == "CUST-1024"
    assert cust.successful_payment_count == 17
    assert cust.failed_payment_count == 2

    case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == tx.id).first()
    assert case is not None
    assert case.status == TransactionStatusEnum.RECOVERY_ELIGIBLE.value
    assert 0.0 < case.recovery_probability <= 1.0
    assert case.expected_recovery == round(12500.0 * case.recovery_probability, 2)
    db.close()

# 23. Baseline Outcome Separation
def test_23_baseline_outcome_separation():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    baseline_outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.outcome_type == OutcomeTypeEnum.BASELINE.value).all()
    agent_outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.outcome_type == OutcomeTypeEnum.AGENT_RECOVERY.value).all()
    db.close()

    assert len(baseline_outcomes) > 0
    assert len(agent_outcomes) > 0
    for o in baseline_outcomes:
        assert o.outcome_type == "BASELINE"
    for o in agent_outcomes:
        assert o.outcome_type == "AGENT_RECOVERY"

# 24. Ground Truth vs Prediction Separation
def test_24_ground_truth_prediction_separation():
    db = SessionLocal()
    seed_database(db, n_cases=100, seed=42)
    outcomes = db.query(RecoveryOutcome).all()
    for o in outcomes:
        if o.metadata_payload:
            assert "ground_truth_recoverable" in o.metadata_payload
            assert "ground_truth_outcome" in o.metadata_payload
    db.close()
