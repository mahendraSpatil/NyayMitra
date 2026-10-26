"""add case_events.event_type

Revision ID: 02d8c9fca308
Revises: edc7261020c2
Create Date: 2026-09-23 12:48:37.573724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02d8c9fca308'
down_revision: Union[str, Sequence[str], None] = 'edc7261020c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default (not just the ORM-side default in app/db/models.py)
    # so this is safe to run against a case_events table that already has
    # rows, even though it's empty as of this migration — nothing has
    # ever written to it (no route existed until now).
    op.add_column(
        'case_events',
        sa.Column('event_type', sa.String(), nullable=False, server_default='other'),
    )
    op.create_check_constraint(
        'ck_case_events_event_type',
        'case_events',
        "event_type in ('charge_sheet_filed', 'bail_application_submitted', "
        "'bail_order_issued', 'remand_extended', 'other')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_case_events_event_type', 'case_events', type_='check')
    op.drop_column('case_events', 'event_type')
