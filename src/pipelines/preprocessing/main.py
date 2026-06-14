#!/usr/bin/env python3
"""
Main preprocessing pipeline:
- Chunk legal documents (from filtered crawler output)
- Build three indexes (document, chunk, hierarchy)
- Detect amendment relationships and build a version graph
"""

import json
from pathlib import Path
from tqdm import tqdm

from src.utils.config_loader import get_config
from src.utils.log import get_logger

# Import chunking and indexing functions
from src.pipelines.preprocessing.utils.chunking_pipeline import (
    chunk_legal_document,
    build_indexes,
    save_indexes,
    clean_stale_documents,
)

# Import amendment detection functions
from src.pipelines.preprocessing.utils.amendment_pipeline import (
    parse_amendment_clause,
    find_target_doc_id,
    find_target_chunk,
)

logger = get_logger("preprocessing_main")


def run_preprocessing():
    """Orchestrate chunking, indexing, and amendment detection."""
    config = get_config()
    pre_cfg = config.get("preprocessing", {})

    # --- Configuration ---
    input_file = Path(pre_cfg.get("input_file", "data/legal_document/metadata_law_ALL_FILTERED.json"))
    output_dir = Path(pre_cfg.get("output_dir", "data/legal_document"))
    index_dir = Path(pre_cfg.get("index_dir", "data/index"))
    max_chunk_size = pre_cfg.get("max_chunk_size", 2000)
    clean_stale = pre_cfg.get("clean_stale", False)
    relations_file = Path(pre_cfg.get("amendment_relations_file", "data/amendment_relations.json"))

    # 1. Load filtered documents
    logger.info(f"Loading documents from {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        documents = json.load(f)
    logger.info(f"Loaded {len(documents)} documents")

    # 2. Chunk all documents
    all_chunks = []
    for doc in tqdm(documents, desc="Chunking documents"):
        chunks = chunk_legal_document(doc, max_chunk_size=max_chunk_size)
        all_chunks.extend(chunks)
    logger.info(f"Total chunks created: {len(all_chunks)}")

    # 3. Save raw chunks (optional)
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = output_dir / "all_chunks.json"
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved raw chunks to {chunks_path}")

    # 4. Build indexes
    logger.info("Building document, chunk, and hierarchy indexes")
    doc_index, chunk_index, hierarchy = build_indexes(all_chunks)
    save_indexes(doc_index, chunk_index, hierarchy, index_dir)

    if clean_stale:
        current_ids = set(doc_index.keys())
        clean_stale_documents(current_ids, index_dir)

    # 5. Detect amendment relationships
    logger.info("Detecting amendment relationships")
    relations = []

    for chunk_id, chunk in tqdm(chunk_index.items(), desc="Detecting amendments"):
        if chunk.get("level") != "clause":
            continue

        source_doc_id = chunk["doc_id"]
        source_doc_meta = doc_index.get(source_doc_id, {})
        parsed = parse_amendment_clause(chunk, source_doc_meta)
        if not parsed:
            continue

        target_doc_id = find_target_doc_id(parsed["target_doc_number"], parsed["target_doc_title"])
        target_chunk = None
        if target_doc_id:
            target_chunk = find_target_chunk(
                target_doc_id,
                parsed["target_article"],
                parsed["target_clause"],
                parsed["target_point"],
                hierarchy,
                chunk_index,
            )

        relations.append({
            "source_chunk_id": chunk_id,
            "source_doc_id": source_doc_id,
            "amendment_type": parsed["amendment_type"],
            "target_doc_id": target_doc_id,
            "target_article": parsed["target_article"],
            "target_clause": parsed["target_clause"],
            "target_point": parsed["target_point"],
            "target_chunk_id": target_chunk.get("chunk_id") if target_chunk else None,
            "description": parsed["description"],
        })

    logger.info(f"Found {len(relations)} amendment relations")

    # 6. Save relations
    with open(relations_file, "w", encoding="utf-8") as f:
        json.dump(relations, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved amendment relations to {relations_file}")

    logger.info("Preprocessing pipeline finished successfully.")


if __name__ == "__main__":
    run_preprocessing()