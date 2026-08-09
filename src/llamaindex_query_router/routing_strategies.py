"""
Routing strategies for query processing.

This module defines different strategies for routing queries to appropriate
retrieval methods based on query characteristics. Supports:
- Predefined strategies: BM25, semantic, hybrid
- Customizable weight presets for different domains
- Domain-specific configurations for optimization
"""

from enum import Enum
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any


class RoutingStrategy(Enum):
    """Enum representing available routing strategies."""

    BM25 = "bm25"           # Keyword-based lexical search
    SEMANTIC = "semantic"   # Dense vector embedding search
    HYBRID = "hybrid"       # Combined BM25 and semantic search


@dataclass
class StrategyWeights:
    """Weights for hybrid routing strategy."""

    bm25_weight: float
    semantic_weight: float

    def __post_init__(self):
        """Validate weights sum to 1.0."""
        total = self.bm25_weight + self.semantic_weight
        if not (0.99 <= total <= 1.01):  # Allow small floating point error
            raise ValueError(
                f"Weights must sum to 1.0, got {total}. "
                f"BM25: {self.bm25_weight}, Semantic: {self.semantic_weight}"
            )


@dataclass
class DomainConfig:
    """
    Configuration for domain-specific routing optimization.

    Attributes:
        name: Domain name (e.g., "technical", "conversational")
        description: Description of the domain
        bm25_weight: Preferred BM25 weight for this domain
        semantic_weight: Preferred semantic weight for this domain
        threshold_specificity: Specificity threshold to prefer BM25 (0-1)
        threshold_keyword_density: Keyword density threshold to prefer BM25 (0-1)
        enable_temporal_boost: Whether to boost BM25 for temporal queries
        metadata_filters: Optional metadata filters to apply
    """

    name: str
    description: str
    bm25_weight: float = 0.5
    semantic_weight: float = 0.5
    threshold_specificity: float = 0.7
    threshold_keyword_density: float = 0.6
    enable_temporal_boost: bool = False
    metadata_filters: Optional[Dict[str, Any]] = None

    def to_strategy_weights(self) -> StrategyWeights:
        """Convert to StrategyWeights."""
        return StrategyWeights(
            bm25_weight=self.bm25_weight,
            semantic_weight=self.semantic_weight,
        )


# Strategy-specific configurations
STRATEGY_CONFIGS = {
    RoutingStrategy.BM25: {
        "description": "Lexical keyword matching for structured queries",
        "pros": [
            "Excellent for exact phrase matching",
            "Fast and efficient keyword lookup",
            "No embedding computation needed",
            "Works well with acronyms and technical terms",
        ],
        "cons": [
            "Cannot handle paraphrasing or synonyms",
            "Poor performance on semantic variations",
            "Struggles with short queries",
        ],
        "use_cases": [
            "Exact phrase queries",
            "Queries with specific technical terms",
            "Structured queries with boolean operators",
            "Product names and acronyms",
            "Numerical searches (prices, dates, versions)",
        ],
    },
    RoutingStrategy.SEMANTIC: {
        "description": "Dense embedding-based semantic search",
        "pros": [
            "Handles paraphrasing and synonyms",
            "Understands semantic similarity",
            "Works well with natural language",
            "Good for conceptual matching",
        ],
        "cons": [
            "Slower due to embedding computation",
            "May miss exact keyword matches",
            "Embedding quality varies by model",
        ],
        "use_cases": [
            "Natural language questions",
            "Paraphrased queries",
            "Conceptual similarity matching",
            "Why/how/explain type questions",
            "Exploratory searches",
        ],
    },
    RoutingStrategy.HYBRID: {
        "description": "Combined lexical and semantic search",
        "pros": [
            "Combines strengths of both approaches",
            "Better recall and precision",
            "Handles diverse query types",
            "Customizable weighting",
        ],
        "cons": [
            "More complex to tune",
            "Higher computational cost",
            "Requires tuning weights for domain",
        ],
        "use_cases": [
            "General purpose queries",
            "Mixed structured and natural language",
            "Queries requiring both precision and recall",
            "Unknown query patterns",
            "Production systems requiring robustness",
        ],
    },
}

# Predefined domain configurations
DOMAIN_CONFIGS = {
    "technical": DomainConfig(
        name="technical",
        description="Technical/engineering queries with acronyms and specific terminology",
        bm25_weight=0.65,
        semantic_weight=0.35,
        threshold_specificity=0.6,
        threshold_keyword_density=0.5,
        enable_temporal_boost=True,
    ),
    "conversational": DomainConfig(
        name="conversational",
        description="Natural conversation and exploratory queries",
        bm25_weight=0.35,
        semantic_weight=0.65,
        threshold_specificity=0.5,
        threshold_keyword_density=0.4,
        enable_temporal_boost=False,
    ),
    "entity_search": DomainConfig(
        name="entity_search",
        description="Entity-focused queries (people, products, places)",
        bm25_weight=0.75,
        semantic_weight=0.25,
        threshold_specificity=0.7,
        threshold_keyword_density=0.6,
        enable_temporal_boost=False,
    ),
    "conceptual": DomainConfig(
        name="conceptual",
        description="Conceptual and analytical queries (why, how, explain)",
        bm25_weight=0.25,
        semantic_weight=0.75,
        threshold_specificity=0.5,
        threshold_keyword_density=0.3,
        enable_temporal_boost=False,
    ),
}


