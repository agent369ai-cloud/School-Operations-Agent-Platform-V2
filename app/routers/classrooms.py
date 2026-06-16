"""Classroom CRUD + teacher assignment."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import assert_same_school, get_current_user, require_role
from app.database import get_db
from app.models import ClassRoom, TeacherClassroom, User
from app.services.audit import log_event

router = APIRouter()


class ClassroomIn(BaseModel):
    name: str


class AssignTeacherIn(BaseModel):
    teacher_id: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_classroom(
    payload: ClassroomIn, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN")),
):
    existing = db.query(ClassRoom).filter(
        ClassRoom.school_id == user.school_id,
        ClassRoom.name == payload.name,
    ).first()
    if existing:
        raise HTTPException(409, "Classroom name already exists in this school")
    c = ClassRoom(school_id=user.school_id, name=payload.name)
    db.add(c)
    db.commit()
    db.refresh(c)
    log_event(db, correlation_id=request.state.correlation_id, actor_id=user.id,
              event_type="CLASSROOM_CREATED", payload={"classroom_id": c.id, "name": c.name})
    return {"id": c.id, "name": c.name, "school_id": c.school_id}


@router.get("")
def list_classrooms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    classes = db.query(ClassRoom).filter(ClassRoom.school_id == user.school_id).all()
    return [{"id": c.id, "name": c.name} for c in classes]


@router.get("/{classroom_id}")
def get_classroom(classroom_id: str, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(ClassRoom).filter(ClassRoom.id == classroom_id).first()
    if not c:
        # Don't leak existence to non-members
        raise HTTPException(404, "Not found")
    assert_same_school(request=request, db=db, actor=user, resource_school_id=c.school_id)
    return {"id": c.id, "name": c.name, "school_id": c.school_id}


@router.post("/{classroom_id}/teachers", status_code=status.HTTP_201_CREATED)
def assign_teacher(
    classroom_id: str, payload: AssignTeacherIn, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_role("ADMIN")),
):
    c = db.query(ClassRoom).filter(ClassRoom.id == classroom_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    assert_same_school(request=request, db=db, actor=user, resource_school_id=c.school_id)
    teacher = db.query(User).filter(User.id == payload.teacher_id).first()
    if not teacher or teacher.role != "TEACHER":
        raise HTTPException(404, "Teacher not found")
    assert_same_school(request=request, db=db, actor=user, resource_school_id=teacher.school_id)
    link = TeacherClassroom(teacher_id=teacher.id, classroom_id=classroom_id)
    db.merge(link)
    db.commit()
    log_event(db, correlation_id=request.state.correlation_id, actor_id=user.id,
              event_type="TEACHER_ASSIGNED",
              payload={"teacher_id": teacher.id, "classroom_id": classroom_id})
    return {"ok": True}
