#!/usr/bin/env python3
"""
Retrieve relevant chunks for test questions and save to a JSON file.
No LLM involved – only retrieval.
"""

import json
import argparse
from tqdm import tqdm

from src.utils.log import get_logger
from src.pipelines.retrieval.utils.retriever import LegalRetriever

logger = get_logger("retrieve_candidates")


def main():
    parser = argparse.ArgumentParser(description="Retrieve candidates for test questions.")
    parser.add_argument("--test-questions", required=True, help="Path to test questions JSON file.")
    parser.add_argument("--output", default="retrieved_chunks.json", help="Output JSON file.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve per question.")
    parser.add_argument("--retrieve-k", type=int, default=10, help="Candidates before rerank.")
    parser.add_argument("--rerank", action="store_true", default=False, help="Use reranking.")
    args = parser.parse_args()

    with open(args.test_questions, "r", encoding="utf-8") as f:
        questions = json.load(f)
    logger.info(f"Loaded {len(questions)} test questions.")

    retriever = LegalRetriever(rerank=args.rerank)

    results = []
    for q in tqdm(questions, desc="Retrieving"):
        qid = q["id"]
        question = q["question"]
        if args.rerank:
            chunks = retriever.search_with_rerank(question, top_k=args.top_k, retrieve_k=args.retrieve_k)
        else:
            chunks = retriever.vector_search(question, top_k=args.top_k)

        # Store necessary info
        results.append({
            "id": qid,
            "question": question,
            "chunks": chunks,   # each chunk includes content, document_title, number, article_number, etc.
        })

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved retrieved chunks to {args.output}")

    retriever.close()


if __name__ == "__main__":
    main()