"""Hybrid retriever with semantic search, keyword matching, and reranking."""

import re
from typing import Optional

import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from .models import Chunk, RetrievalResult
from .vector_store import SQLiteVecStore


class HybridRetriever:
    """Retrieve relevant chunks using hybrid search and reranking."""

    def __init__(
        self,
        vector_store: SQLiteVecStore,
        embedding_model: Optional[str] = "all-MiniLM-L6-v2",
        rerank_model: Optional[str] = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ):
        """Initialize retriever.

        Args:
            vector_store: Vector store instance
            embedding_model: Embedding model name
            rerank_model: Cross-encoder reranking model name
        """
        self.vector_store = vector_store
        self.embeddings = SentenceTransformer(embedding_model) if embedding_model else None
        self.reranker = CrossEncoder(rerank_model) if rerank_model else None

    def retrieve(
        self,
        query: str,
        k: int = 5,
        use_keyword: bool = True,
        use_semantic: bool = True,
        use_rerank: bool = True,
    ) -> list[RetrievalResult]:
        """Retrieve relevant chunks for a query.

        Args:
            query: Query text
            k: Number of results to return
            use_keyword: Enable keyword matching
            use_semantic: Enable semantic search
            use_rerank: Enable cross-encoder reranking

        Returns:
            List of retrieval results ranked by relevance
        """
        candidates = {}  # chunk_id -> RetrievalResult

        # Semantic search
        if use_semantic and self.embeddings:
            query_embedding = self.embeddings.encode(query, convert_to_list=True)
            semantic_results = self.vector_store.similarity_search(query_embedding, k=k * 2)

            for chunk_id, score in semantic_results:
                chunk = self.vector_store.get_chunk(chunk_id)
                if chunk:
                    candidates[chunk_id] = RetrievalResult(
                        chunk=chunk,
                        semantic_score=score,
                        keyword_score=0.0,
                    )

        # Keyword search
        if use_keyword:
            keyword_scores = self._keyword_search(query)
            for chunk_id, keyword_score in keyword_scores.items():
                if chunk_id in candidates:
                    candidates[chunk_id].keyword_score = keyword_score
                else:
                    chunk = self.vector_store.get_chunk(chunk_id)
                    if chunk:
                        candidates[chunk_id] = RetrievalResult(
                            chunk=chunk,
                            semantic_score=0.0,
                            keyword_score=keyword_score,
                        )

        # Reranking with cross-encoder
        if use_rerank and self.reranker and candidates:
            candidates = self._rerank(query, candidates)

        # Sort and return top-k
        sorted_results = sorted(candidates.values(), key=lambda x: x.final_score, reverse=True)
        return sorted_results[:k]

    def _keyword_search(self, query: str) -> dict[str, float]:
        """Perform keyword-based search.

        Args:
            query: Query text

        Returns:
            Dictionary of chunk_id -> keyword_score
        """
        # Extract keywords (simple approach: tokenize and filter stopwords)
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
        }
        keywords = [
            w.lower() for w in re.findall(r"\w+", query)
            if len(w) > 2 and w.lower() not in stopwords
        ]

        if not keywords:
            return {}

        cursor = self.vector_store.connection.cursor()
        cursor.execute("SELECT id FROM chunks")
        chunk_ids = [row[0] for row in cursor.fetchall()]

        scores = {}
        for chunk_id in chunk_ids:
            chunk = self.vector_store.get_chunk(chunk_id)
            if not chunk:
                continue

            chunk_text = chunk.text.lower()
            matches = sum(1 for kw in keywords if kw in chunk_text)

            if matches > 0:
                # Normalize score to 0-1 range
                score = min(matches / len(keywords), 1.0)
                scores[chunk_id] = score

        return scores

    def _rerank(
        self, query: str, candidates: dict[str, RetrievalResult]
    ) -> dict[str, RetrievalResult]:
        """Rerank candidates using cross-encoder.

        Args:
            query: Query text
            candidates: Dictionary of chunk_id -> RetrievalResult

        Returns:
            Updated candidates with rerank scores
        """
        if not candidates:
            return candidates

        # Prepare query-text pairs for reranking
        pairs = [(query, result.chunk.text) for result in candidates.values()]
        chunk_ids = list(candidates.keys())

        # Get rerank scores
        rerank_scores = self.reranker.predict(pairs)

        # Normalize scores to 0-1 range
        scores_array = np.array(rerank_scores)
        scores_normalized = (scores_array - scores_array.min()) / (
            scores_array.max() - scores_array.min() + 1e-8
        )

        # Update candidates with rerank scores
        for chunk_id, score in zip(chunk_ids, scores_normalized):
            candidates[chunk_id].rerank_score = float(score)

        return candidates
