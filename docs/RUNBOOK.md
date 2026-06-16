# Runbook

Practical recipes for running this thing. Each entry is a problem → exact commands → verification.

---

## How do I bring up a fresh local environment?

```bash
git clone <repo-url>
cd School-Operations-Agent-Platform
cp .env.example .env                            # then edit secrets
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python seed.py                                  # optional — creates two demo schools
uvicorn app.main:app --reload
```

Verify: `curl http://127.0.0.1:8000/healthz` returns `{"status":"ok","env":"development"}`.

---

## How do I rotate the JWT signing secret?

1. Generate a new value:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. Update `SECRET_KEY` in the deployment environment (Render → Dashboard → Environment → Edit).
3. Restart the service. **Every existing JWT is now invalid** — users must log in again. This is the expected behaviour after a suspected key compromise. If you instead need a graceful rotation, run two keys in parallel for one token-lifetime window (8 hours by default) — that's not implemented yet, see "Known gaps" at the bottom.

---

## How do I trace one workflow end-to-end?

Every response carries an `X-Correlation-ID` header. Grab it from the browser network tab (or from the user's bug report) and run:

```bash
# Quick view in SQLite
sqlite3 school.db "SELECT created_at, actor_id, event_type, payload FROM audit_events WHERE correlation_id='<ID>' ORDER BY created_at;"

# Or via the API
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/v1/mock/audit-timeline?limit=200" | \
  jq '.session_replay_timeline[] | select(.workflow_id=="<ID>")'
```

The same `correlation_id` appears in application logs — `grep cid=<ID> uvicorn.log`.

---

## A submission is stuck in the wrong state. How do I recover?

`Submission.state` is enforced by the state machine in `app/services/submission_service.py`. **Don't UPDATE the row directly** unless you also write an audit event recording who did it and why — otherwise the next investigation will have a silent gap.

Recommended procedure:
1. Confirm the desired transition is illegal under `LEGAL_TRANSITIONS` (if it's legal, just call the appropriate endpoint).
2. Open a shell with the same correlation ID you'll log under:
   ```python
   from app.database import SessionLocal
   from app.models import Submission, AuditEvent
   import uuid
   db = SessionLocal()
   cid = str(uuid.uuid4())
   sub = db.query(Submission).get("<submission_id>")
   prev = sub.state
   sub.state = "<target_state>"
   db.add(AuditEvent(
       correlation_id=cid, actor_id="ops:<your-name>",
       event_type="SUBMISSION_MANUAL_OVERRIDE",
       payload={"submission_id": sub.id, "from": prev, "to": sub.state, "reason": "<ticket-id>"},
   ))
   db.commit()
   ```
3. Note the `cid` in the ticket so the override is reconstructable.

---

## How do I register the Telegram bot for a new deployment?

1. In Telegram, message `@BotFather` → `/newbot` → follow prompts. Save the bot token.
2. Pick a long random webhook secret:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
3. Set both in your deployment env:
   ```
   TELEGRAM_BOT_TOKEN=<from BotFather>
   TELEGRAM_WEBHOOK_SECRET=<the random value>
   ```
4. Tell Telegram where to send updates:
   ```bash
   curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
     -d "url=https://<your-deploy-host>/api/v1/webhooks/telegram" \
     -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
   ```
5. Verify: `curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"` should show your URL and `"pending_update_count":0`.
6. Send the bot a message from your own Telegram account. Check the audit log for an `INBOUND_CHAT` event with `channel="telegram"`.

If the webhook secret is wrong, the endpoint returns 401 and Telegram will retry with exponential backoff — fix the secret and Telegram catches up automatically.

---

## How do I move from SQLite to Postgres?

1. Provision a Postgres database (Render, Neon, Supabase — anything that gives you a `postgresql://` URL).
2. Update the environment:
   ```
   DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname
   ```
3. `psycopg2-binary` is already in `requirements.txt`, so no code change is needed.
4. Restart. On startup, `init_db()` runs `Base.metadata.create_all` and creates the schema. **For production**, replace this with Alembic migrations (see "Known gaps").
5. If you need to copy demo data over, run `python seed.py` against the new database.

---

## A `pytest` run fails after I added a new model

`tests/conftest.py` uses an in-memory SQLite database that's recreated per test. If you added a model and the tests don't see it, check that the new model file is imported (directly or transitively) before the `Base.metadata.create_all` call in the test fixture. The pattern is: import the model module → `Base` learns about the table → `create_all` creates it.

---

## Known gaps (things this runbook can't solve yet)

- **No Alembic migrations.** Schema changes require a destructive recreate. Acceptable for the take-home; not for production.
- **No graceful JWT key rotation.** Rotation invalidates every session. Acceptable for an emergency rotation; not a routine one.
- **No outbound message kill switch.** If we ever ship a bug that floods guardians, the only recovery is to take the service down. Add a feature flag on the Telegram send path before the first real customer.
- **Audit log has no retention policy.** It will grow forever. Decide retention before this matters.
