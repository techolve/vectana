"""tasks: unified tasks, sprints, security task links

Revision ID: 9d4b6e2a1c58
Revises: 7c2e4a1f9b30
Create Date: 2026-11-07 14:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "9d4b6e2a1c58"
down_revision: str | None = "7c2e4a1f9b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AutoString = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table(
        "sprints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", AutoString(length=100), nullable=False),
        sa.Column("goal", AutoString(), nullable=True),
        sa.Column("definition_of_done", sa.JSON(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", AutoString(length=20), nullable=False),
        sa.Column("committed_points", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
    )
    op.create_index(op.f("ix_sprints_project_id"), "sprints", ["project_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("kind", AutoString(length=20), nullable=False),
        sa.Column("title", AutoString(length=300), nullable=False),
        sa.Column("description", AutoString(), nullable=True),
        sa.Column("status", AutoString(length=20), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("is_milestone", sa.Boolean(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("sprint_id", sa.Uuid(), nullable=True),
        sa.Column("points", sa.Float(), nullable=True),
        sa.Column("position", sa.Float(), nullable=False),
        sa.Column("estimate_hours", sa.Float(), nullable=True),
        sa.Column("subject", AutoString(length=20), nullable=True),
        sa.Column("subject_ecosystem", AutoString(length=30), nullable=True),
        sa.Column("subject_name", AutoString(length=300), nullable=True),
        sa.Column("auto_created", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sprint_id"], ["sprints.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "kind", "status", "assignee_id", "parent_id", "sprint_id"):
        op.create_index(op.f(f"ix_tasks_{column}"), "tasks", [column], unique=False)

    op.add_column("vuln_matches", sa.Column("task_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_vuln_matches_task_id"), "vuln_matches", ["task_id"], unique=False)
    op.create_foreign_key(
        "vuln_matches_task_id_fkey",
        "vuln_matches",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("eol_findings", sa.Column("task_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_eol_findings_task_id"), "eol_findings", ["task_id"], unique=False)
    op.create_foreign_key(
        "eol_findings_task_id_fkey",
        "eol_findings",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "projects",
        sa.Column(
            "security_threshold", AutoString(length=20), nullable=False, server_default="HIGH"
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "security_threshold")
    op.drop_constraint("eol_findings_task_id_fkey", "eol_findings", type_="foreignkey")
    op.drop_index(op.f("ix_eol_findings_task_id"), table_name="eol_findings")
    op.drop_column("eol_findings", "task_id")
    op.drop_constraint("vuln_matches_task_id_fkey", "vuln_matches", type_="foreignkey")
    op.drop_index(op.f("ix_vuln_matches_task_id"), table_name="vuln_matches")
    op.drop_column("vuln_matches", "task_id")
    for column in ("project_id", "kind", "status", "assignee_id", "parent_id", "sprint_id"):
        op.drop_index(op.f(f"ix_tasks_{column}"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_sprints_project_id"), table_name="sprints")
    op.drop_table("sprints")
