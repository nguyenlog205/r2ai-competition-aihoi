#!/usr/bin/env python3
"""
Legal document retrieval with optional reranking.
By default: vector search → retrieve 100 candidates → rerank to top 5.
"""

import argparse
import json
from src.pipelines.retrieval.utils.retriever import LegalRetriever

def main():
    parser = argparse.ArgumentParser(
        description="Retrieve legal document chunks. "
                    "Default: vector search with 100 candidates → rerank to top 5."
    )
    parser.add_argument("--query", required=True, help="User query (Vietnamese).")
    parser.add_argument("--retrieve-k", type=int, default=100,
                        help="Number of candidates to retrieve before reranking (default: 100).")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Number of final results after reranking (default: 5).")
    parser.add_argument("--rerank", action="store_true", default=True,
                        help="Enable cross-encoder reranking (default: True).")
    parser.add_argument("--no-rerank", dest="rerank", action="store_false",
                        help="Disable reranking, return raw vector search results.")
    parser.add_argument("--output-format", choices=["json", "pretty"], default="pretty",
                        help="Output format.")
    args = parser.parse_args()

    retriever = LegalRetriever(rerank=args.rerank)

    try:
        if args.rerank:
            results = retriever.search_with_rerank(
                args.query,
                top_k=args.top_k,
                retrieve_k=args.retrieve_k
            )
        else:
            # Direct vector search, no reranking
            results = retriever.vector_search(args.query, top_k=args.top_k)

        if args.output_format == "json":
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print("\n" + "="*80)
            print(f"Query: {args.query}")
            print(f"Retrieved {len(results)} results (top-{args.top_k})")
            if args.rerank:
                print(f"Candidate pool: {args.retrieve_k} → reranked")
            print("="*80)
            for i, res in enumerate(results, 1):
                score = res.get("rerank_score", res.get("similarity", 0))
                print(f"\n[{i}] Score: {score:.4f}")
                print(f"Document: {res.get('document_title', 'N/A')}")
                print(f"Location: Article {res.get('article_number')}, "
                      f"Clause {res.get('clause_number')}, Point {res.get('point')}")
                print(f"Content: {res.get('content', '')[:400]}...")
                print("-" * 80)
    finally:
        retriever.close()

if __name__ == "__main__":
    main()