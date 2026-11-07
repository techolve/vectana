"""pm foundation: customers, project status, estimates, multiple roles

Revision ID: 7c2e4a1f9b30
Revises: f620d066af9c
Create Date: 2026-11-07 10:00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '7c2e4a1f9b30'
down_revision: str | None = 'f620d066af9c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AutoString = sqlmodel.sql.sqltypes.AutoString


def _roles_from_role(table_name: str) -> None:
    """users.role / invitations.role ("member" = none) -> roles JSON list."""
    bind = op.get_bind()
    table = sa.table(
        table_name,
        sa.column('id', sa.Uuid()),
        sa.column('role', AutoString(length=20)),
        sa.column('roles', sa.JSON()),
    )
    for row in bind.execute(sa.select(table.c.id, table.c.role)).all():
        roles = [] if row.role in (None, 'member') else [row.role]
        bind.execute(table.update().where(table.c.id == row.id).values(roles=roles))


def _role_from_roles(table_name: str) -> None:
    bind = op.get_bind()
    table = sa.table(
        table_name,
        sa.column('id', sa.Uuid()),
        sa.column('role', AutoString(length=20)),
        sa.column('roles', sa.JSON()),
    )
    for row in bind.execute(sa.select(table.c.id, table.c.roles)).all():
        roles = row.roles or []
        role = next((r for r in ('group_admin', 'company_admin') if r in roles), 'member')
        bind.execute(table.update().where(table.c.id == row.id).values(role=role))


def upgrade() -> None:
    op.create_table('customers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('name', AutoString(length=200), nullable=False),
    sa.Column('industry', AutoString(length=100), nullable=True),
    sa.Column('address', AutoString(length=300), nullable=True),
    sa.Column('phone', AutoString(length=50), nullable=True),
    sa.Column('website', AutoString(length=300), nullable=True),
    sa.Column('payment_terms', AutoString(length=200), nullable=True),
    sa.Column('billing_contact', AutoString(length=200), nullable=True),
    sa.Column('notes', AutoString(), nullable=True),
    sa.Column('sales_owner_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sales_owner_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customers_company_id'), 'customers', ['company_id'], unique=False)
    op.create_index(op.f('ix_customers_sales_owner_id'), 'customers', ['sales_owner_id'], unique=False)
    op.create_table('customer_contacts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('customer_id', sa.Uuid(), nullable=False),
    sa.Column('name', AutoString(length=100), nullable=False),
    sa.Column('title', AutoString(length=200), nullable=True),
    sa.Column('email', AutoString(length=255), nullable=True),
    sa.Column('phone', AutoString(length=50), nullable=True),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_contacts_customer_id'), 'customer_contacts', ['customer_id'], unique=False)

    with op.batch_alter_table('projects') as batch:
        batch.add_column(sa.Column('customer_id', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('status', AutoString(length=20), nullable=False, server_default='development'))
        batch.add_column(sa.Column('method', AutoString(length=20), nullable=False, server_default='waterfall'))
        batch.add_column(sa.Column('ordered_on', sa.Date(), nullable=True))
        batch.add_column(sa.Column('starts_on', sa.Date(), nullable=True))
        batch.add_column(sa.Column('ends_on', sa.Date(), nullable=True))
        batch.add_column(sa.Column('sales_owner_id', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('manager_id', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('expected_amount', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('probability', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('next_action', AutoString(length=200), nullable=True))
        batch.add_column(sa.Column('next_action_on', sa.Date(), nullable=True))
        batch.add_column(sa.Column('lost_reason', AutoString(), nullable=True))
        batch.add_column(sa.Column('competitor', AutoString(length=200), nullable=True))
        batch.create_index(batch.f('ix_projects_customer_id'), ['customer_id'], unique=False)
        batch.create_index(batch.f('ix_projects_status'), ['status'], unique=False)
        batch.create_index(batch.f('ix_projects_sales_owner_id'), ['sales_owner_id'], unique=False)
        batch.create_index(batch.f('ix_projects_manager_id'), ['manager_id'], unique=False)
        batch.create_foreign_key('projects_customer_id_fkey', 'customers', ['customer_id'], ['id'], ondelete='SET NULL')
        batch.create_foreign_key('projects_sales_owner_id_fkey', 'users', ['sales_owner_id'], ['id'], ondelete='SET NULL')
        batch.create_foreign_key('projects_manager_id_fkey', 'users', ['manager_id'], ['id'], ondelete='SET NULL')
    # Projects that exist today are running systems: treat them as ordered so
    # department heads, PMO and accounting keep seeing them.
    projects = sa.table('projects', sa.column('ordered_on', sa.Date()), sa.column('created_at', sa.DateTime(timezone=True)))
    op.execute(projects.update().values(ordered_on=sa.cast(projects.c.created_at, sa.Date())))

    op.create_table('estimates',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('title', AutoString(length=200), nullable=False),
    sa.Column('kind', AutoString(length=20), nullable=False),
    sa.Column('status', AutoString(length=20), nullable=False),
    sa.Column('billing', AutoString(length=20), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=True),
    sa.Column('effort_days', sa.Float(), nullable=True),
    sa.Column('issued_on', sa.Date(), nullable=True),
    sa.Column('due_on', sa.Date(), nullable=True),
    sa.Column('valid_until', sa.Date(), nullable=True),
    sa.Column('decided_on', sa.Date(), nullable=True),
    sa.Column('lost_reason', AutoString(), nullable=True),
    sa.Column('competitor', AutoString(length=200), nullable=True),
    sa.Column('notes', AutoString(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_estimates_project_id'), 'estimates', ['project_id'], unique=False)
    op.create_table('estimate_lines',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('estimate_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('label', AutoString(length=200), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('days', sa.Float(), nullable=False),
    sa.Column('unit_cost', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['estimate_id'], ['estimates.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_estimate_lines_estimate_id'), 'estimate_lines', ['estimate_id'], unique=False)

    for name in ('users', 'invitations'):
        with op.batch_alter_table(name) as batch:
            batch.add_column(sa.Column('roles', sa.JSON(), nullable=False, server_default='[]'))
        _roles_from_role(name)
        with op.batch_alter_table(name) as batch:
            batch.drop_column('role')
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('unit_cost', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('unit_cost')
    for name in ('users', 'invitations'):
        with op.batch_alter_table(name) as batch:
            batch.add_column(sa.Column('role', AutoString(length=20), nullable=False, server_default='member'))
        _role_from_roles(name)
        with op.batch_alter_table(name) as batch:
            batch.drop_column('roles')

    op.drop_index(op.f('ix_estimate_lines_estimate_id'), table_name='estimate_lines')
    op.drop_table('estimate_lines')
    op.drop_index(op.f('ix_estimates_project_id'), table_name='estimates')
    op.drop_table('estimates')
    with op.batch_alter_table('projects') as batch:
        batch.drop_constraint('projects_manager_id_fkey', type_='foreignkey')
        batch.drop_constraint('projects_sales_owner_id_fkey', type_='foreignkey')
        batch.drop_constraint('projects_customer_id_fkey', type_='foreignkey')
        batch.drop_index(batch.f('ix_projects_manager_id'))
        batch.drop_index(batch.f('ix_projects_sales_owner_id'))
        batch.drop_index(batch.f('ix_projects_status'))
        batch.drop_index(batch.f('ix_projects_customer_id'))
        for column in ('competitor', 'lost_reason', 'next_action_on', 'next_action', 'probability',
                       'expected_amount', 'manager_id', 'sales_owner_id', 'ends_on', 'starts_on',
                       'ordered_on', 'method', 'status', 'customer_id'):
            batch.drop_column(column)
    op.drop_index(op.f('ix_customer_contacts_customer_id'), table_name='customer_contacts')
    op.drop_table('customer_contacts')
    op.drop_index(op.f('ix_customers_sales_owner_id'), table_name='customers')
    op.drop_index(op.f('ix_customers_company_id'), table_name='customers')
    op.drop_table('customers')
