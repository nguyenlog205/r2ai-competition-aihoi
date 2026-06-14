#!/usr/bin/env python3
"""
Create database schema dynamically based on embedding configuration.
Run this once (or after config changes) to set up tables.
"""

from src.utils.config_loader import get_config
from src.database.utils.database_client import DatabaseClient
from src.utils.log import get_logger

logger = get_logger("create_schema")

def create_schema():
    config = get_config()
    emb_cfg = config.get("embedding", {})
    models = emb_cfg.get("models", [])
    enabled_models = [m for m in models if m.get("enabled")]

    # SQL for base tables (no embedding columns yet)
    base_sql = """
    CREATE EXTENSION IF NOT EXISTS vector;

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

    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
        level TEXT,
        article_number TEXT,
        clause_number TEXT,
        point TEXT,
        content TEXT NOT NULL,
        full_text TSVECTOR,
        start_char INT,
        end_char INT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS chunk_hierarchy (
        chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
        doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
        parent_chunk_id TEXT REFERENCES chunks(chunk_id) ON DELETE CASCADE,
        level_order INT
    );

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

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
    CREATE INDEX IF NOT EXISTS idx_chunks_level ON chunks(level);
    CREATE INDEX IF NOT EXISTS idx_hierarchy_parent ON chunk_hierarchy(parent_chunk_id);
    CREATE INDEX IF NOT EXISTS idx_hierarchy_doc_id ON chunk_hierarchy(doc_id);
    CREATE INDEX IF NOT EXISTS idx_amendments_source ON amendments(source_chunk_id);
    CREATE INDEX IF NOT EXISTS idx_amendments_target ON amendments(target_chunk_id);
    CREATE INDEX IF NOT EXISTS idx_amendments_target_doc ON amendments(target_doc_id);
    """

    db = DatabaseClient(env="development")
    try:
        with db.cursor(commit=True) as cur:
            # Execute base schema
            cur.execute(base_sql)
            logger.info("Base tables created.")

            # Add embedding columns for each enabled model
            for model in enabled_models:
                col_name = model.get("column", f"emb_{model['name'].replace('/', '_')}")
                dim = model["dimension"]
                # Check if column already exists
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='chunks' AND column_name=%s
                """, (col_name,))
                if not cur.fetchone():
                    cur.execute(f"ALTER TABLE chunks ADD COLUMN {col_name} vector({dim})")
                    logger.info(f"Added column {col_name} (dim={dim}) to chunks table.")
                else:
                    logger.info(f"Column {col_name} already exists.")

            # Optional: add combined embedding column if strategy is mean and multiple models
            if emb_cfg.get("strategy") == "mean" and len(enabled_models) > 1:
                # Use the dimension of the first model (assuming all same)
                dim = enabled_models[0]["dimension"]
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='chunks' AND column_name='embedding_combined'
                """)
                if not cur.fetchone():
                    cur.execute(f"ALTER TABLE chunks ADD COLUMN embedding_combined vector({dim})")
                    logger.info("Added column embedding_combined for mean aggregation.")
                else:
                    logger.info("Column embedding_combined already exists.")
        logger.info("Schema creation completed.")
    finally:
        db.close()

if __name__ == "__main__":
    create_schema()