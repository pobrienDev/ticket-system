# Backend image: FastAPI + Alembic. Used by docker-compose and deployable
# to any container host (Render, Railway, Fly).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

# Migrations run on boot so a fresh database is always brought to head;
# upgrade is a no-op when the schema is already current.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
