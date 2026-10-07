from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, load_settings
from app.db import Base, make_engine, make_session_factory
from app.models import Tariff
from app.routers import payments, tariffs, webhooks

# Цены в копейках: 9 900 ₽, 19 900 ₽, 29 900 ₽
DEFAULT_TARIFFS = {
    "basic": 990_000,
    "standard": 1_990_000,
    "premium": 2_990_000,
}


def seed_tariffs(session: Session) -> None:
    existing = set(session.scalars(select(Tariff.title)))
    for title, price in DEFAULT_TARIFFS.items():
        if title not in existing:
            session.add(Tariff(title=title, price=price))
    session.commit()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        with session_factory() as session:
            seed_tariffs(session)
        yield
        engine.dispose()

    app = FastAPI(title="Kvitto payments", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory

    app.include_router(tariffs.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    return app


app = create_app()
