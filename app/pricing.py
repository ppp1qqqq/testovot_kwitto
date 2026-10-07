"""Деньги считаем только в копейках и только целыми числами."""

# код промокода -> скидка в процентах
PROMO_CODES: dict[str, int] = {"KVITTO10": 10}


def normalize_promo_code(code: str) -> str:
    return code.strip().upper()


def calc_discount(price: int, percent: int) -> int:
    # Округляем до целой копейки, половина копейки уходит вверх.
    # Для наших тарифов скидка и так делится нацело, но цены могут поменяться.
    return (price * percent + 50) // 100


def split_into_installments(amount: int, months: int) -> list[int]:
    """Делит сумму на равные части. Лишние копейки достаются первым платежам."""
    if months <= 0:
        raise ValueError("months must be positive")
    base, rest = divmod(amount, months)
    return [base + 1 if i < rest else base for i in range(months)]
