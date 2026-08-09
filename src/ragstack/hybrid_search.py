"""Hybrid search: combine semantic search with BM25 keyword ranking.

Provides better recall by catching both semantic and lexical matches.
Uses rank_bm25 for fast, effective keyword scoring.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from rank_bm25 import BM25Okapi

if TYPE_CHECKING:
    from .qdrant_store import QdrantVectorStore, SearchHit

logger = logging.getLogger(__name__)


class HybridSearcher:
    """Combines semantic + keyword search for better recall."""

    def __init__(self, store: QdrantVectorStore):
        """Initialize hybrid searcher with a Qdrant store.

        Args:
            store: QdrantVectorStore instance to search within
        """
        self.store = store
        self.bm25 = None
        self.documents = None
        self._build_bm25_index()

    def _build_bm25_index(self) -> None:
        """Build BM25 index from all documents in the store.

        Called once on init and after new documents are added.
        """
        scroll, _ = self.store.client.scroll(
            collection_name=self.store.collection_name,
            limit=100000,
            with_payload=True,
        )

        self.documents = []
        for point in scroll:
            text = point.payload["text"]
            self.documents.append({
                "point_id": point.id,
                "text": text,
                "tokens": text.lower().split(),
            })

        if self.documents:
            corpus = [doc["tokens"] for doc in self.documents]
            self.bm25 = BM25Okapi(corpus)
            logger.info(f"Built BM25 index for {len(self.documents)} documents")

    def search(
        self,
        query: str,
        query_vector: np.ndarray,
        *,
        top_k: int = 5,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        filters: dict | None = None,
    ) -> list[SearchHit]:
        """Hybrid search: semantic + keyword scoring.

        Args:
            query: Query text
            query_vector: L2-normalized semantic embedding
            top_k: Number of results to return
            semantic_weight: Weight for semantic similarity (0-1)
            keyword_weight: Weight for keyword matching (0-1)
            filters: Metadata filters (e.g., {"source": "sales.md"})

        Returns:
            Ranked SearchHit results
        """
        if not self.bm25 or not self.documents:
            logger.warning("BM25 index not available, falling back to semantic search")
            return self.store.search(
                query_vector,
                top_k=top_k,
                filters=filters,
            )

        query_tokens = query.lower().split()
        bm25_scores = self.bm25.get_scores(query_tokens)

        keyword_scores = {
            doc["point_id"]: score
            for doc, score in zip(self.documents, bm25_scores)
            if score > 0
        }

        return self.store.hybrid_search(
            query_vector,
            keyword_scores,
            top_k=top_k,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
            filters=filters,
        )

    def refresh(self) -> None:
        """Rebuild BM25 index (call after adding/removing documents)."""
        self._build_bm25_index()


class SearchConfig:
    """Configuration for hybrid search behavior."""

    def __init__(
        self,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        top_k: int = 5,
        min_score: float = 0.15,
    ):
        """Initialize search config.

        Args:
            semantic_weight: Importance of semantic similarity (0-1)
            keyword_weight: Importance of keyword match (0-1)
            top_k: Default number of results
            min_score: Minimum score threshold for results
        """
        if not (0 <= semantic_weight <= 1) or not (0 <= keyword_weight <= 1):
            raise ValueError("Weights must be between 0 and 1")

        total = semantic_weight + keyword_weight
        if total != 1.0:
            logger.warning(
                f"Weights sum to {total}, not 1.0. Consider normalizing."
            )

        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self.top_k = top_k
        self.min_score = min_score

    def for_sales_query(self) -> SearchConfig:
        """Preset: balance semantic understanding with product keywords."""
        return SearchConfig(
            semantic_weight=0.6,
            keyword_weight=0.4,
            top_k=8,
            min_score=0.12,
        )

    def for_exact_match(self) -> SearchConfig:
        """Preset: prioritize exact keyword matches."""
        return SearchConfig(
            semantic_weight=0.4,
            keyword_weight=0.6,
            top_k=5,
            min_score=0.10,
        )

    def for_semantic(self) -> SearchConfig:
        """Preset: pure semantic search (fallback)."""
        return SearchConfig(
            semantic_weight=0.95,
            keyword_weight=0.05,
            top_k=10,
            min_score=0.15,
        )
