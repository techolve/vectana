"""personal tokens

Revision ID: a7e3c5b9d214
Revises: 9d4b6e2a1c58
Create Date: 2026-11-07 11:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a7e3c5b9d214'
down_revision: str | None = '9d4b6e2a1c58'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('personal_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('scope', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
    sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('prefix', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_personal_tokens_token_hash'), 'personal_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_personal_tokens_user_id'), 'personal_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_personal_tokens_user_id'), table_name='personal_tokens')
    op.drop_index(op.f('ix_personal_tokens_token_hash'), table_name='personal_tokens')
    op.drop_table('personal_tokens')
