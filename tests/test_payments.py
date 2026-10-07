import pytest


def test_tariffs_are_seeded(client):
    resp = client.get("/tariffs")
    assert resp.status_code == 200
    prices = {t["title"]: t["price"] for t in resp.json()}
    assert prices == {"basic": 990_000, "standard": 1_990_000, "premium": 2_990_000}
    assert all(isinstance(p, int) for p in prices.values())


def test_payment_without_promo(create_payment):
    resp = create_payment("standard")
    assert resp.status_code == 201
    payment = resp.json()
    assert payment["amount"] == 1_990_000
    assert payment["discount"] == 0
    assert payment["status"] == "pending"
    assert payment["method"] == "card"
    assert payment["schedule"] is None
    assert payment["installment_months"] is None
    assert payment["email"] == "student@example.com"


@pytest.mark.parametrize("code", ["KVITTO10", "kvitto10", "KvItTo10"])
def test_payment_with_promo(create_payment, code):
    resp = create_payment("standard", promo_code=code)
    assert resp.status_code == 201
    payment = resp.json()
    assert payment["discount"] == 199_000
    assert payment["amount"] == 1_791_000


@pytest.mark.parametrize(
    ("tariff", "amount"),
    [("basic", 891_000), ("standard", 1_791_000), ("premium", 2_691_000)],
)
def test_promo_for_every_tariff(create_payment, tariff, amount):
    payment = create_payment(tariff, promo_code="kvitto10").json()
    assert payment["amount"] == amount


@pytest.mark.parametrize("code", ["", "   "])
def test_empty_promo_code_means_no_promo(create_payment, code):
    payment = create_payment("standard", promo_code=code).json()
    assert payment["discount"] == 0
    assert payment["amount"] == 1_990_000


def test_unknown_promo_code(client, create_payment):
    resp = create_payment("standard", promo_code="KVITTO20")
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "promo_code"]
    assert client.get("/payments").json() == []


@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("promo", [None, "kvitto10"])
def test_installment_schedule_sum(create_payment, months, promo):
    resp = create_payment(
        "standard", method="installment", installment_months=months, promo_code=promo
    )
    assert resp.status_code == 201
    payment = resp.json()
    assert payment["installment_months"] == months
    assert len(payment["schedule"]) == months
    assert sum(payment["schedule"]) == payment["amount"]


def test_installment_example_from_task(create_payment):
    payment = create_payment("standard", method="installment", installment_months=3).json()
    assert payment["amount"] == 1_990_000
    assert payment["schedule"] == [663_334, 663_333, 663_333]


@pytest.mark.parametrize(
    "fields",
    [
        {"method": "installment"},  # нет срока
        {"method": "installment", "installment_months": 5},
        {"method": "installment", "installment_months": 0},
        {"method": "card", "installment_months": 3},  # срок без рассрочки
        {"method": "cash"},
        {"email": "not-an-email"},
    ],
)
def test_invalid_body_returns_422(client, create_payment, fields):
    resp = create_payment("standard", **fields)
    assert resp.status_code == 422
    assert "detail" in resp.json()
    assert client.get("/payments").json() == []


def test_unknown_tariff_returns_422(client):
    resp = client.post(
        "/payments", json={"tariff_id": 999, "email": "a@example.com", "method": "card"}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "tariff_id"]


def test_same_idempotency_key_returns_same_payment(client, create_payment):
    headers = {"Idempotency-Key": "order-42"}
    first = create_payment("standard", headers=headers, method="installment", installment_months=6)
    second = create_payment("standard", headers=headers, method="installment", installment_months=6)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(client.get("/payments").json()) == 1


def test_parallel_requests_with_same_key(client, create_payment, monkeypatch):
    # Имитируем гонку: второй запрос не увидел первый платёж при проверке ключа
    # и дошёл до INSERT. Должен сработать unique-индекс, а не появиться дубль.
    from app import services

    first = create_payment(headers={"Idempotency-Key": "race"}).json()

    real_lookup = services.get_payment_by_key
    calls = []

    def lookup_misses_first_time(session, key):
        calls.append(key)
        return None if len(calls) == 1 else real_lookup(session, key)

    monkeypatch.setattr(services, "get_payment_by_key", lookup_misses_first_time)
    second = create_payment(headers={"Idempotency-Key": "race"})

    assert len(calls) == 2  # второй вызов был уже после IntegrityError
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert len(client.get("/payments").json()) == 1


def test_different_keys_create_different_payments(client, create_payment):
    a = create_payment(headers={"Idempotency-Key": "a"})
    b = create_payment(headers={"Idempotency-Key": "b"})
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]
    assert len(client.get("/payments").json()) == 2


def test_without_key_every_request_creates_payment(client, create_payment):
    create_payment()
    create_payment()
    assert len(client.get("/payments").json()) == 2


def test_get_payment(client, create_payment):
    created = create_payment("premium", method="sbp", promo_code="KVITTO10").json()
    resp = client.get(f"/payments/{created['id']}")
    assert resp.status_code == 200
    assert resp.json() == created
    assert set(created) == {
        "id",
        "status",
        "tariff_id",
        "amount",
        "discount",
        "method",
        "installment_months",
        "schedule",
        "email",
        "created_at",
    }


def test_get_missing_payment_returns_404(client):
    resp = client.get("/payments/12345")
    assert resp.status_code == 404


def test_list_payments_filters(client, create_payment):
    first = create_payment(email="one@example.com").json()
    create_payment(email="two@example.com")
    client.post("/webhooks/bank", json={"payment_id": first["id"], "status": "succeeded"})

    by_email = client.get("/payments", params={"email": "one@example.com"}).json()
    assert [p["id"] for p in by_email] == [first["id"]]

    pending = client.get("/payments", params={"status": "pending"}).json()
    assert [p["email"] for p in pending] == ["two@example.com"]

    upper = client.get("/payments", params={"email": "ONE@Example.com"}).json()
    assert [p["id"] for p in upper] == [first["id"]]

    both = client.get("/payments", params={"email": "one@example.com", "status": "pending"})
    assert both.json() == []

    assert client.get("/payments", params={"status": "weird"}).status_code == 422
