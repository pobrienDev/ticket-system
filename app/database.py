"""Database engine and session factory.

Which database backs the app is decided entirely by DATABASE_URL: SQLite for
local development (zero setup), Postgres in CI and production. Nothing else
in the codebase needs to know which one is in use.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# SQLite by default for local development; set DATABASE_URL to a
# postgresql:// URL in .env (or the host's environment) for production.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./ticket_system.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

if DATABASE_URL.startswith("sqlite"):
    # SQLite ignores foreign keys unless the pragma is set per connection;
    # without this every FK in the schema is silently unenforced in dev.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
# One Session per request (see dependencies.get_db); explicit commits only.
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Every model inherits from Base, so Base.metadata describes the full schema —
# that is what the test suite's create_all and Alembic's autogenerate read.
Base = declarative_base()
