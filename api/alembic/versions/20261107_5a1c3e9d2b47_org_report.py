"""org dashboard SLA and weekly report

Revision ID: 5a1c3e9d2b47
Revises: 5b1d2e9c7a3f
Create Date: 2026-11-07 04:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5a1c3e9d2b47'
down_revision: str | None = '5b1d2e9c7a3f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLA_DEFAULTS = {
    'sla_critical_days': '7',
    'sla_high_days': '30',
    'sla_medium_days': '90',
    'sla_low_days': '180',
    'sla_unknown_days': '90',
}


def upgrade() -> None:
    for name, default in SLA_DEFAULTS.items():
        op.add_column('app_settings', sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column('app_settings', sa.Column('report_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('app_settings', sa.Column('report_weekday', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('report_deliveries',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('period', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'period')
    )
    op.create_index(op.f('ix_report_deliveries_user_id'), 'report_deliveries', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_report_deliveries_user_id'), table_name='report_deliveries')
    op.drop_table('report_deliveries')
    op.drop_column('app_settings', 'report_weekday')
    op.drop_column('app_settings', 'report_enabled')
    for name in reversed(list(SLA_DEFAULTS)):
        op.drop_column('app_settings', name)
