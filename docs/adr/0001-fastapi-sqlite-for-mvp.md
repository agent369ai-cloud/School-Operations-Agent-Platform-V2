# ADR 0001 — FastAPI + SQLite for the take-home, Postgres path documented

**Status:** Accepted
**Date:** 2026-06-15

## Context

The assignment asks for a production-shaped slice owned by a small team. We needed an HTTP framework with first-class async support (for SSE and webhook handlers), automatic OpenAPI documentation (the assignment evaluators will exercise `/docs`), and a low-ceremony ORM. The team also needed to be able to clone the repo and have it running in under five minutes without standing up a database server.

## Decision

Use **FastAPI** as the web framework and **SQLAlchemy 2.x** as the ORM, with **SQLite** as the default database and **Postgres** as the documented production target. The same code path serves both — `DATABASE_URL` is read from environment, and the only branch is the `check_same_thread` connect-arg, which is SQLite-specific.

## Consequences

**Positive**
- Zero-install local development; `uvicorn app.main:app --reload` works against the repo on a fresh clone with no external services.
- `Base.metadata.create_all` gives us schema-from-models, which is appropriate for a take-home where every change is visible in the model file. For production we'd switch to Alembic.
- FastAPI's dependency injection is the natural place to put the auth + scoped-access checks, which keeps router functions short and the security policy auditable in one file (`app/auth/deps.py`).

**Negative**
- SQLite's default isolation behaviour is laxer than Postgres'. We have not exercised every concurrency edge case under SQLite; before going to production we would run the test suite against Postgres in CI.
- `JSON` columns behave differently on SQLite vs Postgres for indexed queries. We currently only query JSON payload by full-row scan, which is fine for the audit log volume in a take-home but would need GIN indexes in production.

**Future migration**
Switching to Postgres requires only setting `DATABASE_URL=postgresql+psycopg2://...` in `.env`. `psycopg2-binary` is already in `requirements.txt`. The first deploy should run Alembic migrations rather than `create_all`.
