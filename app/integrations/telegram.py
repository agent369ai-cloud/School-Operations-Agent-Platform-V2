"""Telegram integration.

Inbound: receives Telegram webhook JSON, normalises to ChatEnvelope.
Outbound: optional helper to send a reply (used by guardian digest etc.)
"""
from datetime import datetime
from typing import Optional

import httpx

from app.config import settings
from app.integrations.envelope import ChatEnvelope


def telegram_to_envelope(update: dict) -> Optional[ChatEnvelope]:
    """Map a Telegram Update object to ChatEnvelope. Returns None for unsupported updates."""
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None
    if "text" not in msg:
        return None
    sender = msg.get("from", {})
    sender_name = (sender.get("first_name") or "") + " " + (sender.get("last_name") or "")
    return ChatEnvelope(
        channel="telegram",
        sender_id=str(sender.get("id", "unknown")),
        sender_name=sender_name.strip() or sender.get("username", "unknown"),
        text=msg["text"],
        message_id=str(msg["message_id"]),
        received_at=datetime.utcnow(),
    )


async def send_telegram_message(chat_id: str, text: str) -> dict:
    """Outbound helper. No-op when token absent so tests/dev don't fail."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return {"status": "SKIPPED", "reason": "TELEGRAM_BOT_TOKEN not set"}
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json={"chat_id": chat_id, "text": text})
        return {"status": "SENT" if r.status_code == 200 else "ERROR",
                "code": r.status_code, "body": r.text[:200]}
