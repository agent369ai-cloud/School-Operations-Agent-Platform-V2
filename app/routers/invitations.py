"""Invitation flow: admin/teacher creates a scoped token; recipient accepts via /accept."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.deps import assert_same_school, get_current_user, require_role
from app.auth.security import create_access_token, hash_password
from app.database import get_db
from app.models import ClassRoom, StudentEnrollment, TeacherClassroom, User
from app.schemas import InvitationAcceptIn, InvitationCreateIn, TokenOut
from app.services.audit import log_event
from app.services.invitation_service import consume_invitation, create_invitation

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: InvitationCreateIn, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "TEACHER")),
):
    if payload.classroom_id:
        c = db.query(ClassRoom).filter(ClassRoom.id == payload.classroom_id).first()
        if not c:
            raise HTTPException(404, "Classroom not found")
        assert_same_school(request=request, db=db, actor=user, resource_school_id=c.school_id)
    inv = create_invitation(
        db,
        school_id=user.school_id,
        role=payload.role,
        invitee_name=payload.invitee_name,
        invitee_email=payload.invitee_email,
        classroom_id=payload.classroom_id,
        expires_hours=payload.expires_hours,
        created_by=user.id,
    )
    log_event(db, correlation_id=request.state.correlation_id, actor_id=user.id,
              event_type="INVITATION_CREATED",
              payload={"token_prefix": inv.token[:8], "role": inv.role,
                       "classroom_id": inv.classroom_id})
    return {"token": inv.token, "role": inv.role,
            "classroom_id": inv.classroom_id,
            "expires_at": str(inv.expires_at),
            "accept_url": f"/api/v1/invitations/{inv.token}/accept"}


@router.get("/{token}")
def view_invite(token: str, db: Session = Depends(get_db)):
    """Public — recipient previews the invitation."""
    from app.models import Invitation
    inv = db.query(Invitation).filter(Invitation.token == token).first()
    if not inv:
        raise HTTPException(404, "Not found")
    if inv.used_at is not None:
        raise HTTPException(409, "Already used")
    return {"role": inv.role, "invitee_name": inv.invitee_name,
            "invitee_email": inv.invitee_email, "expires_at": str(inv.expires_at)}


@router.post("/{token}/accept", response_model=TokenOut)
def accept_invite(
    token: str, payload: InvitationAcceptIn, request: Request,
    db: Session = Depends(get_db),
):
    """Public — recipient sets a password and gets a JWT.

    Wires up roles correctly:
    - TEACHER -> TeacherClassroom link if classroom_id provided
    - STUDENT -> StudentEnrollment link
    - GUARDIAN -> Guardian row (linkage to student done separately)
    """
    inv = consume_invitation(db, token)
    user = User(
        school_id=inv.school_id,
        email=inv.invitee_email,
        name=inv.invitee_name or "Invited User",
        role=inv.role,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    if inv.classroom_id and inv.role == "TEACHER":
        db.add(TeacherClassroom(teacher_id=user.id, classroom_id=inv.classroom_id))
    elif inv.classroom_id and inv.role == "STUDENT":
        db.add(StudentEnrollment(student_id=user.id, classroom_id=inv.classroom_id))
    db.commit()

    log_event(db, correlation_id=request.state.correlation_id, actor_id=user.id,
              event_type="INVITATION_ACCEPTED",
              payload={"role": inv.role, "classroom_id": inv.classroom_id})

    token_jwt = create_access_token(user.id, user.role, user.school_id)
    return TokenOut(access_token=token_jwt, role=user.role,
                    school_id=user.school_id, user_id=user.id)
