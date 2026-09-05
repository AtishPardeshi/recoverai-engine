import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.session import SessionLocal, Base, engine
from backend.app.simulator.seed_data import seed_database
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.transaction import Transaction

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db, n_cases=100)
    db.close()
    yield

def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "HEALTHY"

def test_dashboard_summary():
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "recovered_revenue" in data
    assert "revenue_at_risk" in data
    assert "incremental_recovered_revenue" in data
    assert data["total_cases_count"] >= 100

def test_recovery_cases_list_and_filter():
    resp = client.get("/api/recovery-cases?page=1&page_size=10")
    assert resp.status_code == 200
    cases = resp.json()
    assert len(cases) > 0
    # Demo case should be at top or present
    assert any("TX-DEMO-001" in c["transaction"]["external_id"] for c in cases if c["transaction"])

def test_analytics_endpoint():
    resp = client.get("/api/analytics/recovery")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["recovery_by_failure_type"]) > 0
    assert len(data["recovery_by_action"]) > 0
    assert len(data["predicted_vs_actual"]) > 0

def test_activity_feed_endpoint():
    resp = client.get("/api/activity?limit=10")
    assert resp.status_code == 200
    feed = resp.json()
    assert len(feed) > 0
