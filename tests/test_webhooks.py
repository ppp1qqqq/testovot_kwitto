import json

import pytest
from sqlalchemy import update

from app import services
from app.enums import PaymentStatus
from app.models import Payment
from app.routers.webhooks import sign


def send(client, payment_id, status, **kwargs):
    return client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": status}, **kwargs
    )


def status_of(client, payment_id):
    return client.get(f"/payments/{payment_id}").json()["status"]


@pytest.fixture
def payment_id(create_payment):
    return create_payment().json()["id"]


@pytest.mark.parametrize("final", ["succeeded", "failed"])
def test_pending_can_finish(client, payment_id, final):
    resp = send(client, payment_id, final)
    assert resp.status_code == 200
    assert resp.json() == {"result": "ok"}
    assert status_of(client, payment_id) == final


def test_succeeded_can_be_refunded(client, payment_id):
    send(client, payment_id, "succeeded")
    resp = send(client, payment_id, "refunded")
    assert resp.status_code == 200
    assert status_of(client, payment_id) == "refunded"


@pytest.mark.parametrize(
    ("path", "forbidden"),
    [
        ([], "refunded"),  # pending -> refunded
        ([], "pending"),  # pending -> pending
        (["succeeded"], "failed"),
        (["succeeded"], "succeeded"),  # повторный вебхук тоже запрещённый переход
        (["failed"], "succeeded"),
        (["failed"], "refunded"),
        (["succeeded", "refunded"], "succeeded"),
        (["succeeded", "refunded"], "pending"),
    ],
)
def test_forbidden_transition(client, payment_id, path, forbidden):
    for step in path:
        assert send(client, payment_id, step).status_code == 200
    before = status_of(client, payment_id)

    resp = send(client, payment_id, forbidden)

    assert resp.status_code == 409
    assert resp.json() == {"error": "invalid_transition"}
    assert status_of(client, payment_id) == before


def test_concurrent_webhook_is_not_overwritten(client, payment_id, monkeypatch):
    # Пока обрабатываем "failed", другой вебхук успевает перевести платёж в succeeded.
    # Наш UPDATE ... WHERE status = 'pending' не должен затереть его результат.
    real_check = services.can_transition

    def check_while_other_webhook_wins(current, new):
        with client.app.state.session_factory() as other:
            other.execute(
                update(Payment)
                .where(Payment.id == payment_id)
                .values(status=PaymentStatus.SUCCEEDED)
            )
            other.commit()
        return real_check(current, new)

    monkeypatch.setattr(services, "can_transition", check_while_other_webhook_wins)

    resp = send(client, payment_id, "failed")

    assert resp.status_code == 409
    assert resp.json() == {"error": "invalid_transition"}
    assert status_of(client, payment_id) == "succeeded"


def test_webhook_for_missing_payment(client):
    resp = send(client, 9999, "succeeded")
    assert resp.status_code == 404


def test_webhook_with_huge_payment_id_is_422(client):
    assert send(client, 10**20, "succeeded").status_code == 422


def test_webhook_unknown_status_is_422(client, payment_id):
    resp = send(client, payment_id, "paid")
    assert resp.status_code == 422
    assert status_of(client, payment_id) == "pending"


class TestSignature:
    secret = "test-secret"

    @pytest.fixture
    def client(self, make_client):
        return make_client(webhook_secret=self.secret)

    def post_signed(self, client, payload: dict, signature: str | None):
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers["X-Signature"] = signature
        return client.post("/webhooks/bank", content=body, headers=headers)

    def test_valid_signature(self, client, payment_id):
        payload = {"payment_id": payment_id, "status": "succeeded"}
        signature = sign(json.dumps(payload).encode(), self.secret)

        resp = self.post_signed(client, payload, signature)

        assert resp.status_code == 200
        assert status_of(client, payment_id) == "succeeded"

    @pytest.mark.parametrize("signature", [None, "", "deadbeef"])
    def test_bad_signature(self, client, payment_id, signature):
        payload = {"payment_id": payment_id, "status": "succeeded"}
        resp = self.post_signed(client, payload, signature)
        assert resp.status_code == 401
        assert status_of(client, payment_id) == "pending"

    def test_non_ascii_signature_is_401_not_500(self, client, payment_id):
        body = json.dumps({"payment_id": payment_id, "status": "succeeded"}).encode()
        headers = {"Content-Type": "application/json", "X-Signature": "é".encode()}
        resp = client.post("/webhooks/bank", content=body, headers=headers)
        assert resp.status_code == 401

    def test_signature_checked_before_body(self, client):
        resp = self.post_signed(client, {"payment_id": "oops"}, "deadbeef")
        assert resp.status_code == 401

    def test_signature_from_other_body(self, client, payment_id):
        # подпись от одного тела не подходит к другому
        signed = sign(
            json.dumps({"payment_id": payment_id, "status": "failed"}).encode(), self.secret
        )
        resp = self.post_signed(client, {"payment_id": payment_id, "status": "succeeded"}, signed)
        assert resp.status_code == 401
        assert status_of(client, payment_id) == "pending"
