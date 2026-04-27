"""Initial schema: documents + chunks with pgvector

Revision ID: 0001
Revises:
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("doc_id", sa.String(255), primary_key=True),
        sa.Column("source_path", sa.String(1024), nullable=True),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("m2_status", sa.String(20), nullable=True),
        sa.Column("m3_status", sa.String(20), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("doc_id", sa.String(255), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_idx", sa.Integer(), nullable=False),
        sa.Column("chunk_hash", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="'{}'::jsonb"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("chunk_hash", name="uq_chunks_chunk_hash"),
        sa.UniqueConstraint("doc_id", "chunk_idx", name="uq_chunks_doc_chunk_idx"),
    )

    op.execute(
        "ALTER TABLE chunks ADD COLUMN text_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED"
    )
    op.execute(
        "ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024) "
        "USING embedding::vector(1024)"
    )
    op.execute(
        "CREATE INDEX chunks_embedding_ivfflat ON chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
    )
    op.execute("CREATE INDEX chunks_text_tsv ON chunks USING gin(text_tsv)")
    op.create_index("chunks_doc_id", "chunks", ["doc_id"])


def downgrade():
    op.drop_table("chunks")
    op.drop_table("documents")
