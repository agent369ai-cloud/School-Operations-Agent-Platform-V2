"""Intent classifier eval — one assertion per intent type."""
import pytest

from app.services.intent_router import classify


@pytest.mark.parametrize("text, expected_intent", [
    ("I am stuck on question 3", "STUDENT_BLOCKED"),
    ("Help, I'm blocked", "STUDENT_BLOCKED"),
    ("I can't figure this out", "STUDENT_BLOCKED"),
    ("All done!", "STUDENT_SUBMISSION"),
    ("finished the worksheet", "STUDENT_SUBMISSION"),
    ("submitted via email", "STUDENT_SUBMISSION"),
    ("Working on it now", "PROGRESS_UPDATE"),
    ("I started the homework", "PROGRESS_UPDATE"),
    ("Can my parent see this?", "PARENT_OPTIN"),
    ("the weather today is nice", "UNKNOWN"),
    ("xyzzy plover", "UNKNOWN"),
])
def test_intent_classification(text, expected_intent):
    result = classify(text)
    assert result.intent == expected_intent, (
        f"Text {text!r} expected {expected_intent} but got {result.intent} (note: {result.note})"
    )


def test_unknown_intent_has_safe_fallback():
    """Critical: unknown messages must not silently move state."""
    result = classify("random message")
    assert result.intent == "UNKNOWN"
    assert result.new_state is None
