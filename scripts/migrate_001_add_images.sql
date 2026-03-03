-- Migration: Add image support
-- Run this on existing deployments that already have the schema

-- 1. Create doc_image table
CREATE TABLE IF NOT EXISTS doc_image (
    image_id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    page_number INTEGER,
    image_path TEXT NOT NULL,
    image_type VARCHAR(20),
    width INTEGER,
    height INTEGER,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_doc_image_doc ON doc_image(doc_id);
CREATE INDEX IF NOT EXISTS idx_doc_image_page ON doc_image(doc_id, page_number);

-- 2. Add columns to doc_chunk
ALTER TABLE doc_chunk ADD COLUMN IF NOT EXISTS chunk_type VARCHAR(20) DEFAULT 'text';
ALTER TABLE doc_chunk ADD COLUMN IF NOT EXISTS image_id INTEGER REFERENCES doc_image(image_id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_doc_chunk_type ON doc_chunk(chunk_type);
