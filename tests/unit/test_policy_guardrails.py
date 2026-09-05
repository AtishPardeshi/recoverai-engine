import pytest
from datetime import datetime, timezone, timedelta
from backend.app.policies.policy_engine import policy_engine
from backend.app.schemas.common import RecoveryActionTypeEnum, TransactionStatusEnum, GuardrailDecisionEnum
from backend.app.config.config import settings

def test_terminal_state_guardrail():
    res = policy_engine.validate(
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        case_status=TransactionStatusEnum.RECOVERED.value,
        retry_count=0,
        message_count=0,
        case_created_at=datetime.now(timezone.utc),
        last_action_time=None,
        is_opted_out=False,
        has_open_dispute=False,
    )
    assert not res.approved
    assert res.decision == GuardrailDecisionEnum.REJECTED
    assert "terminal case" in res.reason

def test_customer_opt_out_guardrail():
    res = policy_engine.validate(
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        retry_count=0,
        message_count=0,
        case_created_at=datetime.now(timezone.utc),
        last_action_time=None,
        is_opted_out=True,
        has_open_dispute=False,
    )
    assert not res.approved
    assert res.decision == GuardrailDecisionEnum.REJECTED
    assert "opted out" in res.reason

def test_max_retries_guardrail():
    res = policy_engine.validate(
        action_type=RecoveryActionTypeEnum.RETRY_PAYMENT.value,
        case_status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        retry_count=settings.MAX_AUTOMATED_RETRIES,
        message_count=0,
        case_created_at=datetime.now(timezone.utc),
        last_action_time=datetime.now(timezone.utc) - timedelta(hours=10),
        is_opted_out=False,
        has_open_dispute=False,
    )
    assert not res.approved
    assert "Max automated retries exceeded" in res.reason

def test_cooldown_period_guardrail():
    res = policy_engine.validate(
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        case_status=TransactionStatusEnum.RECOVERY_IN_PROGRESS.value,
        retry_count=1,
        message_count=0,
        case_created_at=datetime.now(timezone.utc) - timedelta(hours=3),
        last_action_time=datetime.now(timezone.utc) - timedelta(hours=2),  # 2h < 6h cooldown
        is_opted_out=False,
        has_open_dispute=False,
    )
    assert not res.approved
    assert "cooldown active" in res.reason

def test_systemic_incident_circuit_breaker():
    res = policy_engine.validate(
        action_type=RecoveryActionTypeEnum.DELAYED_RETRY.value,
        case_status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        retry_count=0,
        message_count=0,
        case_created_at=datetime.now(timezone.utc),
        last_action_time=None,
        is_opted_out=False,
        has_open_dispute=False,
        is_systemic_incident_active=True,
    )
    assert not res.approved
    assert "bank failure incident active" in res.reason
