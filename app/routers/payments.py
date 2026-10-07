from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.enums import PaymentStatus
from app.models import Payment
from app.schemas import PaymentCreate, PaymentOut
from app.services import TariffNotFound, create_payment

router = APIRouter(tags=["payments"])


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment_view(
    data: PaymentCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, max_length=255),
    session: Session = Depends(get_session),
) -> Payment:
    try:
        payment, created = create_payment(session, data, idempotency_key)
    except TariffNotFound:
        # Тариф приходит в теле запроса, поэтому это ошибка валидации, а не 404.
        # Формат ответа такой же, как у остальных 422 от FastAPI.
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "tariff_id"),
                    "msg": "Value error, tariff not found",
                    "input": data.tariff_id,
                }
            ]
        ) from None

    if not created:
        response.status_code = status.HTTP_200_OK
    return payment


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(
    email: str | None = None,
    status_: PaymentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[Payment]:
    query = select(Payment).order_by(Payment.id)
    if email is not None:
        query = query.where(Payment.email == email)
    if status_ is not None:
        query = query.where(Payment.status == status_)
    return list(session.scalars(query.limit(limit).offset(offset)))


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: int, session: Session = Depends(get_session)) -> Payment:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment
