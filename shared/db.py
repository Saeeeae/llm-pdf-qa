# shared/db.py
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from shared.config import shared_settings
from shared.search_terms import BUILTIN_ALIAS_ROWS, normalize_search_text

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def _ensure_app_schema(engine) -> None:
    statements = [
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,
        """
        CREATE TABLE IF NOT EXISTS doc_block (
            block_id SERIAL PRIMARY KEY,
            doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
            block_idx INTEGER NOT NULL,
            block_type VARCHAR(30) NOT NULL DEFAULT 'text',
            page_number INTEGER,
            sheet_name VARCHAR(255),
            slide_number INTEGER,
            section_path TEXT,
            language VARCHAR(10) DEFAULT 'ko',
            bbox JSONB,
            source_text TEXT NOT NULL,
            normalized_text TEXT,
            parent_block_id INTEGER REFERENCES doc_block(block_id) ON DELETE SET NULL,
            image_id INTEGER REFERENCES doc_image(image_id) ON DELETE SET NULL,
            metadata_json JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_doc_block_doc ON doc_block(doc_id, block_idx)",
        "CREATE INDEX IF NOT EXISTS idx_doc_block_type ON doc_block(block_type)",
        "CREATE INDEX IF NOT EXISTS idx_doc_block_page ON doc_block(doc_id, page_number)",
        "CREATE INDEX IF NOT EXISTS idx_doc_block_norm ON doc_block USING gin(to_tsvector('simple', coalesce(normalized_text, source_text)))",
        "ALTER TABLE doc_chunk ADD COLUMN IF NOT EXISTS block_id INTEGER",
        "CREATE INDEX IF NOT EXISTS idx_doc_chunk_block ON doc_chunk(block_id)",
        """
        CREATE TABLE IF NOT EXISTS entity_alias (
            id SERIAL PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            alias_type VARCHAR(50) DEFAULT 'domain',
            language VARCHAR(10) DEFAULT 'ko',
            boost FLOAT DEFAULT 1.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (normalized_alias, canonical_name)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_entity_alias_norm ON entity_alias(normalized_alias)",
        "CREATE INDEX IF NOT EXISTS idx_entity_alias_canonical ON entity_alias(canonical_name)",
        """
        CREATE TABLE IF NOT EXISTS doc_keyword (
            id SERIAL PRIMARY KEY,
            doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
            chunk_id INTEGER NOT NULL REFERENCES doc_chunk(chunk_id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            normalized_keyword TEXT NOT NULL,
            keyword_type VARCHAR(50) DEFAULT 'token',
            weight FLOAT DEFAULT 1.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_doc_keyword_norm ON doc_keyword(normalized_keyword)",
        "CREATE INDEX IF NOT EXISTS idx_doc_keyword_doc ON doc_keyword(doc_id, chunk_id)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_doc_chunk_block'
            ) THEN
                ALTER TABLE doc_chunk
                    ADD CONSTRAINT fk_doc_chunk_block
                    FOREIGN KEY (block_id) REFERENCES doc_block(block_id) ON DELETE SET NULL;
            END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_trigger
                WHERE tgname = 'update_doc_block_updated_at'
            ) THEN
                CREATE TRIGGER update_doc_block_updated_at
                BEFORE UPDATE ON doc_block
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            END IF;
        END $$;
        """,
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

        insert_sql = text(
            """
            INSERT INTO entity_alias (
                canonical_name, alias, normalized_alias, alias_type, language, boost
            ) VALUES (
                :canonical_name, :alias, :normalized_alias, :alias_type, :language, :boost
            )
            ON CONFLICT (normalized_alias, canonical_name) DO NOTHING
            """
        )
        for row in BUILTIN_ALIAS_ROWS:
            conn.execute(insert_sql, {
                "canonical_name": row["canonical_name"],
                "alias": row["alias"],
                "normalized_alias": normalize_search_text(row["alias"]),
                "alias_type": row["alias_type"],
                "language": row["language"],
                "boost": row["boost"],
            })


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            shared_settings.postgres_dsn,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        _ensure_app_schema(_engine)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_session():
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
