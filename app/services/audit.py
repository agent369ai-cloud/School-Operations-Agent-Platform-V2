"""Audit log helper — writes immutable events keyed by correlation_id."""
from typing import Optional
from sqlalchemy.orm import Session

from app.models import AuditEvent


def log_event(
    db: Session,
    *,
    correlation_id: str,
    actor_id: str,
    event_type: str,
    payload: Optional[dict] = None,
    commit: bool = True,
) -> AuditEvent:
    event = AuditEvent(
        correlation_id=correlation_id,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload or {},
    )
    db.add(event)
    if commit:
        db.commit()
    return event
