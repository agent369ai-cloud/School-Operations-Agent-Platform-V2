"""Submission + feedback endpoints with guarded state transitions."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.deps import assert_same_school, get_current_user, require_role
from app.database import get_db
from app.models import (
    Assignment, ClassRoom, Feedback, StudentEnrollment, Submission, TeacherClassroom, User,
)
from app.schemas import FeedbackIn, SubmissionCreateIn
from app.services.submission_service import transition

router = APIRouter()


def _load_submission(db: Session, submission_id: str) -> Submission:
    s = db.query(Submission).filter(Submission.id == submission_id).first()
    if not s:
        raise HTTPException(404, "Not found")
    return s


def _classroom_for_submission(db: Session, sub: Submission) -> ClassRoom:
    a = db.query(Assignment).filter(Assignment.id == sub.assignment_id).first()
    return db.query(ClassRoom).filter(ClassRoom.id == a.classroom_id).first()


def _teacher_can_access(db: Session, teacher: User, classroom: ClassRoom) -> bool:
    if teacher.role == "ADMIN":
        return teacher.school_id == classroom.school_id
    link = db.query(TeacherClassroom).filter(
        TeacherClassroom.teacher_id == teacher.id,
        TeacherClassroom.classroom_id == classroom.id,
    ).first()
    return link is not None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_or_update_submission(
    payload: SubmissionCreateIn, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("STUDENT")),
):
    a = db.query(Assignment).filter(Assignment.id == payload.assignment_id).first()
    if not a:
        raise HTTPException(404, "Assignment not found")
    classroom = db.query(ClassRoom).filter(ClassRoom.id == a.classroom_id).first()
    assert_same_school(request=request, db=db, actor=user, resource_school_id=classroom.school_id)

    # Confirm student is enrolled in the classroom
    enrolled = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == user.id,
        StudentEnrollment.classroom_id == a.classroom_id,
    ).first()
    if not enrolled:
        raise HTTPException(403, "Not enrolled in this classroom")
    if a.status != "ACTIVE":
        raise HTTPException(409, f"Assignment is {a.status}")

    sub = db.query(Submission).filter(
        Submission.assignment_id == a.id, Submission.student_id == user.id,
    ).first()
    if not sub:
        sub = Submission(assignment_id=a.id, student_id=user.id, state="NOT_STARTED")
        db.add(sub)
        db.flush()
    sub.content = payload.content
    db.commit()
    transition(db, submission=sub, to_state="SUBMITTED",
               actor_id=user.id, correlation_id=request.state.correlation_id,
               extra_payload={"has_content": bool(payload.content)})
    return {"submission_id": sub.id, "state": sub.state}


@router.post("/{submission_id}/feedback")
def give_feedback(
    submission_id: str, payload: FeedbackIn, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("TEACHER", "ADMIN")),
):
    sub = _load_submission(db, submission_id)
    classroom = _classroom_for_submission(db, sub)
    assert_same_school(request=request, db=db, actor=user, resource_school_id=classroom.school_id)
    if not _teacher_can_access(db, user, classroom):
        raise HTTPException(403, "Not assigned to this classroom")

    # FEEDBACK_GIVEN first (from SUBMITTED), then decision routes to next state
    transition(db, submission=sub, to_state="FEEDBACK_GIVEN",
               actor_id=user.id, correlation_id=request.state.correlation_id,
               extra_payload={"decision": payload.decision})
    db.add(Feedback(submission_id=sub.id, teacher_id=user.id,
                    text=payload.text, decision=payload.decision))
    db.commit()
    db.refresh(sub)

    transition(db, submission=sub, to_state=payload.decision,
               actor_id=user.id, correlation_id=request.state.correlation_id)
    return {"submission_id": sub.id, "state": sub.state}


@router.get("/{submission_id}")
def get_submission(
    submission_id: str, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = _load_submission(db, submission_id)
    classroom = _classroom_for_submission(db, sub)
    assert_same_school(request=request, db=db, actor=user, resource_school_id=classroom.school_id)

    if user.role == "STUDENT" and sub.student_id != user.id:
        raise HTTPException(403, "Cannot read another student's submission")
    if user.role == "TEACHER" and not _teacher_can_access(db, user, classroom):
        raise HTTPException(403, "Not assigned to this classroom")
    return {"id": sub.id, "assignment_id": sub.assignment_id,
            "student_id": sub.student_id, "state": sub.state,
            "content": sub.content, "updated_at": str(sub.updated_at)}
