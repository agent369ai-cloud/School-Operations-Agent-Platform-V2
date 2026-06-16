"""FastAPI dependencies for auth and scoped access checks.

The core rule: actor.school_id must match resource.school_id. Violations
return 403 and emit an ACCESS_DENIED audit event.
"""
from typing import Callable, Optional
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.database import get_db
from app.models import AuditEvent, User


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "no-correlation")


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    request.state.actor_id = user.id
    return user


def require_role(*allowed_roles: str) -> Callable:
    def _checker(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if user.role not in allowed_roles:
            db.add(AuditEvent(
                correlation_id=_correlation_id(request),
                actor_id=user.id,
                event_type="ACCESS_DENIED",
                payload={"reason": "role_not_allowed", "actor_role": user.role,
                         "required_roles": list(allowed_roles), "path": str(request.url.path)},
            ))
            db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return _checker


def assert_same_school(
    *, request: Request, db: Session, actor: User, resource_school_id: str,
) -> None:
    """Call from inside an endpoint after you've loaded the resource."""
    if actor.school_id != resource_school_id:
        db.add(AuditEvent(
            correlation_id=_correlation_id(request),
            actor_id=actor.id,
            event_type="ACCESS_DENIED",
            payload={"reason": "cross_school_attempt",
                     "actor_school_id": actor.school_id,
                     "resource_school_id": resource_school_id,
                     "path": str(request.url.path)},
        ))
        db.commit()
        # Return a generic 403 — don't leak whether the resource exists
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
