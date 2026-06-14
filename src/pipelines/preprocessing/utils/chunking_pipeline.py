#!/usr/bin/env python3
"""
Pipeline for chunking legal documents and building hierarchical indexes.
Configuration: uses src.utils.config_loader (YAML + .env)
"""

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any, Optional

from tqdm import tqdm

from src.utils.config_loader import get_config
from src.utils.log import get_logger

logger = get_logger("chunking_pipeline")


# ----------------------------------------------------------------------
# Chunking functions (from notebook)
# ----------------------------------------------------------------------
def _split_by_sentences(doc, text, article_number, clause_number, article_title, max_chunk_size):
    sentences = re.split(r'(?<=\.)\s+(?=[A-ZÀ-ÁÂÃÈ-ÉÊÌ-ÍÒ-ÓÔÕÙ-ÚÝĐ])', text)
    chunks = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 2 <= max_chunk_size:
            current += sent + " "
        else:
            if current:
                chunk = doc.copy()
                chunk["chunk_content"] = current.strip()
                chunk["level"] = "sentence"
                chunk["article_number"] = article_number
                chunk["article_title"] = article_title
                chunk["clause_number"] = clause_number
                chunk["point"] = None
                chunks.append(chunk)
            current = sent + " "
    if current:
        chunk = doc.copy()
        chunk["chunk_content"] = current.strip()
        chunk["level"] = "sentence"
        chunk["article_number"] = article_number
        chunk["article_title"] = article_title
        chunk["clause_number"] = clause_number
        chunk["point"] = None
        chunks.append(chunk)
    return chunks


def _chunk_by_paragraphs(doc, text, max_chunk_size):
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks = []
    for para in paragraphs:
        if len(para) <= max_chunk_size:
            chunk = doc.copy()
            chunk["chunk_content"] = para
            chunk["level"] = "paragraph"
            chunks.append(chunk)
        else:
            sentences = re.split(r'(?<=\.)\s+(?=[A-ZÀ-ÁÂÃÈ-ÉÊÌ-ÍÒ-ÓÔÕÙ-ÚÝĐ])', para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) + 2 <= max_chunk_size:
                    current += sent + " "
                else:
                    if current:
                        chunk = doc.copy()
                        chunk["chunk_content"] = current.strip()
                        chunk["level"] = "sentence"
                        chunks.append(chunk)
                    current = sent + " "
            if current:
                chunk = doc.copy()
                chunk["chunk_content"] = current.strip()
                chunk["level"] = "sentence"
                chunks.append(chunk)
    return chunks


def chunk_legal_document(doc: Dict[str, Any], max_chunk_size: int = 2000) -> List[Dict[str, Any]]:
    text = doc.get("nội dung", "")
    if not text:
        return []

    article_pattern = re.compile(r'^Điều\s+(\d+|[IVXLCDM]+)\s*[\.\:]?\s*(.*)$', re.MULTILINE | re.IGNORECASE)
    article_matches = list(article_pattern.finditer(text))
    if not article_matches:
        return _chunk_by_paragraphs(doc, text, max_chunk_size)

    chunks = []
    for i, match in enumerate(article_matches):
        start = match.start()
        end = article_matches[i+1].start() if i+1 < len(article_matches) else len(text)
        article_text = text[start:end].strip()
        article_number = match.group(1)
        article_title = match.group(2).strip() or None

        if len(article_text) < 50:
            continue

        clause_pattern = re.compile(r'^(\d+|[IVXLCDM]+)\s*[\.\:]\s*(.*)$', re.MULTILINE)
        clause_matches = list(clause_pattern.finditer(article_text))

        if not clause_matches:
            chunk = doc.copy()
            chunk["chunk_content"] = article_text
            chunk["level"] = "article"
            chunk["article_number"] = article_number
            chunk["article_title"] = article_title
            chunk["clause_number"] = None
            chunk["point"] = None
            chunks.append(chunk)
        else:
            for j, cl_match in enumerate(clause_matches):
                cl_start = cl_match.start()
                cl_end = clause_matches[j+1].start() if j+1 < len(clause_matches) else len(article_text)
                clause_text = article_text[cl_start:cl_end].strip()
                clause_number = cl_match.group(1)
                clause_title = cl_match.group(2).strip() or None

                if len(clause_text) <= max_chunk_size:
                    chunk = doc.copy()
                    chunk["chunk_content"] = clause_text
                    chunk["level"] = "clause"
                    chunk["article_number"] = article_number
                    chunk["article_title"] = article_title
                    chunk["clause_number"] = clause_number
                    chunk["clause_title"] = clause_title
                    chunk["point"] = None
                    chunks.append(chunk)
                else:
                    sub_chunks = _split_by_sentences(
                        doc, clause_text, article_number, clause_number,
                        article_title, max_chunk_size
                    )
                    chunks.extend(sub_chunks)
    return chunks


# ----------------------------------------------------------------------
# Indexing functions (from indexing notebook)
# ----------------------------------------------------------------------
def get_doc_id(doc_metadata: Dict[str, Any]) -> str:
    url = doc_metadata.get("url", "")
    if url:
        unique = url
    else:
        unique = f"{doc_metadata.get('Tên văn bản', '')}_{doc_metadata.get('Số hiệu', '')}"
    return hashlib.md5(unique.encode("utf-8")).hexdigest()[:16]


def get_chunk_id(doc_id: str, chunk: Dict[str, Any]) -> str:
    level = chunk.get("level", "unknown")
    article = chunk.get("article_number", "") or "0"
    clause = chunk.get("clause_number", "") or "0"
    point = chunk.get("point", "") or "0"
    return f"{doc_id}__{level}__art{article}__cl{clause}__pt{point}"


