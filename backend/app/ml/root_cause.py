from typing import Any
from backend.app.schemas.common import FailureTypeEnum

RECOVERABILITY_CLASSES = ["HIGH", "MEDIUM", "LOW", "NOT_RECOMMENDED"]

class RootCauseEngine:
    """
    Root-Cause Intelligence Engine for RecoverAI.
    Translates normalized payment failure taxonomy and customer context into
    explainable root-cause diagnostics and recoverability risk tiers.
    """

    @staticmethod
    def analyze_root_cause(
        failure_type: str,
        error_description: str | None = None,
        customer_success_rate: float = 0.80,
        retry_count: int = 0,
        recovery_probability: float = 0.50,
    ) -> dict[str, Any]:
        """
        Generates explainable root-cause intelligence and recoverability classification.
        """
        ft = failure_type.upper() if failure_type else FailureTypeEnum.TEMPORARY_BANK_DECLINE.value

        if ft == FailureTypeEnum.TEMPORARY_BANK_DECLINE.value:
            rec_class = "HIGH" if customer_success_rate >= 0.70 else "MEDIUM"
            confidence = min(0.95, max(0.65, recovery_probability + 0.05))
            explanation = (
                "Transient issuer throttling or temporary bank clearing blockage detected. "
                "Historical payment reliability indicates high resolution probability after a cooldown window."
            )

        elif ft == FailureTypeEnum.NETWORK_ERROR.value:
            rec_class = "HIGH" if retry_count == 0 else "MEDIUM"
            confidence = min(0.92, max(0.60, recovery_probability + 0.04))
            explanation = (
                "Transient communication or gateway socket timeout during payment authorization. "
                "Immediate or short-interval retry exhibits strong capture probability."
            )

        elif ft == FailureTypeEnum.INSUFFICIENT_FUNDS.value:
            rec_class = "MEDIUM" if customer_success_rate >= 0.65 else "LOW"
            confidence = min(0.85, max(0.50, recovery_probability))
            explanation = (
                "Customer account balance insufficient at settlement attempt. "
                "Interactive payment link or secondary account top-up notification recommended."
            )

        elif ft == FailureTypeEnum.BANK_DECLINE.value:
            rec_class = "MEDIUM" if recovery_probability >= 0.50 else "LOW"
            confidence = min(0.82, max(0.45, recovery_probability))
            explanation = (
                "Card network or issuer declined the transaction under standard security rules. "
                "Alternative payment method suggestion (e.g. UPI Intent) recommended."
            )

        elif ft == FailureTypeEnum.EXPIRED_METHOD.value:
            rec_class = "LOW"
            confidence = min(0.90, max(0.60, recovery_probability))
            explanation = (
                "Saved payment instrument (card or e-mandate) has expired. "
                "Customer re-authorization with an active payment method required."
            )

        elif ft == FailureTypeEnum.INVALID_DETAILS.value:
            rec_class = "NOT_RECOMMENDED"
            confidence = 0.98
            explanation = (
                "Invalid card credentials, CVV, or authentication parameters provided. "
                "Automated charging blocked to protect customer experience and fraud score."
            )

        else:
            rec_class = "MEDIUM"
            confidence = 0.50
            explanation = "Unclassified payment failure. Standard retry heuristic applied."

        return {
            "root_cause": ft,
            "explanation": explanation,
            "recoverability_class": rec_class,
            "confidence": round(confidence, 2),
        }

root_cause_engine = RootCauseEngine()
