import json
import re
from typing import Any

CONTROLLED_RISK_FLAGS = [
    "LOW_RECOVERY_PROBABILITY",
    "HIGH_RETRY_COUNT",
    "SYSTEMIC_INCIDENT",
    "CUSTOMER_OPTED_OUT",
    "OPEN_DISPUTE",
    "LOW_MODEL_CONFIDENCE",
    "PAYMENT_METHOD_UNRELIABLE",
    "FAILURE_NOT_RECOVERABLE",
    "RECOVERY_WINDOW_EXCEEDED",
    "HUMAN_REVIEW_REQUIRED",
    "COMMUNICATION_LIMIT_REACHED",
    "INVALID_CREDENTIALS",
    "ACTIVE_CHARGEBACK_DISPUTE",
    "SYSTEMIC_PROVIDER_OUTAGE",
    "COMPLIANCE_OPT_OUT",
    "MAX_RETRIES_REACHED",
]

SYSTEM_PROMPT = """You are a payment revenue recovery recommendation agent.
You analyze failed payment case context and recommend the single most effective, compliant recovery action.

CRITICAL CONSTRAINTS:
1. You may recommend ONLY one action from this approved enum:
   - RETRY_PAYMENT
   - DELAYED_RETRY
   - SEND_PAYMENT_LINK
   - SUGGEST_ALTERNATIVE_PAYMENT_METHOD
   - SEND_REMINDER
   - ESCALATE_TO_HUMAN
   - STOP_RECOVERY

2. You have RECOMMENDATION AUTHORITY ONLY. You have NO execution authority.
3. You must NEVER call tools, execute payments, call payment gateways, send live messages, modify records, or bypass policy guardrails.
4. Use ONLY the supplied case context. Do not invent facts, error codes, payment methods, or actions.
5. Return ONLY a valid JSON object matching the exact schema below. Do not include markdown codeblocks, explanation text, or chain-of-thought.
6. The 'reason' must be concise (maximum 500 characters).
7. The 'expected_recovery' must strictly match the ML-provided expected_recovery from the input. Do not alter or recalculate this value.
8. The 'confidence' represents your confidence in the recommended action (float between 0.0 and 1.0), distinct from ML recovery probability.

JSON SCHEMA:
{
  "recommended_action": "RETRY_PAYMENT | DELAYED_RETRY | SEND_PAYMENT_LINK | SUGGEST_ALTERNATIVE_PAYMENT_METHOD | SEND_REMINDER | ESCALATE_TO_HUMAN | STOP_RECOVERY",
  "root_cause": "TEMPORARY_BANK_DECLINE | INSUFFICIENT_FUNDS | BANK_DECLINE | NETWORK_ERROR | EXPIRED_METHOD | INVALID_DETAILS | ...",
  "reason": "Concise justification under 500 characters.",
  "confidence": 0.85,
  "expected_recovery": 1234.56,
  "risk_flags": ["HIGH_RETRY_COUNT", "..."],
  "requires_human_review": false
}
"""

def sanitize_untrusted_input(val: Any, max_len: int = 200) -> str:
    """
    Sanitizes untrusted string fields (customer name, notes, failure descriptions)
    to prevent prompt injection and schema corruption.
    """
    if val is None:
        return "N/A"
    s = str(val)
    # Strip non-printable / control characters
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", s)
    # Neutralize instruction injection attempts by escaping delimiters
    s = s.replace("```", "").replace("System:", "").replace("Assistant:", "").strip()
    return s[:max_len]


def build_case_prompt(context: dict[str, Any]) -> str:
    """
    Constructs a structured JSON-safe payload for the AI recommendation prompt.
    """
    safe_payload = {
        "transaction": {
            "amount": float(context.get("transaction_amount", 0.0)),
            "payment_method": sanitize_untrusted_input(context.get("payment_method", "CARD")),
            "failure_type": sanitize_untrusted_input(context.get("failure_type", "TEMPORARY_BANK_DECLINE")),
            "error_description": sanitize_untrusted_input(context.get("error_description", "None")),
        },
        "customer": {
            "name": sanitize_untrusted_input(context.get("customer_name", "Anonymous")),
            "historical_success_rate": float(context.get("customer_success_rate", 0.80)),
            "prior_successes": int(context.get("customer_success_count", 0)),
            "prior_failures": int(context.get("customer_failed_count", 0)),
            "is_opted_out": bool(context.get("is_opted_out", False)),
            "has_open_dispute": bool(context.get("has_open_dispute", False)),
        },
        "recovery_status": {
            "retry_count": int(context.get("retry_count", 0)),
            "message_count": int(context.get("message_count", 0)),
            "systemic_incident_active": bool(context.get("is_systemic_incident", False)),
        },
        "ml_intelligence": {
            "recovery_probability": float(context.get("recovery_probability", 0.50)),
            "expected_recovery": float(context.get("expected_recovery", 0.0)),
            "priority_score": float(context.get("priority_score", 50.0)),
            "root_cause": sanitize_untrusted_input(context.get("root_cause", "TEMPORARY_BANK_DECLINE")),
            "recoverability_class": sanitize_untrusted_input(context.get("recoverability_class", "HIGH")),
        },
    }

    return f"Case Context:\n{json.dumps(safe_payload, indent=2)}\n\nRecommend the optimal recovery action."
