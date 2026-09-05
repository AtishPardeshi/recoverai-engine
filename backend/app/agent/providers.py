import json
import logging
from abc import ABC, abstractmethod
from typing import Any
from pydantic import ValidationError
from backend.app.schemas.common import RecoveryActionTypeEnum, FailureTypeEnum
from backend.app.schemas.recovery import AIRecommendationDetail, AgentMetadata
from backend.app.agent.prompts import SYSTEM_PROMPT, build_case_prompt, CONTROLLED_RISK_FLAGS
from backend.app.config.config import settings

logger = logging.getLogger("recoverai.agent")

class BaseAIProvider(ABC):
    """
    Abstract interface for AI Recommendation Providers.
    Advisory only: produces AIRecommendationDetail with NO execution authority.
    """

    @abstractmethod
    def recommend(self, context: dict[str, Any]) -> tuple[AIRecommendationDetail, AgentMetadata]:
        pass


class DeterministicFallbackProvider(BaseAIProvider):
    """
    Deterministic rule-matrix recommendation provider.
    Evaluates ML recovery risk, root-cause taxonomy, safety guardrails,
    customer history, and systemic indicators 100% offline.
    """

    def __init__(self, agent_version: str = "recovery-agent-v1", prompt_version: str = "prompt-v1"):
        self.agent_version = agent_version
        self.prompt_version = prompt_version

    def recommend(self, context: dict[str, Any]) -> tuple[AIRecommendationDetail, AgentMetadata]:
        amount = float(context.get("transaction_amount", 0.0))
        rec_prob = float(context.get("recovery_probability", 0.50))
        expected_rec = float(context.get("expected_recovery", round(amount * rec_prob, 2)))
        ft = str(context.get("failure_type", "TEMPORARY_BANK_DECLINE"))
        retry_count = int(context.get("retry_count", 0))
        message_count = int(context.get("message_count", 0))
        cust_rate = float(context.get("customer_success_rate", 0.80))
        is_opted_out = bool(context.get("is_opted_out", False))
        has_open_dispute = bool(context.get("has_open_dispute", False))
        is_systemic_incident = bool(context.get("is_systemic_incident", False))
        cust_name = str(context.get("customer_name", "Customer"))

        risk_flags = []

        # 1. Customer Opt-Out Constraint
        if is_opted_out:
            risk_flags.append("CUSTOMER_OPTED_OUT")
            risk_flags.append("COMPLIANCE_OPT_OUT")
            detail = AIRecommendationDetail(
                recommended_action=RecoveryActionTypeEnum.STOP_RECOVERY,
                root_cause="COMPLIANCE_OPT_OUT",
                reason=f"Customer {cust_name} has opted out of automated recovery outreach.",
                confidence=0.99,
                expected_recovery=0.0,
                risk_flags=risk_flags,
                requires_human_review=False,
            )
            return detail, self._metadata("deterministic-rule-matrix", "fallback")

        # 2. Active Chargeback Dispute Constraint
        if has_open_dispute:
            risk_flags.append("OPEN_DISPUTE")
            risk_flags.append("ACTIVE_CHARGEBACK_DISPUTE")
            risk_flags.append("HUMAN_REVIEW_REQUIRED")
            detail = AIRecommendationDetail(
                recommended_action=RecoveryActionTypeEnum.ESCALATE_TO_HUMAN,
                root_cause="DISPUTE_HOLD",
                reason="Active payment dispute detected on customer account. Escalating to compliance officer.",
                confidence=0.95,
                expected_recovery=0.0,
                risk_flags=risk_flags,
                requires_human_review=True,
            )
            return detail, self._metadata("deterministic-rule-matrix", "fallback")

        # 3. Systemic Incident / Outage Handling
        if is_systemic_incident:
            risk_flags.append("SYSTEMIC_INCIDENT")
            risk_flags.append("SYSTEMIC_PROVIDER_OUTAGE")
            if retry_count >= 2:
                detail = AIRecommendationDetail(
                    recommended_action=RecoveryActionTypeEnum.ESCALATE_TO_HUMAN,
                    root_cause="SYSTEMIC_BANK_OUTAGE",
                    reason="Correlated failure spike with prior retries. Escalating for systemic outage monitoring.",
                    confidence=0.80,
                    expected_recovery=expected_rec,
                    risk_flags=risk_flags,
                    requires_human_review=True,
                )
            else:
                detail = AIRecommendationDetail(
                    recommended_action=RecoveryActionTypeEnum.DELAYED_RETRY,
                    root_cause="SYSTEMIC_BANK_OUTAGE",
                    reason="Correlated failure spike detected on provider network. Retries throttled until outage resolution.",
                    confidence=0.75,
                    expected_recovery=expected_rec,
                    risk_flags=risk_flags,
                    requires_human_review=False,
                )
            return detail, self._metadata("deterministic-rule-matrix", "fallback")

        # 4. Retry Exhaustion Threshold
        if retry_count >= settings.MAX_AUTOMATED_RETRIES:
            risk_flags.append("HIGH_RETRY_COUNT")
            risk_flags.append("MAX_RETRIES_REACHED")
            detail = AIRecommendationDetail(
                recommended_action=RecoveryActionTypeEnum.STOP_RECOVERY,
                root_cause="RECOVERY_ATTEMPTS_EXHAUSTED",
                reason=f"Reached maximum automated retry threshold ({retry_count}/{settings.MAX_AUTOMATED_RETRIES}). Stopping automated charging.",
                confidence=0.92,
                expected_recovery=0.0,
                risk_flags=risk_flags,
                requires_human_review=False,
            )
            return detail, self._metadata("deterministic-rule-matrix", "fallback")

        # 5. Low Recovery Probability Branch
        if rec_prob < 0.30:
            risk_flags.append("LOW_RECOVERY_PROBABILITY")
            if ft == FailureTypeEnum.INVALID_DETAILS.value:
                risk_flags.append("FAILURE_NOT_RECOVERABLE")
                risk_flags.append("INVALID_CREDENTIALS")
                detail = AIRecommendationDetail(
                    recommended_action=RecoveryActionTypeEnum.STOP_RECOVERY,
                    root_cause=ft,
                    reason="Low recovery probability with invalid payment credentials. Terminating recovery to protect gateway score.",
                    confidence=0.95,
                    expected_recovery=0.0,
                    risk_flags=risk_flags,
                    requires_human_review=False,
                )
            else:
                risk_flags.append("HUMAN_REVIEW_REQUIRED")
                detail = AIRecommendationDetail(
                    recommended_action=RecoveryActionTypeEnum.ESCALATE_TO_HUMAN,
                    root_cause=ft,
                    reason=f"Sub-30% ML recovery probability ({int(rec_prob*100)}%). Manual intervention required.",
                    confidence=0.80,
                    expected_recovery=expected_rec,
                    risk_flags=risk_flags,
                    requires_human_review=True,
                )
            return detail, self._metadata("deterministic-rule-matrix", "fallback")

        # 6. Failure Taxonomy-Driven Actions
        if ft == FailureTypeEnum.TEMPORARY_BANK_DECLINE.value:
            detail = AIRecommendationDetail(
                recommended_action=RecoveryActionTypeEnum.DELAYED_RETRY,
                root_cause=ft,
                reason=(
                    f"Transient bank decline detected with strong historical payment success ({int(cust_rate * 100)}%) "
                    f"and high recovery probability. Scheduling delayed retry post bank clearing cycle."
                ),
                confidence=round(min(0.95, max(0.60, rec_prob + 0.05)), 2),
                expected_recovery=expected_rec,
                risk_flags=risk_flags,
                requires_human_review=False,
            )
        elif ft == FailureTypeEnum.NETWORK_ERROR.value:
            action = RecoveryActionTypeEnum.DELAYED_RETRY if retry_count > 0 else RecoveryActionTypeEnum.RETRY_PAYMENT
            detail = AIRecommendationDetail(
                recommended_action=action,
                root_cause=ft,
                reason="Network gateway socket timeout. Short-delay retry recommended to capture before customer session drops.",
                confidence=round(min(0.92, max(0.60, rec_prob + 0.04)), 2),
                expected_recovery=expected_rec,
                risk_flags=risk_flags,
                requires_human_review=False,
            )
        elif ft == FailureTypeEnum.INSUFFICIENT_FUNDS.value:
            if message_count >= settings.MAX_MESSAGES_PER_RECOVERY_CASE:
                risk_flags.append("COMMUNICATION_LIMIT_REACHED")
                risk_flags.append("HUMAN_REVIEW_REQUIRED")
                detail = AIRecommendationDetail(
                    recommended_action=RecoveryActionTypeEnum.ESCALATE_TO_HUMAN,
                    root_cause=ft,
                    reason="Customer notification limit reached for balance top-up. Escalating to account representative.",
                    confidence=0.85,
                    expected_recovery=expected_rec,
                    risk_flags=risk_flags,
                    requires_human_review=True,
                )
            else:
                detail = AIRecommendationDetail(
                    recommended_action=RecoveryActionTypeEnum.SEND_PAYMENT_LINK,
                    root_cause=ft,
                    reason="Insufficient account balance. Dispatching frictionless Payment Link allowing alternate card/UPI completion.",
                    confidence=round(min(0.88, max(0.50, rec_prob + 0.02)), 2),
                    expected_recovery=expected_rec,
                    risk_flags=risk_flags,
                    requires_human_review=False,
                )
        elif ft == FailureTypeEnum.EXPIRED_METHOD.value:
            detail = AIRecommendationDetail(
                recommended_action=RecoveryActionTypeEnum.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
                root_cause=ft,
                reason="Saved payment mandate or card instrument has expired. Prompting customer to update payment credentials.",
                confidence=0.82,
                expected_recovery=expected_rec,
                risk_flags=risk_flags,
                requires_human_review=False,
            )
        elif ft == FailureTypeEnum.INVALID_DETAILS.value:
            risk_flags.append("FAILURE_NOT_RECOVERABLE")
            risk_flags.append("INVALID_CREDENTIALS")
            detail = AIRecommendationDetail(
                recommended_action=RecoveryActionTypeEnum.STOP_RECOVERY,
                root_cause=ft,
                reason="Invalid card/authentication details entered. Automated retries prohibited; stopping recovery.",
                confidence=0.98,
                expected_recovery=0.0,
                risk_flags=risk_flags,
                requires_human_review=False,
            )
        elif ft == FailureTypeEnum.BANK_DECLINE.value:
            if retry_count == 0 and cust_rate > 0.80:
                action = RecoveryActionTypeEnum.DELAYED_RETRY
            else:
                action = RecoveryActionTypeEnum.SUGGEST_ALTERNATIVE_PAYMENT_METHOD
            detail = AIRecommendationDetail(
                recommended_action=action,
                root_cause=ft,
                reason="Issuer bank decline. Suggesting alternative payment route or deferred clearing retry.",
                confidence=round(max(0.50, rec_prob), 2),
                expected_recovery=expected_rec,
                risk_flags=risk_flags,
                requires_human_review=False,
            )
        else:
            detail = AIRecommendationDetail(
                recommended_action=RecoveryActionTypeEnum.DELAYED_RETRY,
                root_cause="UNCLASSIFIED_DECLINE",
                reason="Unclassified decline. Applying standard bounded recovery policy.",
                confidence=0.60,
                expected_recovery=expected_rec,
                risk_flags=risk_flags,
                requires_human_review=False,
            )

        return detail, self._metadata("deterministic-rule-matrix", "fallback")

    def _metadata(self, model_name: str, prediction_source: str) -> AgentMetadata:
        return AgentMetadata(
            agent_version=self.agent_version,
            prompt_version=self.prompt_version,
            provider="fallback",
            model_name=model_name,
            prediction_source=prediction_source,
        )


