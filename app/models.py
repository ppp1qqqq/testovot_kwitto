from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import PaymentMethod, PaymentStatus


def _str_enum(enum_cls: type[StrEnum]) -> Enum:
    # Храним в базе значения ("pending"), а не имена членов ("PENDING"),
    # чтобы в таблице было то же, что и в API.
    return Enum(
        enum_cls,
        native_enum=False,
        length=16,
        values_callable=lambda cls: [item.value for item in cls],
    )


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(64), unique=True)
    price: Mapped[int]  # в копейках


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"))
    email: Mapped[str] = mapped_column(String(320), index=True)
    method: Mapped[PaymentMethod] = mapped_column(_str_enum(PaymentMethod))
    installment_months: Mapped[int | None]
    promo_code: Mapped[str | None] = mapped_column(String(32))
    # amount и discount в копейках, amount = цена тарифа - discount
    amount: Mapped[int]
    discount: Mapped[int]
    schedule: Mapped[list[int] | None] = mapped_column(JSON)
    status: Mapped[PaymentStatus] = mapped_column(
        _str_enum(PaymentStatus), default=PaymentStatus.PENDING, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
