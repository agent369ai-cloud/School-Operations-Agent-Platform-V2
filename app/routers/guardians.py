"""Guardian endpoints: opt-in via scoped token + redacted digest projection."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_role
from app.database import get_db
from app.models import (
    Assignment, Guardian, GuardianStudentLink, StudentEnrollment, Submission, User,
)
from app.services.audit import log_event

router = APIRouter()


class GuardianOptInIn(BaseModel):
    name: str
    phone: str | None = None
    email: EmailStr | None = None
    student_id: str  # the child being linked


@router.post("/opt-in", status_code=status.HTTP_201_CREATED)
def opt_in(payload: GuardianOptInIn, request: Request, db: Session = Depends(get_db)):
    """In a real flow, this would be reached via a scoped invitation token.
    For demo purposes the endpoint accepts a student_id directly and we just
    verify the student exists."""
    student = db.query(User).filter(User.id == payload.student_id, User.role == "STUDENT").first()
    if not student:
        raise HTTPException(404, "Student not found")
    g = Guardian(
        school_id=student.school_id,
        name=payload.name, phone=payload.phone, email=payload.email,
        opted_in=True,
    )
    db.add(g)
    db.flush()
    db.add(GuardianStudentLink(guardian_id=g.id, student_id=student.id))
    db.commit()
    log_event(db, correlation_id=request.state.correlation_id, actor_id=g.id,
              event_type="GUARDIAN_OPTED_IN",
              payload={"guardian_id": g.id, "student_id": student.id})
    return {"guardian_id": g.id, "linked_student": student.name}


@router.get("/{guardian_id}/digest")
def digest(guardian_id: str, db: Session = Depends(get_db)):
    """Public digest endpoint for demo. Production would require a guardian
    auth token. Returns ONLY counts — no submission text, no feedback content."""
    g = db.query(Guardian).filter(Guardian.id == guardian_id).first()
    if not g or not g.opted_in:
        raise HTTPException(404, "Not found")
    links = db.query(GuardianStudentLink).filter(
        GuardianStudentLink.guardian_id == g.id
    ).all()
    children = []
    for link in links:
        student = db.query(User).filter(User.id == link.student_id).first()
        if not student:
            continue
        # Find all assignments via classroom enrollment
        enrollments = db.query(StudentEnrollment).filter(
            StudentEnrollment.student_id == student.id
        ).all()
        class_ids = [e.classroom_id for e in enrollments]
        assignments = db.query(Assignment).filter(
            Assignment.classroom_id.in_(class_ids),
            Assignment.status == "ACTIVE",
        ).all()
        subs = db.query(Submission).filter(Submission.student_id == student.id).all()
        sub_states = [s.state for s in subs]
        children.append({
            "name": student.name,
            "active_assignments": len(assignments),
            "submitted": sub_states.count("SUBMITTED") + sub_states.count("FEEDBACK_GIVEN"),
            "completed": sub_states.count("COMPLETED"),
            "blocked": sub_states.count("BLOCKED"),
            # NOTE: deliberately no submission text, no feedback content, no grades
        })
    return {"guardian": g.name, "children": children}
