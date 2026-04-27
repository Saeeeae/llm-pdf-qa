"""add error_msg + m3_started_at

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("error_msg", sa.Text, nullable=True))
    op.add_column("documents", sa.Column("m3_started_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade():
    op.drop_column("documents", "m3_started_at")
    op.drop_column("documents", "error_msg")
