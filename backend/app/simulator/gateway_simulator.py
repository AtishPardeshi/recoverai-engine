import uuid
from datetime import datetime, timezone
import random
from typing import Any
from backend.app.schemas.common import RecoveryActionTypeEnum, FailureTypeEnum, OutcomeResultEnum

class PaymentGatewaySimulator:
    """
    Deterministic payment gateway simulator.
    Simulates payment execution outcomes for automated retries and communication actions.
    Enforces that already captured/recovered transactions cannot be double-charged.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def reseed(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def simulate_execution(
        self,
        transaction_amount: float,
        payment_method: str,
        failure_type: str,
        action_type: str,
        attempt_number: int,
        customer_success_rate: float,
        is_demo_tx: bool = False,
        is_already_recovered: bool = False,
        transaction_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Executes a deterministic simulated recovery action.
        Returns:
            {
                "success": bool,
                "result": "SUCCESS" | "FAILURE" | "SKIPPED",
                "simulator_result": "CAPTURED" | "DECLINED" | ...,
                "transaction_id": str | None,
                "recovered_amount": float,
                "currency": "INR",
                "failure_reason": str | None,
                "provider_reference": str,
                "reason_code": str,
                "timestamp": str,
            }
        """
        ref_id = f"sim_pay_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # Terminal state protection: no duplicate charges if already recovered/captured
        if is_already_recovered:
            return {
                "success": True,
                "result": OutcomeResultEnum.SKIPPED.value,
                "simulator_result": "ALREADY_CAPTURED",
                "transaction_id": transaction_id,
                "recovered_amount": 0.0,
                "currency": "INR",
                "failure_reason": "Transaction is already in terminal recovered/captured state.",
                "provider_reference": ref_id,
                "reason_code": "ALREADY_CAPTURED",
                "timestamp": timestamp,
            }

        # Action compatibility and calibrated simulation:
        is_compatible = False
        base_success_chance = 0.50

        if failure_type == FailureTypeEnum.TEMPORARY_BANK_DECLINE.value:
            if action_type in [RecoveryActionTypeEnum.DELAYED_RETRY.value, RecoveryActionTypeEnum.RETRY_PAYMENT.value]:
                is_compatible = True
                base_success_chance = 0.88
            else:
                base_success_chance = 0.30

        elif failure_type == FailureTypeEnum.NETWORK_ERROR.value:
            if action_type in [RecoveryActionTypeEnum.DELAYED_RETRY.value, RecoveryActionTypeEnum.RETRY_PAYMENT.value]:
                is_compatible = True
                base_success_chance = 0.85
            else:
                base_success_chance = 0.25

        elif failure_type == FailureTypeEnum.INSUFFICIENT_FUNDS.value:
            if action_type in [RecoveryActionTypeEnum.SEND_PAYMENT_LINK.value, RecoveryActionTypeEnum.SEND_REMINDER.value]:
                is_compatible = True
                base_success_chance = 0.68
            else:
                base_success_chance = 0.15

        elif failure_type == FailureTypeEnum.EXPIRED_METHOD.value:
            if action_type in [RecoveryActionTypeEnum.SUGGEST_ALTERNATIVE_PAYMENT_METHOD.value, RecoveryActionTypeEnum.SEND_PAYMENT_LINK.value]:
                is_compatible = True
                base_success_chance = 0.72
            else:
                base_success_chance = 0.05

        elif failure_type == FailureTypeEnum.BANK_DECLINE.value:
            if action_type == RecoveryActionTypeEnum.SUGGEST_ALTERNATIVE_PAYMENT_METHOD.value:
                is_compatible = True
                base_success_chance = 0.75
            elif action_type == RecoveryActionTypeEnum.DELAYED_RETRY.value:
                base_success_chance = 0.45
            else:
                base_success_chance = 0.10

        elif failure_type == FailureTypeEnum.INVALID_DETAILS.value:
            if action_type in [RecoveryActionTypeEnum.STOP_RECOVERY.value, RecoveryActionTypeEnum.ESCALATE_TO_HUMAN.value]:
                return {
                    "success": False,
                    "result": OutcomeResultEnum.SKIPPED.value,
                    "simulator_result": "MANUAL_CORRECTION_REQUIRED",
                    "transaction_id": transaction_id,
                    "recovered_amount": 0.0,
                    "currency": "INR",
                    "failure_reason": "Invalid card details require manual customer re-entry",
                    "provider_reference": ref_id,
                    "reason_code": "MANUAL_CORRECTION_REQUIRED",
                    "timestamp": timestamp,
                }
            base_success_chance = 0.02

        if action_type == RecoveryActionTypeEnum.STOP_RECOVERY.value:
            return {
                "success": False,
                "result": OutcomeResultEnum.SKIPPED.value,
                "simulator_result": "RECOVERY_STOPPED",
                "transaction_id": transaction_id,
                "recovered_amount": 0.0,
                "currency": "INR",
                "failure_reason": "Recovery terminated by policy or agent",
                "provider_reference": ref_id,
                "reason_code": "STOPPED",
                "timestamp": timestamp,
            }

        # Weight by customer historical success rate and penalty for attempt count
        attempt_penalty = max(0.0, (attempt_number - 1) * 0.15)
        customer_boost = (customer_success_rate - 0.5) * 0.25
        final_probability = max(0.05, min(0.96, base_success_chance + customer_boost - attempt_penalty))

        roll = self.rng.random()
        if roll < final_probability:
            return {
                "success": True,
                "result": OutcomeResultEnum.SUCCESS.value,
                "simulator_result": "CAPTURED",
                "transaction_id": transaction_id,
                "recovered_amount": transaction_amount,
                "currency": "INR",
                "failure_reason": None,
                "provider_reference": ref_id,
                "reason_code": "CAPTURED",
                "timestamp": timestamp,
            }
        else:
            return {
                "success": False,
                "result": OutcomeResultEnum.FAILURE.value,
                "simulator_result": "DECLINED_AGAIN",
                "transaction_id": transaction_id,
                "recovered_amount": 0.0,
                "currency": "INR",
                "failure_reason": f"Provider declined during {action_type} attempt {attempt_number}",
                "provider_reference": ref_id,
                "reason_code": "DECLINED",
                "timestamp": timestamp,
            }

simulator = PaymentGatewaySimulator()
