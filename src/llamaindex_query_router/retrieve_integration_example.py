"""
Integration example: QueryRouter with retrieve_v2.py

This example demonstrates how to use the QueryRouter to intelligently
select retrieval strategies and weights for the retrieve_v2 module.
"""

from llamaindex_query_router import (
    QueryRouter,
    QueryFeatures,
    RoutingDecision,
    get_domain_config,
    list_available_domains,
)

# Note: In actual usage, import from ragstack
# from ragstack.retrieve_v2 import search


def example_basic_routing():
    """Basic example: route a query and get optimal weights."""
    print("=" * 60)
    print("Example 1: Basic Query Routing")
    print("=" * 60)

    router = QueryRouter(verbose=True)

    query = "What are the best practices for machine learning?"
    print(f"\nQuery: {query}\n")

    # Analyze and route
    features = router.analyze_query(query)
    decision = router.route_query(features)

    print(f"Strategy: {decision.strategy.value}")
    print(f"Confidence: {decision.confidence:.2%}")
    print(f"BM25 Weight: {decision.weights.bm25_weight:.2%}")
    print(f"Semantic Weight: {decision.weights.semantic_weight:.2%}")

    # In actual use:
    # results = search(
    #     query,
    #     top_k=5,
    #     semantic_weight=decision.weights.semantic_weight,
    #     keyword_weight=decision.weights.bm25_weight,
    # )


def example_domain_specific_routing():
    """Example: use domain-specific routing."""
    print("\n" + "=" * 60)
    print("Example 2: Domain-Specific Routing")
    print("=" * 60)

    # List available domains
    print("\nAvailable domains:", list_available_domains())

    # Create routers for different domains
    domains = ["technical", "conversational", "entity_search", "conceptual"]
    query = "python version 3.11 release date"

    print(f"\nQuery: {query}\n")
    print("Routing decisions by domain:")
    print("-" * 60)

    for domain in domains:
        router = QueryRouter(domain=domain)
        decision = router.route_query(router.analyze_query(query))

        config = get_domain_config(domain)
        print(f"\n{domain.upper()} Domain")
        print(f"  Description: {config.description}")
        print(f"  Strategy: {decision.strategy.value}")
        print(f"  Confidence: {decision.confidence:.2%}")
        print(f"  Weights: BM25={decision.weights.bm25_weight:.1%}, "
              f"Semantic={decision.weights.semantic_weight:.1%}")


def example_diverse_queries():
    """Example: demonstrate routing for diverse query types."""
    print("\n" + "=" * 60)
    print("Example 3: Diverse Query Routing")
    print("=" * 60)

    router = QueryRouter()

    queries = [
        "machine learning tutorial",                # General topic
        '"exactly this phrase"',                     # Exact phrase
        'Python AND (machine learning OR AI)',      # Boolean operators
        "What is artificial intelligence?",         # Natural language question
        "How do neural networks work?",              # Reasoning question
        "API documentation version 3.0",            # Technical/acronyms
        "Why did sales increase last quarter?",     # Analytical question
        "John Smith CEO TechCorp",                   # Named entities
    ]

    print(f"\n{'Query':<40} {'Strategy':<10} {'Conf':<6} {'Reason':<30}")
    print("-" * 86)

    for query in queries:
        features = router.analyze_query(query)
        decision = router.route_query(features)

        primary_reason = decision.reasoning[0] if decision.reasoning else "Default"
        print(
            f"{query[:40]:<40} {decision.strategy.value:<10} "
            f"{decision.confidence:>5.1%} {primary_reason:<30}"
        )


def example_detailed_explanation():
    """Example: get detailed explanation of routing decision."""
    print("\n" + "=" * 60)
    print("Example 4: Detailed Routing Explanation")
    print("=" * 60)

    router = QueryRouter()

    queries = [
        "TensorFlow 2.0 vs PyTorch performance",
        "explain machine learning concepts",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 60)
        explanation = router.explain_routing_decision(query)
        print(explanation)


