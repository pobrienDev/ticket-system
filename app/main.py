import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .rate_limit import limiter
from .routers import categories, comments, tickets, users

app = FastAPI(
    title="Ticket Management System",
    description="Helpdesk-style ticket tracking: JWT auth, RBAC, audit logging, email notifications.",
    version="1.0.0",
)

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

app.include_router(users.auth_router)
app.include_router(users.users_router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(categories.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
