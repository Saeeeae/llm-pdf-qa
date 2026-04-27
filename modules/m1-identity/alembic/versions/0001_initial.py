"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "department",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), sa.ForeignKey("department.id"), nullable=True),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("permissions", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("department_id", sa.BigInteger(), sa.ForeignKey("department.id"), nullable=True),
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_token",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("device_info", sa.String(512), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_hash"),
    )
    op.create_index("ix_refresh_token_hash", "refresh_token", ["token_hash"], unique=True)

    op.create_table(
        "user_preference",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("theme", sa.String(50), nullable=True, server_default="light"),
        sa.Column("language", sa.String(10), nullable=True, server_default="en"),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "access_request",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_user_ts", "audit_log", ["user_id", "ts"])

    # Seed default roles
    op.execute("""
        INSERT INTO roles (name, description, permissions) VALUES
        ('admin', 'Full access', '["user.read","user.write","user.delete","doc.read","doc.write","chat.use","web.search","admin.read","admin.write","audit.read"]'::jsonb),
        ('manager', 'Manager access', '["user.read","doc.read","doc.write","chat.use","web.search","admin.read","audit.read"]'::jsonb),
        ('user', 'Standard user', '["doc.read","chat.use"]'::jsonb)
    """)


def downgrade():
    op.drop_table("audit_log")
    op.drop_table("access_request")
    op.drop_table("user_preference")
    op.drop_table("refresh_token")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("department")
