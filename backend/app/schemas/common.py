from enum import Enum
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class PaymentMethodEnum(str, Enum):
    CARD = "CARD"
    UPI = "UPI"
    NETBANKING = "NETBANKING"
    WALLET = "WALLET"
    EMANDATE = "EMANDATE"

class TransactionStatusEnum(str, Enum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    RECOVERY_ELIGIBLE = "RECOVERY_ELIGIBLE"
    RECOVERY_IN_PROGRESS = "RECOVERY_IN_PROGRESS"
    RECOVERED = "RECOVERED"
    RECOVERY_EXHAUSTED = "RECOVERY_EXHAUSTED"
    ESCALATED = "ESCALATED"
    STOPPED = "STOPPED"

class FailureTypeEnum(str, Enum):
    TEMPORARY_BANK_DECLINE = "TEMPORARY_BANK_DECLINE"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    BANK_DECLINE = "BANK_DECLINE"
    NETWORK_ERROR = "NETWORK_ERROR"
    EXPIRED_METHOD = "EXPIRED_METHOD"
    INVALID_DETAILS = "INVALID_DETAILS"

class RecoveryActionTypeEnum(str, Enum):
    RETRY_PAYMENT = "RETRY_PAYMENT"
    DELAYED_RETRY = "DELAYED_RETRY"
    SEND_PAYMENT_LINK = "SEND_PAYMENT_LINK"
    SUGGEST_ALTERNATIVE_PAYMENT_METHOD = "SUGGEST_ALTERNATIVE_PAYMENT_METHOD"
    SEND_REMINDER = "SEND_REMINDER"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    STOP_RECOVERY = "STOP_RECOVERY"

class GuardrailDecisionEnum(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class OutcomeTypeEnum(str, Enum):
    BASELINE = "BASELINE"
    AGENT_RECOVERY = "AGENT_RECOVERY"

class OutcomeResultEnum(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    SKIPPED = "SKIPPED"

class ActorTypeEnum(str, Enum):
    SYSTEM = "SYSTEM"
    ML = "ML"
    AI_AGENT = "AI_AGENT"
    POLICY_ENGINE = "POLICY_ENGINE"
    EXECUTOR = "EXECUTOR"
    SIMULATOR = "SIMULATOR"
    HUMAN = "HUMAN"
    OPERATOR = "OPERATOR"

class NotificationChannelEnum(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    PAYMENT_LINK = "PAYMENT_LINK"
    REMINDER = "REMINDER"

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None

class ErrorResponse(BaseModel):
    error: ErrorDetail

class PaginationMetadata(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    pagination: PaginationMetadata
