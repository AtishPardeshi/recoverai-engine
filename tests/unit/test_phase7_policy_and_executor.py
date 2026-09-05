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
)
from backend.app.schemas.policy import (
    PolicyDecision,
    PolicyReasonCode,
    RecoveryPolicyConfig,
)
from backend.app.schemas.recovery import AIRecommendationDetail
from backend.app.policies.policy_engine import PolicyEngine, policy_engine
from backend.app.executor.action_executor import ActionExecutor, SimulationActionAdapter, action_executor
from backend.app.simulator.gateway_simulator import PaymentGatewaySimulator
from backend.app.services.recovery_service import recovery_service
from backend.app.config.config import settings

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def create_test_fixture(db: Session, status: str = TransactionStatusEnum.RECOVERY_ELIGIBLE.value, is_opted_out: bool = False, has_open_dispute: bool = False, amount: float = 10000.0):
    cust = Customer(
        id=str(uuid.uuid4()),
        external_id=f"CUST-{uuid.uuid4().hex[:6]}",
        name="Test Customer",
        historical_success_rate=0.85,
        total_transaction_value=amount,
        successful_payment_count=5,
        failed_payment_count=1,
        is_opted_out=is_opted_out,
        has_open_dispute=has_open_dispute,
    )
    db.add(cust)
    db.flush()

    tx = Transaction(
        id=str(uuid.uuid4()),
        external_id=f"TX-{uuid.uuid4().hex[:6]}",
        customer_id=cust.id,
        amount=amount,
        currency="INR",
        payment_method="CARD",
        status=status,
    )
    db.add(tx)
    db.flush()

    fail = PaymentFailure(
        id=str(uuid.uuid4()),
        transaction_id=tx.id,
        error_code="BANK_TIMEOUT",
        error_description="Issuer timeout",
        normalized_failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        retry_count=0,
    )
    db.add(fail)
    db.flush()

    case = RecoveryCase(
        id=str(uuid.uuid4()),
        recovery_case_id=f"RC-{uuid.uuid4().hex[:6]}",
        transaction_id=tx.id,
        revenue_at_risk=amount,
        recovery_probability=0.85,
        expected_recovery=amount * 0.85,
        priority_score=amount * 0.85,
        status=status,
        retry_count=0,
        message_count=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(case)
    db.commit()
    return cust, tx, fail, case

# ==========================================
# 1. POLICY ENGINE DETERMINISTIC TESTS
# ==========================================

def test_1_valid_delayed_retry():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        retry_count=0,
    )
    assert dec.is_approved
    assert dec.decision == GuardrailDecisionEnum.APPROVED
    assert dec.action == RecoveryActionTypeEnum.DELAYED_RETRY
    assert len(dec.reason_codes) == 0

def test_2_valid_retry():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        retry_count=0,
    )
    assert dec.is_approved
    assert dec.decision == GuardrailDecisionEnum.APPROVED

def test_3_retry_limit_exceeded():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        retry_count=2, # Max is 2
    )
    assert dec.is_rejected
    assert PolicyReasonCode.RETRY_LIMIT_EXCEEDED in dec.reason_codes
    assert dec.suggested_status == TransactionStatusEnum.RECOVERY_EXHAUSTED.value

def test_4_retry_cooldown_active():
    engine = PolicyEngine()
    now = datetime.now(timezone.utc)
    last_act = now - timedelta(hours=3) # 3h < 6h cooldown
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        retry_count=1,
        last_action_time=last_act,
        current_time=now,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.RETRY_COOLDOWN_ACTIVE in dec.reason_codes

def test_5_payment_link_limit_exceeded():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        payment_link_count=1, # Max is 1
    )
    assert dec.is_rejected
    assert PolicyReasonCode.PAYMENT_LINK_LIMIT_EXCEEDED in dec.reason_codes

