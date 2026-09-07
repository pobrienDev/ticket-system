"""Engine configuration in app/database.py.

The API tests run against the test engine built in conftest, so the app's
own engine is otherwise never exercised. These pin the settings that only
matter in real deployments (connection health checks) or that silently
change behavior if lost (SQLite foreign-key enforcement).
"""

from sqlalchemy import text

from app import database


def test_engine_pre_pings_pooled_connections():
    # A dead pooled connection must be replaced, not handed to a request.
    assert database.engine.pool._pre_ping is True


def test_sqlite_connections_enforce_foreign_keys():
    if not database.IS_SQLITE:
        return  # Postgres always enforces; the hook is SQLite-only by design
    with database.engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_sessions_do_not_autoflush():
    # Writes reach the database only on explicit commit(); a query inside a
    # handler must never flush pending changes as a side effect.
    session = database.SessionLocal()
    try:
        assert session.autoflush is False
        assert session.get_bind() is database.engine
    finally:
        session.close()


def test_base_metadata_covers_every_table():
    # Alembic's drift check and the test suite's create_all both rely on
    # Base.metadata being the complete schema.
    from app import models  # noqa: F401  (importing registers the tables)

    assert set(database.Base.metadata.tables) == {
        "users",
        "categories",
        "tickets",
        "comments",
        "audit_log_entries",
    }
