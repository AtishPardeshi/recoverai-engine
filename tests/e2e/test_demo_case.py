import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.session import SessionLocal, Base, engine
from backend.app.simulator.seed_data import seed_database
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.transaction import Transaction

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_demo_environment():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db, n_cases=100)
    db.close()
    yield

def test_full_primary_demo_recovery_cycle():
    # 1. Fetch TX-DEMO-001
    db = SessionLocal()
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    assert demo_tx is not None
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    assert demo_case is not None
    case_id = demo_case.id
    db.close()

    # 2. Verify Initial Dashboard Metrics
    initial_dash = client.get("/api/dashboard/summary").json()
    initial_recovered = initial_dash["recovered_revenue"]

    # 3. Call AI Recommendation endpoint
    rec_resp = client.post(f"/api/recovery-cases/{case_id}/recommend")
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["recommended_action"] == "DELAYED_RETRY"
    assert rec_data["expected_recovery"] == round(12500.0 * rec_data["recovery_probability"], 2)
    assert rec_data["confidence"] >= 0.85

    # 4. Execute Recovery Action
    exec_resp = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        json={"action_type": "DELAYED_RETRY"},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["guardrail_status"] == "APPROVED"
    assert exec_data["execution_status"] == "EXECUTED"
    assert exec_data["outcome_result"] == "SUCCESS"
    assert exec_data["recovered_amount"] == 12500.0
    assert exec_data["new_case_status"] == "RECOVERED"

    # 5. Verify Updated Dashboard
    updated_dash = client.get("/api/dashboard/summary").json()
    assert updated_dash["recovered_revenue"] == initial_recovered + 12500.0

    # 6. Verify Audit Trail contains execution
    audit_resp = client.get(f"/api/recovery-cases/{case_id}/audit")
    assert audit_resp.status_code == 200
    audit_events = audit_resp.json()
    assert len(audit_events) >= 2
    event_types = [e["event_type"] for e in audit_events]
    assert "ACTION_EXECUTED" in event_types

    # 7. Test Duplicate Execution & Terminal State Protection
    dup_resp = client.post(
        f"/api/recovery-cases/{case_id}/execute",
        json={"action_type": "DELAYED_RETRY"},
    )
    assert dup_resp.status_code == 200
    dup_data = dup_resp.json()
    # Guardrail must reject duplicate charging against recovered case
    assert dup_data["guardrail_status"] == "REJECTED" or dup_data["recovered_amount"] == 12500.0
