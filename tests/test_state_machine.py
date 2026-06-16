"""Submission state machine: legal transitions accepted, illegal rejected."""
import pytest
from fastapi import HTTPException

from app.models import Submission
from app.services.submission_service import LEGAL_TRANSITIONS, transition


def test_all_documented_transitions_are_legal(db_session):
    """Sanity: every transition in LEGAL_TRANSITIONS is actually traversable."""
    for from_state, targets in LEGAL_TRANSITIONS.items():
        for to_state in targets:
            sub = Submission(assignment_id="a", student_id="s", state=from_state)
            db_session.add(sub); db_session.commit(); db_session.refresh(sub)
            transition(db_session, submission=sub, to_state=to_state,
                       actor_id="test", correlation_id="cid")
            assert sub.state == to_state


def test_illegal_jump_to_completed_rejected(db_session):
    sub = Submission(assignment_id="a", student_id="s", state="NOT_STARTED")
    db_session.add(sub); db_session.commit()
    with pytest.raises(HTTPException) as exc:
        transition(db_session, submission=sub, to_state="COMPLETED",
                   actor_id="t", correlation_id="cid")
    assert exc.value.status_code == 409


def test_completed_is_terminal(db_session):
    sub = Submission(assignment_id="a", student_id="s", state="COMPLETED")
    db_session.add(sub); db_session.commit()
    for target in ["SUBMITTED", "IN_PROGRESS", "BLOCKED", "FEEDBACK_GIVEN"]:
        with pytest.raises(HTTPException):
            transition(db_session, submission=sub, to_state=target,
                       actor_id="t", correlation_id="cid")
