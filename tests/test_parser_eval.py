"""Parser eval — tests fall back to the placeholder path when no API key is set,
which is the safe-by-default behaviour we want to assert in CI.
"""
import os

from app.services.ai_parser import _placeholder, parse_assignment_brief
from app.schemas import ParsedAssignment


BRIEFS_DIR = os.path.join(os.path.dirname(__file__), "evals", "briefs")


def _read(name: str) -> str:
    with open(os.path.join(BRIEFS_DIR, name), "r") as f:
        return f.read()


def test_placeholder_is_ambiguous():
    """Fallback must always be ambiguous — never silently activates."""
    p = _placeholder("test")
    assert isinstance(p, ParsedAssignment)
    assert p.is_ambiguous is True
    assert p.clarification_question is not None


def test_parse_uses_placeholder_when_no_api_key():
    """Without OPENAI_API_KEY, we expect deterministic placeholder, not an exception."""
    result = parse_assignment_brief(_read("missing_date.txt"))
    assert result.is_ambiguous is True


def test_prompt_injection_text_does_not_crash_parser():
    """The parser should treat injected instructions as data, not commands."""
    text = _read("prompt_injection.txt")
    result = parse_assignment_brief(text)
    # Regardless of LLM output, we must get a valid ParsedAssignment back.
    assert isinstance(result, ParsedAssignment)


def test_garbage_input_does_not_crash_parser():
    text = _read("garbage.txt")
    result = parse_assignment_brief(text)
    assert isinstance(result, ParsedAssignment)
