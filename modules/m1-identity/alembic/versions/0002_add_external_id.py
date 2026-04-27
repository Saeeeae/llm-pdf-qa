"""Add external_id, last_synced_at, sync_run table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("external_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_users_external_id", "users", ["external_id"])
    op.create_index("ix_users_external_id", "users", ["external_id"])
    op.create_index("ix_users_last_synced_at", "users", ["last_synced_at"])

    op.add_column("roles", sa.Column("external_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("uq_roles_external_id", "roles", ["external_id"])

    op.add_column("department", sa.Column("external_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("uq_department_external_id", "department", ["external_id"])

    op.create_table(
        "sync_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column("report", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table("sync_run")
    op.drop_constraint("uq_department_external_id", "department")
    op.drop_column("department", "external_id")
    op.drop_constraint("uq_roles_external_id", "roles")
    op.drop_column("roles", "external_id")
    op.drop_index("ix_users_last_synced_at", "users")
    op.drop_index("ix_users_external_id", "users")
    op.drop_constraint("uq_users_external_id", "users")
    op.drop_column("users", "last_synced_at")
    op.drop_column("users", "external_id")
