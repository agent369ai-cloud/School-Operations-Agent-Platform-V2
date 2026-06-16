"""Authentication routes: register-school, login, /me."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models import School, User
from app.schemas import LoginIn, SchoolRegisterIn, TokenOut
from app.services.audit import log_event

router = APIRouter()


@router.post("/register-school", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register_school(payload: SchoolRegisterIn, request: Request, db: Session = Depends(get_db)):
    if db.query(School).filter(School.name == payload.school_name).first():
        raise HTTPException(409, "School name already taken")
    if db.query(User).filter(User.email == payload.admin_email).first():
        raise HTTPException(409, "Email already registered")

    school = School(name=payload.school_name)
    db.add(school)
    db.flush()
    admin = User(
        school_id=school.id,
        email=payload.admin_email,
        name=payload.admin_name,
        role="ADMIN",
        password_hash=hash_password(payload.admin_password),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    correlation_id = getattr(request.state, "correlation_id", "register")
    log_event(db, correlation_id=correlation_id, actor_id=admin.id,
              event_type="SCHOOL_REGISTERED",
              payload={"school_id": school.id, "school_name": school.name,
                       "admin_email": admin.email})

    token = create_access_token(admin.id, admin.role, school.id)
    return TokenOut(access_token=token, role=admin.role, school_id=school.id, user_id=admin.id)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    correlation_id = getattr(request.state, "correlation_id", "login")
    if not user or not verify_password(payload.password, user.password_hash):
        log_event(db, correlation_id=correlation_id,
                  actor_id=user.id if user else f"unknown:{payload.email}",
                  event_type="LOGIN_FAILED", payload={"email": payload.email})
        raise HTTPException(401, "Invalid email or password")
    log_event(db, correlation_id=correlation_id, actor_id=user.id,
              event_type="LOGIN_SUCCESS", payload={"role": user.role})
    token = create_access_token(user.id, user.role, user.school_id)
    return TokenOut(access_token=token, role=user.role, school_id=user.school_id, user_id=user.id)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "email": user.email,
            "role": user.role, "school_id": user.school_id}
