"""add web.search permission to admin and manager roles

Revision ID: 0003_add_web_search_permission
Revises: 0002_add_external_id
Create Date: 2026-04-24
"""

from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE roles
        SET permissions = CASE
            WHEN permissions ? 'web.search' THEN permissions
            ELSE permissions || '["web.search"]'::jsonb
        END
        WHERE name IN ('admin', 'manager')
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE roles
        SET permissions = permissions - 'web.search'
        WHERE name IN ('admin', 'manager')
        """
    )
