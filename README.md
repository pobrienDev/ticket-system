# Ticket Management System

A full-stack helpdesk ticket tracker: **FastAPI + PostgreSQL** backend, **React + Vite** frontend, JWT authentication with role-based access control, audit logging, email notifications, and CI/CD via GitHub Actions.

Built from real helpdesk domain experience: status transitions, assignment, priority triage, comments, and an audit trail — the things a real ticket system actually needs.

## Architecture

```
React (Vite) ──/auth /tickets /users /categories──▶ FastAPI ──▶ PostgreSQL (SQLite in dev)
                                                      │
                                                      └──▶ SendGrid (assignment emails,
                                                           failures logged, never fatal)
GitHub Actions: pytest + ruff + client build on every push; deploy hook on merge to main
```

| Layer | Component | Purpose |
| --- | --- | --- |
| Backend | Auth (JWT) | Registration, login, bcrypt hashing, role checks, login rate limiting |
| Backend | Ticket logic | CRUD, filtering, pagination, search, priority sort |
| Backend | Audit logging | Records every status and assignment change |
| Data | SQLAlchemy + Alembic | Users, Tickets, Comments, Categories, AuditLogEntries |
| Integration | Email API | Notifies the assignee when a ticket is assigned |
| Frontend | React UI | Login/register, ticket list + filters, detail view with comments |
| CI/CD | GitHub Actions | Tests + lint on push, automated deploy on merge to `main` |

## Quick start

Requires Python 3.12+ and Node 20+.

**Backend:**

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (use `source .venv/bin/activate` on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env        # then set JWT_SECRET (see comment in the file)
alembic upgrade head
python -m app.seed            # seeds categories; admin user if ADMIN_EMAIL/ADMIN_PASSWORD set
uvicorn app.main:app --reload
```

API runs at http://localhost:8000 — interactive docs at http://localhost:8000/docs.

**Frontend** (second terminal):

```bash
cd client
npm install
npm run dev
```

UI at http://localhost:5173. The Vite dev server proxies API routes to :8000, so there's no CORS setup in development.

## Data model

- **User** — email, bcrypt-hashed password, `is_admin` flag
- **Ticket** — belongs to an owner (User) and optionally an assignee (User) — two FKs to the same table, so relationships declare `foreign_keys=[...]` explicitly; status enum (`open → in_progress → resolved → closed`), integer priority (1 = highest), optional Category
- **Comment** — belongs to a Ticket and an author (User)
- **Category** — seeded with real helpdesk categories (Printer, Network, M365/Exchange, Yardi/Property Software, Account Access, Hardware)
- **AuditLogEntry** — written automatically whenever a ticket's status or assignee changes: field, old value, new value, actor, timestamp

## API reference

| Method | Route | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/register` | — | Create account (400 on duplicate email) |
| POST | `/auth/login` | — | OAuth2 password form → JWT (rate limited) |
| GET | `/users/me` | user | Current user |
| GET | `/users` | admin | List users |
| GET | `/categories` | user | List categories |
| POST | `/categories` | admin | Create category |
| POST | `/tickets` | user | Create ticket — owner always comes from the token |
| GET | `/tickets` | user | Filters: `status`, `category_id`, `assignee_id`, `q`; `sort=priority\|-priority\|created_at\|-created_at`; `limit`/`offset` pagination; returns `{items, total, limit, offset}` |
| GET | `/tickets/{id}` | user | Ticket with nested comments |
| PATCH | `/tickets/{id}` | owner/admin | Partial update (`exclude_unset`); changing `assignee_id` is admin-only and triggers the email notification |
| DELETE | `/tickets/{id}` | admin | Delete ticket |
| GET | `/tickets/{id}/audit` | user | Status/assignment history |
| POST | `/tickets/{id}/comments` | user | Add comment — author always comes from the token |

## Testing

```bash
pytest --cov=app     # 44 tests, ~89% coverage
ruff check .         # lint
```

Tests cover: registration/login flows (including duplicate email and wrong password), token-derived ownership (a client cannot claim another owner), admin-only routes returning 403 for regular users, partial updates changing only sent fields, audit entries on status/assignee changes, and email failures never breaking assignment (the email API is mocked — the suite makes no network calls).

Tests run on SQLite locally and on PostgreSQL 16 in CI (`TEST_DATABASE_URL`).

## Email notifications

When an admin assigns a ticket, the assignee is emailed via SendGrid. Failure handling is explicit: a failed email is logged with a warning and **never** blocks the assignment (see `app/notifications.py`). Without `SENDGRID_API_KEY` set, emails are logged to the console instead — dev needs no key.

## CI/CD

`.github/workflows/ci.yml` runs on every push and PR:

1. **test** — ruff + pytest against a PostgreSQL 16 service container
2. **frontend** — oxlint + production build of the client
3. **deploy** — on merge to `main` only, POSTs to a Render deploy hook (`RENDER_DEPLOY_HOOK_URL` secret)

## Deployment

- **Backend** → Render/Railway: set `JWT_SECRET`, `DATABASE_URL` (managed Postgres), `SENDGRID_API_KEY`, `EMAIL_FROM`, `CORS_ORIGINS`; run `alembic upgrade head` then `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Frontend** → Vercel/Netlify: build `client/`, point API calls at the backend URL, add that origin to `CORS_ORIGINS`

## Key design decisions

- **`owner_id` and `assignee_id` are both FKs to `users`** — a real two-roles-one-table relationship; SQLAlchemy requires explicit `foreign_keys=[...]` to disambiguate.
- **Owner comes from the JWT, never the request body** — otherwise a client could create tickets in someone else's name. Same for comment authors.
- **Audit log is a separate table** — history is a requirement of its own; overwriting fields loses it.
- **Email failure never blocks assignment** — a secondary concern (notify) must not break a primary one (assign).
- **At 10× scale**: indexes already exist on `status` and `assignee_id`; next would be connection pooling, comment pagination, and caching the category list.
- **For production hardening**: structured logging, a staging environment, team-scoped visibility instead of a single admin flag, soft deletes.
