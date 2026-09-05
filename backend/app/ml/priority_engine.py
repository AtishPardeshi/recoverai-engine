import math

class PriorityEngine:
    """
    Deterministic Priority Scoring and Expected Recovery Calculation Engine.
    Combines recovery probability, recoverable revenue, customer reliability, and attempt count
    into a calibrated 0-100 priority score and formula-derived expected recovery amount.
    """

    @staticmethod
    def calculate_expected_recovery(amount: float, recovery_probability: float) -> float:
        """
        Formula: expected_recovery = recovery_probability * amount
        """
        prob = max(0.0, min(1.0, float(recovery_probability)))
        amt = max(0.0, float(amount))
        return round(prob * amt, 2)

    @staticmethod
    def calculate_priority_score(
        amount: float,
        recovery_probability: float,
        customer_success_rate: float,
        retry_count: int = 0,
    ) -> float:
        """
        Calculates deterministic 0-100 priority score:
        - recovery_probability weight: 40%
        - log-normalized amount weight: 30%
        - customer historical reliability weight: 20%
        - urgency / attempt penalty weight: 10%
        """
        prob = max(0.0, min(1.0, float(recovery_probability)))
        amt = max(100.0, float(amount))
        cust_rate = max(0.0, min(1.0, float(customer_success_rate)))
        retries = max(0, int(retry_count))

        # Log normalization for amount: mapping ₹500 - ₹100,000 smoothly to ~0.1 - 1.0
        amount_factor = min(1.0, max(0.05, math.log(amt) / math.log(100000.0)))

        # Urgency factor: fresh failures (retry=0) have highest urgency
        urgency_factor = max(0.30, 1.0 - (retries * 0.20))

        raw_score = (
            (0.40 * prob) +
            (0.30 * amount_factor) +
            (0.20 * cust_rate) +
            (0.10 * urgency_factor)
        ) * 100.0

        return round(max(0.0, min(100.0, raw_score)), 2)

priority_engine = PriorityEngine()
