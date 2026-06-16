"""Single source of truth for intent classification + dispatch.

Used by chat_mock, telegram_webhook, and any future channel. Keep the
keyword matching here simple and deterministic — it is the boundary
where untrusted user text turns into a typed action.
"""
import asyncio
import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations.envelope import ChatEnvelope
from app.models import (
    AuditEvent, ChatIdentity, InboundChatMessage, Submission, User,
)
from app.services.audit import log_event

# Shared SSE queue — chat_mock and telegram both push into it
DASHBOARD_SSE_QUEUE: asyncio.Queue = asyncio.Queue()


@dataclass
class IntentResult:
    intent: str
    new_state: Optional[str]
    note: str


INTENTS = {
    "BLOCKED": {"blocked", "stuck", "help", "can't", "cannot", "don't understand"},
    "SUBMISSION": {"done", "finished", "submit", "submitted", "completed"},
    "PROGRESS": {"working", "in progress", "started", "doing"},
    "PARENT_OPTIN": {"opt in", "parent access", "guardian access", "my parent can see"},
}


def classify(text: str) -> IntentResult:
    """Plain-keyword classifier. Replace with LLM later if desired."""
    t = (text or "").lower()
    for kw in INTENTS["BLOCKED"]:
        if kw in t:
            return IntentResult("STUDENT_BLOCKED", "BLOCKED", f"matched keyword: {kw}")
    for kw in INTENTS["SUBMISSION"]:
        if kw in t:
            return IntentResult("STUDENT_SUBMISSION", "SUBMITTED", f"matched keyword: {kw}")
    for kw in INTENTS["PROGRESS"]:
        if kw in t:
            return IntentResult("PROGRESS_UPDATE", "IN_PROGRESS", f"matched keyword: {kw}")
    for kw in INTENTS["PARENT_OPTIN"]:
        if kw in t:
            return IntentResult("PARENT_OPTIN", None, f"matched keyword: {kw}")
    return IntentResult("UNKNOWN", None, "no keyword matched — review manually")


async def handle_inbound(
    *,
    db: Session,
    envelope: ChatEnvelope,
    correlation_id: str,
) -> dict:
    """Idempotent inbound message handler.

    Returns a dict suitable for HTTP response. Pushes SSE update if the
    intent changes a dashboard-visible state.
    """
    # 1. Idempotency check
    existing = db.query(InboundChatMessage).filter(
        InboundChatMessage.channel == envelope.channel,
        InboundChatMessage.message_id == envelope.message_id,
    ).first()
    if existing:
        return {"status": "DUPLICATE_IGNORED",
                "first_processed_at": str(existing.processed_at),
                "correlation_id": correlation_id}

    db.add(InboundChatMessage(
        channel=envelope.channel,
        message_id=envelope.message_id,
        sender_id=envelope.sender_id,
        text=envelope.text,
    ))

    # 2. Resolve chat identity -> User (if linked)
    chat_id = db.query(ChatIdentity).filter(
        ChatIdentity.channel == envelope.channel,
        ChatIdentity.channel_user_id == envelope.sender_id,
    ).first()
    user: Optional[User] = None
    if chat_id:
        user = db.query(User).filter(User.id == chat_id.user_id).first()

    # 3. Classify
    result = classify(envelope.text)

    # 4. Update submission state if applicable (only if we can identify the user
    #    AND they're a STUDENT with at least one active assignment)
    state_changed = False
    if user and user.role == "STUDENT" and result.new_state in ("BLOCKED", "SUBMITTED", "IN_PROGRESS"):
        # Update the most recent open submission. In production you'd disambiguate via
        # message content, but for demo we update all open ones.
        open_subs = db.query(Submission).filter(
            Submission.student_id == user.id,
            Submission.state.in_(["NOT_STARTED", "IN_PROGRESS", "BLOCKED"]),
        ).all()
        for sub in open_subs:
            sub.state = result.new_state
            state_changed = True

    # 5. Audit
    log_event(
        db,
        correlation_id=correlation_id,
        actor_id=user.id if user else f"unlinked:{envelope.channel}:{envelope.sender_id}",
        event_type=result.intent,
        payload={
            "channel": envelope.channel,
            "message_id": envelope.message_id,
            "sender_name": envelope.sender_name,
            "raw_message": envelope.text,
            "classifier_note": result.note,
            "linked_user_id": user.id if user else None,
            "state_changed": state_changed,
        },
        commit=False,
    )
    db.commit()

    # 6. Push SSE update for any state-affecting intent
    if result.new_state:
        ui_payload = json.dumps({
            "student_id": user.id if user else envelope.sender_id,
            "student_name": envelope.sender_name,
            "status": result.new_state,
            "latest_message": envelope.text,
            "channel": envelope.channel,
            "correlation_id": correlation_id,
        })
        await DASHBOARD_SSE_QUEUE.put(ui_payload)

    return {
        "status": "PROCESSED",
        "intent": result.intent,
        "new_state": result.new_state,
        "correlation_id": correlation_id,
        "linked_user": bool(user),
    }