def build_indexes(chunks: List[Dict[str, Any]]) -> tuple:
    doc_index = {}
    chunk_index = {}
    # Four levels: doc_id -> article -> clause -> point -> list of chunk_ids
    hierarchy = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))

    for chunk in chunks:
        # Extract document metadata (non‑chunk fields)
        doc_metadata = {k: v for k, v in chunk.items()
                        if k not in ["chunk_content", "level", "article_number",
                                     "article_title", "clause_number", "clause_title",
                                     "point", "start_char", "end_char", "subpart"]}
        doc_id = get_doc_id(doc_metadata)

        # Document index (upsert)
        doc_index[doc_id] = {
            "doc_id": doc_id,
            "url": doc_metadata.get("url"),
            "title": doc_metadata.get("Tên văn bản"),
            "number": doc_metadata.get("Số hiệu"),
            "last_updated": datetime.now().isoformat(),
            **doc_metadata
        }

        # Chunk index
        chunk_entry = chunk.copy()
        chunk_entry["doc_id"] = doc_id
        chunk_id = get_chunk_id(doc_id, chunk)
        chunk_entry["chunk_id"] = chunk_id
        chunk_index[chunk_id] = chunk_entry

        # Hierarchy: convert None to "0" for consistent keys
        art = str(chunk.get("article_number") or "0")
        clause = str(chunk.get("clause_number") or "0")
        point = str(chunk.get("point") or "0")

        # Append chunk_id to the appropriate point list (will create all intermediate dicts automatically)
        hierarchy[doc_id][art][clause][point].append(chunk_id)

    return doc_index, chunk_index, hierarchy


def save_indexes(doc_index, chunk_index, hierarchy, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "document_index.json", "w", encoding="utf-8") as f:
        json.dump(doc_index, f, ensure_ascii=False, indent=2)
    with open(output_dir / "chunk_index.json", "w", encoding="utf-8") as f:
        json.dump(chunk_index, f, ensure_ascii=False, indent=2)

    hierarchy_plain = {
        doc_id: {art: {cl: {pt: chunk_ids for pt, chunk_ids in cl_dict.items()}
                      for cl, cl_dict in art_dict.items()}
                for art, art_dict in doc_dict.items()}
        for doc_id, doc_dict in hierarchy.items()
    }
    with open(output_dir / "hierarchy.json", "w", encoding="utf-8") as f:
        json.dump(hierarchy_plain, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved document index: {len(doc_index)} documents")
    logger.info(f"Saved chunk index: {len(chunk_index)} chunks")
    logger.info("Saved hierarchy tree")


def clean_stale_documents(current_doc_ids, output_dir: Path):
    doc_path = output_dir / "document_index.json"
    chunk_path = output_dir / "chunk_index.json"
    if not doc_path.exists() or not chunk_path.exists():
        return
    with open(doc_path, "r", encoding="utf-8") as f:
        old_doc_index = json.load(f)
    with open(chunk_path, "r", encoding="utf-8") as f:
        old_chunk_index = json.load(f)

    new_doc_index = {k: v for k, v in old_doc_index.items() if k in current_doc_ids}
    new_chunk_index = {k: v for k, v in old_chunk_index.items() if v.get("doc_id") in current_doc_ids}

    with open(doc_path, "w", encoding="utf-8") as f:
        json.dump(new_doc_index, f, ensure_ascii=False, indent=2)
    with open(chunk_path, "w", encoding="utf-8") as f:
        json.dump(new_chunk_index, f, ensure_ascii=False, indent=2)

    removed = len(old_doc_index) - len(new_doc_index)
    logger.info(f"Removed {removed} stale documents")


# ----------------------------------------------------------------------
# Main pipeline
# ----------------------------------------------------------------------
def run_chunking_pipeline():
    """Load config, chunk documents, build indexes, and save all outputs."""
    config = get_config()
    chunk_cfg = config.get("chunking", {})

    input_file = Path(chunk_cfg.get("input_file", "../../data/legal_document/metadata_law_ALL_FILTERED.json"))
    output_dir = Path(chunk_cfg.get("output_dir", "../../data/legal_document"))
    max_chunk_size = chunk_cfg.get("max_chunk_size", 2000)
    index_dir = Path(chunk_cfg.get("index_dir", "../../data/index"))
    clean_stale = chunk_cfg.get("clean_stale", False)

    logger.info(f"Loading documents from {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        documents = json.load(f)
    logger.info(f"Loaded {len(documents)} documents")

    # Chunk all documents
    all_chunks = []
    for doc in tqdm(documents, desc="Chunking documents"):
        chunks = chunk_legal_document(doc, max_chunk_size=max_chunk_size)
        all_chunks.extend(chunks)
    logger.info(f"Total chunks created: {len(all_chunks)}")

    # Save raw chunks
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = output_dir / "all_chunks.json"
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(all_chunks)} chunks to {chunks_path}")

    # Build indexes
    logger.info("Building document, chunk, and hierarchy indexes")
    doc_index, chunk_index, hierarchy = build_indexes(all_chunks)

    # Save indexes
    save_indexes(doc_index, chunk_index, hierarchy, index_dir)

    # Optionally clean stale documents
    if clean_stale:
        current_ids = set(doc_index.keys())
        clean_stale_documents(current_ids, index_dir)

    logger.info("Chunking pipeline finished successfully")


if __name__ == "__main__":
    run_chunking_pipeline()