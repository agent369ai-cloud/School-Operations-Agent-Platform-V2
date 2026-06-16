# ADR 0002 — LLM output is a proposal, never an action

**Status:** Accepted
**Date:** 2026-06-15

## Context

The platform parses documents (assignment briefs, rosters) with an LLM and routes inbound chat messages by inferred intent. LLMs hallucinate, mis-extract dates, and can be prompt-injected by the very documents they're asked to parse. If the model's output silently activates state — creating an assignment with a wrong due date, or marking a submission complete because a student typed the word "done" inside an unrelated sentence — the system has effectively delegated a teacher's authority to a probabilistic function.

The assignment's "Ask, Don't Guess" rubric criterion (Section 3) makes this concrete: when the model is uncertain, the system must surface a clarification, not fabricate a value.

## Decision

**No model output ever directly activates state.** Every LLM call produces a *proposal* that lives in a `DRAFT` / `PENDING` row and requires an explicit human approval transition before it counts.

Concretely:

1. **Structured output only.** `ai_parser.parse_assignment_brief` always returns a `ParsedAssignment` pydantic schema, never raw text. If the upstream call fails or returns unparseable JSON, we return a deterministic placeholder with `is_ambiguous=True` — we do *not* silently activate state on failure.
2. **Prompt-injection fencing.** Document text is wrapped in `<document>…</document>` tags in the prompt, and the system message tells the model to ignore any instructions appearing inside those tags. This is defence in depth, not a guarantee — see the threat model.
3. **Approval gate at the data layer.** New `Assignment` rows are created with `status="DRAFT"` and a `source_document_id` pointing at the `Document` row. `POST /assignments/{id}/approve` is the only path that moves them to `ACTIVE`. Until then, students don't see them.
4. **Intent routing writes proposed state transitions, not final ones.** When a student message classifies as `STUDENT_SUBMISSION`, we move the submission to `SUBMITTED` (which is itself a state requiring teacher review before `COMPLETED`). We never let an LLM-inferred intent reach a terminal state.

## Consequences

**Positive**
- A bad parse never silently corrupts the gradebook. The worst case is a teacher seeing a draft they have to fix.
- Prompt injection that succeeds in changing the parsed JSON still cannot ship without a human click — the blast radius is "one weird draft", not "altered live data".
- The approval gate gives us a free audit trail: every approved assignment has a recorded approver and timestamp.

**Negative**
- More clicks for the teacher in the happy path. We expect this to be acceptable for high-stakes operations (assignments, rosters); we would not apply the same gate to a low-stakes feature like message summarisation.
- Two-stage state for assignments (`DRAFT` → `ACTIVE`) increases the surface the UI has to handle — every list view needs a filter and a "needs review" badge.

**Out of scope for the take-home, in scope for production**
- A confidence score on every extraction, surfaced in the review UI.
- Diff view between the raw document and the proposed structured fields, so the approver can spot-check without re-reading the source.
- A small evals harness comparing model outputs to a gold set on every PR (we have a placeholder at `tests/evals/`).
