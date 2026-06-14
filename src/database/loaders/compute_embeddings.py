#!/usr/bin/env python3
"""
Compute embeddings for all chunks using the configured models.
Requires sentence-transformers and pgvector.
"""

import numpy as np
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

from src.utils.config_loader import get_config
from src.utils.log import get_logger
from src.database.utils.database_client import DatabaseClient

logger = get_logger("compute_embeddings")


def compute_and_update_embeddings(db: DatabaseClient, model_name: str, column_name: str, batch_size: int = 64):
    """
    Compute embeddings for all chunks that currently have NULL in the given column.
    Updates the column in batches.
    """
    logger.info(f"Processing model: {model_name} -> column {column_name}")
    model = SentenceTransformer(model_name)

    # Fetch all chunk IDs and contents that need embedding
    with db.cursor() as cur:
        cur.execute(f"SELECT chunk_id, content FROM chunks WHERE {column_name} IS NULL")
        rows = cur.fetchall()
    if not rows:
        logger.info(f"No chunks need embedding for {column_name}")
        return

    total = len(rows)
    logger.info(f"Need to embed {total} chunks for {column_name}")

    # Process in batches
    for i in tqdm(range(0, total, batch_size), desc=f"{model_name}"):
        batch_rows = rows[i:i+batch_size]
        batch_ids = [r[0] for r in batch_rows]
        batch_texts = [r[1] for r in batch_rows]
        # Generate embeddings
        embeddings = model.encode(batch_texts, show_progress_bar=False).tolist()
        # Update database
        with db.cursor(commit=True) as cur:
            for chunk_id, emb in zip(batch_ids, embeddings):
                cur.execute(f"UPDATE chunks SET {column_name} = %s WHERE chunk_id = %s", (emb, chunk_id))
    logger.info(f"Completed embeddings for {model_name}")


def compute_combined_embedding(db: DatabaseClient, models_config, strategy: str):
    """Compute combined embedding (e.g., mean) from enabled models."""
    if strategy != "mean":
        logger.info(f"Strategy '{strategy}' not implemented for combined embedding")
        return

    enabled_models = [m for m in models_config if m.get("enabled")]
    if len(enabled_models) < 2:
        logger.info("Less than two models enabled; no mean combination needed.")
        return

    # Get column names for each enabled model
    columns = [m.get("column", f"emb_{m['name'].replace('/', '_').replace('-', '_')}") for m in enabled_models]

    # Fetch chunks where any of the columns is NULL (incomplete) or combined is NULL
    with db.cursor() as cur:
        # First, ensure all base columns are populated
        null_condition = " OR ".join([f"{col} IS NULL" for col in columns])
        cur.execute(f"SELECT chunk_id FROM chunks WHERE {null_condition} OR embedding_combined IS NULL")
        rows = cur.fetchall()
    if not rows:
        logger.info("All chunks already have combined embedding.")
        return

    # We will compute combined only for those rows where all base embeddings are present
    # For simplicity, we process all rows that are missing combined embedding, and compute mean if all base present.
    # To avoid many individual queries, we'll fetch all base embeddings for those rows and then update.
    chunk_ids = [r[0] for r in rows]
    # Placeholders for SQL IN clause
    placeholders = ','.join(['%s'] * len(chunk_ids))
    with db.cursor() as cur:
        # Fetch all base embeddings in one query
        select_cols = ", ".join(columns)
        cur.execute(f"SELECT chunk_id, {select_cols} FROM chunks WHERE chunk_id IN ({placeholders})", chunk_ids)
        data = cur.fetchall()

    updates = []
    for row in data:
        chunk_id = row[0]
        vecs = [np.array(row[i+1]) for i in range(len(columns)) if row[i+1] is not None]
        if len(vecs) == len(columns):
            mean_vec = np.mean(vecs, axis=0).tolist()
            updates.append((mean_vec, chunk_id))
        else:
            logger.warning(f"Chunk {chunk_id} missing some base embeddings, skipping combined")

    # Update combined column
    if updates:
        with db.cursor(commit=True) as cur:
            for mean_vec, chunk_id in tqdm(updates, desc="Updating combined embedding"):
                cur.execute("UPDATE chunks SET embedding_combined = %s WHERE chunk_id = %s", (mean_vec, chunk_id))
        logger.info(f"Updated combined embedding for {len(updates)} chunks")
    else:
        logger.info("No combined embedding updates needed.")


def main():
    config = get_config()
    emb_cfg = config.get("embedding", {})
    models = emb_cfg.get("models", [])
    batch_size = emb_cfg.get("batch_size", 64)
    strategy = emb_cfg.get("strategy", "mean")
    db_env = config.get("database", {}).get("env", "development")

    db = DatabaseClient(env=db_env)

    # Compute embeddings for each enabled model
    for model in models:
        if not model.get("enabled"):
            continue
        model_name = model["name"]
        col_name = model.get("column", f"emb_{model_name.replace('/', '_').replace('-', '_')}")
        compute_and_update_embeddings(db, model_name, col_name, batch_size)

    # Compute combined embedding (if multiple models and strategy mean)
    if strategy == "mean" and len([m for m in models if m.get("enabled")]) > 1:
        compute_combined_embedding(db, models, strategy)

    db.close()
    logger.info("Embedding computation finished.")


if __name__ == "__main__":
    main()