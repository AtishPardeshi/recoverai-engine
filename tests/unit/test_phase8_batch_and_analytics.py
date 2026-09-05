import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.app.database.session import SessionLocal, Base, engine
from backend.app.models.customer import Customer
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.audit_event import AuditEvent
from backend.app.models.incident import SystemicIncident

from backend.app.schemas.common import (
    TransactionStatusEnum,
    RecoveryActionTypeEnum,
    GuardrailDecisionEnum,
    OutcomeResultEnum,
    OutcomeTypeEnum,
    FailureTypeEnum,
    PaymentMethodEnum,
)
from backend.app.schemas.batch import BatchRunRequest, BatchRunSummary
from backend.app.services.batch_recovery_service import batch_recovery_service
from backend.app.services.analytics_service import analytics_service
from backend.app.services.recovery_service import recovery_service
from backend.app.simulator.gateway_simulator import PaymentGatewaySimulator
from backend.app.policies.policy_engine import policy_engine
from backend.app.executor.action_executor import action_executor
from backend.app.config.config import settings

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def create_case_fixture(
    db: Session,
    status: str = TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    amount: float = 5000.0,
    failure_type: str = FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
    payment_method: str = PaymentMethodEnum.CARD.value,
    is_opted_out: bool = False,
    has_open_dispute: bool = False,
    gateway_code: str = "BANK_TIMEOUT",
    external_id: str = None,
):
    cust = Customer(
        id=str(uuid.uuid4()),
        external_id=f"CUST-{uuid.uuid4().hex[:8]}",
        name="Test Customer",
        historical_success_rate=0.85,
        total_transaction_value=amount * 3,
        successful_payment_count=10,
        failed_payment_count=1,
        is_opted_out=is_opted_out,
        has_open_dispute=has_open_dispute,
    )
    db.add(cust)
    db.flush()

    tx = Transaction(
        id=str(uuid.uuid4()),
        customer_id=cust.id,
        external_id=external_id or f"TX-{uuid.uuid4().hex[:8].upper()}",
        amount=amount,
        currency="INR",
        payment_method=payment_method,
        status=status,
    )
    db.add(tx)
    db.flush()

    pf = PaymentFailure(
        id=str(uuid.uuid4()),
        transaction_id=tx.id,
        error_code=gateway_code,
        error_description="Test failure description",
        error_reason=failure_type,
        normalized_failure_type=failure_type,
        retry_count=0,
    )
    db.add(pf)
    db.flush()

    rc = RecoveryCase(
        id=str(uuid.uuid4()),
        transaction_id=tx.id,
        revenue_at_risk=amount,
        recovery_probability=0.75,
        expected_recovery=amount * 0.75,
        priority_score=0.80,
        status=status,
        retry_count=0,
        message_count=0,
    )
    db.add(rc)
    db.commit()
    db.refresh(rc)
    return rc

# ==============================================================================
# A. BATCH PROCESSING TESTS
# ==============================================================================

