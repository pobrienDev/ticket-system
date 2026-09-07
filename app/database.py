"""Database engine and session factory.

Which database backs the app is decided entirely by DATABASE_URL: SQLite for
local development (zero setup), Postgres in CI and production. Nothing else
in the codebase needs to know which one is in use — the two places that must
differ (foreign-key enforcement, threading) are handled here.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

# SQLite by default for local development; set DATABASE_URL to a
# postgresql:// URL in .env (or the host's environment) for production.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./ticket_system.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    # SQLite connections refuse use from a thread other than the one that
    # opened them; FastAPI runs sync handlers on a threadpool, so that check
    # must be off. (Postgres drivers have no such restriction.)
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    # Test each pooled connection with a trivial round-trip before handing
    # it out, so a connection that died while idle (database restart, idle
    # timeout at a proxy) is replaced instead of surfacing as a 500 on the
    # first request after the outage.
    pool_pre_ping=True,
    # SQL_ECHO=true logs every statement — the quickest way to spot an N+1.
    echo=os.environ.get("SQL_ECHO", "").lower() == "true",
)

if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, _record):
        """Turn on foreign-key enforcement for each new SQLite connection.

        SQLite ships with foreign keys OFF and the setting is per connection,
        so it has to be applied every time the pool opens one. Without this,
        every ForeignKey in the schema is decoration in development while
        Postgres enforces it in CI and production — a behavior gap that hides
        bugs. (tests/conftest.py installs the same hook on the test engine.)
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Factory for the per-request Session handed out by dependencies.get_db.
# autoflush is off so a query never triggers a surprise write mid-request:
# changes reach the database only on the explicit commit() in the handler.
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """Declarative base every model inherits from.

    Base.metadata knows every table, which is what the test suite's
    create_all and Alembic's autogenerate/`alembic check` read.
    """
