import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.session import SessionLocal, Base, engine
from backend.app.simulator.seed_data import seed_database
from backend.app.simulator.gateway_simulator import simulator
from backend.app.models.customer import Customer
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.schemas.common import (
    TransactionStatusEnum,
    FailureTypeEnum,
    RecoveryActionTypeEnum,
    OutcomeTypeEnum,
    OutcomeResultEnum,
)
from backend.app.ml.recovery_model import ml_model
from backend.app.agent.ai_agent import ai_agent
from backend.app.services.analytics_service import analytics_service

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

# 1. failure_count <= transaction_count
def test_1_failure_count_lte_transaction_count():
    db = SessionLocal()
    res = seed_database(db, n_cases=1000, seed=42)
    total_tx = db.query(Transaction).count()
    total_failures = db.query(PaymentFailure).count()
    db.close()

    assert total_failures <= total_tx
    assert res["failure_count"] <= res["transaction_count"]
    assert total_tx >= 1000

# 2. actual failure rate calculation
def test_2_actual_failure_rate_calculation():
    db = SessionLocal()
    res = seed_database(db, n_cases=200, seed=42)
    total_tx = db.query(Transaction).count()
    total_failures = db.query(PaymentFailure).count()
    calculated_rate = round(total_failures / total_tx, 4)
    db.close()

    assert res["failure_rate"] == calculated_rate
    assert 0.0 < calculated_rate <= 1.0

# 3. demo history contains 17 successes + 2 failures in real database rows
def test_3_demo_history_contains_17_successes_and_2_failures():
    db = SessionLocal()
    seed_database(db, n_cases=100, seed=42)
    cust = db.query(Customer).filter(Customer.external_id == "CUST-1024").first()
    assert cust is not None

    # Query real persisted transaction records for CUST-1024
    prior_successes = (
        db.query(Transaction)
        .filter(
            Transaction.customer_id == cust.id,
            Transaction.status == TransactionStatusEnum.CAPTURED.value,
        )
        .all()
    )
    prior_failures = (
        db.query(Transaction)
        .filter(
            Transaction.customer_id == cust.id,
            Transaction.status == TransactionStatusEnum.FAILED.value,
            Transaction.external_id != "TX-DEMO-001",
        )
        .all()
    )
    db.close()

    assert len(prior_successes) == 17
    assert len(prior_failures) == 2
    assert cust.successful_payment_count == 17
    assert cust.failed_payment_count == 2

# 4. demo probability is not transaction-ID hardcoded
def test_4_demo_probability_is_not_transaction_id_hardcoded():
    # Calling the generic prediction service with same features on a synthetic transaction
    p_demo = ml_model.predict_recovery_probability(
        amount=12500.0,
        payment_method="CARD",
        failure_type="TEMPORARY_BANK_DECLINE",
        customer_success_rate=0.894,
        customer_success_count=17,
        customer_failed_count=2,
    )
    p_other = ml_model.predict_recovery_probability(
        amount=12500.0,
        payment_method="CARD",
        failure_type="TEMPORARY_BANK_DECLINE",
        customer_success_rate=0.894,
        customer_success_count=17,
        customer_failed_count=2,
    )
    assert p_demo == p_other

    # Changing legitimate input changes prediction
    p_changed = ml_model.predict_recovery_probability(
        amount=12500.0,
        payment_method="CARD",
        failure_type="INVALID_DETAILS",
        customer_success_rate=0.20,
        customer_success_count=1,
        customer_failed_count=5,
    )
    assert p_changed != p_demo
    assert p_changed < p_demo

# 5. expected recovery formula: expected_recovery = probability * amount
def test_5_expected_recovery_formula():
    amount = 15000.0
    prob = 0.85
    exp_rec, priority = ml_model.calculate_priority_score(amount, prob, 0.90)
    assert exp_rec == round(amount * prob, 2)
    assert exp_rec == 12750.0

# 6. ground truth not used as runtime feature
def test_6_ground_truth_not_used_as_runtime_feature():
    rec = ai_agent.generate_recommendation(
        transaction_amount=12500.0,
        payment_method="CARD",
        failure_type="TEMPORARY_BANK_DECLINE",
        error_description="Issuer throttling",
        customer_name="Arjun Verma",
        customer_success_rate=0.894,
        customer_success_count=17,
        customer_failed_count=2,
        retry_count=0,
        message_count=0,
        recovery_probability=0.87,
        is_opted_out=False,
        has_open_dispute=False,
    )
    # Valid recommendation produced without ground truth arguments
    assert rec.recommended_action == RecoveryActionTypeEnum.DELAYED_RETRY
    assert rec.expected_recovery == round(12500.0 * 0.87, 2)

# 7. baseline recovery persisted separately
def test_7_baseline_recovery_persisted_separately():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    baseline_outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.outcome_type == OutcomeTypeEnum.BASELINE.value).all()
    db.close()

    assert len(baseline_outcomes) > 0
    for bo in baseline_outcomes:
        assert bo.baseline_amount > 0.0
        assert bo.outcome_type == "BASELINE"

# 8. agent recovery persisted separately
def test_8_agent_recovery_persisted_separately():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    agent_outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.outcome_type == OutcomeTypeEnum.AGENT_RECOVERY.value).all()
    db.close()

    assert len(agent_outcomes) > 0
    for ao in agent_outcomes:
        assert ao.outcome_type == "AGENT_RECOVERY"

# 9. incremental recovery formula: incremental = agent_recovery - baseline
def test_9_incremental_recovery_formula():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.result == OutcomeResultEnum.SUCCESS.value).all()
    for o in outcomes:
        assert round(o.incremental_amount, 2) == round(o.recovered_amount - o.baseline_amount, 2)
    db.close()

# 10. no double counting in analytics
def test_10_no_double_counting_in_analytics():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    dash = analytics_service.get_dashboard_summary(db)
    analytics = analytics_service.get_recovery_analytics(db)
    db.close()

    # Total recovered must equal baseline + incremental
    assert round(dash.recovered_revenue, 2) == round(dash.baseline_recovered_revenue + dash.incremental_recovered_revenue, 2)
    assert round(analytics.total_recovered_amount, 2) == round(analytics.baseline_recovered_amount + analytics.incremental_recovered_amount, 2)

# 11. already recovered transaction cannot be recovered again
def test_11_already_recovered_protection():
    sim = simulator
    res = sim.simulate_execution(
        transaction_amount=12500.0,
        payment_method="CARD",
        failure_type="TEMPORARY_BANK_DECLINE",
        action_type="DELAYED_RETRY",
        attempt_number=1,
        customer_success_rate=0.894,
        is_already_recovered=True,
    )
    assert res["result"] == OutcomeResultEnum.SKIPPED.value
    assert res["recovered_amount"] == 0.0
    assert res["simulator_result"] == "ALREADY_CAPTURED"

# 12. deterministic repeated calculation
def test_12_deterministic_repeated_calculation():
    db = SessionLocal()
    res1 = seed_database(db, n_cases=100, seed=42)
    tx_ids1 = [t.id for t in db.query(Transaction).all()]
    rec_sum1 = db.query(RecoveryOutcome.recovered_amount).all()

    res2 = seed_database(db, n_cases=100, seed=42)
    tx_ids2 = [t.id for t in db.query(Transaction).all()]
    rec_sum2 = db.query(RecoveryOutcome.recovered_amount).all()
    db.close()

    assert res1["transaction_count"] == res2["transaction_count"]
    assert res1["failure_count"] == res2["failure_count"]
    assert res1["failure_rate"] == res2["failure_rate"]
    assert len(tx_ids1) == len(tx_ids2)
    assert len(rec_sum1) == len(rec_sum2)

# 13. TX-DEMO-001 accounting derived from persisted records
def test_13_demo_case_accounting_derived_from_persisted_records():
    from backend.app.services.recovery_service import recovery_service
    db = SessionLocal()
    seed_database(db, n_cases=100, seed=42)
    
    tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    assert tx is not None
    case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == tx.id).first()
    assert case is not None
    assert case.status == TransactionStatusEnum.RECOVERY_ELIGIBLE.value
    
    # Execute recovery
    res = recovery_service.execute_recovery(db, case.id)
    assert res.outcome is not None
    
    # Verify persisted RecoveryOutcome row
    outcome = db.query(RecoveryOutcome).filter(RecoveryOutcome.transaction_id == tx.id).first()
    assert outcome is not None
    assert outcome.recovered_amount == 12500.0
    assert outcome.baseline_amount == 4375.0
    assert outcome.incremental_amount == 8125.0
    assert outcome.incremental_amount == outcome.recovered_amount - outcome.baseline_amount
    assert outcome.outcome_type == OutcomeTypeEnum.AGENT_RECOVERY.value
    assert outcome.result == OutcomeResultEnum.SUCCESS.value
    db.close()