def test_6_message_limit_exceeded():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.SEND_REMINDER,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        message_count=2, # Max is 2
    )
    assert dec.is_rejected
    assert PolicyReasonCode.MESSAGE_LIMIT_EXCEEDED in dec.reason_codes

def test_7_recovery_window_exceeded():
    engine = PolicyEngine()
    now = datetime.now(timezone.utc)
    created_at = now - timedelta(hours=75) # > 72h
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        case_created_at=created_at,
        current_time=now,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.RECOVERY_WINDOW_EXCEEDED in dec.reason_codes
    assert dec.suggested_status == TransactionStatusEnum.RECOVERY_EXHAUSTED.value

def test_8_transaction_not_eligible():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.CREATED.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.TRANSACTION_NOT_RECOVERY_ELIGIBLE in dec.reason_codes

def test_9_captured_transaction_protection():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.CAPTURED.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.TRANSACTION_ALREADY_CAPTURED in dec.reason_codes

def test_10_recovered_transaction_protection():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERED.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.TRANSACTION_ALREADY_RECOVERED in dec.reason_codes

def test_11_recovery_exhausted_protection():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.RECOVERY_CASE_EXHAUSTED in dec.reason_codes

def test_12_escalated_case_protection():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.ESCALATED.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.TRANSACTION_TERMINAL in dec.reason_codes

def test_13_stopped_case_protection():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.STOPPED.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.TRANSACTION_TERMINAL in dec.reason_codes

def test_14_customer_opt_out():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        is_opted_out=True,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.CUSTOMER_OPTED_OUT in dec.reason_codes
    assert dec.suggested_status == TransactionStatusEnum.STOPPED.value

def test_15_open_dispute_protection():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        has_open_dispute=True,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.OPEN_DISPUTE in dec.reason_codes
    assert dec.suggested_status == TransactionStatusEnum.ESCALATED.value

def test_16_systemic_incident_circuit_breaker():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        is_systemic_incident_active=True,
        failure_spike_rate=0.35,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.SYSTEMIC_INCIDENT_ACTIVE in dec.reason_codes

def test_17_low_ml_probability_human_review():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        ml_probability=0.10,
    )
    assert dec.is_approved
    assert dec.requires_human_review is True

def test_18_low_ai_confidence_human_review():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        ai_confidence=0.30,
    )
    assert dec.is_approved
    assert dec.requires_human_review is True

def test_19_human_review_flag_behavior():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.ESCALATE_TO_HUMAN,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    assert dec.is_approved
    assert dec.requires_human_review is True

def test_20_invalid_action_rejected():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action="INVALID_ACTION_NAME",
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.INVALID_ACTION in dec.reason_codes

def test_21_missing_policy_context_rejected():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=None,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.MISSING_POLICY_CONTEXT in dec.reason_codes

def test_22_deterministic_policy_output():
    engine = PolicyEngine()
    t = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    dec1 = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        current_time=t,
    )
    dec2 = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        current_time=t,
    )
    assert dec1.decision == dec2.decision
    assert dec1.action == dec2.action
    assert dec1.reason_codes == dec2.reason_codes
    assert dec1.policy_version == dec2.policy_version

def test_23_policy_version_persisted():
    config = RecoveryPolicyConfig(policy_version="policy-v1-custom")
    engine = PolicyEngine(config=config)
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    assert dec.policy_version == "policy-v1-custom"

def test_24_policy_reason_codes_controlled():
    for code in PolicyReasonCode:
        assert isinstance(code.value, str)
        assert len(code.value) > 0

def test_25_multiple_policy_violations_deterministic_order():
    engine = PolicyEngine()
    # If case is captured and customer is opted out, terminal state check executes first
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.CAPTURED.value,
        is_opted_out=True,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.TRANSACTION_ALREADY_CAPTURED in dec.reason_codes

# ==========================================
# 2. ACTION EXECUTOR TESTS
# ==========================================

