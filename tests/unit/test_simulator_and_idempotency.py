import pytest
from backend.app.simulator.gateway_simulator import simulator
from backend.app.schemas.common import RecoveryActionTypeEnum, FailureTypeEnum, OutcomeResultEnum

def test_simulator_primary_demo_rule():
    out = simulator.simulate_execution(
        transaction_amount=12500.0,
        payment_method="CARD",
        failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        attempt_number=1,
        customer_success_rate=0.894,
        is_demo_tx=True,
    )
    assert out["result"] == OutcomeResultEnum.SUCCESS.value
    assert out["recovered_amount"] == 12500.0
    assert out["simulator_result"] == "CAPTURED"
    assert out["provider_reference"].startswith("sim_pay_")

def test_simulator_invalid_details_stop():
    out = simulator.simulate_execution(
        transaction_amount=5000.0,
        payment_method="CARD",
        failure_type=FailureTypeEnum.INVALID_DETAILS.value,
        action_type=RecoveryActionTypeEnum.STOP_RECOVERY.value,
        attempt_number=1,
        customer_success_rate=0.5,
        is_demo_tx=False,
    )
    assert out["result"] == OutcomeResultEnum.SKIPPED.value
    assert out["recovered_amount"] == 0.0
