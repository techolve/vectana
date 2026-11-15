"""oauth clients and codes (remote MCP)

Revision ID: b2d4f6a8c013
Revises: 9e5b0912c027
Create Date: 2026-11-15 04:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c013'
down_revision: str | None = '9e5b0912c027'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('oauth_clients',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('client_id', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('client_name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
    sa.Column('redirect_uris', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_oauth_clients_client_id'), 'oauth_clients', ['client_id'], unique=True)
    op.create_table('oauth_codes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('code_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('client_id', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('redirect_uri', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False),
    sa.Column('code_challenge', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
    sa.Column('scope', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_oauth_codes_code_hash'), 'oauth_codes', ['code_hash'], unique=True)
    op.create_index(op.f('ix_oauth_codes_user_id'), 'oauth_codes', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_oauth_codes_user_id'), table_name='oauth_codes')
    op.drop_index(op.f('ix_oauth_codes_code_hash'), table_name='oauth_codes')
    op.drop_table('oauth_codes')
    op.drop_index(op.f('ix_oauth_clients_client_id'), table_name='oauth_clients')
    op.drop_table('oauth_clients')