def get_default_hybrid_weights() -> StrategyWeights:
    """
    Get default weights for hybrid routing strategy.

    Returns:
        StrategyWeights: Default weights (0.5 BM25, 0.5 semantic)
    """
    return StrategyWeights(bm25_weight=0.5, semantic_weight=0.5)


def get_aggressive_bm25_weights() -> StrategyWeights:
    """
    Get weights favoring BM25 for keyword-heavy queries.

    Returns:
        StrategyWeights: Weights (0.7 BM25, 0.3 semantic)
    """
    return StrategyWeights(bm25_weight=0.7, semantic_weight=0.3)


def get_aggressive_semantic_weights() -> StrategyWeights:
    """
    Get weights favoring semantic search for conceptual queries.

    Returns:
        StrategyWeights: Weights (0.3 BM25, 0.7 semantic)
    """
    return StrategyWeights(bm25_weight=0.3, semantic_weight=0.7)


def get_technical_domain_weights() -> StrategyWeights:
    """
    Get weights optimized for technical/domain-specific queries.

    Technical queries often contain acronyms, specific terminology, and
    product names that benefit from keyword matching.

    Returns:
        StrategyWeights: Weights (0.65 BM25, 0.35 semantic)
    """
    return StrategyWeights(bm25_weight=0.65, semantic_weight=0.35)


def get_conversational_weights() -> StrategyWeights:
    """
    Get weights optimized for conversational/natural language queries.

    Conversational queries benefit from semantic understanding as users
    may phrase similar questions in different ways.

    Returns:
        StrategyWeights: Weights (0.35 BM25, 0.65 semantic)
    """
    return StrategyWeights(bm25_weight=0.35, semantic_weight=0.65)


def get_entity_search_weights() -> StrategyWeights:
    """
    Get weights optimized for entity/name-based searches.

    Queries targeting specific entities (people, products, places) benefit
    from strong keyword matching.

    Returns:
        StrategyWeights: Weights (0.75 BM25, 0.25 semantic)
    """
    return StrategyWeights(bm25_weight=0.75, semantic_weight=0.25)


def get_conceptual_weights() -> StrategyWeights:
    """
    Get weights optimized for conceptual/exploratory queries.

    Conceptual queries asking "why", "how", "explain" benefit from
    semantic understanding and concept matching.

    Returns:
        StrategyWeights: Weights (0.25 BM25, 0.75 semantic)
    """
    return StrategyWeights(bm25_weight=0.25, semantic_weight=0.75)


def create_custom_weights(
    bm25_weight: float, semantic_weight: float
) -> StrategyWeights:
    """
    Create custom weights for hybrid strategy.

    Args:
        bm25_weight: Weight for BM25 keyword search (0-1)
        semantic_weight: Weight for semantic search (0-1)

    Returns:
        StrategyWeights: Custom weights (will be normalized if needed)

    Raises:
        ValueError: If weights don't sum to approximately 1.0
    """
    total = bm25_weight + semantic_weight
    if total < 0.99 or total > 1.01:
        # Normalize
        normalized_bm25 = bm25_weight / total
        normalized_semantic = semantic_weight / total
        return StrategyWeights(
            bm25_weight=normalized_bm25, semantic_weight=normalized_semantic
        )
    return StrategyWeights(bm25_weight=bm25_weight, semantic_weight=semantic_weight)


def get_domain_config(domain_name: str) -> Optional[DomainConfig]:
    """
    Get domain configuration by name.

    Args:
        domain_name: Name of the domain (technical, conversational, entity_search, conceptual)

    Returns:
        DomainConfig if found, None otherwise
    """
    return DOMAIN_CONFIGS.get(domain_name.lower())


def list_available_domains() -> list[str]:
    """
    List all available domain configurations.

    Returns:
        List of domain names
    """
    return list(DOMAIN_CONFIGS.keys())


def create_domain_config(
    name: str,
    description: str,
    bm25_weight: float = 0.5,
    semantic_weight: float = 0.5,
    threshold_specificity: float = 0.7,
    threshold_keyword_density: float = 0.6,
    enable_temporal_boost: bool = False,
) -> DomainConfig:
    """
    Create a custom domain configuration.

    Args:
        name: Domain name
        description: Domain description
        bm25_weight: Preferred BM25 weight
        semantic_weight: Preferred semantic weight
        threshold_specificity: Specificity threshold for BM25 boost
        threshold_keyword_density: Keyword density threshold for BM25 boost
        enable_temporal_boost: Whether to boost BM25 for temporal queries

    Returns:
        DomainConfig instance
    """
    return DomainConfig(
        name=name,
        description=description,
        bm25_weight=bm25_weight,
        semantic_weight=semantic_weight,
        threshold_specificity=threshold_specificity,
        threshold_keyword_density=threshold_keyword_density,
        enable_temporal_boost=enable_temporal_boost,
    )
