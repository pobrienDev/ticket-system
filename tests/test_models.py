"""Model-level rules in app/models.py: the UTC datetime type, the priority
check constraint, the indexes the list query depends on, and the domain
constants the rest of the app derives from."""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app import models

UTC = datetime.timezone.utc


# --- UTCDateTime ------------------------------------------------------------


def test_utcdatetime_normalizes_on_the_way_in():
    column_type = models.UTCDateTime()
    eastern = datetime.timezone(datetime.timedelta(hours=-5))
    aware = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=eastern)
    naive = datetime.datetime(2026, 1, 1, 12, 0)

    # An aware value is converted to UTC; a naive one is taken AS UTC rather
    # than passed through ambiguous.
    assert column_type.process_bind_param(aware, None) == datetime.datetime(2026, 1, 1, 17, 0, tzinfo=UTC)
    assert column_type.process_bind_param(naive, None) == datetime.datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert column_type.process_bind_param(None, None) is None


def test_utcdatetime_reattaches_utc_on_the_way_out():
    # SQLite returns naive datetimes; the decorator restores the offset so
    # the API never serializes a timestamp without one.
    column_type = models.UTCDateTime()
    naive_from_db = datetime.datetime(2026, 1, 1, 12, 0)
    assert column_type.process_result_value(naive_from_db, None).tzinfo == UTC
    assert column_type.process_result_value(None, None) is None


# --- Database-level constraints ---------------------------------------------


def test_priority_range_is_enforced_by_the_database(db, test_user):
    # Pydantic guards the API; this guards every other writer.
    db.add(models.Ticket(title="Bad priority", priority=9, owner_id=test_user.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(models.Ticket(title="Edge priorities", priority=models.PRIORITY_MAX, owner_id=test_user.id))
    db.commit()  # 5 is allowed


def test_list_filter_columns_are_indexed():
    indexed = {column.name for index in models.Ticket.__table__.indexes for column in index.columns}
    assert {"owner_id", "assignee_id", "category_id", "status"} <= indexed


# --- Domain constants -------------------------------------------------------


def test_transition_map_covers_every_status_without_self_loops():
    statuses = set(models.TicketStatus)
    assert set(models.ALLOWED_TRANSITIONS) == statuses
    for status, targets in models.ALLOWED_TRANSITIONS.items():
        assert status not in targets
        assert targets <= statuses


def test_unresolved_statuses_are_exactly_the_unfinished_ones():
    assert set(models.UNRESOLVED_STATUSES) == {
        models.TicketStatus.new,
        models.TicketStatus.open,
        models.TicketStatus.in_progress,
    }


def test_sla_hours_cover_every_priority_and_get_longer_as_priority_drops():
    assert sorted(models.SLA_HOURS) == list(range(models.PRIORITY_MIN, models.PRIORITY_MAX + 1))
    hours = [models.SLA_HOURS[p] for p in sorted(models.SLA_HOURS)]
    assert hours == sorted(hours)  # P1 shortest, P5 longest
