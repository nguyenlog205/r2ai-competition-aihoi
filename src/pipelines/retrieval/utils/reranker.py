#!/usr/bin/env python3
"""
Cross-encoder reranker for Vietnamese using BGE-based model.
"""

import numpy as np
from sentence_transformers import CrossEncoder
from typing import List, Dict, Any, Optional

from src.utils.config_loader import get_config
from src.utils.log import get_logger

logger = get_logger("reranker")


class Reranker:
    """
    Reranks a list of (query, document) pairs using a Vietnamese cross-encoder model.
    """

    def __init__(self, model_name: Optional[str] = None, max_length: Optional[int] = None):
        config = get_config()
        rerank_cfg = config.get("reranker", {})
        self.model_name = model_name or rerank_cfg.get("model", "AITeamVN/Vietnamese_Reranker")
        self.max_length = max_length or rerank_cfg.get("max_length", 2304)
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            # Use CrossEncoder from sentence_transformers (handles the model automatically)
            self.model = CrossEncoder(self.model_name, max_length=self.max_length)
            logger.info(f"Reranker initialized with {self.model_name} (max_length={self.max_length})")
        except Exception as e:
            logger.error(f"Failed to load reranker model {self.model_name}: {e}")
            logger.warning("Reranking disabled. Falling back to vector search only.")
            self.model = None

    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Rerank retrieved documents based on cross-encoder scores.
        """
        if not documents or self.model is None:
            return documents[:top_k]

        # Prepare (query, document text) pairs
        pairs = [(query, doc["content"]) for doc in documents]
        scores = self.model.predict(pairs)

        # Sort documents by score descending
        sorted_idx = np.argsort(scores)[::-1][:top_k]
        reranked = [documents[i] for i in sorted_idx]

        # Add rerank score to each document
        for i, doc in enumerate(reranked):
            doc["rerank_score"] = float(scores[sorted_idx[i]])

        return reranked