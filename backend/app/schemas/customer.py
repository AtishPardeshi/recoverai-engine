from datetime import datetime
from pydantic import BaseModel, Field

class CustomerBase(BaseModel):
    external_id: str
    name: str
    historical_success_rate: float = Field(ge=0.0, le=1.0)
    total_transaction_value: float = Field(ge=0.0)
    successful_payment_count: int = Field(ge=0)
    failed_payment_count: int = Field(ge=0)
    is_opted_out: bool = False
    has_open_dispute: bool = False

class CustomerCreate(CustomerBase):
    pass

class CustomerResponse(CustomerBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True
