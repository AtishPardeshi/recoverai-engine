import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "RecoverAI"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./recover_ai.db")
    
    # Guardrail Policies
    MAX_AUTOMATED_RETRIES: int = 2
    MIN_RETRY_INTERVAL_HOURS: int = 6
    MAX_PAYMENT_LINK_ATTEMPTS: int = 1
    MAX_RECOVERY_DURATION_HOURS: int = 72
    MAX_MESSAGES_PER_RECOVERY_CASE: int = 2
    POLICY_VERSION: str = "v1.2.0"
    AGENT_VERSION: str = "v1.0.0-calibrated"
    
    # Systemic Incident Threshold
    SYSTEMIC_FAILURE_SPIKE_THRESHOLD: float = 0.25  # 25% spike across same bank/provider
    
    # LLM Settings (Optional external provider)
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY", None)
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY", None)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "auto")  # 'gemini', 'openai', 'calibrated'
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
