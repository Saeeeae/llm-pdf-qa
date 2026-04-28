"""parent_chunks + L1 metadata + HNSW index

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-28

Changes:
- New table parent_chunks for hierarchical retrieval (small leaf -> large parent expansion).
- chunks.parent_id FK to parent_chunks(id).
- documents.folder_path / chunks.folder_path for L1 structural filtering.
- Drop ivfflat, add HNSW on chunks.embedding.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # 1. parent_chunks
    op.create_table(
        "parent_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "doc_id",
            sa.String(255),
            sa.ForeignKey("documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_idx", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="'{}'::jsonb"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("doc_id", "chunk_idx", name="uq_parent_chunks_doc_idx"),
    )
    op.create_index("parent_chunks_doc_id", "parent_chunks", ["doc_id"])

    # 2. chunks.parent_id (nullable initially; backfill later if existing rows)
    op.add_column(
        "chunks",
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            sa.ForeignKey("parent_chunks.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("chunks_parent_id", "chunks", ["parent_id"])

    # 3. L1 structural metadata
    op.add_column("documents", sa.Column("folder_path", sa.String(1024), nullable=True))
    op.add_column("documents", sa.Column("doc_meta", postgresql.JSONB(), server_default="'{}'::jsonb"))
    op.add_column("chunks", sa.Column("folder_path", sa.String(1024), nullable=True))
    op.create_index("chunks_folder_path", "chunks", ["folder_path"])
    op.create_index("documents_folder_path", "documents", ["folder_path"])

    # 4. ivfflat -> HNSW
    op.execute("DROP INDEX IF EXISTS chunks_embedding_ivfflat")
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS chunks_embedding_hnsw")
    op.execute(
        "CREATE INDEX chunks_embedding_ivfflat ON chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
    )
    op.drop_index("documents_folder_path", table_name="documents")
    op.drop_index("chunks_folder_path", table_name="chunks")
    op.drop_column("chunks", "folder_path")
    op.drop_column("documents", "doc_meta")
    op.drop_column("documents", "folder_path")
    op.drop_index("chunks_parent_id", table_name="chunks")
    op.drop_column("chunks", "parent_id")
    op.drop_index("parent_chunks_doc_id", table_name="parent_chunks")
    op.drop_table("parent_chunks")
