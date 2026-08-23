"""'new' ticket status, SLA columns, category index

Revision ID: b7e21f0c9d44
Revises: 9a1a2c548483
Create Date: 2026-08-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e21f0c9d44'
down_revision: Union[str, None] = '9a1a2c548483'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # SQLite stores the enum as plain VARCHAR, so only Postgres needs the
        # type extended. ADD VALUE must run outside the migration transaction.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE ticketstatus ADD VALUE IF NOT EXISTS 'new' BEFORE 'open'")

    op.add_column('tickets', sa.Column('due_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tickets', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_tickets_category_id'), 'tickets', ['category_id'], unique=False)


def downgrade() -> None:
    # Postgres cannot drop an enum value; fold any 'new' tickets back into
    # 'open' and leave the extra value in the type.
    op.execute("UPDATE tickets SET status = 'open' WHERE status = 'new'")
    op.drop_index(op.f('ix_tickets_category_id'), table_name='tickets')
    op.drop_column('tickets', 'resolved_at')
    op.drop_column('tickets', 'due_date')