def example_adaptive_weights():
    """Example: demonstrate adaptive weight selection."""
    print("\n" + "=" * 60)
    print("Example 5: Adaptive Weight Selection")
    print("=" * 60)

    router = QueryRouter()

    queries = [
        ("short query", 2),              # Short, non-specific
        ("medium length informational query", 5),  # Medium, general
        ("very specific technical query with exact phrase about API endpoints", 9),  # Long, specific
    ]

    print(f"\n{'Query':<50} {'Length':<7} {'Specificity':<11} {'Weights (BM25/Semantic)'}")
    print("-" * 90)

    for query, expected_length in queries:
        features = router.analyze_query(query)
        decision = router.route_query(features)

        weights_str = (
            f"{decision.weights.bm25_weight:.1%}/{decision.weights.semantic_weight:.1%}"
        )
        print(
            f"{query:<50} {len(query):<7} {features.specificity_score:>10.2f} {weights_str:<20}"
        )


def example_cache_statistics():
    """Example: demonstrate caching and statistics."""
    print("\n" + "=" * 60)
    print("Example 6: Cache Statistics")
    print("=" * 60)

    router = QueryRouter()

    # Process some queries
    queries = [
        "machine learning basics",
        "what is AI?",
        "machine learning basics",  # Duplicate
        "API documentation",
        "what is AI?",  # Duplicate
    ] * 2  # Process twice to show caching

    print(f"\nProcessing {len(queries)} queries...")
    for query in queries:
        router.route_query(router.analyze_query(query))

    # Get statistics
    stats = router.get_cache_stats()
    print("\nCache Statistics:")
    print(f"  Cached queries: {stats['cached_queries']}")
    print(f"  BM25 routed: {stats['bm25_count']}")
    print(f"  Semantic routed: {stats['semantic_count']}")
    print(f"  Hybrid routed: {stats['hybrid_count']}")
    print(f"  Average confidence: {stats['avg_confidence']:.2%}")


def example_feature_analysis():
    """Example: deep dive into feature extraction."""
    print("\n" + "=" * 60)
    print("Example 7: Feature Analysis")
    print("=" * 60)

    router = QueryRouter()

    query = "Why did sales decrease in Q2? Analyze the revenue trends."
    print(f"\nQuery: {query}\n")

    features = router.analyze_query(query)

    print("Extracted Features:")
    print(f"  Length: {features.length} tokens")
    print(f"  Has Quotes: {features.has_quotes}")
    print(f"  Boolean Operators: {features.has_boolean_operators}")
    print(f"  Special Characters: {features.has_special_chars}")
    print(f"  Keyword Density: {features.keyword_density:.2f}")
    print(f"  Entity Count: {features.entity_count}")
    print(f"  Is Question: {features.is_question} ({features.question_type})")
    print(f"  Average Word Length: {features.avg_word_length:.2f}")
    print(f"  Contains Acronyms: {features.contains_acronyms}")
    print(f"  Contains Numbers: {features.contains_numbers}")
    print(f"  Specificity Score: {features.specificity_score:.2f}")
    print(f"  Has Temporal: {features.has_temporal}")
    print(f"  Temporal Markers: {features.temporal_markers}")
    print(f"  Has Reasoning Keywords: {features.has_reasoning_keywords}")
    print(f"  Reasoning Keywords: {features.reasoning_keywords}")


def example_retrieve_integration():
    """Example: integration with retrieve_v2 (pseudocode)."""
    print("\n" + "=" * 60)
    print("Example 8: Integration with retrieve_v2")
    print("=" * 60)

    print("""
    # Actual integration code with retrieve_v2:

    from ragstack.retrieve_v2 import search
    from llamaindex_query_router import QueryRouter

    # Initialize router
    router = QueryRouter(domain="technical")

    def smart_search(query: str, top_k: int = 10):
        '''Search with automatically optimized weights.'''
        # Get routing decision
        decision = router.route_query(router.analyze_query(query))

        # Search with optimized weights
        return search(
            query,
            top_k=top_k,
            semantic_weight=decision.weights.semantic_weight,
            keyword_weight=decision.weights.bm25_weight,
        )

    # Usage
    results = smart_search("What is the difference between API v1 and v2?")
    for hit in results:
        print(f"[{hit.score:.2f}] {hit.citation()}: {hit.text[:50]}")
    """)


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("QueryRouter Integration Examples")
    print("=" * 60)

    example_basic_routing()
    example_domain_specific_routing()
    example_diverse_queries()
    example_detailed_explanation()
    example_adaptive_weights()
    example_cache_statistics()
    example_feature_analysis()
    example_retrieve_integration()

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