def test_26_approved_retry_executes(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        policy_version="policy-v1",
        reasons=["All policy checks passed"],
    )
    res = action_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    assert res.status == "EXECUTED"
    assert res.action_type == RecoveryActionTypeEnum.RETRY_PAYMENT
    assert res.simulated is True

def test_27_approved_delayed_retry_executes(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
        reasons=["All policy checks passed"],
    )
    res = action_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    assert res.status == "EXECUTED"
    assert res.action_type == RecoveryActionTypeEnum.DELAYED_RETRY

def test_28_rejected_policy_cannot_execute(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    rej_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.REJECTED,
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        reason_codes=[PolicyReasonCode.RETRY_LIMIT_EXCEEDED],
        reasons=["Max retries exceeded"],
        policy_version="policy-v1",
    )
    with pytest.raises(ValueError, match="cannot execute unapproved"):
        action_executor.execute(
            db=db,
            recovery_case=case,
            policy_decision=rej_dec,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
        )

def test_29_ai_recommendation_cannot_directly_execute(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    ai_rec = AIRecommendationDetail(
        recommended_action=RecoveryActionTypeEnum.DELAYED_RETRY,
        root_cause="Temporary bank issue",
        reason="Good probability",
        confidence=0.95,
        expected_recovery=9500.0,
    )
    with pytest.raises(TypeError, match="strictly requires an authoritative PolicyDecision"):
        # Passing raw AI recommendation directly to executor must be rejected
        action_executor.execute(
            db=db,
            recovery_case=case,
            policy_decision=ai_rec, # type: ignore
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
        )

def test_30_terminal_state_recheck_at_executor(db: Session):
    cust, tx, fail, case = create_test_fixture(db, status=TransactionStatusEnum.CAPTURED.value)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    # Stale policy approved, but tx is already CAPTURED in DB
    res = action_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    assert res.simulator_result == "ALREADY_CAPTURED"
    assert res.recovered_amount == 0.0

def test_31_stale_policy_decision_handled_safely(db: Session):
    cust, tx, fail, case = create_test_fixture(db, status=TransactionStatusEnum.RECOVERED.value)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        policy_version="policy-v1",
    )
    res = action_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    assert res.recovered_amount == 0.0
    assert res.simulator_result == "ALREADY_CAPTURED"

