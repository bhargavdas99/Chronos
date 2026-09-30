from pydantic import BaseModel, Field
from decimal import Decimal
import uuid
from enum import Enum


class EntryType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    RESERVATION_HOLD = "RESERVATION_HOLD"
    RESERVATION_COMMIT = "RESERVATION_COMMIT"


class CreateAccountRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    initial_balance: Decimal = Field(
        ge=Decimal("0.0000"), max_digits=12, decimal_places=4, default=Decimal("0.0000")
    )


class TransactionRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    amount: Decimal = Field(ge=Decimal("0.0000"), max_digits=12, decimal_places=4)
    entry_type: EntryType
    reference_id: uuid.UUID | None = None
