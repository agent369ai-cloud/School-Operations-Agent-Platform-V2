"""Document ingestion: assignment brief, roster CSV. Always goes through the
parse -> propose -> approve workflow."""
import csv
import io
import os
import uuid

from fastapi import (
    APIRouter, Depends, File, HTTPException, Request, UploadFile, status,
)
from sqlalchemy.orm import Session

from app.auth.deps import assert_same_school, get_current_user, require_role
from app.database import get_db
from app.models import (
    Assignment, AuditEvent, ClassRoom, Document, StudentEnrollment, User,
)
from app.schemas import AssignmentApprovalIn
from app.services.ai_parser import parse_assignment_brief
from app.services.audit import log_event

router = APIRouter()

# Simple file-size guard. Production would also do MIME sniff + AV scan.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTS = {".txt", ".csv", ".md", ".json"}  # PDF/DOCX would need a converter


def _validate_upload(file: UploadFile) -> None:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext and ext not in ALLOWED_EXTS:
        raise HTTPException(415, f"Unsupported file type {ext}")


@router.post("/upload-brief", status_code=status.HTTP_202_ACCEPTED)
async def upload_assignment_brief(
    request: Request,
    classroom_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("TEACHER", "ADMIN")),
):
    _validate_upload(file)
    classroom = db.query(ClassRoom).filter(ClassRoom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(404, "Classroom not found")
    assert_same_school(request=request, db=db, actor=user, resource_school_id=classroom.school_id)

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    document_text = contents.decode("utf-8", errors="replace")
    correlation_id = request.state.correlation_id

    parsed = parse_assignment_brief(document_text)

    # Persist Document row
    doc = Document(
        school_id=user.school_id,
        uploaded_by=user.id,
        doc_type="BRIEF",
        filename=file.filename or "unnamed.txt",
        parsed_json=parsed.model_dump(),
        is_ambiguous=parsed.is_ambiguous,
        approval_state="PENDING" if parsed.is_ambiguous else "APPROVED",
    )
    db.add(doc)
    db.flush()

    # Always create the Assignment, but in DRAFT if ambiguous
    assignment = Assignment(
        classroom_id=classroom_id,
        created_by=user.id,
        title=parsed.title,
        subject=parsed.subject,
        instructions=parsed.instructions,
        due_date=None,  # caller approves with date
        status="DRAFT" if parsed.is_ambiguous else "ACTIVE",
        source_document_id=doc.id,
    )
    db.add(assignment)
    db.flush()

    log_event(db, correlation_id=correlation_id, actor_id=user.id,
              event_type="ASSIGNMENT_BRIEF_PARSED",
              payload={"document_id": doc.id, "assignment_id": assignment.id,
                       "is_ambiguous": parsed.is_ambiguous,
                       "title": parsed.title}, commit=False)
    db.commit()

    if parsed.is_ambiguous:
        return {
            "status": "REQUIRES_CLARIFICATION",
            "assignment_id": assignment.id,
            "document_id": doc.id,
            "correlation_id": correlation_id,
            "clarification_question": parsed.clarification_question,
            "extracted_draft": {
                "title": parsed.title,
                "subject": parsed.subject,
                "instructions": parsed.instructions,
            },
        }
    return {"status": "ACTIVE", "assignment_id": assignment.id,
            "correlation_id": correlation_id}


@router.post("/assignments/{assignment_id}/approve")
def approve_assignment(
    assignment_id: str, payload: AssignmentApprovalIn, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_role("TEACHER", "ADMIN")),
):
    """Caller approves a DRAFT assignment by filling in the missing field(s)."""
    from datetime import datetime
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(404, "Not found")
    classroom = db.query(ClassRoom).filter(ClassRoom.id == a.classroom_id).first()
    assert_same_school(request=request, db=db, actor=user, resource_school_id=classroom.school_id)
    if a.status != "DRAFT":
        raise HTTPException(409, f"Assignment is not in DRAFT (current: {a.status})")

    if payload.title:
        a.title = payload.title
    if payload.instructions:
        a.instructions = payload.instructions
    if payload.due_date:
        try:
            a.due_date = datetime.fromisoformat(payload.due_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Invalid due_date format (use ISO 8601)")

    if payload.approve:
        a.status = "ACTIVE"
    db.commit()

    log_event(db, correlation_id=request.state.correlation_id, actor_id=user.id,
              event_type="ASSIGNMENT_APPROVED",
              payload={"assignment_id": a.id, "new_status": a.status,
                       "due_date": str(a.due_date) if a.due_date else None})
    return {"status": a.status, "assignment_id": a.id,
            "due_date": str(a.due_date) if a.due_date else None}


@router.post("/upload-roster", status_code=status.HTTP_202_ACCEPTED)
async def upload_roster_csv(
    request: Request,
    classroom_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN")),
):
    """Roster CSV format: name,email,guardian_name,guardian_email,guardian_phone"""
    _validate_upload(file)
    classroom = db.query(ClassRoom).filter(ClassRoom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(404, "Classroom not found")
    assert_same_school(request=request, db=db, actor=user, resource_school_id=classroom.school_id)

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    decoded = contents.decode("utf-8", errors="replace").splitlines()
    reader = csv.DictReader(decoded)

    correlation_id = request.state.correlation_id
    errors: list[dict] = []
    processed: list[dict] = []
    seen_names: set[str] = set()
    last_idx = 0

    for idx, row in enumerate(reader, start=1):
        last_idx = idx
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip()
        guardian = (row.get("guardian_name") or row.get("guardian") or "").strip()

        if not name:
            errors.append({"row": idx, "field": "name", "issue": "Missing name"})
            continue
        if name in seen_names:
            errors.append({"row": idx, "field": "name",
                           "issue": f"Duplicate student name: '{name}'"})
            continue
        seen_names.add(name)
        if not guardian:
            errors.append({"row": idx, "field": "guardian_name",
                           "issue": f"Student '{name}' missing guardian contact"})
            continue
        processed.append({"name": name, "email": email or None, "guardian": guardian})

    # Always persist a Document for auditability, including pending approval
    doc = Document(
        school_id=user.school_id,
        uploaded_by=user.id,
        doc_type="ROSTER",
        filename=file.filename or "roster.csv",
        parsed_json={"processed_rows": processed, "anomalies": errors},
        is_ambiguous=bool(errors),
        approval_state="PENDING" if errors else "APPROVED",
    )
    db.add(doc)
    db.flush()
    log_event(db, correlation_id=correlation_id, actor_id=user.id,
              event_type="ROSTER_CSV_INGESTED",
              payload={"document_id": doc.id, "filename": doc.filename,
                       "rows_seen": last_idx,
                       "rows_clean": len(processed),
                       "anomalies": len(errors)}, commit=False)

    if errors:
        db.commit()
        return {"status": "REQUIRES_CLARIFICATION", "document_id": doc.id,
                "correlation_id": correlation_id,
                "message": "Roster ingestion halted due to anomalies. Review and re-upload.",
                "anomalies": errors,
                "rows_clean_preview": processed}

    # All clean -> commit students
    for row in processed:
        student = User(school_id=user.school_id, name=row["name"],
                       email=row["email"], role="STUDENT", password_hash=None)
        db.add(student)
        db.flush()
        db.add(StudentEnrollment(student_id=student.id, classroom_id=classroom_id))
    db.commit()
    log_event(db, correlation_id=correlation_id, actor_id=user.id,
              event_type="ROSTER_COMMITTED",
              payload={"document_id": doc.id, "students_added": len(processed)})
    return {"status": "ACTIVE", "document_id": doc.id,
            "students_added": len(processed),
            "correlation_id": correlation_id}


@router.post("/trigger-scheduler")
def trigger_scheduler_endpoint(
    request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "TEACHER")),
):
    from app.services.scheduler import run_reminder_engine
    return run_reminder_engine(db, request.state.correlation_id)
