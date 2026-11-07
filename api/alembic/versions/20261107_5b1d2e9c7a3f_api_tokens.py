"""api tokens

Revision ID: 5b1d2e9c7a3f
Revises: 0c48bb708de9
Create Date: 2026-11-07 04:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5b1d2e9c7a3f'
down_revision: str | None = '0c48bb708de9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('prefix', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_api_tokens_created_by'), 'api_tokens', ['created_by'], unique=False)
    op.create_index(op.f('ix_api_tokens_project_id'), 'api_tokens', ['project_id'], unique=False)
    op.create_index(op.f('ix_api_tokens_token_hash'), 'api_tokens', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_api_tokens_token_hash'), table_name='api_tokens')
    op.drop_index(op.f('ix_api_tokens_project_id'), table_name='api_tokens')
    op.drop_index(op.f('ix_api_tokens_created_by'), table_name='api_tokens')
    op.drop_table('api_tokens')
