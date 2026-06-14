#!/usr/bin/env python3
"""
Retriever class for legal document chunks using vector similarity, full‑text search,
and optional cross-encoder reranking.
"""

import os
from typing import List, Dict, Any, Optional

from sentence_transformers import SentenceTransformer

from src.utils.config_loader import get_config
from src.utils.log import get_logger
from src.database.utils.database_client import DatabaseClient
from .reranker import Reranker   # ensure this import works

logger = get_logger("retriever")


class LegalRetriever:
    """
    Retrieves relevant chunks from the legal database using:
      - Dense vector similarity (cosine) with pgvector
      - (Optional) Full‑text search with PostgreSQL tsvector
      - Hybrid ranking (Reciprocal Rank Fusion)
      - Cross-encoder reranking (optional)
    """

    def __init__(self, env: str = "development", embedding_model_name: Optional[str] = None,
                 rerank: bool = False):
        config = get_config()
        db_env = config.get("database", {}).get("env", env)
        self.db = DatabaseClient(env=db_env)

        # Determine embedding model
        emb_cfg = config.get("embedding", {})
        if embedding_model_name is None:
            # Use the first enabled model
            for m in emb_cfg.get("models", []):
                if m.get("enabled"):
                    embedding_model_name = m["name"]
                    break
        if not embedding_model_name:
            raise ValueError("No enabled embedding model found in configuration.")
        self.model = SentenceTransformer(embedding_model_name)
        self.vector_column = emb_cfg.get("vector_column", "emb_keepitreal")

        # Initialize reranker if requested
        if rerank:
            self.reranker = Reranker()
        else:
            self.reranker = None

        logger.info(f"Retriever initialized with model {embedding_model_name}, column {self.vector_column}, rerank={rerank}")

    def vector_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search by vector similarity."""
        query_vec = self.model.encode(query).tolist()
        with self.db.cursor(dict_cursor=True) as cur:
            cur.execute(f"""
                SELECT
                    c.chunk_id,
                    c.doc_id,
                    c.content,
                    c.article_number,
                    c.clause_number,
                    c.point,
                    d.title AS document_title,
                    d.url AS document_url,
                    1 - (c.{self.vector_column} <=> %s::vector) AS similarity
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE c.{self.vector_column} IS NOT NULL
                ORDER BY c.{self.vector_column} <=> %s::vector
                LIMIT %s
            """, (query_vec, query_vec, top_k))
            return cur.fetchall()

    def full_text_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search by full‑text (requires full_text column populated)."""
        tsquery = " & ".join(query.strip().split())
        with self.db.cursor(dict_cursor=True) as cur:
            cur.execute("""
                SELECT
                    c.chunk_id,
                    c.doc_id,
                    c.content,
                    c.article_number,
                    c.clause_number,
                    c.point,
                    d.title AS document_title,
                    d.url AS document_url,
                    ts_rank_cd(c.full_text, to_tsquery('vietnamese', %s)) AS rank
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE c.full_text @@ to_tsquery('vietnamese', %s)
                ORDER BY rank DESC
                LIMIT %s
            """, (tsquery, tsquery, top_k))
            return cur.fetchall()

    def hybrid_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Combine vector and full‑text results using Reciprocal Rank Fusion (RRF).
        """
        vec_results = self.vector_search(query, top_k=top_k)
        ft_results = self.full_text_search(query, top_k=top_k) if self._full_text_available() else []

        scores = {}
        k = 60
        for rank, res in enumerate(vec_results):
            chunk_id = res["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank + 1)
        for rank, res in enumerate(ft_results):
            chunk_id = res["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank + 1)

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:top_k]
        results = []
        for chunk_id in sorted_ids:
            for r in vec_results + ft_results:
                if r["chunk_id"] == chunk_id:
                    results.append(r)
                    break
        return results

    def search_with_rerank(self, query: str, top_k: int = 5, retrieve_k: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve a larger set of candidates via vector search, then rerank with cross-encoder.
        """
        if not self.reranker:
            logger.warning("Reranker not enabled. Falling back to vector search.")
            return self.vector_search(query, top_k=top_k)

        candidates = self.vector_search(query, top_k=retrieve_k)
        if not candidates:
            return []
        reranked = self.reranker.rerank(query, candidates, top_k=top_k)
        return reranked

    def _full_text_available(self) -> bool:
        with self.db.cursor() as cur:
            cur.execute("SELECT 1 FROM chunks WHERE full_text IS NOT NULL LIMIT 1")
            return cur.fetchone() is not None

    def close(self):
        self.db.close()