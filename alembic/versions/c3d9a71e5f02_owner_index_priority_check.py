"""owner_id index and priority range check

Revision ID: c3d9a71e5f02
Revises: b7e21f0c9d44
Create Date: 2026-09-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d9a71e5f02'
down_revision: Union[str, None] = 'b7e21f0c9d44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every non-admin list query filters on owner_id OR assignee_id;
    # assignee_id was already indexed, owner_id was not.
    op.create_index(op.f('ix_tickets_owner_id'), 'tickets', ['owner_id'], unique=False)
    # The API validates priority 1–5; this makes the database enforce it
    # too. Batch mode rebuilds the table on SQLite, which cannot add a
    # constraint in place; on Postgres it is a plain ALTER TABLE.
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.create_check_constraint('ck_tickets_priority_range', 'priority BETWEEN 1 AND 5')


def downgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_constraint('ck_tickets_priority_range', type_='check')
    op.drop_index(op.f('ix_tickets_owner_id'), table_name='tickets')
