import logging
from typing import Any
from backend.app.schemas.recovery import AIRecommendationDetail, AgentMetadata
from backend.app.agent.providers import get_ai_provider, BaseAIProvider, DeterministicFallbackProvider

logger = logging.getLogger("recoverai.agent")

AGENT_VERSION = "recovery-agent-v1"
PROMPT_VERSION = "prompt-v1"

class AIAgentService:
    """
    AI Autonomous Recommendation Agent for Payment Recovery.
    Provides structured, safe recommendations combining root-cause intelligence, ML probabilities,
    customer profiles, and safe guardrail heuristics.
    
    ARCHITECTURAL GUARANTEES:
    - RECOMMENDATION AUTHORITY ONLY. NO execution authority.
    - Cannot execute payments, call payment gateways, or modify transaction state.
    - AI output is an advisory recommendation evaluated by the deterministic Policy Engine.
    - Consumes ML recovery probability and expected recovery without modification.
    """

    def __init__(self, provider: BaseAIProvider | None = None):
        self.provider = provider or get_ai_provider()
        self.fallback = DeterministicFallbackProvider(agent_version=AGENT_VERSION, prompt_version=PROMPT_VERSION)

    def generate_recommendation(
        self,
        transaction_amount: float,
        payment_method: str,
        failure_type: str,
        error_description: str | None,
        customer_name: str,
        customer_success_rate: float,
        customer_success_count: int,
        customer_failed_count: int,
        retry_count: int,
        message_count: int,
        recovery_probability: float,
        is_opted_out: bool,
        has_open_dispute: bool,
        is_systemic_incident: bool = False,
        expected_recovery: float | None = None,
        priority_score: float | None = None,
        root_cause: str | None = None,
        recoverability_class: str | None = None,
    ) -> AIRecommendationDetail:
        """
        Produces a validated AIRecommendationDetail conforming strictly to the approved action taxonomy.
        """
        context = {
            "transaction_amount": transaction_amount,
            "payment_method": payment_method,
            "failure_type": failure_type,
            "error_description": error_description,
            "customer_name": customer_name,
            "customer_success_rate": customer_success_rate,
            "customer_success_count": customer_success_count,
            "customer_failed_count": customer_failed_count,
            "retry_count": retry_count,
            "message_count": message_count,
            "recovery_probability": recovery_probability,
            "expected_recovery": expected_recovery if expected_recovery is not None else round(transaction_amount * recovery_probability, 2),
            "priority_score": priority_score if priority_score is not None else 50.0,
            "root_cause": root_cause or failure_type,
            "recoverability_class": recoverability_class or "HIGH",
            "is_opted_out": is_opted_out,
            "has_open_dispute": has_open_dispute,
            "is_systemic_incident": is_systemic_incident,
        }

        detail, _ = self.recommend_with_metadata(context)
        return detail

    def recommend_with_metadata(
        self,
        context: dict[str, Any],
        provider_override: BaseAIProvider | None = None,
    ) -> tuple[AIRecommendationDetail, AgentMetadata]:
        """
        Executes recommendation pipeline through configured provider with fallback safety and metadata.
        """
        active_provider = provider_override or self.provider or self.fallback
        try:
            detail, meta = active_provider.recommend(context)
            return detail, meta
        except Exception as e:
            logger.warning(f"Provider {active_provider.__class__.__name__} failed ({e}). Using deterministic fallback.")
            return self.fallback.recommend(context)


ai_agent = AIAgentService()
