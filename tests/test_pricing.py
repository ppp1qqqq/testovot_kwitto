import pytest

from app.pricing import calc_discount, normalize_promo_code, split_into_installments


def test_example_from_task():
    assert split_into_installments(1_990_000, 3) == [663_334, 663_333, 663_333]


@pytest.mark.parametrize("amount", [990_000, 1_990_000, 2_990_000, 1_791_000, 1, 0, 100_001])
@pytest.mark.parametrize("months", [3, 6, 12])
def test_schedule_sum_is_exact(amount, months):
    schedule = split_into_installments(amount, months)
    assert len(schedule) == months
    assert sum(schedule) == amount
    # части отличаются максимум на копейку, и крупнее всегда первые
    assert max(schedule) - min(schedule) <= 1
    assert schedule == sorted(schedule, reverse=True)


def test_extra_kopecks_go_first():
    # 100 копеек на 12 месяцев: 8 * 12 = 96, лишние 4 копейки в первые 4 платежа
    assert split_into_installments(100, 12) == [9, 9, 9, 9, 8, 8, 8, 8, 8, 8, 8, 8]


def test_split_rejects_zero_months():
    with pytest.raises(ValueError):
        split_into_installments(100, 0)


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (990_000, 99_000),
        (1_990_000, 199_000),
        (2_990_000, 299_000),
        (999, 100),  # 99.9 копейки -> 100
        (994, 99),  # 99.4 копейки -> 99
        (995, 100),  # ровно половина копейки уходит вверх
    ],
)
def test_discount_rounding(price, expected):
    assert calc_discount(price, 10) == expected


@pytest.mark.parametrize("raw", ["KVITTO10", "kvitto10", "Kvitto10", "  kvitto10 "])
def test_promo_code_normalization(raw):
    assert normalize_promo_code(raw) == "KVITTO10"
