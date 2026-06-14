#!/usr/bin/env python3
"""
Load the generated JSON indexes into PostgreSQL tables.
Applies text preprocessing to chunk content.
"""

import json
from pathlib import Path
from tqdm import tqdm

from src.utils.config_loader import get_config
from src.utils.log import get_logger
from src.utils.text_processor import preprocess_text
from src.database.utils.database_client import DatabaseClient

logger = get_logger("load_to_postgres")

def load_documents(db: DatabaseClient, doc_index_path: Path):
    """Upsert documents from document_index.json."""
    with open(doc_index_path, "r", encoding="utf-8") as f:
        doc_index = json.load(f)

    logger.info(f"Loading {len(doc_index)} documents...")
    with db.cursor(commit=True) as cur:
        for doc_id, meta in tqdm(doc_index.items(), desc="Documents"):
            # Preprocess any text fields? For now, raw_metadata remains as is.
            # Title may need cleaning, but keep original.
            cur.execute("""
                INSERT INTO documents (doc_id, title, number, url, issued_date, effective_date, status, raw_metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    number = EXCLUDED.number,
                    url = EXCLUDED.url,
                    issued_date = EXCLUDED.issued_date,
                    effective_date = EXCLUDED.effective_date,
                    status = EXCLUDED.status,
                    raw_metadata = EXCLUDED.raw_metadata,
                    updated_at = NOW()
            """, (
                doc_id,
                meta.get("title"),
                meta.get("number"),
                meta.get("url"),
                meta.get("issued_date"),
                meta.get("effective_date"),
                meta.get("status"),
                json.dumps(meta)
            ))
    logger.info("Documents loaded.")

def load_chunks(db: DatabaseClient, chunk_index_path: Path):
    """Upsert chunks from chunk_index.json, applying text preprocessing to content."""
    with open(chunk_index_path, "r", encoding="utf-8") as f:
        chunk_index = json.load(f)

    logger.info(f"Loading {len(chunk_index)} chunks...")
    with db.cursor(commit=True) as cur:
        for chunk_id, chunk in tqdm(chunk_index.items(), desc="Chunks"):
            content_raw = chunk.get("chunk_content", "")
            content_processed = preprocess_text(content_raw)
            cur.execute("""
                INSERT INTO chunks (chunk_id, doc_id, level, article_number, clause_number, point, content, start_char, end_char)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    doc_id = EXCLUDED.doc_id,
                    level = EXCLUDED.level,
                    article_number = EXCLUDED.article_number,
                    clause_number = EXCLUDED.clause_number,
                    point = EXCLUDED.point,
                    content = EXCLUDED.content,
                    start_char = EXCLUDED.start_char,
                    end_char = EXCLUDED.end_char
            """, (
                chunk_id,
                chunk.get("doc_id"),
                chunk.get("level"),
                chunk.get("article_number"),
                chunk.get("clause_number"),
                chunk.get("point"),
                content_processed,
                chunk.get("start_char"),
                chunk.get("end_char")
            ))
    logger.info("Chunks loaded.")

def load_hierarchy(db: DatabaseClient, hierarchy_path: Path):
    """Load hierarchy relationships from hierarchy.json into chunk_hierarchy table."""
    with open(hierarchy_path, "r", encoding="utf-8") as f:
        hierarchy = json.load(f)

    records = []
    for doc_id, articles in hierarchy.items():
        for article, clauses in articles.items():
            for clause, points in clauses.items():
                for point, chunk_ids in points.items():
                    for chunk_id in chunk_ids:
                        records.append((chunk_id, doc_id, None))  # parent_chunk_id not stored here

    logger.info(f"Loading {len(records)} hierarchy entries...")
    with db.cursor(commit=True) as cur:
        for chunk_id, doc_id, parent_id in tqdm(records, desc="Hierarchy"):
            cur.execute("""
                INSERT INTO chunk_hierarchy (chunk_id, doc_id, parent_chunk_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    doc_id = EXCLUDED.doc_id,
                    parent_chunk_id = EXCLUDED.parent_chunk_id
            """, (chunk_id, doc_id, parent_id))
    logger.info("Hierarchy loaded.")

def load_amendments(db: DatabaseClient, amendments_path: Path):
    """Load amendment relations from amendment_relations.json."""
    with open(amendments_path, "r", encoding="utf-8") as f:
        relations = json.load(f)

    # Preprocess description field (optional)
    for rel in relations:
        if "description" in rel:
            rel["description"] = preprocess_text(rel["description"])

    logger.info(f"Loading {len(relations)} amendment relations...")
    with db.cursor(commit=True) as cur:
        for rel in tqdm(relations, desc="Amendments"):
            cur.execute("""
                INSERT INTO amendments (
                    source_chunk_id, source_doc_id, target_chunk_id, target_doc_id,
                    amendment_type, target_article, target_clause, target_point, description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                rel.get("source_chunk_id"),
                rel.get("source_doc_id"),
                rel.get("target_chunk_id"),
                rel.get("target_doc_id"),
                rel.get("amendment_type"),
                rel.get("target_article"),
                rel.get("target_clause"),
                rel.get("target_point"),
                rel.get("description")
            ))
    logger.info("Amendments loaded.")

def main():
    config = get_config()
    load_cfg = config.get("database_loading", {})
    db_env = config.get("database", {}).get("env", "development")

    doc_index_path = Path(load_cfg.get("document_index", "data/index/document_index.json"))
    chunk_index_path = Path(load_cfg.get("chunk_index", "data/index/chunk_index.json"))
    hierarchy_path = Path(load_cfg.get("hierarchy", "data/index/hierarchy.json"))
    amendments_path = Path(load_cfg.get("amendment_relations", "data/index/amendment_relations.json"))

    db = DatabaseClient(env=db_env)
    try:
        load_documents(db, doc_index_path)
        load_chunks(db, chunk_index_path)
        load_hierarchy(db, hierarchy_path)
        load_amendments(db, amendments_path)
    finally:
        db.close()
        logger.info("Database loading completed.")

if __name__ == "__main__":
    main()