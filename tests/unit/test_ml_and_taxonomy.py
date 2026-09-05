import pytest
from backend.app.ml.recovery_model import ml_model
from backend.app.simulator.event_ingestion import normalize_razorpay_error
from backend.app.schemas.common import FailureTypeEnum

def test_failure_taxonomy_normalization():
    assert normalize_razorpay_error("BAD_REQUEST_AUTHENTICATION", None, None, None) == FailureTypeEnum.INVALID_DETAILS.value
    assert normalize_razorpay_error("GATEWAY_ERROR", "Card expired", None, "EXPIRED_CARD") == FailureTypeEnum.EXPIRED_METHOD.value
    assert normalize_razorpay_error("BAD_REQUEST_ERROR", "Insufficient balance", None, "INSUFFICIENT_FUNDS") == FailureTypeEnum.INSUFFICIENT_FUNDS.value
    assert normalize_razorpay_error("GATEWAY_TIMEOUT", "Network error", None, None) == FailureTypeEnum.NETWORK_ERROR.value
    assert normalize_razorpay_error("GATEWAY_ERROR", "Bank system outage", None, "BANK_SYSTEM_OUTAGE") == FailureTypeEnum.TEMPORARY_BANK_DECLINE.value

def test_ml_prediction_bounds_and_demo_case():
    prob = ml_model.predict_recovery_probability(
        amount=12500.0,
        payment_method="CARD",
        failure_type="TEMPORARY_BANK_DECLINE",
        customer_success_rate=0.894,
        customer_success_count=17,
        customer_failed_count=2,
    )
    assert 0.80 <= prob <= 0.98
    exp_rec, p_score = ml_model.calculate_priority_score(12500.0, prob, 0.894)
    assert exp_rec == round(12500.0 * prob, 2)
    assert p_score > exp_rec  # boosted by reliable customer track record

def test_ml_prediction_extreme_cases():
    low_prob = ml_model.predict_recovery_probability(
        amount=50000.0,
        payment_method="CARD",
        failure_type="INVALID_DETAILS",
        customer_success_rate=0.2,
        customer_success_count=1,
        customer_failed_count=4,
        retry_count=2,
    )
    assert 0.01 <= low_prob <= 0.15
