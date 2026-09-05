"""Application entry point: assembles the FastAPI app.

Everything here is wiring — logging, rate limiting, CORS, and router
registration. Business logic lives in the routers; persistence in models
and database; the API contract in schemas. Run with:

    uvicorn app.main:app --reload
"""

import logging
import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session

from .dependencies import get_db
from .rate_limit import limiter
from .routers import categories, comments, tickets, users

# Root logging config so app loggers (e.g. the console email backend in
# notifications.py) actually print; uvicorn only configures its own loggers.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="Ticket Management System",
    description="Helpdesk-style ticket tracking: JWT auth, RBAC, audit logging, email notifications.",
    version="1.0.0",
)

# slowapi reads the limiter off app.state and needs a handler registered to
# turn RateLimitExceeded into a proper 429 response.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

# Each router owns a URL prefix (/auth, /users, /tickets, /categories); the
# comments router nests under /tickets/{id}/comments.
app.include_router(users.auth_router)
app.include_router(users.users_router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(categories.router)


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    # Touch the database so a deploy health check fails when the DB is down,
    # not just when the process is up.
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - only reachable with a dead DB
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}
