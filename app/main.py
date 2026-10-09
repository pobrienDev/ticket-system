"""Application entry point: assembles the FastAPI app.

Everything here is wiring — logging, rate limiting, CORS, security headers,
router registration, and the health check. Business logic lives in the
routers; persistence in models and database; the API contract in schemas.
Run with:

    uvicorn app.main:app --reload
"""

import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .dependencies import get_db
from .rate_limit import limiter
from .routers import categories, comments, tickets, users

# Root logging config so app loggers (e.g. the console email backend in
# notifications.py) actually print; uvicorn only configures its own loggers.
logging.basicConfig(
    level=(os.environ.get("LOG_LEVEL") or "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# APP_ENV=production turns off the interactive docs and the raw OpenAPI
# spec. They are invaluable in development and for demos, but in production
# they publish every route and schema to anyone who finds the URL.
APP_ENV = (os.environ.get("APP_ENV") or "development").lower()


def docs_settings(env: str) -> dict:
    """FastAPI constructor arguments controlling the docs, by environment."""
    if env == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


app = FastAPI(
    title="Ticket Management System",
    description="Helpdesk-style ticket tracking: JWT auth, RBAC, audit logging, email notifications.",
    version="1.0.0",
    **docs_settings(APP_ENV),
)



def rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Turn a tripped limit into a 429 the client can explain.

    slowapi's stock handler answers {"error": ...}; every other error from
    this API carries `detail`, which is the key the frontend reads, so a
    throttled login used to surface as a bare "Request failed (429)".
    Retry-After is the window of the limit that tripped (60 for "10/minute").
    """
    retry_after = exc.limit.limit.get_expiry()
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many attempts. Try again in {retry_after} seconds."},
        headers={"Retry-After": str(retry_after)},
    )


# slowapi reads the limiter off app.state and needs a handler registered to
# turn RateLimitExceeded into a 429 response.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded)

# In dev the Vite proxy makes requests same-origin, so CORS only matters for a
# separately-hosted frontend (e.g. Vercel). Set CORS_ORIGINS=https://myapp.vercel.app
cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add the browser-protection headers that are safe for a JSON API.

    nosniff stops a browser second-guessing content types; DENY blocks the
    API (and /docs) from being framed by another site; the referrer policy
    keeps URLs from leaking to third parties. Strict-Transport-Security is
    deliberately absent — it must be set by whatever terminates TLS — and a
    Content-Security-Policy would break the CDN-served /docs page.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


# Each router owns a URL prefix (/auth, /users, /tickets, /categories); the
# comments router nests under /tickets/{id}/comments.
app.include_router(users.auth_router)
app.include_router(users.users_router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(categories.router)


@app.get("/", tags=["health"])
def root():
    """Say what this is to anyone who opens the bare URL.

    The API has no pages of its own, so without this the service's address
    answers 404 and looks broken to a person checking a deploy. It names the
    service and points at the health check, at the frontend when APP_URL is
    configured, and at the docs only where they are actually served. No
    database access and no auth: it must answer even when everything else
    is down, and it reveals nothing the frontend's own requests don't.
    """
    info = {"service": app.title, "health": "/health"}
    app_url = os.environ.get("APP_URL", "").rstrip("/")
    if app_url:
        info["app"] = app_url
    if APP_ENV != "production":
        info["docs"] = "/docs"
    return info


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    """Liveness and readiness in one: 200 only if the database answers.

    A platform health check that only proved the process was up would keep
    routing traffic to an instance whose database connection had failed;
    the SELECT 1 makes the check reflect real readiness.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}