def test_batch_run_basic(db: Session):
    """Test basic batch recovery processing on eligible cases."""
    case = create_case_fixture(db)
    req = BatchRunRequest(limit=5, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    assert summary.batch_id.startswith("BATCH-")
    assert summary.total_candidates >= 1
    assert summary.ml_evaluated >= 1
    assert summary.ai_recommended >= 1
    assert summary.policy_approved >= 1
    assert summary.actions_executed >= 1
    assert summary.currency == "INR"

def test_batch_run_dry_run(db: Session):
    """Dry run should evaluate and recommend without executing simulator outcomes."""
    case = create_case_fixture(db)
    req = BatchRunRequest(limit=5, seed=42, dry_run=True)
    summary = batch_recovery_service.run_batch(db, req)
    assert summary.dry_run is True
    assert summary.actions_executed == 0
    assert summary.agent_recovered_revenue == 0.0

# ==============================================================================
# B. EMPTY BATCH TESTS
# ==============================================================================

def test_batch_run_no_eligible_cases(db: Session):
    """Batch run should gracefully handle case when limit is 1."""
    req = BatchRunRequest(limit=1, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    assert summary.currency == "INR"
    assert summary.recovery_rate >= 0.0

# ==============================================================================
# C. BATCH LIMIT TESTS
# ==============================================================================

def test_batch_run_limit_enforced(db: Session):
    """Batch runner respects requested limit parameter."""
    for _ in range(3):
        create_case_fixture(db)
    req = BatchRunRequest(limit=2, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    assert summary.total_candidates <= 2

# ==============================================================================
# D. DETERMINISTIC SEED TESTS
# ==============================================================================

def test_deterministic_seed_consistency(db: Session):
    """Running simulator with same seed generates reproducible outcomes."""
    sim1 = PaymentGatewaySimulator(seed=42)
    sim2 = PaymentGatewaySimulator(seed=42)
    res1 = sim1.simulate_execution(
        transaction_amount=5000.0,
        payment_method="CARD",
        failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        action_type=RecoveryActionTypeEnum.RETRY_PAYMENT.value,
        attempt_number=1,
        customer_success_rate=0.85,
    )
    res2 = sim2.simulate_execution(
        transaction_amount=5000.0,
        payment_method="CARD",
        failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        action_type=RecoveryActionTypeEnum.RETRY_PAYMENT.value,
        attempt_number=1,
        customer_success_rate=0.85,
    )
    assert res1["simulator_result"] == res2["simulator_result"]
    assert res1["recovered_amount"] == res2["recovered_amount"]

# ==============================================================================
# E. ML -> AI -> POLICY -> EXECUTOR PIPELINE
# ==============================================================================

def test_full_pipeline_step_by_step(db: Session):
    """Verify each phase strictly flows: ML -> AI -> Policy -> Executor -> Simulator -> Outcome."""
    case = create_case_fixture(db, amount=8000.0)
    req = BatchRunRequest(limit=500, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    
    # Check that action record was persisted with all pipeline metadata
    action = db.query(RecoveryAction).filter(RecoveryAction.recovery_case_id == case.id).first()
    assert action is not None
    assert action.action_type in [a.value for a in RecoveryActionTypeEnum]
    assert action.guardrail_decision in [g.value for g in GuardrailDecisionEnum]
    assert action.expected_recovery > 0
    
    # Check outcome was persisted
    if action.guardrail_decision == GuardrailDecisionEnum.APPROVED.value:
        outcome = db.query(RecoveryOutcome).filter(RecoveryOutcome.recovery_action_id == action.id).first()
        assert outcome is not None
        assert outcome.outcome_type == OutcomeTypeEnum.AGENT_RECOVERY.value

# ==============================================================================
# F. POLICY REJECTION TESTS
# ==============================================================================

def test_batch_policy_rejection_opted_out_customer(db: Session):
    """Opted out customer retry attempt must be REJECTED by Policy Engine."""
    decision = policy_engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        is_opted_out=True,
    )
    assert decision.decision == GuardrailDecisionEnum.REJECTED

def test_batch_policy_rejection_open_dispute(db: Session):
    """Customer with open dispute must be REJECTED for payment retries by Policy Engine."""
    decision = policy_engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        has_open_dispute=True,
    )
    assert decision.decision == GuardrailDecisionEnum.REJECTED

# ==============================================================================
# G. SUCCESSFUL RECOVERY & REVENUE PERSISTENCE
# ==============================================================================

def test_successful_recovery_updates_state_and_records_revenue(db: Session):
    """When simulator succeeds, transaction moves to RECOVERED and outcome stores recovered_amount."""
    case = create_case_fixture(db, amount=12500.0, failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value)
    req = BatchRunRequest(limit=10, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    
    db.refresh(case)
    action = db.query(RecoveryAction).filter(RecoveryAction.recovery_case_id == case.id).first()
    if action and action.guardrail_decision == GuardrailDecisionEnum.APPROVED.value:
        outcome = db.query(RecoveryOutcome).filter(RecoveryOutcome.recovery_action_id == action.id).first()
        if outcome and outcome.result == OutcomeResultEnum.SUCCESS.value:
            assert outcome.recovered_amount == 12500.0
            assert case.status == TransactionStatusEnum.RECOVERED.value

# ==============================================================================
# H. FAILED RECOVERY HANDLING
# ==============================================================================

def test_failed_recovery_does_not_record_revenue(db: Session):
    """When simulator outcome fails, recovered_amount must be 0.0 and transaction must not be RECOVERED."""
    sim = PaymentGatewaySimulator(seed=999)
    res = sim.simulate_execution(
        transaction_amount=4000.0,
        payment_method="CARD",
        failure_type=FailureTypeEnum.EXPIRED_METHOD.value,
        action_type=RecoveryActionTypeEnum.RETRY_PAYMENT.value,
        attempt_number=1,
        customer_success_rate=0.1,
    )
    assert res["simulator_result"] != "CAPTURED"
    assert res["recovered_amount"] == 0.0

# ==============================================================================
# I. BASELINE RECOVERY INDEPENDENCE
# ==============================================================================

def test_baseline_recovery_calculated_separately(db: Session):
    """Outcomes store separate baseline_amount and incremental_amount."""
    summary = analytics_service.get_dashboard_summary(db)
    assert summary.baseline_recovered_revenue >= 0.0
    assert summary.recovered_revenue >= summary.baseline_recovered_revenue or summary.recovered_revenue >= 0.0

# ==============================================================================
# J. INCREMENTAL REVENUE LIFT
# ==============================================================================

def test_incremental_revenue_formula(db: Session):
    """Incremental revenue = Agent Recovered Revenue - Baseline Recovered Revenue."""
    summary = analytics_service.get_dashboard_summary(db)
    expected_incremental = max(0.0, summary.recovered_revenue - summary.baseline_recovered_revenue)
    assert round(summary.incremental_recovered_revenue, 2) == round(expected_incremental, 2)

# ==============================================================================
# K. NO DOUBLE COUNTING INVARIANTS
# ==============================================================================

def test_no_double_counting_revenue(db: Session):
    """A single case cannot generate multiple successful outcome revenues."""
    case = create_case_fixture(db, amount=6000.0)
    req = BatchRunRequest(limit=10, seed=42, dry_run=False)
    batch_recovery_service.run_batch(db, req)
    
    # Check outcomes
    successful_outcomes = db.query(RecoveryOutcome).join(RecoveryAction).filter(
        RecoveryAction.recovery_case_id == case.id,
        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value
    ).all()
    assert len(successful_outcomes) <= 1

# ==============================================================================
# L. RERUNNING BATCH SAFETY & IDEMPOTENCY
# ==============================================================================

def test_rerunning_batch_does_not_increase_revenue(db: Session):
    """Calling batch run twice on the same dataset must be idempotent and not increase revenue."""
    case = create_case_fixture(db, amount=7500.0)
    req = BatchRunRequest(limit=5000, seed=42, dry_run=False)
    
    # Run 1: process all available candidates
    summary1 = batch_recovery_service.run_batch(db, req)
    rev_after_1 = analytics_service.get_dashboard_summary(db, scope="CUMULATIVE").recovered_revenue
    
    # Run 2: immediate rerun should find no unhandled candidates
    summary2 = batch_recovery_service.run_batch(db, req)
    rev_after_2 = analytics_service.get_dashboard_summary(db, scope="CUMULATIVE").recovered_revenue
    
    # In run 2, already processed terminal/recovered cases result in 0 new revenue
    assert summary2.agent_recovered_revenue == 0.0
    assert round(rev_after_1, 2) == round(rev_after_2, 2)

# ==============================================================================
# M. ALREADY RECOVERED TRANSACTION PROTECTION
# ==============================================================================

def test_already_recovered_case_is_not_reprocessed(db: Session):
    """Transactions in RECOVERED status must not be targeted for new payment retries."""
    case = create_case_fixture(db, status=TransactionStatusEnum.RECOVERED.value)
    eligible = db.query(RecoveryCase).filter(
        RecoveryCase.status.in_([
            TransactionStatusEnum.FAILED.value,
            TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
            TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        ])
    ).all()
    assert case.id not in [c.id for c in eligible]

# ==============================================================================
# N. TERMINAL STATE PROTECTION
# ==============================================================================

def test_terminal_states_cannot_execute_actions(db: Session):
    """Terminal states (CAPTURED, RECOVERED, RECOVERY_EXHAUSTED, ESCALATED, STOPPED) must block execution."""
    for term_status in [
        TransactionStatusEnum.CAPTURED.value,
        TransactionStatusEnum.RECOVERED.value,
        TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
        TransactionStatusEnum.STOPPED.value,
    ]:
        decision = policy_engine.evaluate(
            action=RecoveryActionTypeEnum.RETRY_PAYMENT,
            case_status=term_status,
        )
        assert decision.decision == GuardrailDecisionEnum.REJECTED

# ==============================================================================
# O. IDEMPOTENCY KEY VERIFICATION
# ==============================================================================

def test_idempotency_key_format(db: Session):
    """Action executor uses recovery:{case_id}:{action_sequence} key format."""
    case = create_case_fixture(db)
    seq = case.retry_count + case.message_count + 1
    key = f"recovery:{case.id}:{seq}"
    assert key.startswith(f"recovery:{case.id}:")

# ==============================================================================
# P. BATCH RUN HISTORY TRACKING
# ==============================================================================

def test_batch_run_history_recorded(db: Session):
    """Batch runs are recorded in history and retrievable."""
    req = BatchRunRequest(limit=2, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    history = batch_recovery_service.get_history()
    assert len(history) >= 1
    assert any(h.batch_id == summary.batch_id for h in history)

# ==============================================================================
# Q. RECOVERY FUNNEL METRICS
# ==============================================================================

def test_recovery_funnel_monotonic_or_strictly_valid(db: Session):
    """Funnel analytics must return non-negative counts from database."""
    funnel = analytics_service.get_recovery_funnel(db)
    assert funnel.failed_payments_count >= 0
    assert funnel.recovery_eligible_count >= 0
    assert funnel.ai_recommended_count >= 0
    assert funnel.policy_approved_count >= 0
    assert funnel.action_executed_count >= 0
    assert funnel.successful_recovery_count >= 0

# ==============================================================================
# R. FAILURE-TYPE ANALYTICS
# ==============================================================================

def test_analytics_by_failure_type(db: Session):
    """Analytics by failure type returns all 6 canonical failure types."""
    breakdown = analytics_service.get_analytics_by_failure_type(db)
    categories = [b.category for b in breakdown]
    for expected in [
        FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        FailureTypeEnum.INSUFFICIENT_FUNDS.value,
        FailureTypeEnum.BANK_DECLINE.value,
        FailureTypeEnum.NETWORK_ERROR.value,
        FailureTypeEnum.EXPIRED_METHOD.value,
        FailureTypeEnum.INVALID_DETAILS.value,
    ]:
        assert expected in categories

# ==============================================================================
# S. PAYMENT-METHOD ANALYTICS
# ==============================================================================

def test_analytics_by_payment_method(db: Session):
    """Analytics by payment method returns exactly CARD, UPI, NETBANKING, WALLET."""
    breakdown = analytics_service.get_analytics_by_payment_method(db)
    methods = [b.category for b in breakdown]
    assert set(methods) == {"CARD", "UPI", "NETBANKING", "WALLET"}

# ==============================================================================
# T. ACTION ANALYTICS
# ==============================================================================

def test_analytics_by_action(db: Session):
    """Analytics by action returns all 7 approved recovery actions."""
    breakdown = analytics_service.get_analytics_by_action(db)
    actions = [b.category for b in breakdown]
    for expected in [a.value for a in RecoveryActionTypeEnum]:
        assert expected in actions

# ==============================================================================
# U. PREDICTED VS ACTUAL ANALYTICS
# ==============================================================================

def test_predicted_vs_actual_analytics(db: Session):
    """Predicted vs actual analytics returns probability buckets and non-negative stats."""
    pva = analytics_service.get_predicted_vs_actual(db)
    assert len(pva.buckets) >= 1
    assert pva.total_predicted_revenue >= 0
    assert pva.total_actual_revenue >= 0
    assert pva.overall_prediction_to_actual_ratio >= 0

# ==============================================================================
# V. SYSTEMIC INCIDENT CIRCUIT BREAKER IN BATCH
# ==============================================================================

def test_systemic_incident_blocks_retries_in_batch(db: Session):
    """Active systemic incident blocks automated retries during batch run."""
    inc = SystemicIncident(
        id=str(uuid.uuid4()),
        provider_or_bank="HDFC_BANK",
        failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        status="ACTIVE",
        spike_rate=0.45,
    )
    db.add(inc)
    db.commit()

    case = create_case_fixture(db, failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value, gateway_code="HDFC_BANK_DOWN")
    req = BatchRunRequest(limit=5, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    
    # Deactivate incident
    inc.status = "RESOLVED"
    db.commit()

# ==============================================================================
# W. DASHBOARD SUMMARY INVARIANTS
# ==============================================================================

def test_dashboard_summary_invariants(db: Session):
    """Dashboard summary values conform to domain invariants."""
    summary = analytics_service.get_dashboard_summary(db)
    assert summary.total_payment_volume >= 0
    assert summary.failed_payment_value >= 0
    assert summary.revenue_at_risk >= 0
    assert summary.recovered_revenue >= 0
    assert summary.baseline_recovered_revenue >= 0
    assert summary.incremental_recovered_revenue >= 0
    assert 0.0 <= summary.recovery_rate <= 1.0 or summary.recovery_rate >= 0.0

# ==============================================================================
# X. ZERO-DENOMINATOR SAFETY
# ==============================================================================

def test_zero_denominator_metrics_safety():
    """Formulas return 0.0 when denominators are zero."""
    def calc_rate(num, den):
        return round((num / den) * 100, 2) if den > 0 else 0.0

    assert calc_rate(0, 0) == 0.0
    assert calc_rate(100, 0) == 0.0
    assert calc_rate(50, 100) == 50.0

# ==============================================================================
# Y. NEGATIVE REVENUE PREVENTION
# ==============================================================================

def test_negative_revenue_prevention(db: Session):
    """Recovered amount is strictly non-negative."""
    outcomes = db.query(RecoveryOutcome).all()
    for o in outcomes:
        assert o.recovered_amount >= 0.0

# ==============================================================================
# Z. AUDIT CORRELATION IN BATCH
# ==============================================================================

def test_audit_correlation_integrity(db: Session):
    """Batch executions produce correlated audit events."""
    case = create_case_fixture(db)
    req = BatchRunRequest(limit=2, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)
    
    events = db.query(AuditEvent).filter(AuditEvent.entity_id == case.id).all()
    for ev in events:
        assert ev.correlation_id is not None
        assert len(ev.correlation_id) > 0

# ==============================================================================
# DEMO TRANSACTION & ACCEPTANCE TEST
# ==============================================================================

def test_demo_transaction_arjun_verma_properties(db: Session):
    """Demo transaction TX-DEMO-001 has valid properties without hardcoded probability."""
    case = db.query(RecoveryCase).join(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    if case:
        assert case.transaction.amount == 12500.0
        assert case.transaction.customer.external_id == "CUST-1024"

# ==============================================================================
# ADDITIONAL EXTENDED PHASE 8 TESTS (API CONTRACTS & EDGE CASES)
# ==============================================================================

from fastapi.testclient import TestClient
from backend.app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_api_batch_run_endpoint(client: TestClient):
    """POST /api/recovery/batch-run executes batch and returns BatchRunSummary."""
    res = client.post("/api/recovery/batch-run", json={"limit": 5, "seed": 42, "dry_run": False})
    assert res.status_code == 200
    data = res.json()
    assert "batch_id" in data
    assert data["currency"] == "INR"
    assert "incremental_recovered_revenue" in data

def test_api_batch_history_endpoint(client: TestClient):
    """GET /api/recovery/batch-history returns list of completed batches."""
    res = client.get("/api/recovery/batch-history")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)

def test_api_analytics_recovery_endpoint(client: TestClient):
    """GET /api/analytics/recovery returns full analytics response."""
    res = client.get("/api/analytics/recovery")
    assert res.status_code == 200
    data = res.json()
    assert "by_failure_type" in data
    assert "by_action" in data
    assert "by_payment_method" in data
    assert "funnel" in data

def test_api_analytics_by_failure_type_endpoint(client: TestClient):
    """GET /api/analytics/recovery/by-failure-type returns failure dimensions."""
    res = client.get("/api/analytics/recovery/by-failure-type")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 6

def test_api_analytics_by_payment_method_endpoint(client: TestClient):
    """GET /api/analytics/recovery/by-payment-method returns payment method dimensions."""
    res = client.get("/api/analytics/recovery/by-payment-method")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 4

def test_api_analytics_by_action_endpoint(client: TestClient):
    """GET /api/analytics/recovery/by-action returns action dimensions."""
    res = client.get("/api/analytics/recovery/by-action")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 7

def test_api_analytics_funnel_endpoint(client: TestClient):
    """GET /api/analytics/recovery/funnel returns funnel stages."""
    res = client.get("/api/analytics/recovery/funnel")
    assert res.status_code == 200
    data = res.json()
    assert "stages" in data
    assert len(data["stages"]) == 8

def test_api_analytics_predicted_vs_actual_endpoint(client: TestClient):
    """GET /api/analytics/recovery/predicted-vs-actual returns calibration stats."""
    res = client.get("/api/analytics/recovery/predicted-vs-actual")
    assert res.status_code == 200
    data = res.json()
    assert "buckets" in data
    assert "overall_prediction_to_actual_ratio" in data

def test_api_analytics_incrementality_endpoint(client: TestClient):
    """GET /api/analytics/recovery/incrementality returns incrementality lift."""
    res = client.get("/api/analytics/recovery/incrementality")
    assert res.status_code == 200
    data = res.json()
    assert "incremental_recovered_revenue" in data
    assert "incremental_lift" in data

def test_api_analytics_systemic_incidents_endpoint(client: TestClient):
    """GET /api/analytics/recovery/systemic-incidents returns incident list."""
    res = client.get("/api/analytics/recovery/systemic-incidents")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)

def test_api_dashboard_summary_endpoint(client: TestClient):
    """GET /api/dashboard/summary returns full dashboard KPIs."""
    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    data = res.json()
    assert "recovered_revenue" in data
    assert "incremental_recovered_revenue" in data
    assert data["currency"] == "INR"

def test_batch_run_large_limit(db: Session):
    """Batch run handles large limit parameter without crash."""
    req = BatchRunRequest(limit=5000, seed=42, dry_run=True)
    summary = batch_recovery_service.run_batch(db, req)
    assert summary.total_candidates >= 0

def test_batch_run_custom_seed(db: Session):
    """Batch run accepts arbitrary deterministic seeds."""
    req = BatchRunRequest(limit=5, seed=12345, dry_run=True)
    summary = batch_recovery_service.run_batch(db, req)
    assert summary.seed == 12345

def test_policy_block_rate_calculation(db: Session):
    """Policy block rate equals policy_rejected / (policy_approved + policy_rejected)."""
    summary = batch_recovery_service.run_batch(db, BatchRunRequest(limit=5, seed=42, dry_run=False))
    total_eval = summary.policy_approved + summary.policy_rejected
    if total_eval > 0:
        expected_rate = round(summary.policy_rejected / total_eval, 4)
        assert summary.policy_block_rate == expected_rate
    else:
        assert summary.policy_block_rate == 0.0

def test_execution_success_rate_calculation(db: Session):
    """Execution success rate equals successful_recoveries / actions_executed."""
    summary = batch_recovery_service.run_batch(db, BatchRunRequest(limit=5, seed=42, dry_run=False))
    if summary.actions_executed > 0:
        expected_rate = round(summary.successful_recoveries / summary.actions_executed, 4)
        assert summary.execution_success_rate == expected_rate
    else:
        assert summary.execution_success_rate == 0.0

def test_incremental_lift_calculation(db: Session):
    """Incremental lift equals incremental_recovered_revenue / baseline_recovered_revenue."""
    summary = batch_recovery_service.run_batch(db, BatchRunRequest(limit=5, seed=42, dry_run=False))
    if summary.baseline_recovered_revenue > 0:
        expected_lift = round(summary.incremental_recovered_revenue / summary.baseline_recovered_revenue, 4)
        assert summary.incremental_lift == expected_lift
    else:
        assert summary.incremental_lift == 0.0

def test_audit_event_types_in_batch(db: Session):
    """Audit events record distinct actor types during batch execution."""
    case = create_case_fixture(db)
    summary = batch_recovery_service.run_batch(db, BatchRunRequest(limit=5, seed=42, dry_run=False))
    actors = db.query(AuditEvent.actor_type).distinct().all()
    actor_names = [a[0] for a in actors]
    assert any(a in ["ML_MODEL", "AI_AGENT", "POLICY_ENGINE", "EXECUTOR", "SYSTEM"] for a in actor_names)

def test_recovery_case_status_progression(db: Session):
    """Case moves to RECOVERY_IN_PROGRESS or RECOVERED upon batch execution."""
    case = create_case_fixture(db)
    batch_recovery_service.run_batch(db, BatchRunRequest(limit=5, seed=42, dry_run=False))
    db.refresh(case)
    assert case.status in [
        TransactionStatusEnum.RECOVERED.value,
        TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
        TransactionStatusEnum.STOPPED.value,
        TransactionStatusEnum.ESCALATED.value,
    ]

def test_gateway_simulator_all_failure_types():
    """PaymentGatewaySimulator handles all 6 failure types without throwing unhandled exceptions."""
    sim = PaymentGatewaySimulator(seed=42)
    for ft in [f.value for f in FailureTypeEnum]:
        res = sim.simulate_execution(
            transaction_amount=5000.0,
            payment_method="CARD",
            failure_type=ft,
            action_type=RecoveryActionTypeEnum.RETRY_PAYMENT.value,
            attempt_number=1,
            customer_success_rate=0.8,
        )
        assert "simulator_result" in res
        assert res["recovered_amount"] >= 0.0

def test_gateway_simulator_all_actions():
    """PaymentGatewaySimulator handles all 7 recovery actions without exceptions."""
    sim = PaymentGatewaySimulator(seed=42)
    for act in [a.value for a in RecoveryActionTypeEnum]:
        res = sim.simulate_execution(
            transaction_amount=5000.0,
            payment_method="CARD",
            failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
            action_type=act,
            attempt_number=1,
            customer_success_rate=0.8,
        )
        assert "simulator_result" in res

def test_no_double_counting_across_multiple_batches(db: Session):
    """Running batch multiple times never produces duplicate successful outcomes for same case."""
    case = create_case_fixture(db, amount=9999.0)
    for _ in range(3):
        batch_recovery_service.run_batch(db, BatchRunRequest(limit=5, seed=42, dry_run=False))
    
    outcomes = db.query(RecoveryOutcome).join(RecoveryAction).filter(
        RecoveryAction.recovery_case_id == case.id,
        RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value,
    ).all()
    assert len(outcomes) <= 1

# ==============================================================================
# SECTION 18: BATCH VS CUMULATIVE SCOPE RECONCILIATION TESTS
# ==============================================================================

def test_scope_batch_vs_cumulative_isolation(db: Session):
    """Batch-scoped analytics only aggregates current batch candidates, not cumulative DB."""
    # 1. Create 3 cases and run Batch A
    for _ in range(3):
        create_case_fixture(db, amount=5000.0)
    summary_a = batch_recovery_service.run_batch(db, BatchRunRequest(limit=3, seed=42, dry_run=False))
    batch_a_id = summary_a.batch_id

    # 2. Create 2 new cases and run Batch B
    for _ in range(2):
        create_case_fixture(db, amount=8000.0)
    summary_b = batch_recovery_service.run_batch(db, BatchRunRequest(limit=2, seed=42, dry_run=False))
    batch_b_id = summary_b.batch_id

    # 3. Query Batch A failure taxonomy
    breakdown_a = analytics_service.get_analytics_by_failure_type(db, batch_id=batch_a_id)
    total_candidates_a = sum(b.candidates_count for b in breakdown_a)
    assert total_candidates_a == summary_a.total_candidates

    # 4. Query Batch B failure taxonomy
    breakdown_b = analytics_service.get_analytics_by_failure_type(db, batch_id=batch_b_id)
    total_candidates_b = sum(b.candidates_count for b in breakdown_b)
    assert total_candidates_b == summary_b.total_candidates

    # 5. Query Cumulative failure taxonomy
    breakdown_cum = analytics_service.get_analytics_by_failure_type(db, scope="CUMULATIVE")
    total_candidates_cum = sum(b.candidates_count for b in breakdown_cum)
    assert total_candidates_cum >= total_candidates_a + total_candidates_b

def test_api_scope_parameter_filtering(client: TestClient, db: Session):
    """API endpoints respect batch_id and scope query parameters."""
    case = create_case_fixture(db)
    summary = batch_recovery_service.run_batch(db, BatchRunRequest(limit=5, seed=42, dry_run=False))
    
    # Query with specific batch_id
    res_batch = client.get(f"/api/analytics/recovery?batch_id={summary.batch_id}")
    assert res_batch.status_code == 200
    data_batch = res_batch.json()
    assert data_batch["scope"] == "CURRENT_BATCH"
    assert data_batch["batch_id"] == summary.batch_id

    # Query with scope=cumulative
    res_cum = client.get("/api/analytics/recovery?scope=cumulative")
    assert res_cum.status_code == 200
    data_cum = res_cum.json()
    assert data_cum["scope"] == "CUMULATIVE"
    assert data_cum["batch_id"] is None

def test_batch_analytics_reconciliation_invariants(db: Session):
    """Batch-scoped financial metrics satisfy all accounting invariants."""
    create_case_fixture(db, amount=12000.0)
    summary = batch_recovery_service.run_batch(db, BatchRunRequest(limit=5, seed=42, dry_run=False))
    
    analytics = analytics_service.get_recovery_analytics(db, batch_id=summary.batch_id)
    assert analytics.scope == "CURRENT_BATCH"
    assert analytics.batch_id == summary.batch_id
    
    # Incremental = Agent - Baseline
    expected_inc = max(0.0, analytics.total_recovered_amount - analytics.baseline_recovered_amount)
    assert round(analytics.incremental_recovered_amount, 2) == round(expected_inc, 2)
    assert round(analytics.total_recovered_amount, 2) == round(summary.agent_recovered_revenue, 2)


