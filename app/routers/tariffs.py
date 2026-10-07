from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Tariff
from app.schemas import TariffOut

router = APIRouter(tags=["tariffs"])


@router.get("/tariffs", response_model=list[TariffOut])
def list_tariffs(session: Session = Depends(get_session)) -> list[Tariff]:
    return list(session.scalars(select(Tariff).order_by(Tariff.id)))
