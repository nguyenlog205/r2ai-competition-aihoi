#!/usr/bin/env python3
"""
Generate answers from previously retrieved chunks (saved from retrieval step).
Can use simple rules (top chunk, concatenation) or an LLM.
"""

import json
import argparse
from tqdm import tqdm
import re

from src.utils.log import get_logger

logger = get_logger("generate_answers")


def format_doc_meta(doc_title: str, doc_number: str) -> str:
    """Format document metadata for relevant_docs and relevant_articles."""
    doc_type = "Luật"
    if doc_title:
        if "Nghị định" in doc_title:
            doc_type = "Nghị định"
        elif "Thông tư" in doc_title:
            doc_type = "Thông tư"
        elif "Quyết định" in doc_title:
            doc_type = "Quyết định"
    short_title = re.sub(r'\s+số\s+\S+', '', doc_title).strip()
    return f"{doc_number}|{doc_type} {doc_number} {short_title}"


def extract_docs_and_articles(chunks):
    docs = set()
    articles = set()
    for ch in chunks:
        doc_number = ch.get("number") or ch.get("document_number") or ""
        doc_title = ch.get("document_title") or ""
        if doc_number:
            docs.add(format_doc_meta(doc_title, doc_number))
        article = ch.get("article_number")
        if doc_number and article:
            formatted = format_doc_meta(doc_title, doc_number)
            title_part = formatted.split("|")[1] if "|" in formatted else doc_title
            articles.add(f"{doc_number}|{title_part}|Điều {article}")
    return list(docs), list(articles)


def main():
    parser = argparse.ArgumentParser(description="Generate answers from retrieved chunks.")
    parser.add_argument("--input", default="retrieved_chunks.json", help="Input file from retrieval step.")
    parser.add_argument("--output", default="results.json", help="Output submission file.")
    parser.add_argument("--answer-strategy", choices=["top_chunk", "concat"], default="top_chunk",
                        help="How to produce answer (no LLM).")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for item in tqdm(data, desc="Generating answers"):
        qid = item["id"]
        question = item["question"]
        chunks = item["chunks"]

        docs, articles = extract_docs_and_articles(chunks)

        if not chunks:
            answer = "Không tìm thấy thông tin liên quan."
        else:
            if args.answer_strategy == "top_chunk":
                answer = chunks[0].get("content", "")
            else:  # concat
                answer = "\n\n".join(ch.get("content", "") for ch in chunks)

        results.append({
            "id": qid,
            "question": question,
            "answer": answer,
            "relevant_docs": docs,
            "relevant_articles": articles,
        })

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved results to {args.output}")


if __name__ == "__main__":
    main()