from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

from app.enums import PaymentMethod, PaymentStatus
from app.pricing import PROMO_CODES, normalize_promo_code


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: int


class PaymentCreate(BaseModel):
    tariff_id: int
    email: EmailStr
    method: PaymentMethod
    installment_months: Literal[3, 6, 12] | None = None
    promo_code: str | None = None

    @field_validator("promo_code")
    @classmethod
    def check_promo_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = normalize_promo_code(value)
        if code not in PROMO_CODES:
            raise ValueError("unknown promo code")
        return code

    @model_validator(mode="after")
    def check_installment_months(self) -> "PaymentCreate":
        if self.method == PaymentMethod.INSTALLMENT and self.installment_months is None:
            raise ValueError("installment_months is required for installment (3, 6 or 12)")
        if self.method != PaymentMethod.INSTALLMENT and self.installment_months is not None:
            raise ValueError("installment_months is allowed only for installment")
        return self


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: PaymentStatus
    tariff_id: int
    amount: int
    discount: int
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None
    email: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def assume_utc(cls, value: datetime) -> datetime:
        # SQLite не хранит часовой пояс и отдаёт naive datetime, а пишем мы всегда UTC
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class BankWebhook(BaseModel):
    payment_id: int
    status: PaymentStatus