class GeminiProvider(BaseAIProvider):
    """
    Google Gemini AI recommendation provider.
    Validates LLM outputs against strict Pydantic contract; falls back to DeterministicFallbackProvider
    on timeout, network error, or schema validation failure.
    """

    def __init__(self, api_key: str | None = None, model_name: str = "gemini-1.5-pro", fallback: BaseAIProvider | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name
        self.fallback = fallback or DeterministicFallbackProvider()

    def recommend(self, context: dict[str, Any]) -> tuple[AIRecommendationDetail, AgentMetadata]:
        if not self.api_key:
            logger.info("Gemini API key not configured. Using deterministic fallback.")
            return self.fallback.recommend(context)

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT,
            )
            prompt = build_case_prompt(context)
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json", "temperature": 0.1},
            )
            raw_text = response.text.strip()
            data = json.loads(raw_text)
            
            # Enforce expected_recovery strictly from ML context
            data["expected_recovery"] = float(context.get("expected_recovery", 0.0))
            
            detail = AIRecommendationDetail(**data)
            meta = AgentMetadata(
                agent_version="recovery-agent-v1",
                prompt_version="prompt-v1",
                provider="gemini",
                model_name=self.model_name,
                prediction_source="llm",
            )
            return detail, meta
        except Exception as e:
            logger.warning(f"Gemini recommendation failed ({e}). Gracefully falling back to deterministic matrix.")
            detail, meta = self.fallback.recommend(context)
            meta.provider = "gemini"
            meta.prediction_source = "fallback"
            return detail, meta


