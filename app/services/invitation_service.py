"""Scoped, single-use invitation tokens with TTL."""
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Invitation, User


def create_invitation(
    db: Session,
    *,
    school_id: str,
    role: str,
    invitee_name: str,
    created_by: str,
    invitee_email: Optional[str] = None,
    classroom_id: Optional[str] = None,
    expires_hours: int = 168,
) -> Invitation:
    token = secrets.token_urlsafe(32)
    inv = Invitation(
        token=token,
        school_id=school_id,
        classroom_id=classroom_id,
        role=role,
        invitee_email=invitee_email,
        invitee_name=invitee_name,
        expires_at=datetime.utcnow() + timedelta(hours=expires_hours),
        created_by=created_by,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def consume_invitation(db: Session, token: str) -> Invitation:
    inv = db.query(Invitation).filter(Invitation.token == token).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    if inv.used_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invitation already used")
    if inv.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_410_GONE, "Invitation expired")
    inv.used_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)
    return inv
