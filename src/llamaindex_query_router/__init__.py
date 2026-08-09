"""
LlamaIndex Query Router - Intelligent query routing for retrieval strategies.

This package provides a QueryRouter that analyzes queries and routes them
to appropriate retrieval strategies (BM25, semantic, or hybrid search).

Features:
- Intelligent query feature extraction and analysis
- Decision tree-based routing with confidence scoring
- Domain-specific customization (technical, conversational, entity, conceptual)
- Transparent routing explanations for debugging
- Caching of routing decisions for performance
"""

from .router import QueryRouter, RoutingDecision
from .feature_extractor import QueryFeatureExtractor, QueryFeatures
from .routing_strategies import (
    RoutingStrategy,
    StrategyWeights,
    DomainConfig,
    get_default_hybrid_weights,
    get_aggressive_bm25_weights,
    get_aggressive_semantic_weights,
    get_technical_domain_weights,
    get_conversational_weights,
    get_entity_search_weights,
    get_conceptual_weights,
    get_domain_config,
    list_available_domains,
    create_domain_config,
    create_custom_weights,
)

__version__ = "0.2.0"
__author__ = "LlamaIndex Contributors"

__all__ = [
    # Router
    "QueryRouter",
    "RoutingDecision",
    # Feature Extraction
    "QueryFeatureExtractor",
    "QueryFeatures",
    # Routing Strategies
    "RoutingStrategy",
    "StrategyWeights",
    "DomainConfig",
    # Weight Presets
    "get_default_hybrid_weights",
    "get_aggressive_bm25_weights",
    "get_aggressive_semantic_weights",
    "get_technical_domain_weights",
    "get_conversational_weights",
    "get_entity_search_weights",
    "get_conceptual_weights",
    # Domain Configuration
    "get_domain_config",
    "list_available_domains",
    "create_domain_config",
    "create_custom_weights",
]