class OpenAIProvider(BaseAIProvider):
    """
    OpenAI-compatible AI recommendation provider.
    Validates LLM outputs against strict Pydantic contract; falls back to DeterministicFallbackProvider
    on timeout, network error, or schema validation failure.
    """

    def __init__(self, api_key: str | None = None, model_name: str = "gpt-4o-mini", fallback: BaseAIProvider | None = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = model_name
        self.fallback = fallback or DeterministicFallbackProvider()

    def recommend(self, context: dict[str, Any]) -> tuple[AIRecommendationDetail, AgentMetadata]:
        if not self.api_key:
            logger.info("OpenAI API key not configured. Using deterministic fallback.")
            return self.fallback.recommend(context)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            prompt = build_case_prompt(context)
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=5.0,
            )
            raw_text = response.choices[0].message.content or "{}"
            data = json.loads(raw_text)
            
            # Enforce expected_recovery strictly from ML context
            data["expected_recovery"] = float(context.get("expected_recovery", 0.0))
            
            detail = AIRecommendationDetail(**data)
            meta = AgentMetadata(
                agent_version="recovery-agent-v1",
                prompt_version="prompt-v1",
                provider="openai",
                model_name=self.model_name,
                prediction_source="llm",
            )
            return detail, meta
        except Exception as e:
            logger.warning(f"OpenAI recommendation failed ({e}). Gracefully falling back to deterministic matrix.")
            detail, meta = self.fallback.recommend(context)
            meta.provider = "openai"
            meta.prediction_source = "fallback"
            return detail, meta


def get_ai_provider(provider_type: str | None = None) -> BaseAIProvider:
    """
    Factory creating the configured AI recommendation provider.
    """
    p_type = (provider_type or settings.AI_PROVIDER).lower()
    fallback = DeterministicFallbackProvider()

    if p_type == "gemini":
        return GeminiProvider(fallback=fallback)
    elif p_type == "openai":
        return OpenAIProvider(fallback=fallback)
    else:
        return fallback
