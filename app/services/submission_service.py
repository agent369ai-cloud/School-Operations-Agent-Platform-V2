"""Submission state machine. Guards illegal transitions and writes audit events."""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Submission
from app.services.audit import log_event


LEGAL_TRANSITIONS = {
    "NOT_STARTED": {"IN_PROGRESS", "BLOCKED", "SUBMITTED"},
    "IN_PROGRESS": {"BLOCKED", "SUBMITTED"},
    "BLOCKED": {"IN_PROGRESS", "SUBMITTED"},
    "SUBMITTED": {"FEEDBACK_GIVEN"},
    "FEEDBACK_GIVEN": {"REVISION_REQUESTED", "COMPLETED"},
    "REVISION_REQUESTED": {"SUBMITTED"},
    "COMPLETED": set(),
}


def transition(
    db: Session,
    *,
    submission: Submission,
    to_state: str,
    actor_id: str,
    correlation_id: str,
    extra_payload: dict | None = None,
) -> Submission:
    from_state = submission.state
    if to_state not in LEGAL_TRANSITIONS.get(from_state, set()):
        # Audit the rejection too — it tells you about buggy clients
        log_event(
            db,
            correlation_id=correlation_id,
            actor_id=actor_id,
            event_type="SUBMISSION_TRANSITION_REJECTED",
            payload={"submission_id": submission.id, "from": from_state,
                     "to": to_state, "reason": "illegal_transition"},
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Illegal transition {from_state} -> {to_state}",
        )

    submission.state = to_state
    payload = {"submission_id": submission.id, "from": from_state, "to": to_state}
    if extra_payload:
        payload.update(extra_payload)
    log_event(
        db,
        correlation_id=correlation_id,
        actor_id=actor_id,
        event_type=f"SUBMISSION_{to_state}",
        payload=payload,
        commit=False,
    )
    db.commit()
    db.refresh(submission)
    return submission
