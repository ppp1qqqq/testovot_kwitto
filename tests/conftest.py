from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def make_client(tmp_path) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def factory(webhook_secret: str | None = None) -> TestClient:
        settings = Settings(
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            webhook_secret=webhook_secret,
        )
        client = TestClient(create_app(settings))
        client.__enter__()  # запускает lifespan: таблицы и тарифы
        clients.append(client)
        return client

    yield factory

    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture
def tariff_ids(client) -> dict[str, int]:
    return {t["title"]: t["id"] for t in client.get("/tariffs").json()}


@pytest.fixture
def create_payment(client, tariff_ids):
    def _create(tariff: str = "standard", headers: dict | None = None, **fields):
        body = {"tariff_id": tariff_ids[tariff], "email": "student@example.com", "method": "card"}
        body.update(fields)
        return client.post("/payments", json=body, headers=headers or {})

    return _create
