"""add documents.text_source and documents.ocr_confidence

Revision ID: a7c41e9d2b10
Revises: 02d8c9fca308
Create Date: 2026-10-26 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c41e9d2b10'
down_revision: Union[str, Sequence[str], None] = '02d8c9fca308'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default so existing rows get a valid value; the UPDATE below
    # then corrects the ones we can know the source of. Before this
    # migration the only source of text was the PDF's own text layer
    # (ocrStatus 'extracted'), so that mapping is exact, not a guess.
    op.add_column(
        'documents',
        sa.Column('text_source', sa.String(), nullable=False, server_default='none'),
    )
    op.add_column('documents', sa.Column('ocr_confidence', sa.Float(), nullable=True))
    op.execute(
        "UPDATE documents SET text_source = 'text_layer' "
        "WHERE ocr_status = 'extracted' AND raw_text IS NOT NULL"
    )
    op.create_check_constraint(
        'ck_documents_text_source',
        'documents',
        "text_source in ('text_layer', 'ocr', 'none')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_documents_text_source', 'documents', type_='check')
    op.drop_column('documents', 'ocr_confidence')
    op.drop_column('documents', 'text_source')
