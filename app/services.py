from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import PaymentMethod, PaymentStatus, can_transition
from app.models import Payment, Tariff
from app.pricing import PROMO_CODES, calc_discount, split_into_installments
from app.schemas import PaymentCreate


class TariffNotFound(Exception):
    pass


class PaymentNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


def get_payment_by_key(session: Session, key: str) -> Payment | None:
    return session.scalar(select(Payment).where(Payment.idempotency_key == key))


def create_payment(
    session: Session, data: PaymentCreate, idempotency_key: str | None
) -> tuple[Payment, bool]:
    """Возвращает (платёж, создан ли он сейчас)."""
    if idempotency_key is not None:
        existing = get_payment_by_key(session, idempotency_key)
        if existing is not None:
            return existing, False

    tariff = session.get(Tariff, data.tariff_id)
    if tariff is None:
        raise TariffNotFound(data.tariff_id)

    discount = 0
    if data.promo_code is not None:
        discount = calc_discount(tariff.price, PROMO_CODES[data.promo_code])
    amount = tariff.price - discount

    schedule = None
    if data.method == PaymentMethod.INSTALLMENT:
        schedule = split_into_installments(amount, data.installment_months)

    payment = Payment(
        tariff_id=tariff.id,
        email=data.email,
        method=data.method,
        installment_months=data.installment_months,
        promo_code=data.promo_code,
        amount=amount,
        discount=discount,
        schedule=schedule,
        status=PaymentStatus.PENDING,
        idempotency_key=idempotency_key,
    )
    session.add(payment)
    try:
        session.commit()
    except IntegrityError:
        # Два одинаковых запроса пришли одновременно и второй упёрся в unique.
        # Отдаём тот платёж, который успел создаться.
        session.rollback()
        if idempotency_key is None:
            raise
        existing = get_payment_by_key(session, idempotency_key)
        if existing is None:
            raise
        return existing, False

    session.refresh(payment)
    return payment, True


def change_status(session: Session, payment_id: int, new_status: PaymentStatus) -> Payment:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise PaymentNotFound(payment_id)

    current = payment.status
    if not can_transition(current, new_status):
        raise InvalidTransition(current, new_status)

    # Обновляем только если статус всё ещё тот, что мы прочитали.
    # Иначе два вебхука подряд (succeeded и failed) могли бы оба пройти проверку.
    result = session.execute(
        update(Payment)
        .where(Payment.id == payment_id, Payment.status == current)
        .values(status=new_status)
    )
    if result.rowcount == 0:
        session.rollback()
        raise InvalidTransition(current, new_status)
    session.commit()
    session.refresh(payment)
    return payment