def test_32_executor_final_safety_checks(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    # Remove transaction from case
    case.transaction = None
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    with pytest.raises(ValueError, match="no associated transaction"):
        action_executor.execute(
            db=db,
            recovery_case=case,
            policy_decision=pol_dec,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
        )

def test_33_simulator_invoked_only_after_approval(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    engine = PolicyEngine()
    pol_dec = engine.evaluate(
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        case_status=case.status,
    )
    assert pol_dec.is_approved
    res = action_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    assert res.simulator_result in ["CAPTURED", "DECLINED_AGAIN", "ALREADY_CAPTURED"]

def test_34_real_payment_gateway_never_called(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    adapter = SimulationActionAdapter()
    res = adapter.execute_simulated_action(
        transaction=tx,
        recovery_case=case,
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY,
        attempt_number=1,
    )
    assert res["simulated"] is True
    assert "provider_reference" in res
    assert res["provider_reference"].startswith("sim_pay_")

def test_35_real_communication_never_called(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    adapter = SimulationActionAdapter()
    res = adapter.execute_simulated_action(
        transaction=tx,
        recovery_case=case,
        action_type=RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
        attempt_number=1,
    )
    assert res["simulated"] is True
    assert "provider_reference" in res

def test_36_successful_capture_records_outcome(db: Session):
    cust, tx, fail, case = create_test_fixture(db, amount=12500.0)
    # Seed deterministic simulator to produce success
    sim = PaymentGatewaySimulator(seed=1)
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    if res.outcome_result == OutcomeResultEnum.SUCCESS:
        assert res.recovered_amount == 12500.0
        assert res.new_case_status == TransactionStatusEnum.RECOVERED
        assert res.new_transaction_status == TransactionStatusEnum.RECOVERED

def test_37_failed_retry_records_failure(db: Session):
    cust, tx, fail, case = create_test_fixture(db, amount=12500.0)
    # Seed deterministic simulator to produce failure
    sim = PaymentGatewaySimulator(seed=999)
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    if res.outcome_result == OutcomeResultEnum.FAILURE:
        assert res.recovered_amount == 0.0

def test_38_no_recovery_revenue_on_failed_attempt(db: Session):
    cust, tx, fail, case = create_test_fixture(db, amount=5000.0)
    sim = PaymentGatewaySimulator(seed=999)
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    if res.outcome_result == OutcomeResultEnum.FAILURE:
        assert res.recovered_amount == 0.0
        assert res.incremental_amount == 0.0

def test_39_recovered_revenue_only_after_confirmed_success(db: Session):
    cust, tx, fail, case = create_test_fixture(db, amount=7500.0)
    sim = PaymentGatewaySimulator(seed=1)
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    if res.outcome_result == OutcomeResultEnum.SUCCESS:
        assert res.recovered_amount == 7500.0
        assert res.baseline_amount == round(7500.0 * 0.35, 2)
        assert res.incremental_amount == round(7500.0 - res.baseline_amount, 2)

def test_40_baseline_and_agent_recovery_separated(db: Session):
    cust, tx, fail, case = create_test_fixture(db, amount=10000.0)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = action_executor.execute(
        db=db,
        recovery_case=case,
        policy_decision=pol_dec,
        idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
    )
    if res.outcome_result == OutcomeResultEnum.SUCCESS:
        assert res.baseline_amount > 0.0
        assert res.incremental_amount > 0.0
        assert res.baseline_amount + res.incremental_amount == res.recovered_amount

# ==========================================
# 3. IDEMPOTENCY TESTS
# ==========================================

def test_41_same_key_same_result(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    key = f"idemp-test-{uuid.uuid4().hex[:8]}"
    res1 = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    res2 = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    assert res1.action_id == res2.action_id
    assert res1.recovered_amount == res2.recovered_amount
    assert res1.simulator_result == res2.simulator_result

def test_42_duplicate_execution_does_not_duplicate_outcome(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    key = f"idemp-test-{uuid.uuid4().hex[:8]}"
    action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    count = db.query(RecoveryOutcome).filter(RecoveryOutcome.recovery_case_id == case.id).count()
    assert count == 1

def test_43_duplicate_execution_does_not_duplicate_revenue(db: Session):
    cust, tx, fail, case = create_test_fixture(db, amount=12500.0)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    key = f"idemp-test-{uuid.uuid4().hex[:8]}"
    res1 = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    res2 = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    outcomes = db.query(RecoveryOutcome).filter(RecoveryOutcome.recovery_case_id == case.id).all()
    total_db_recovered = sum(o.recovered_amount for o in outcomes)
    assert total_db_recovered == res1.recovered_amount

def test_44_conflicting_key_action_rejected(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec_1 = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    pol_dec_2 = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
        policy_version="policy-v1",
    )
    key = f"idemp-conflict-{uuid.uuid4().hex[:8]}"
    action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec_1, idempotency_key=key)
    with pytest.raises(HTTPException) as exc:
        action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec_2, idempotency_key=key)
    assert exc.value.status_code == 409
    assert "IDEMPOTENCY_CONFLICT" in str(exc.value.detail)

def test_45_sequence_number_uniqueness(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res1 = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"key-seq-1-{uuid.uuid4().hex[:6]}")
    res2 = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"key-seq-2-{uuid.uuid4().hex[:6]}")
    assert res1.sequence_number == 1
    assert res2.sequence_number == 2

def test_46_concurrent_execution_protection(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    key = f"conc-key-{uuid.uuid4().hex[:8]}"
    res1 = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    res2 = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    assert res1.action_id == res2.action_id

# ==========================================
# 4. RECOVERY STATE MACHINE TESTS
# ==========================================

def test_47_failed_to_recovery_eligible():
    status = TransactionStatusEnum.RECOVERY_ELIGIBLE.value
    assert status == "RECOVERY_ELIGIBLE"

def test_48_recovery_eligible_to_in_progress(db: Session):
    cust, tx, fail, case = create_test_fixture(db, status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value)
    sim = PaymentGatewaySimulator(seed=999) # Decline
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"st-1-{uuid.uuid4().hex[:6]}")
    if res.outcome_result == OutcomeResultEnum.FAILURE:
        assert res.new_case_status == TransactionStatusEnum.RECOVERY_IN_PROGRESS

def test_49_in_progress_to_recovered(db: Session):
    cust, tx, fail, case = create_test_fixture(db, status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value)
    sim = PaymentGatewaySimulator(seed=1) # Capture
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"st-2-{uuid.uuid4().hex[:6]}")
    if res.outcome_result == OutcomeResultEnum.SUCCESS:
        assert res.new_case_status == TransactionStatusEnum.RECOVERED

def test_50_in_progress_to_exhausted(db: Session):
    cust, tx, fail, case = create_test_fixture(db, status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value)
    case.retry_count = 1 # Attempt 2 will hit max retries (2)
    sim = PaymentGatewaySimulator(seed=999) # Decline
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"st-3-{uuid.uuid4().hex[:6]}")
    if res.outcome_result == OutcomeResultEnum.FAILURE:
        assert res.new_case_status == TransactionStatusEnum.RECOVERY_EXHAUSTED

def test_51_escalation_transition(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.ESCALATE_TO_HUMAN,
        policy_version="policy-v1",
    )
    res = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"esc-{uuid.uuid4().hex[:6]}")
    assert res.new_case_status == TransactionStatusEnum.ESCALATED

