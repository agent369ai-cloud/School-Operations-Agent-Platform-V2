# ADR 0003 — `correlation_id` is the single workflow trace ID

**Status:** Accepted
**Date:** 2026-06-15

## Context

The minimum live scenario (assignment Section 6) ends with a request to "show one workflow_id stitched across webhook → intent → action → notification → dashboard." Any operations team running this in production needs the same property for incident debugging — when something looks wrong on the dashboard, you have to be able to follow the thread back through every service that touched it.

Without a deliberate plan, this fragments instantly: the webhook handler logs one ID, the intent classifier generates a new one, the notification job runs hours later with no context, and the audit log ends up with five disconnected fragments per real-world workflow.

## Decision

**One `correlation_id` per inbound trigger, propagated and persisted everywhere downstream.**

- The HTTP middleware in `app/main.py` runs first on every request. If the caller supplied an `X-Correlation-ID` header, we use it; otherwise we generate a UUID4. Either way, it lives on `request.state.correlation_id` and is echoed in the response header.
- The logging factory injects `correlation_id` into every log record's format string, so application logs and the audit log share the same identifier without any per-log-call wiring.
- Every `AuditEvent` row stores the `correlation_id` in an indexed column. The audit timeline endpoint groups by it; that's how the demo "stitch a workflow" view works.
- For background work triggered by an inbound request (scheduler runs, outbound Telegram sends), the originating `correlation_id` is passed forward in the call args. When a job is *not* triggered by a request (the periodic scheduler tick), it generates its own ID at the top of the run.

## Consequences

**Positive**
- One-line query to reconstruct any workflow: `SELECT * FROM audit_events WHERE correlation_id = ? ORDER BY created_at`. This is also what powers the "session replay timeline" endpoint.
- The same ID surfaces in the `X-Correlation-ID` response header, so when a teacher reports a bug ("submission didn't go through") they can copy the header from their browser's network tab and we can find the exact trace.
- Migration to OpenTelemetry later is straightforward — `correlation_id` becomes the `trace_id` and individual handlers become spans. No data model change.

**Negative**
- We do not (yet) sample. Every request creates an audit trail. At the take-home's expected volume this is fine; at scale we would either move audit writes async or apply a sampling policy to non-state-changing requests.
- We rely on developer discipline to thread the ID through background jobs. A static analysis check or a context-var-based approach would be more robust; we accepted the simpler version for the take-home and documented the gap.

**Anti-patterns this rules out**
- *Don't* generate a new ID inside service functions when one is already on the request. The middleware is authoritative.
- *Don't* skip the audit write on "boring" actions. The whole point is reconstruction; gaps are worse than verbosity.
