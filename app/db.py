from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# id в SQLite (и BIGINT в Postgres) 64-битные. Число больше драйвер не примет
# и упадёт с OverflowError, поэтому такие значения отсекаем ещё на валидации.
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        # FastAPI гоняет sync-эндпоинты в тредпуле, а sqlite3 по умолчанию это запрещает
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