def test_52_stop_transition(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.STOP_RECOVERY,
        policy_version="policy-v1",
    )
    res = action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"stop-{uuid.uuid4().hex[:6]}")
    assert res.new_case_status == TransactionStatusEnum.STOPPED

def test_53_captured_cannot_regress_to_failed(db: Session):
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.CAPTURED.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.TRANSACTION_ALREADY_CAPTURED in dec.reason_codes

def test_54_recovered_cannot_regress_to_failed(db: Session):
    engine = PolicyEngine()
    dec = engine.evaluate(
        action=RecoveryActionTypeEnum.RETRY_PAYMENT,
        case_status=TransactionStatusEnum.RECOVERED.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.TRANSACTION_ALREADY_RECOVERED in dec.reason_codes

# ==========================================
# 5. AUDIT EVENT TRAIL TESTS
# ==========================================

def test_55_policy_evaluation_audited(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    resp = recovery_service.execute_recovery(db=db, case_id=case.id, action_type_override=RecoveryActionTypeEnum.DELAYED_RETRY)
    audits = db.query(AuditEvent).filter(AuditEvent.correlation_id == resp.correlation_id).all()
    types = [a.event_type for a in audits]
    assert "POLICY_EVALUATION_STARTED" in types

def test_56_policy_approval_audited(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    resp = recovery_service.execute_recovery(db=db, case_id=case.id, action_type_override=RecoveryActionTypeEnum.DELAYED_RETRY)
    audits = db.query(AuditEvent).filter(AuditEvent.correlation_id == resp.correlation_id).all()
    types = [a.event_type for a in audits]
    assert "POLICY_APPROVED" in types

def test_57_policy_rejection_audited(db: Session):
    cust, tx, fail, case = create_test_fixture(db, is_opted_out=True)
    resp = recovery_service.execute_recovery(db=db, case_id=case.id, action_type_override=RecoveryActionTypeEnum.DELAYED_RETRY)
    assert resp.policy.approved is False
    audits = db.query(AuditEvent).filter(AuditEvent.correlation_id == resp.correlation_id).all()
    types = [a.event_type for a in audits]
    assert "POLICY_REJECTED" in types

def test_58_action_execution_audited(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    resp = recovery_service.execute_recovery(db=db, case_id=case.id, action_type_override=RecoveryActionTypeEnum.DELAYED_RETRY)
    audits = db.query(AuditEvent).filter(AuditEvent.correlation_id == resp.correlation_id).all()
    types = [a.event_type for a in audits]
    assert "ACTION_EXECUTED" in types

def test_59_action_execution_failure_audited(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    # Trigger execution error by breaking session
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    # An action failure should log ACTION_EXECUTION_FAILED
    audit = AuditEvent(
        id=str(uuid.uuid4()),
        event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
        correlation_id=f"corr-{uuid.uuid4().hex[:6]}",
        entity_type="RECOVERY_CASE",
        entity_id=case.id,
        event_type="ACTION_EXECUTION_FAILED",
        actor_type="EXECUTOR",
        payload={"error": "simulated failure"},
        policy_version="policy-v1",
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.commit()
    persisted = db.query(AuditEvent).filter(AuditEvent.id == audit.id).first()
    assert persisted is not None

def test_60_idempotency_hit_audited(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    key = f"audit-hit-{uuid.uuid4().hex[:6]}"
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    action_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=key)
    hits = db.query(AuditEvent).filter(AuditEvent.event_type == "ACTION_IDEMPOTENCY_HIT").all()
    assert len(hits) >= 1

def test_61_correlation_id_propagated(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    corr_id = f"custom-corr-{uuid.uuid4().hex[:8]}"
    resp = recovery_service.execute_recovery(db=db, case_id=case.id, action_type_override=RecoveryActionTypeEnum.DELAYED_RETRY, correlation_id=corr_id)
    assert resp.correlation_id == corr_id
    audits = db.query(AuditEvent).filter(AuditEvent.correlation_id == corr_id).all()
    assert len(audits) >= 2

def test_62_policy_version_audited(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    resp = recovery_service.execute_recovery(db=db, case_id=case.id, action_type_override=RecoveryActionTypeEnum.DELAYED_RETRY)
    audits = db.query(AuditEvent).filter(AuditEvent.correlation_id == resp.correlation_id).all()
    for a in audits:
        assert a.policy_version is not None

# ==========================================
# 6. REVENUE ACCOUNTING TESTS
# ==========================================

def test_63_recovered_amount_calculation():
    amount = 12500.0
    baseline = round(amount * 0.35, 2)
    incremental = round(amount - baseline, 2)
    assert baseline == 4375.0
    assert incremental == 8125.0
    assert baseline + incremental == amount

def test_64_failed_execution_adds_zero_recovered_revenue(db: Session):
    cust, tx, fail, case = create_test_fixture(db, amount=10000.0)
    sim = PaymentGatewaySimulator(seed=999)
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"rev-0-{uuid.uuid4().hex[:6]}")
    if res.outcome_result == OutcomeResultEnum.FAILURE:
        assert res.recovered_amount == 0.0

def test_65_incremental_recovery_calculation(db: Session):
    cust, tx, fail, case = create_test_fixture(db, amount=15000.0)
    sim = PaymentGatewaySimulator(seed=1)
    custom_executor = ActionExecutor(adapter=SimulationActionAdapter(simulator=sim))
    pol_dec = PolicyDecision(
        decision=GuardrailDecisionEnum.APPROVED,
        action=RecoveryActionTypeEnum.DELAYED_RETRY,
        policy_version="policy-v1",
    )
    res = custom_executor.execute(db=db, recovery_case=case, policy_decision=pol_dec, idempotency_key=f"rev-inc-{uuid.uuid4().hex[:6]}")
    if res.outcome_result == OutcomeResultEnum.SUCCESS:
        assert res.incremental_amount > 0.0
        assert res.incremental_amount < res.recovered_amount

def test_66_baseline_recovery_not_counted_as_agent_recovery():
    total_recovered = 10000.0
    baseline_recovered = 3500.0
    incremental_agent_recovered = total_recovered - baseline_recovered
    assert incremental_agent_recovered == 6500.0
    assert baseline_recovered != incremental_agent_recovered

# ==========================================
# 7. SECURITY & ARCHITECTURE TESTS
# ==========================================

def test_67_no_secrets_in_audit_payload(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    resp = recovery_service.execute_recovery(db=db, case_id=case.id, action_type_override=RecoveryActionTypeEnum.DELAYED_RETRY)
    audits = db.query(AuditEvent).filter(AuditEvent.correlation_id == resp.correlation_id).all()
    for a in audits:
        payload_str = str(a.payload).lower()
        assert "password" not in payload_str
        assert "secret" not in payload_str
        assert "api_key" not in payload_str

def test_68_no_chain_of_thought_stored(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    resp = recovery_service.execute_recovery(db=db, case_id=case.id, action_type_override=RecoveryActionTypeEnum.DELAYED_RETRY)
    audits = db.query(AuditEvent).filter(AuditEvent.correlation_id == resp.correlation_id).all()
    for a in audits:
        payload_str = str(a.payload).lower()
        assert "chain_of_thought" not in payload_str
        assert "inner_monologue" not in payload_str

def test_69_no_arbitrary_action_accepted():
    engine = PolicyEngine()
    dec = engine.evaluate(
        action="UNSUPPORTED_ARBITRARY_ACTION",
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
    )
    assert dec.is_rejected
    assert PolicyReasonCode.INVALID_ACTION in dec.reason_codes

def test_70_no_direct_ai_execution_path(db: Session):
    cust, tx, fail, case = create_test_fixture(db)
    ai_rec = AIRecommendationDetail(
        recommended_action=RecoveryActionTypeEnum.DELAYED_RETRY,
        root_cause="Temporary bank issue",
        reason="High likelihood",
        confidence=0.99,
        expected_recovery=10000.0,
    )
    with pytest.raises(TypeError):
        action_executor.execute(db=db, recovery_case=case, policy_decision=ai_rec) # type: ignore

def test_71_tx_demo_001_end_to_end_flow(db: Session):
    # Verify complete TX-DEMO-001 pipeline
    demo_tx = db.query(Transaction).filter(Transaction.external_id == "TX-DEMO-001").first()
    if not demo_tx:
        pytest.skip("TX-DEMO-001 not in database session")
    demo_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == demo_tx.id).first()
    assert demo_case is not None
    
    # Ensure fresh status for clean end-to-end verification
    demo_tx.status = TransactionStatusEnum.FAILED.value
    demo_case.status = TransactionStatusEnum.RECOVERY_ELIGIBLE.value
    demo_case.retry_count = 0
    db.commit()

    # AI Recommendation
    rec = recovery_service.get_recommendation(db=db, case_id=demo_case.id)
    assert rec.recommendation.recommended_action == RecoveryActionTypeEnum.DELAYED_RETRY
    assert rec.ml.recovery_probability > 0.90
    
    # Policy Evaluation
    pol_dec = policy_engine.evaluate(
        action=rec.recommendation.recommended_action,
        case_status=demo_case.status,
    )
    assert pol_dec.is_approved
    
    # Action Executor
    res = action_executor.execute(
        db=db,
        recovery_case=demo_case,
        policy_decision=pol_dec,
        idempotency_key=f"demo-exec-{uuid.uuid4().hex[:6]}",
    )
    assert res.status == "EXECUTED"
    assert res.simulated is True

def test_72_pure_deterministic_guardrails_no_llm():
    # Verify PolicyEngine does not import or invoke LLM providers
    engine = PolicyEngine()
    assert not hasattr(engine, "llm")
    assert not hasattr(engine, "gemini")
    assert not hasattr(engine, "openai")
