"""
Ready-to-use integration module for QueryRouter with retrieve_v2.

This module provides wrapper functions that integrate the QueryRouter
into the retrieve_v2 search API for automatic weight optimization.

Usage:
    from llamaindex_query_router.retrieve_v2_integration import smart_search, routed_search

    # Simple smart search with automatic routing
    results = smart_search("What is machine learning?")

    # With domain-specific optimization
    results = routed_search(
        "API documentation version 3.0",
        domain="technical",
        top_k=10
    )
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from .router import QueryRouter, RoutingDecision
from .feature_extractor import QueryFeatures


@dataclass
class RoutedSearchResult:
    """Result of a routed search with routing metadata."""

    hits: List[Any]  # SearchHit objects from retrieve_v2
    routing_decision: RoutingDecision
    query_features: QueryFeatures
    execution_time_ms: float


class RoutedSearcher:
    """
    Wrapper around retrieve_v2 that automatically routes queries to optimal strategies.

    Integrates QueryRouter with retrieve_v2.search() to automatically select
    weights based on query characteristics.

    Example:
        >>> searcher = RoutedSearcher(domain="technical")
        >>> results = searcher.search("API documentation", top_k=5)
        >>> print(f"Routed to: {results.routing_decision.strategy.value}")
        >>> for hit in results.hits:
        ...     print(hit.text[:50])
    """

    def __init__(
        self,
        domain: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize RoutedSearcher.

        Args:
            domain: Domain for routing (technical, conversational, entity_search, conceptual)
            verbose: Whether to print routing details
        """
        self.router = QueryRouter(domain=domain, verbose=verbose)
        self.verbose = verbose

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        min_score: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> RoutedSearchResult:
        """
        Search with automatic query routing.

        Args:
            query: Query string
            top_k: Number of results to return
            min_score: Minimum score threshold
            filters: Metadata filters

        Returns:
            RoutedSearchResult with hits and routing metadata
        """
        import time

        # Import here to avoid circular dependency
        try:
            from ragstack.retrieve_v2 import search
        except ImportError:
            raise ImportError(
                "retrieve_v2 module not found. Make sure ragstack is installed."
            )

        start_time = time.time()

        # Analyze and route query
        features = self.router.analyze_query(query)
        decision = self.router.route_query(features)

        if self.verbose:
            print(f"\nRouted '{query}' to {decision.strategy.value}")
            print(f"Confidence: {decision.confidence:.2%}")

        # Perform search with optimized weights
        hits = search(
            query,
            top_k=top_k,
            min_score=min_score,
            filters=filters,
            use_hybrid=True,
            semantic_weight=decision.weights.semantic_weight,
            keyword_weight=decision.weights.bm25_weight,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return RoutedSearchResult(
            hits=hits,
            routing_decision=decision,
            query_features=features,
            execution_time_ms=elapsed_ms,
        )

    def explain_search(self, query: str) -> str:
        """
        Get explanation of how query will be routed.

        Args:
            query: Query string

        Returns:
            Detailed explanation string
        """
        return self.router.explain_routing_decision(query)

    def batch_search(
        self,
        queries: List[str],
        *,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RoutedSearchResult]:
        """
        Perform batch search on multiple queries.

        Args:
            queries: List of query strings
            top_k: Number of results per query
            filters: Metadata filters

        Returns:
            List of RoutedSearchResult objects
        """
        return [
            self.search(query, top_k=top_k, filters=filters)
            for query in queries
        ]

    def get_router_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        return self.router.get_cache_stats()

    def clear_cache(self) -> None:
        """Clear routing cache."""
        self.router.clear_cache()


# Convenience functions for direct usage

_default_searcher: Optional[RoutedSearcher] = None


def get_routed_searcher(
    domain: Optional[str] = None,
    verbose: bool = False,
    reset: bool = False,
) -> RoutedSearcher:
    """
    Get or create a RoutedSearcher instance.

    Args:
        domain: Domain for routing
        verbose: Whether to print routing details
        reset: Whether to reset cached searcher

    Returns:
        RoutedSearcher instance
    """
    global _default_searcher

    if reset or _default_searcher is None:
        _default_searcher = RoutedSearcher(domain=domain, verbose=verbose)

    return _default_searcher


def smart_search(
    query: str,
    *,
    top_k: int = 10,
    domain: Optional[str] = None,
    verbose: bool = False,
) -> List[Any]:
    """
    Perform smart search with automatic query routing.

    Simple wrapper that routes query and returns hits.

    Args:
        query: Query string
        top_k: Number of results to return
        domain: Domain for routing
        verbose: Whether to print routing details

    Returns:
        List of SearchHit objects

    Example:
        >>> results = smart_search("machine learning basics", top_k=5)
        >>> for hit in results:
        ...     print(f"[{hit.score:.2f}] {hit.text[:50]}")
    """
    searcher = get_routed_searcher(domain=domain, verbose=verbose)
    result = searcher.search(query, top_k=top_k)
    return result.hits


def routed_search(
    query: str,
    *,
    top_k: int = 10,
    min_score: float = 0.0,
    domain: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    verbose: bool = False,
    explain: bool = False,
) -> Dict[str, Any]:
    """
    Perform search with routing details.

    Returns both results and routing metadata.

    Args:
        query: Query string
        top_k: Number of results to return
        min_score: Minimum score threshold
        domain: Domain for routing
        filters: Metadata filters
        verbose: Whether to print routing details
        explain: Whether to print routing explanation

    Returns:
        Dictionary with:
        - hits: List of SearchHit objects
        - strategy: Routing strategy used
        - confidence: Confidence score
        - weights: (bm25_weight, semantic_weight)
        - reasoning: List of reasoning strings

    Example:
        >>> result = routed_search("API documentation", domain="technical")
        >>> print(f"Routed to: {result['strategy']}")
        >>> print(f"Confidence: {result['confidence']:.2%}")
        >>> for hit in result['hits']:
        ...     print(hit.text[:50])
    """
    searcher = get_routed_searcher(domain=domain, verbose=verbose)
    search_result = searcher.search(query, top_k=top_k, min_score=min_score, filters=filters)

    if explain:
        print(searcher.explain_search(query))

    return {
        "hits": search_result.hits,
        "strategy": search_result.routing_decision.strategy.value,
        "confidence": search_result.routing_decision.confidence,
        "weights": (
            search_result.routing_decision.weights.bm25_weight,
            search_result.routing_decision.weights.semantic_weight,
        ),
        "reasoning": search_result.routing_decision.reasoning,
        "execution_time_ms": search_result.execution_time_ms,
    }


def get_routing_decision(query: str, domain: Optional[str] = None) -> Dict[str, Any]:
    """
    Get routing decision for a query without performing search.

    Args:
        query: Query string
        domain: Domain for routing

    Returns:
        Dictionary with routing decision details
    """
    searcher = get_routed_searcher(domain=domain)
    features = searcher.router.analyze_query(query)
    decision = searcher.router.route_query(features)

    return {
        "query": query,
        "strategy": decision.strategy.value,
        "confidence": decision.confidence,
        "weights": (decision.weights.bm25_weight, decision.weights.semantic_weight),
        "reasoning": decision.reasoning,
        "alternatives": [
            (s.value, score) for s, score in decision.alternative_strategies
        ],
        "specificity": features.specificity_score,
        "keyword_density": features.keyword_density,
    }


def explain_routing(query: str, domain: Optional[str] = None) -> str:
    """
    Get human-readable explanation of query routing.

    Args:
        query: Query string
        domain: Domain for routing

    Returns:
        Explanation string
    """
    searcher = get_routed_searcher(domain=domain)
    return searcher.explain_search(query)
