import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import BankWebhook
from app.services import InvalidTransition, PaymentNotFound, change_status

router = APIRouter(tags=["webhooks"])


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def verify_signature(
    request: Request, x_signature: str | None = Header(default=None)
) -> None:
    secret = request.app.state.settings.webhook_secret
    if secret is None:
        return
    body = await request.body()
    # Сравниваем байты: compare_digest на строках с не-ASCII символами падает с TypeError
    if x_signature is None or not hmac.compare_digest(
        sign(body, secret).encode(), x_signature.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")


@router.post(
    "/webhooks/bank",
    dependencies=[Depends(verify_signature)],
    responses={
        404: {"description": "Payment not found"},
        409: {"description": "Invalid status transition"},
    },
)
def bank_webhook(data: BankWebhook, session: Session = Depends(get_session)):
    try:
        change_status(session, data.payment_id, data.status)
    except PaymentNotFound:
        raise HTTPException(status_code=404, detail="Payment not found") from None
    except InvalidTransition:
        return JSONResponse(status_code=409, content={"error": "invalid_transition"})
    return {"result": "ok"}
