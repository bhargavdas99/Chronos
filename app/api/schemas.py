from decimal import Decimal
from enum import Enum
import uuid
from pydantic import BaseModel, Field, model_validator


class EntryType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    RESERVATION_HOLD = "RESERVATION_HOLD"
    RESERVATION_COMMIT = "RESERVATION_COMMIT"


class CreateAccountRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    initial_balance: Decimal = Field(
        ge=Decimal("0.0000"),
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0000"),
    )


class TransactionRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    amount: Decimal = Field(
        gt=Decimal("0.0000"),
        max_digits=12,
        decimal_places=4,
    )
    entry_type: EntryType
    idempotency_key: uuid.UUID | None = None
    reference_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_reservation_commit_reference(self) -> "TransactionRequest":
        if self.entry_type == EntryType.RESERVATION_COMMIT and not self.reference_id:
            raise ValueError(
                "reference_id is required when entry_type is RESERVATION_COMMIT."
            )
        return self
