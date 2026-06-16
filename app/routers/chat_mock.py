"""Mock chat channel for demo/testing. Same path as Telegram, just over HTTP."""
import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.integrations.envelope import ChatEnvelope
from app.models import AuditEvent
from app.schemas import ChatInput
from app.services.intent_router import DASHBOARD_SSE_QUEUE, handle_inbound

router = APIRouter()


@router.post("/webhook")
async def mock_chat_webhook(payload: ChatInput, request: Request, db: Session = Depends(get_db)):
    """Mock inbound chat. In production this is replaced by a real channel webhook."""
    envelope = ChatEnvelope(
        channel="mock",
        sender_id=payload.student_id,
        sender_name=payload.student_name,
        text=payload.message,
        message_id=payload.message_id or str(uuid.uuid4()),
        received_at=datetime.utcnow(),
    )
    return await handle_inbound(
        db=db, envelope=envelope,
        correlation_id=request.state.correlation_id,
    )


@router.get("/stream")
async def dashboard_realtime_stream(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await asyncio.wait_for(DASHBOARD_SSE_QUEUE.get(), timeout=1.0)
                yield {"event": "student_update", "data": data}
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "keep-alive"}
    return EventSourceResponse(event_generator())


@router.get("/audit-timeline")
def audit_timeline(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 100,
):
    """Returns the global audit feed. In production you'd scope this by school
    and require admin role; left open for the demo dashboard."""
    events = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return {
        "total": len(events),
        "events": [
            {
                "time": str(e.created_at),
                "workflow_id": e.correlation_id,
                "actor_id": e.actor_id,
                "event_type": e.event_type,
                "payload": e.payload,
            }
            for e in events
        ],
    }
