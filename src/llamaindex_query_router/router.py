"""
Query routing system for LlamaIndex.

This module provides the QueryRouter class that analyzes queries and
routes them to appropriate retrieval strategies based on query characteristics.

Features include:
- Intelligent query analysis and feature extraction
- Decision tree-based routing with confidence scoring
- Domain-specific customization
- Routing explanations for transparency and debugging
"""

from dataclasses import dataclass
from typing import Tuple, Dict, Any, Optional, List
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
)


@dataclass
class RoutingDecision:
    """
    Result of routing analysis with confidence and reasoning.

    Attributes:
        strategy: Recommended routing strategy
        confidence: Confidence score (0.0-1.0) in the routing decision
        weights: Weights for hybrid strategy
        reasoning: List of reasons for the routing decision
        alternative_strategies: List of alternative strategies considered
    """

    strategy: RoutingStrategy
    confidence: float
    weights: StrategyWeights
    reasoning: List[str]
    alternative_strategies: List[Tuple[RoutingStrategy, float]]


class QueryRouter:
    """
    Router that analyzes queries and recommends retrieval strategies.

    The QueryRouter examines query characteristics and recommends whether
    to use BM25 (keyword-based), semantic (embedding-based), or hybrid
    retrieval approaches. Supports:
    - Adaptive weighting based on query content
    - Domain-specific customization
    - Confidence scoring with transparent reasoning
    - Caching of routing decisions
    """

    def __init__(
        self,
        verbose: bool = False,
        domain: Optional[str] = None,
        domain_config: Optional[DomainConfig] = None,
    ):
        """
        Initialize the QueryRouter.

        Args:
            verbose: Whether to print routing decision details
            domain: Domain name (technical, conversational, entity_search, conceptual)
            domain_config: Custom DomainConfig for specialized routing

        Raises:
            ValueError: If domain name is invalid
        """
        self.feature_extractor = QueryFeatureExtractor()
        self.verbose = verbose
        self._routing_decisions_cache: Dict[str, RoutingDecision] = {}

        # Set up domain configuration
        if domain_config:
            self.domain_config = domain_config
        elif domain:
            config = get_domain_config(domain)
            if not config:
                raise ValueError(
                    f"Unknown domain: {domain}. "
                    f"Available: technical, conversational, entity_search, conceptual"
                )
            self.domain_config = config
        else:
            self.domain_config = None

    def analyze_query(self, query: str) -> QueryFeatures:
        """
        Analyze a query and extract its features.

        Args:
            query: The input query string

        Returns:
            QueryFeatures: Extracted features from the query
        """
        features = self.feature_extractor.extract_features(query)
        if self.verbose:
            self._print_features(features)
        return features

    def route_strategy(self, features: QueryFeatures) -> RoutingStrategy:
        """
        Determine the optimal routing strategy for a query.

        Uses query features to decide between BM25, SEMANTIC, or HYBRID
        retrieval strategies.

        Args:
            features: QueryFeatures extracted from the query

        Returns:
            RoutingStrategy: Recommended strategy
        """
        decision = self.route_query(features)
        return decision.strategy

    def route_query(self, features: QueryFeatures) -> RoutingDecision:
        """
        Analyze a query and return a complete routing decision with confidence.

        Args:
            features: QueryFeatures extracted from the query

        Returns:
            RoutingDecision: Complete routing decision with reasoning and confidence

        Example:
            >>> router = QueryRouter()
            >>> features = router.analyze_query("What is machine learning?")
            >>> decision = router.route_query(features)
            >>> print(f"Strategy: {decision.strategy.value} (confidence: {decision.confidence:.2f})")
        """
        # Check cache first
        if features.query in self._routing_decisions_cache:
            return self._routing_decisions_cache[features.query]

        # Compute routing decision
        strategy, confidence, reasoning, alternatives = self._determine_strategy_with_confidence(
            features
        )
        weights = self._get_strategy_weights(strategy, features)

        decision = RoutingDecision(
            strategy=strategy,
            confidence=confidence,
            weights=weights,
            reasoning=reasoning,
            alternative_strategies=alternatives,
        )

        # Cache the decision
        self._routing_decisions_cache[features.query] = decision

        if self.verbose:
            self._print_routing_decision(decision, features)

        return decision

    def get_weights(self, strategy: RoutingStrategy) -> Tuple[float, float]:
        """
        Get the BM25 and semantic weights for a given strategy.

        Args:
            strategy: The routing strategy

        Returns:
            Tuple of (bm25_weight, semantic_weight)
        """
        if strategy == RoutingStrategy.BM25:
            return (1.0, 0.0)
        elif strategy == RoutingStrategy.SEMANTIC:
            return (0.0, 1.0)
        elif strategy == RoutingStrategy.HYBRID:
            weights = get_default_hybrid_weights()
            return (weights.bm25_weight, weights.semantic_weight)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def get_weights_for_query(self, query: str) -> Tuple[float, float]:
        """
        Get optimized weights for a specific query.

        Analyzes the query and returns domain/query-specific weights.

        Args:
            query: The query string

        Returns:
            Tuple of (bm25_weight, semantic_weight)
        """
        features = self.analyze_query(query)
        decision = self.route_query(features)
        return (decision.weights.bm25_weight, decision.weights.semantic_weight)

    def explain_routing_decision(self, query: str) -> str:
        """
        Generate a human-readable explanation of routing decision.

        Args:
            query: The input query string

        Returns:
            String explanation of why the query was routed to its strategy
        """
        features = self.analyze_query(query)
        decision = self.route_query(features)

        explanation = self._build_detailed_explanation(features, decision)
        return explanation

    def _determine_strategy_with_confidence(
        self, features: QueryFeatures
    ) -> Tuple[RoutingStrategy, float, List[str], List[Tuple[RoutingStrategy, float]]]:
        """
        Determine strategy based on query features with confidence scoring.

        Uses a decision tree approach with multiple criteria to route queries.

        Args:
            features: Extracted query features

        Returns:
            Tuple of (strategy, confidence, reasoning, alternatives)
        """
        # Score each strategy
        bm25_score = self._score_bm25(features)
        semantic_score = self._score_semantic(features)
        hybrid_score = self._score_hybrid(features)

        # Determine primary strategy
        scores = {
            RoutingStrategy.BM25: bm25_score,
            RoutingStrategy.SEMANTIC: semantic_score,
            RoutingStrategy.HYBRID: hybrid_score,
        }

        strategy = max(scores, key=scores.get)
        confidence = scores[strategy]

        # Collect reasoning
        reasoning = self._build_reasoning(features, strategy)

        # Rank alternatives
        alternatives = sorted(
            [(s, score) for s, score in scores.items() if s != strategy],
            key=lambda x: x[1],
            reverse=True,
        )

        return strategy, confidence, reasoning, alternatives

    def _score_bm25(self, features: QueryFeatures) -> float:
        """Calculate BM25 suitability score (0-1)."""
        score = 0.0
        max_score = 0.0

        # Exact phrase indicator (strong)
        if features.has_quotes:
            score += 0.25
        max_score += 0.25

        # Boolean operators (strong)
        if features.has_boolean_operators:
            score += 0.20
        max_score += 0.20

        # Acronyms/special terms (strong)
        if features.contains_acronyms:
            score += 0.15
        max_score += 0.15

        # Numbers with high keyword density (moderate)
        if features.contains_numbers and features.keyword_density > 0.5:
            score += 0.15
        max_score += 0.15

        # High specificity (moderate)
        if features.specificity_score > 0.7:
            score += 0.10
        max_score += 0.10

        # Short query with special chars (moderate)
        if features.length <= 2 and features.has_special_chars:
            score += 0.10
        max_score += 0.10

        # High keyword density (weak)
        if features.keyword_density > 0.6:
            score += 0.05
        max_score += 0.05

        return score / max_score if max_score > 0 else 0.0

    def _score_semantic(self, features: QueryFeatures) -> float:
        """Calculate semantic suitability score (0-1)."""
        score = 0.0
        max_score = 0.0

        # Natural language question (strong)
        if features.is_question and features.length > 3:
            score += 0.25
        max_score += 0.25

        # Reasoning keywords (strong)
        if features.has_reasoning_keywords:
            score += 0.20
        max_score += 0.20

        # Good query length (moderate)
        if 4 <= features.length <= 15:
            score += 0.15
        max_score += 0.15

        # Moderate to low keyword density (moderate)
        if features.keyword_density < 0.6:
            score += 0.15
        max_score += 0.15

        # Moderate specificity (weak)
        if 0.3 < features.specificity_score < 0.8:
            score += 0.10
        max_score += 0.10

        # Temporal markers (weak - suggests context awareness)
        if features.has_temporal:
            score += 0.05
        max_score += 0.05

        # Not a structured query (weak)
        if not features.has_special_chars and not features.has_boolean_operators:
            score += 0.10
        max_score += 0.10

        return score / max_score if max_score > 0 else 0.0

    def _score_hybrid(self, features: QueryFeatures) -> float:
        """Calculate hybrid suitability score (0-1)."""
        # Hybrid is a safe default for mixed queries
        score = 0.0
        max_score = 0.0

        # Mixed characteristics (moderate)
        has_mixed = (
            (features.has_quotes or features.has_boolean_operators)
            and features.is_question
        )
        if has_mixed:
            score += 0.20
        max_score += 0.20

        # Medium specificity (moderate)
        if 0.4 <= features.specificity_score <= 0.7:
            score += 0.15
        max_score += 0.15

        # Balanced keyword density (moderate)
        if 0.3 <= features.keyword_density <= 0.7:
            score += 0.15
        max_score += 0.15

        # Medium query length (weak)
        if 3 <= features.length <= 12:
            score += 0.10
        max_score += 0.10

        # No strong indicators for specific strategy (weak)
        bm25_strong = (
            features.has_quotes
            or features.has_boolean_operators
            or features.contains_acronyms
        )
        semantic_strong = features.is_question and features.length > 5
        if not bm25_strong and not semantic_strong:
            score += 0.25
        max_score += 0.25

        return score / max_score if max_score > 0 else 0.0

    def _build_reasoning(
        self, features: QueryFeatures, strategy: RoutingStrategy
    ) -> List[str]:
        """Build list of reasoning for routing decision."""
        reasons = []

        if features.has_quotes:
            reasons.append("Contains exact phrases (quoted)")
        if features.has_boolean_operators:
            reasons.append("Contains boolean operators (AND/OR/NOT)")
        if features.is_question:
            reasons.append(f"Phrased as a {features.question_type}-question")
        if features.contains_acronyms:
            reasons.append("Contains acronyms or specialized terms")
        if features.contains_numbers:
            reasons.append("Contains numerical values or measurements")
        if features.has_reasoning_keywords:
            reasons.append(
                f"Contains analytical keywords: {', '.join(features.reasoning_keywords[:2])}"
            )
        if features.has_temporal:
            reasons.append(
                f"Contains temporal markers: {', '.join(features.temporal_markers[:2])}"
            )

        if features.specificity_score > 0.7:
            reasons.append(f"High specificity score ({features.specificity_score:.2f})")
        if features.keyword_density > 0.6:
            reasons.append(f"High keyword density ({features.keyword_density:.2f})")

        if strategy == RoutingStrategy.HYBRID and not reasons:
            reasons.append("Mixed or general-purpose query characteristics")

        return reasons

    def _get_strategy_weights(
        self, strategy: RoutingStrategy, features: QueryFeatures
    ) -> StrategyWeights:
        """Get appropriate weights for the selected strategy."""
        if strategy == RoutingStrategy.BM25:
            return StrategyWeights(bm25_weight=1.0, semantic_weight=0.0)
        elif strategy == RoutingStrategy.SEMANTIC:
            return StrategyWeights(bm25_weight=0.0, semantic_weight=1.0)
        elif strategy == RoutingStrategy.HYBRID:
            # Use domain config if available, otherwise use adaptive weighting
            if self.domain_config:
                return self.domain_config.to_strategy_weights()

            # Adaptive weighting based on query characteristics
            if features.specificity_score > 0.75:
                return get_aggressive_bm25_weights()
            elif features.has_reasoning_keywords and features.is_question:
                return get_aggressive_semantic_weights()
            else:
                return get_default_hybrid_weights()
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _determine_strategy(self, features: QueryFeatures) -> RoutingStrategy:
        """
        Legacy method for backward compatibility.

        Determine strategy based on query features.

        Args:
            features: Extracted query features

        Returns:
            RoutingStrategy: Recommended strategy
        """
        strategy, _, _, _ = self._determine_strategy_with_confidence(features)
        return strategy

    def _build_detailed_explanation(
        self, features: QueryFeatures, decision: RoutingDecision
    ) -> str:
        """
        Build detailed human-readable explanation of routing decision.

        Args:
            features: Extracted query features
            decision: RoutingDecision with reasoning and confidence

        Returns:
            Comprehensive explanation string
        """
        strategy_desc = {
            RoutingStrategy.BM25: "keyword-based lexical search",
            RoutingStrategy.SEMANTIC: "semantic embedding-based search",
            RoutingStrategy.HYBRID: "hybrid (lexical + semantic) search",
        }

        explanation = f"Query: '{features.query}'\n"
        explanation += (
            f"Strategy: {decision.strategy.value.upper()} "
            f"({strategy_desc[decision.strategy]})\n"
        )
        explanation += f"Confidence: {decision.confidence:.2%}\n\n"

        if decision.reasoning:
            explanation += "Reasoning:\n"
            for i, reason in enumerate(decision.reasoning, 1):
                explanation += f"  {i}. {reason}\n"
        else:
            explanation += "Reasoning: General purpose query\n"

        # Show alternative strategies if confidence < 0.8
        if decision.confidence < 0.8 and decision.alternative_strategies:
            explanation += "\nAlternatives considered:\n"
            for alt_strategy, alt_score in decision.alternative_strategies:
                explanation += f"  - {alt_strategy.value}: {alt_score:.2%}\n"

        # Show weights for hybrid strategy
        if decision.strategy == RoutingStrategy.HYBRID:
            explanation += (
                f"\nWeights: BM25={decision.weights.bm25_weight:.1%}, "
                f"Semantic={decision.weights.semantic_weight:.1%}\n"
            )

        # Show query characteristics
        explanation += f"\nQuery Characteristics:\n"
        explanation += f"  Length: {features.length} tokens\n"
        explanation += f"  Specificity: {features.specificity_score:.2f}/1.0\n"
        explanation += f"  Keyword Density: {features.keyword_density:.2f}\n"

        return explanation

    def _build_explanation(
        self, features: QueryFeatures, strategy: RoutingStrategy
    ) -> str:
        """
        Legacy method for backward compatibility.

        Build human-readable explanation of routing decision.

        Args:
            features: Extracted query features
            strategy: Selected routing strategy

        Returns:
            Explanation string
        """
        decision = RoutingDecision(
            strategy=strategy,
            confidence=0.75,  # Default confidence
            weights=self._get_strategy_weights(strategy, features),
            reasoning=self._build_reasoning(features, strategy),
            alternative_strategies=[],
        )
        return self._build_detailed_explanation(features, decision)

    def _print_features(self, features: QueryFeatures) -> None:
        """Print extracted query features."""
        print(f"\nQuery Features for: '{features.query}'")
        print(f"  Length: {features.length} tokens")
        print(f"  Has Quotes: {features.has_quotes}")
        print(f"  Boolean Operators: {features.has_boolean_operators}")
        print(f"  Special Chars: {features.has_special_chars}")
        print(f"  Keyword Density: {features.keyword_density:.2f}")
        print(f"  Entity Count: {features.entity_count}")
        print(f"  Is Question: {features.is_question} ({features.question_type})")
        print(f"  Avg Word Length: {features.avg_word_length:.2f}")
        print(f"  Acronyms: {features.contains_acronyms}")
        print(f"  Numbers: {features.contains_numbers}")
        print(f"  Specificity Score: {features.specificity_score:.2f}")
        print(f"  Temporal Markers: {features.temporal_markers}")
        print(f"  Reasoning Keywords: {features.reasoning_keywords}\n")

    def _print_routing_decision(
        self, decision: RoutingDecision, features: QueryFeatures
    ) -> None:
        """Print routing decision details."""
        print(f"Routing Decision:")
        print(f"  Strategy: {decision.strategy.value}")
        print(f"  Confidence: {decision.confidence:.2%}")
        if decision.reasoning:
            print(f"  Reasoning:")
            for reason in decision.reasoning:
                print(f"    - {reason}")

    def clear_cache(self) -> None:
        """Clear the routing decisions cache."""
        self._routing_decisions_cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the routing cache.

        Returns:
            Dictionary with cache statistics including:
            - cached_queries: Number of cached queries
            - bm25_count: Number of queries routed to BM25
            - semantic_count: Number of queries routed to semantic
            - hybrid_count: Number of queries routed to hybrid
            - avg_confidence: Average confidence score
        """
        decisions = list(self._routing_decisions_cache.values())
        if not decisions:
            return {
                "cached_queries": 0,
                "bm25_count": 0,
                "semantic_count": 0,
                "hybrid_count": 0,
                "avg_confidence": 0.0,
            }

        bm25_decisions = [d for d in decisions if d.strategy == RoutingStrategy.BM25]
        semantic_decisions = [d for d in decisions if d.strategy == RoutingStrategy.SEMANTIC]
        hybrid_decisions = [d for d in decisions if d.strategy == RoutingStrategy.HYBRID]

        avg_confidence = sum(d.confidence for d in decisions) / len(decisions)

        return {
            "cached_queries": len(decisions),
            "bm25_count": len(bm25_decisions),
            "semantic_count": len(semantic_decisions),
            "hybrid_count": len(hybrid_decisions),
            "avg_confidence": avg_confidence,
        }
