"""Real Telegram webhook. Set up via:
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<host>/api/v1/webhooks/telegram&secret_token=<SECRET>"
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.integrations.telegram import telegram_to_envelope
from app.services.intent_router import handle_inbound

router = APIRouter()


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    if settings.TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(401, "Invalid secret token")
    update = await request.json()
    envelope = telegram_to_envelope(update)
    if envelope is None:
        # Non-message updates (e.g. edits without text) — acknowledge to stop Telegram retries
        return {"ok": True, "ignored": True}
    return await handle_inbound(
        db=db, envelope=envelope,
        correlation_id=request.state.correlation_id,
    )
