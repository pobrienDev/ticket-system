# Backend image: FastAPI + Alembic. Used by docker-compose and deployable
# to any container host (Render, Railway, Fly).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as an unprivileged user. The app never needs root at runtime, and a
# container escape or a code-execution bug is far less useful without it.
# Created after pip install so the site-packages layer stays root-owned
# and read-only to the app; /app is chowned so the SQLite fallback and
# Alembic can write there when no DATABASE_URL is provided.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app

COPY --chown=app:app alembic.ini .
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
RUN chown app:app /app

USER app

EXPOSE 8000

# Mirrors the /health route, which only returns 200 when the database
# answers, so the container reports unhealthy on a lost DB connection, not
# just a dead process. Uses the stdlib because the slim image has no curl.
# start-period covers migrations running before uvicorn is listening.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

# Migrations run on boot so a fresh database is always brought to head;
# upgrade is a no-op when the schema is already current.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