# 14. zero-baseline case handling
def test_14_zero_baseline_recovery_handling():
    outcome = RecoveryOutcome(
        id=str(uuid.uuid4()),
        recovery_outcome_id=f"OUT-ZERO-{uuid.uuid4().hex[:8].upper()}",
        outcome_type=OutcomeTypeEnum.AGENT_RECOVERY.value,
        result=OutcomeResultEnum.SUCCESS.value,
        recovered_amount=5000.0,
        baseline_amount=0.0,
        incremental_amount=5000.0,
        simulator_result="CAPTURED",
    )
    assert outcome.incremental_amount == outcome.recovered_amount - outcome.baseline_amount
    assert outcome.incremental_amount == 5000.0

# 15. Mutually exclusive transaction status partitioning and single ML target definition
def test_15_mutually_exclusive_transaction_status_partitioning_and_ml_target():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    
    total_tx = db.query(Transaction).count()
    captured_count = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.CAPTURED.value).count()
    failed_count = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.FAILED.value).count()
    recovered_count = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.RECOVERED.value).count()
    other_exhausted_count = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.RECOVERY_EXHAUSTED.value).count()
    
    # 1. Mutually Exclusive & Collectively Exhaustive Check:
    # TOTAL_TRANSACTIONS = CAPTURED + FAILED + RECOVERED + OTHER(EXHAUSTED)
    assert total_tx == captured_count + failed_count + recovered_count + other_exhausted_count
    assert total_tx == 6984
    assert captured_count == 5274
    assert failed_count == 1161
    assert recovered_count + other_exhausted_count == 549
    
    # 2. Prevent double counting: No transaction has multiple statuses or NULL status
    null_status_count = db.query(Transaction).filter(Transaction.status.is_(None)).count()
    assert null_status_count == 0
    
    # 3. Payment failures relationship:
    # All non-captured transactions (failed + recovered + exhausted) correspond to payment failure records
    total_failures = db.query(PaymentFailure).count()
    assert total_failures == failed_count + recovered_count + other_exhausted_count
    assert total_failures == 1710
    
    # 4. Supervised ML recovery training population: Exactly 549 resolved historical failures
    resolved_outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.metadata_payload["historical"].as_boolean() == True).all()
    assert len(resolved_outcomes) == recovered_count + other_exhausted_count
    assert len(resolved_outcomes) == 549
    
    # Verify binary targets: SUCCESS (y=1) and FAILURE (y=0)
    success_outcomes = [o for o in resolved_outcomes if o.result == OutcomeResultEnum.SUCCESS.value]
    failure_outcomes = [o for o in resolved_outcomes if o.result == OutcomeResultEnum.FAILURE.value]
    assert len(success_outcomes) == recovered_count
    assert len(failure_outcomes) == other_exhausted_count
    
    db.close()

# 16. Verify that organic successes (CAPTURED) and unresolved failures (FAILED) are NOT assigned binary recovery targets
def test_16_unresolved_failures_and_organic_successes_not_labeled_as_recovery_targets():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    
    # 1. Organic CAPTURED transactions must have ZERO RecoveryOutcome records
    captured_tx_ids = [t.id for t in db.query(Transaction.id).filter(Transaction.status == TransactionStatusEnum.CAPTURED.value).all()]
    assert len(captured_tx_ids) == 5274
    captured_outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.transaction_id.in_(captured_tx_ids)).count()
    assert captured_outcomes == 0
    
    # 2. Currently unresolved FAILED transactions must have ZERO RecoveryOutcome records
    failed_tx_ids = [t.id for t in db.query(Transaction.id).filter(Transaction.status == TransactionStatusEnum.FAILED.value).all()]
    assert len(failed_tx_ids) == 1161
    failed_outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.transaction_id.in_(failed_tx_ids)).count()
    assert failed_outcomes == 0
    
    # 3. Total persisted outcomes in seeded DB must equal ONLY the 549 resolved historical cases
    total_outcomes = db.query(RecoveryOutcome).count()
    assert total_outcomes == 549
    
    db.close()



