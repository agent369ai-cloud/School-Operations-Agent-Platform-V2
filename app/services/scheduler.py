"""Policy-aware reminder engine.

Reads real submission state from the DB. Treats:
- BLOCKED -> escalation message (would notify guardian in prod)
- NOT_STARTED (silent) -> nudge reminder
- SUBMITTED / FEEDBACK_GIVEN / COMPLETED -> suppress

Quiet-hours policy: configurable via env (QUIET_HOURS_START/END).
"""
from datetime import datetime
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Assignment, AuditEvent, Submission, User
from app.services.audit import log_event


def _is_quiet_hours(now_hour: int) -> bool:
    start = settings.QUIET_HOURS_START
    end = settings.QUIET_HOURS_END
    # Overnight window e.g. 20 -> 8: anything >= start or < end is quiet
    if start > end:
        return now_hour >= start or now_hour < end
    return start <= now_hour < end


def run_reminder_engine(db: Session, correlation_id: str) -> dict:
    now = datetime.now()
    if _is_quiet_hours(now.hour):
        log_event(
            db,
            correlation_id=correlation_id,
            actor_id="SYSTEM_SCHEDULER",
            event_type="REMINDER_SKIPPED_QUIET_HOURS",
            payload={"current_hour": now.hour,
                     "window": f"{settings.QUIET_HOURS_START}-{settings.QUIET_HOURS_END}"},
        )
        return {"status": "SKIPPED", "reason": "QUIET_HOURS_ACTIVE",
                "current_hour": now.hour}

    # Find active assignments
    active_assignments = db.query(Assignment).filter(Assignment.status == "ACTIVE").all()

    nudged: list[str] = []
    escalated: list[str] = []
    suppressed: list[str] = []

    for assignment in active_assignments:
        # Find all enrolled students with their submission state
        # Subquery would be cleaner; explicit loop keeps it readable
        submissions = db.query(Submission).filter(
            Submission.assignment_id == assignment.id
        ).all()
        sub_by_student = {s.student_id: s for s in submissions}

        # Get every enrolled student (from StudentEnrollment via classroom)
        from app.models import StudentEnrollment  # local import to avoid cycles
        enrollments = db.query(StudentEnrollment).filter(
            StudentEnrollment.classroom_id == assignment.classroom_id
        ).all()

        for enr in enrollments:
            student = db.query(User).filter(User.id == enr.student_id).first()
            if not student:
                continue
            sub = sub_by_student.get(student.id)
            state = sub.state if sub else "NOT_STARTED"

            if state in ("SUBMITTED", "FEEDBACK_GIVEN", "COMPLETED"):
                suppressed.append(student.name)
                continue

            if state == "BLOCKED":
                log_event(
                    db,
                    correlation_id=correlation_id,
                    actor_id="SYSTEM_SCHEDULER",
                    event_type="REMINDER_ESCALATED",
                    payload={"student_id": student.id, "student_name": student.name,
                             "assignment_id": assignment.id, "state": state,
                             "channel": "teacher_dashboard",
                             "message": f"{student.name} is BLOCKED on '{assignment.title}'."},
                    commit=False,
                )
                escalated.append(student.name)
            else:
                # NOT_STARTED or IN_PROGRESS -> nudge
                log_event(
                    db,
                    correlation_id=correlation_id,
                    actor_id="SYSTEM_SCHEDULER",
                    event_type="REMINDER_SENT",
                    payload={"student_id": student.id, "student_name": student.name,
                             "assignment_id": assignment.id, "state": state,
                             "message": f"Hi {student.name}, you have a pending assignment: '{assignment.title}'."},
                    commit=False,
                )
                nudged.append(student.name)

    db.commit()
    return {
        "status": "COMPLETED",
        "processed_at": str(now),
        "nudged": nudged,
        "escalated": escalated,
        "suppressed": suppressed,
        "active_assignments": len(active_assignments),
    }
