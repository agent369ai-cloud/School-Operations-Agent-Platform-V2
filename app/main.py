"""FastAPI app factory + middleware + router wiring."""
import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db
from app.routers import (
    auth as auth_router,
    chat_mock,
    classrooms as classrooms_router,
    guardians as guardians_router,
    ingestion,
    invitations as invitations_router,
    submissions as submissions_router,
    telegram_webhook,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] cid=%(correlation_id)s %(message)s",
)

# Inject default correlation_id into every log record
old_factory = logging.getLogRecordFactory()


def record_factory(*args, **kwargs):
    record = old_factory(*args, **kwargs)
    if not hasattr(record, "correlation_id"):
        record.correlation_id = "-"
    return record


logging.setLogRecordFactory(record_factory)


app = FastAPI(
    title="School Operations Agent Platform",
    version="2.0.0",
    description="Multi-tenant school operations with role-scoped access and audited LLM-as-proposal workflows.",
)

# CORS — keep tight in production; permissive here for the demo dashboard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else [],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    try:
        return templates.TemplateResponse("dashboard.html", {"request": request})
    except Exception as e:
        return HTMLResponse(
            f"<h1>School Operations Platform</h1>"
            f"<p>Dashboard template missing. Visit <a href='/docs'>/docs</a>.</p>"
            f"<pre>{e}</pre>"
        )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "env": settings.APP_ENV}


# Router wiring
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(invitations_router.router, prefix="/api/v1/invitations", tags=["Invitations"])
app.include_router(classrooms_router.router, prefix="/api/v1/classrooms", tags=["Classrooms"])
app.include_router(ingestion.router, prefix="/api/v1/ingestion", tags=["Document Ingestion"])
app.include_router(submissions_router.router, prefix="/api/v1/submissions", tags=["Submissions"])
app.include_router(guardians_router.router, prefix="/api/v1/guardians", tags=["Guardians"])
app.include_router(chat_mock.router, prefix="/api/v1/mock", tags=["Chat (mock)"])
app.include_router(telegram_webhook.router, prefix="/api/v1/webhooks", tags=["Webhooks"])
