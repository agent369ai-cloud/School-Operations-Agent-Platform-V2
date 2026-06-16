"""Canonical inbound chat message — same shape from Telegram, WhatsApp, mock, etc."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class ChatEnvelope(BaseModel):
    channel: Literal["telegram", "whatsapp", "mock"]
    sender_id: str
    sender_name: str
    text: str
    message_id: str
    received_at: datetime
