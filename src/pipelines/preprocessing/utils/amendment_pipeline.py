#!/usr/bin/env python3
"""
Amendment detection pipeline for legal documents.
Given a chunk_id, returns whether it contains an amendment and shows source/target info.
Usage: python amendment_pipeline.py --chunk-id "doc123__article__art1__cl4__pt0"
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# ----------------------------------------------------------------------
# Configuration – adjust paths to your index files
# ----------------------------------------------------------------------
INDEX_DIR = Path("data/index")   # folder containing document_index.json, chunk_index.json, hierarchy.json

# Load indexes once at module level
with open(INDEX_DIR / "document_index.json", "r", encoding="utf-8") as f:
    DOC_INDEX = json.load(f)

with open(INDEX_DIR / "chunk_index.json", "r", encoding="utf-8") as f:
    CHUNK_INDEX = json.load(f)

with open(INDEX_DIR / "hierarchy.json", "r", encoding="utf-8") as f:
    HIERARCHY = json.load(f)


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def parse_amendment_clause(chunk: Dict[str, Any], parent_doc_meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = chunk.get("chunk_content", "")
    if not text:
        return None

    # 1. Detect amendment keywords
    keywords = [r"Sửa đổi", r"Bổ sung", r"Bãi bỏ", r"Thay thế", r"Sửa đổi, bổ sung"]
    pattern = r"(" + "|".join(keywords) + r")"
    match = re.search(pattern, text)
    if not match:
        return None
    amendment_type = match.group(0).strip()

    # 2. Extract target location (article/clause/point)
    location_pattern = r"(?:khoản\s+(\d+|[IVXLCDM]+))?\s*(?:điểm\s+([a-z]+))?\s*Điều\s+(\d+|[IVXLCDM]+)"
    loc_match = re.search(location_pattern, text, re.IGNORECASE)
    if loc_match:
        clause_num = loc_match.group(1)
        point_letter = loc_match.group(2)
        article_num = loc_match.group(3)
    else:
        art_only = re.search(r"Điều\s+(\d+|[IVXLCDM]+)", text, re.IGNORECASE)
        article_num = art_only.group(1) if art_only else None
        clause_num = None
        point_letter = None

    # 3. Determine target document (law number or title)
    target_doc_number = None
    target_doc_title = None

    def extract_target_law_number(txt: str, self_number: str = None) -> Optional[str]:
        # Primary: look for "Luật Doanh nghiệp số X" (exact law name)
        m = re.search(r"Luật\s+Doanh\s+nghiệp\s+số\s*:?\s*(\d+/\d+/\w+)", txt, re.IGNORECASE)
        if m:
            return m.group(1)
        # Secondary: look for "của Luật ... số X" (any law name, but with "của")
        m = re.search(r"của\s+Luật\s+[^0-9]+?\s+số\s*:?\s*(\d+/\d+/\w+)", txt, re.IGNORECASE)
        if m:
            candidate = m.group(1)
            if self_number and candidate == self_number:
                return None
            return candidate
        # Tertiary: generic "Luật ... số X", avoid "Luật số:" and "Nghị quyết"
        m = re.search(r"(?<!Luật\s)(?<!Nghị\squyết\s)Luật\s+\S+\s+số\s*:?\s*(\d+/\d+/\w+)", txt, re.IGNORECASE)
        if m:
            candidate = m.group(1)
            if self_number and candidate == self_number:
                return None
            return candidate
        return None

    self_number = parent_doc_meta.get("number")
    if self_number:
        self_number = self_number.strip()

    target_doc_number = extract_target_law_number(text, self_number)
    if not target_doc_number:
        target_doc_number = extract_target_law_number(parent_doc_meta.get("nội dung", ""), self_number)
    if not target_doc_number:
        target_doc_number = extract_target_law_number(parent_doc_meta.get("title", ""), self_number)

    if not target_doc_number:
        title_match = re.search(r"của\s+Luật\s+([^0-9\n]+)", parent_doc_meta.get("title", ""), re.IGNORECASE)
        if title_match:
            target_doc_title = title_match.group(1).strip()
            target_doc_title = re.sub(r'\s+số$', '', target_doc_title)

    return {
        "is_amendment": True,
        "amendment_type": amendment_type,
        "target_article": article_num,
        "target_clause": clause_num,
        "target_point": point_letter,
        "target_doc_number": target_doc_number,
        "target_doc_title": target_doc_title,
        "description": text[:300],
    }


def find_target_doc_id(target_number: Optional[str], target_title: Optional[str]) -> Optional[str]:
    """Find doc_id of the target document by number or title."""
    if target_number:
        for doc_id, meta in DOC_INDEX.items():
            if meta.get("number") == target_number:
                return doc_id
    if target_title:
        target_title_clean = target_title.strip()
        for doc_id, meta in DOC_INDEX.items():
            title = meta.get("title", "")
            if target_title_clean.lower() in title.lower():
                return doc_id
    return None


def extract_point_content(clause_text: str, point_label: str) -> Optional[str]:
    """
    Extract the content of a specific point (e.g., 'a', 'b', 'c') from a clause.
    Handles various formats: 'a)', 'a.', 'a)', 'a. ' and points that span multiple lines.
    """
    point_label = point_label.strip().lower()
    patterns = [
        rf"{point_label}\)\s*(.*?)(?=\n\s*[b-z]\)|\n\s*[b-z]\.|\Z)",
        rf"{point_label}\)\s*(.*?)(?=;\s*\n|\.\s*\n|\n\s*[b-z]|$)",
        rf"{point_label}\.\s*(.*?)(?=\n\s*[b-z]\)|\n\s*[b-z]\.|\Z)",
        rf"{point_label}\.\s*(.*?)(?=;\s*\n|\.\s*\n|\n\s*[b-z]|$)",
        rf"{point_label}\s+(.*?)(?=\n\s*[b-z]\)|\n\s*[b-z]\.|\Z)",
    ]
    for pat in patterns:
        match = re.search(pat, clause_text, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            content = re.sub(r'[;\.]$', '', content)
            if content:
                return content
    return None


def find_target_chunk(target_doc_id: str, article: Optional[str], clause: Optional[str], point: Optional[str]) -> Optional[Dict[str, Any]]:
    """Find the target chunk. If point is specified but no dedicated chunk, extract from clause."""
    doc_hierarchy = HIERARCHY.get(target_doc_id, {})
    if not doc_hierarchy:
        return None

    art_key = article if article else "0"
    clause_key = clause if clause else "0"
    point_key = point if point else "0"

    # 1. Exact match
    chunk_ids = doc_hierarchy.get(art_key, {}).get(clause_key, {}).get(point_key, [])
    if chunk_ids:
        return CHUNK_INDEX.get(chunk_ids[0])

    # 2. If point is specified, try to extract from the clause chunk
    if point_key != "0" and clause_key != "0":
        clause_chunk_ids = doc_hierarchy.get(art_key, {}).get(clause_key, {}).get("0", [])
        if clause_chunk_ids:
            clause_chunk = CHUNK_INDEX.get(clause_chunk_ids[0])
            if clause_chunk:
                point_content = extract_point_content(clause_chunk["chunk_content"], point_key)
                if point_content:
                    virtual_chunk = clause_chunk.copy()
                    virtual_chunk["chunk_content"] = point_content
                    virtual_chunk["level"] = "point"
                    virtual_chunk["point"] = point_key
                    virtual_chunk["chunk_id"] = f"{target_doc_id}__virtual_point__art{art_key}__cl{clause_key}__pt{point_key}"
                    return virtual_chunk
                else:
                    # Fallback: return the whole clause chunk
                    virtual_chunk = clause_chunk.copy()
                    virtual_chunk["level"] = "clause_fallback"
                    virtual_chunk["note"] = f"Point {point_key} not found; showing whole clause instead."
                    return virtual_chunk

    # 3. Fallback to article-level or clause-level chunk
    if clause_key != "0":
        chunk_ids = doc_hierarchy.get(art_key, {}).get(clause_key, {}).get("0", [])
        if chunk_ids:
            return CHUNK_INDEX.get(chunk_ids[0])
    chunk_ids = doc_hierarchy.get(art_key, {}).get("0", {}).get("0", [])
    if chunk_ids:
        return CHUNK_INDEX.get(chunk_ids[0])
    return None


def get_amendment_info(chunk_id: str) -> Dict[str, Any]:
    """
    Main function: given a chunk_id, return comprehensive information about the amendment.
    """
    chunk = CHUNK_INDEX.get(chunk_id)
    if not chunk:
        return {"error": f"Chunk ID '{chunk_id}' not found in chunk_index."}

    if chunk.get("level") != "clause":
        return {"error": f"Chunk level is '{chunk.get('level')}', not 'clause'. Only clause chunks may contain amendments."}

    source_doc_id = chunk["doc_id"]
    source_doc_meta = DOC_INDEX.get(source_doc_id, {})

    parsed = parse_amendment_clause(chunk, source_doc_meta)
    if not parsed:
        return {"error": "No amendment keywords found in this chunk."}

    target_doc_id = find_target_doc_id(parsed["target_doc_number"], parsed["target_doc_title"])
    target_doc_meta = DOC_INDEX.get(target_doc_id, {}) if target_doc_id else {}

    target_chunk = None
    if target_doc_id:
        target_chunk = find_target_chunk(
            target_doc_id,
            parsed["target_article"],
            parsed["target_clause"],
            parsed["target_point"]
        )

    return {
        "is_amendment": True,
        "source_chunk": chunk,
        "source_document": source_doc_meta,
        "parsed_amendment": parsed,
        "target_document_id": target_doc_id,
        "target_document": target_doc_meta,
        "target_chunk": target_chunk,
    }


# ----------------------------------------------------------------------
# Command-line interface
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Detect if a chunk is an amendment and show target info.")
    parser.add_argument("--chunk-id", required=True, help="Chunk ID to examine.")
    args = parser.parse_args()

    result = get_amendment_info(args.chunk_id)
    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    # Pretty print results
    print("\n" + "=" * 80)
    print("SOURCE CHUNK (amending clause)")
    print("=" * 80)
    src = result["source_chunk"]
    print(f"Chunk ID     : {src['chunk_id']}")
    print(f"Document     : {result['source_document'].get('title', 'N/A')} ({result['source_document'].get('number', 'N/A')})")
    print(f"Content      : {src['chunk_content'][:300]}...")

    print("\n" + "=" * 80)
    print("PARSED AMENDMENT INFO")
    print("=" * 80)
    am = result["parsed_amendment"]
    print(f"Type         : {am['amendment_type']}")
    print(f"Affects      : Article {am['target_article']}, Clause {am['target_clause']}, Point {am['target_point']}")
    print(f"Target Law   : {am['target_doc_number'] or am['target_doc_title'] or 'Luật này (inferred from preamble)'}")
    print(f"Description  : {am['description']}")

    print("\n" + "=" * 80)
    print("TARGET DOCUMENT (being amended)")
    print("=" * 80)
    tgt_doc = result["target_document"]
    if tgt_doc:
        print(f"Doc ID       : {result['target_document_id']}")
        print(f"Title        : {tgt_doc.get('title')}")
        print(f"Number       : {tgt_doc.get('number')}")
        print(f"URL          : {tgt_doc.get('url')}")
    else:
        print("Target document not found in document index.")

    print("\n" + "=" * 80)
    print("TARGET CHUNK (the exact article/clause/point being amended)")
    print("=" * 80)
    tgt_chunk = result["target_chunk"]
    if tgt_chunk:
        print(f"Chunk ID     : {tgt_chunk.get('chunk_id')}")
        print(f"Level        : {tgt_chunk.get('level')}")
        if tgt_chunk.get("note"):
            print(f"Note         : {tgt_chunk['note']}")
        print(f"Content      : {tgt_chunk.get('chunk_content', '')[:300]}...")
    else:
        print("Target chunk not found – the location may not exist as a separate chunk or the parsing may be imprecise.")

    print("\n" + "=" * 80 + "\n")