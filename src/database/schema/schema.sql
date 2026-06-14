-- =============================================================================
-- SCHEMA: legal_db
-- Tables for documents, chunks, hierarchy, and amendment relationships.
-- =============================================================================

-- Enable required extensions (vector is commented out until pgvector is installed)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- -----------------------------------------------------------------------------
-- Documents table (parent level)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    title TEXT,
    number TEXT,
    url TEXT,
    issued_date DATE,
    effective_date DATE,
    status TEXT,
    raw_metadata JSONB,
    full_text TSVECTOR,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Chunks table (child level)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    level TEXT,
    article_number TEXT,
    clause_number TEXT,
    point TEXT,
    content TEXT NOT NULL,
    -- embedding vector(768),   -- uncomment after installing pgvector
    full_text TSVECTOR,
    start_char INT,
    end_char INT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Hierarchy table (parent-child relationships between chunks)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunk_hierarchy (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    parent_chunk_id TEXT REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    level_order INT
);

-- -----------------------------------------------------------------------------
-- Amendments table (version graph: which chunk amended which target)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS amendments (
    id SERIAL PRIMARY KEY,
    source_chunk_id TEXT REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    source_doc_id TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
    target_chunk_id TEXT REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    target_doc_id TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
    amendment_type TEXT,
    target_article TEXT,
    target_clause TEXT,
    target_point TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Indexes for performance
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_level ON chunks(level);
CREATE INDEX IF NOT EXISTS idx_hierarchy_parent ON chunk_hierarchy(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_doc_id ON chunk_hierarchy(doc_id);
CREATE INDEX IF NOT EXISTS idx_amendments_source ON amendments(source_chunk_id);
CREATE INDEX IF NOT EXISTS idx_amendments_target ON amendments(target_chunk_id);
CREATE INDEX IF NOT EXISTS idx_amendments_target_doc ON amendments(target_doc_id);

-- Optional: full‑text search indexes (can be created after data is loaded)
-- CREATE INDEX IF NOT EXISTS idx_documents_fulltext ON documents USING GIN(full_text);
-- CREATE INDEX IF NOT EXISTS idx_chunks_fulltext ON chunks USING GIN(full_text);