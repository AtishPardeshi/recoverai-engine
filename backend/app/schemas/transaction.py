from datetime import datetime
from pydantic import BaseModel, Field
from backend.app.schemas.common import PaymentMethodEnum, TransactionStatusEnum, FailureTypeEnum
from backend.app.schemas.customer import CustomerResponse

class PaymentFailureResponse(BaseModel):
    id: str
    transaction_id: str
    error_code: str
    error_description: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    error_reason: str | None = None
    normalized_failure_type: FailureTypeEnum
    occurred_at: datetime

    class Config:
        from_attributes = True

class TransactionResponse(BaseModel):
    id: str
    external_id: str
    customer_id: str
    amount: float = Field(gt=0.0)
    currency: str = "INR"
    payment_method: PaymentMethodEnum
    status: TransactionStatusEnum
    created_at: datetime
    updated_at: datetime
    customer: CustomerResponse | None = None
    payment_failure: PaymentFailureResponse | None = None

    class Config:
        from_attributes = True
