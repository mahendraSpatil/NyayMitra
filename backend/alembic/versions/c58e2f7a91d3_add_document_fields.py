"""add document_fields and documents.uncertain_spans

Revision ID: c58e2f7a91d3
Revises: a7c41e9d2b10
Create Date: 2026-10-26 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c58e2f7a91d3'
down_revision: Union[str, Sequence[str], None] = 'a7c41e9d2b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'documents',
        sa.Column(
            'uncertain_spans',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
    )
    op.create_table(
        'document_fields',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('extracted_value', sa.String(), nullable=True),
        sa.Column('value', sa.String(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('extractor', sa.String(), nullable=False, server_default='pattern'),
        sa.Column('role_basis', sa.String(), nullable=True),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('span_start', sa.Integer(), nullable=True),
        sa.Column('span_end', sa.Integer(), nullable=True),
        sa.Column('issues', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('reviewed_role', sa.String(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("kind in ('fir_number', 'section', 'date')", name='ck_document_fields_kind'),
        sa.CheckConstraint(
            "role is null or role in "
            "('arrest', 'fir_registered', 'hearing', 'offence_date', 'document_date')",
            name='ck_document_fields_role',
        ),
        sa.CheckConstraint(
            "status in ('auto_accepted', 'needs_review', 'confirmed', 'rejected')",
            name='ck_document_fields_status',
        ),
        sa.CheckConstraint("source in ('text_layer', 'ocr', 'manual')", name='ck_document_fields_source'),
        sa.CheckConstraint(
            "extractor in ('form', 'pattern', 'llm', 'manual')", name='ck_document_fields_extractor'
        ),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_document_fields_document_id', 'document_fields', ['document_id'])
    op.create_index('ix_document_fields_case_id', 'document_fields', ['case_id'])
    # Existing documents get their fields from scripts/extract_fields.py,
    # not here — extraction is Python, and a migration shouldn't import app
    # code that will keep changing after this revision is frozen.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_document_fields_case_id', table_name='document_fields')
    op.drop_index('ix_document_fields_document_id', table_name='document_fields')
    op.drop_table('document_fields')
    op.drop_column('documents', 'uncertain_spans')
