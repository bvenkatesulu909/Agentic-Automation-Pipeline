"""Examples: Using the production vector database at scale.

Run with: python -m ragstack.scale_examples
"""

from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

# Example 1: Basic Setup
def example_basic_search():
    """Simple semantic search with caching."""
    from retrieve_v2 import search, cache_stats

    print("=" * 60)
    print("Example 1: Basic Semantic Search")
    print("=" * 60)

    queries = [
        "How much does enterprise pricing cost?",
        "What's the annual license price?",
        "How much does enterprise pricing cost?",  # Cached
    ]

    for q in queries:
        print(f"\nQuery: {q}")
        hits = search(q, top_k=3)
        for hit in hits:
            print(f"  [{hit.score:.2f}] {hit.citation()}")

    print("\nCache Stats:", cache_stats())


# Example 2: Hybrid Search
def example_hybrid_search():
    """Combine semantic and keyword matching."""
    from retrieve_v2 import search, SearchConfig

    print("\n" + "=" * 60)
    print("Example 2: Hybrid Search (Semantic + Keyword)")
    print("=" * 60)

    query = "discount for non-profit organizations"

    print(f"\nQuery: {query}\n")

    print("Semantic-only (0.95 weight):")
    semantic_results = search(query, use_hybrid=False)
    for hit in semantic_results[:3]:
        print(f"  [{hit.score:.2f}] {hit.text[:60]}")

    print("\nKeyword-only (0.95 keyword weight):")
    keyword_results = search(
        query,
        semantic_weight=0.05,
        keyword_weight=0.95,
    )
    for hit in keyword_results[:3]:
        print(f"  [{hit.score:.2f}] {hit.text[:60]}")

    print("\nBalanced hybrid (0.6/0.4):")
    hybrid_config = SearchConfig(
        semantic_weight=0.6,
        keyword_weight=0.4,
        top_k=5,
    )
    from retrieve_v2 import search_with_config
    hybrid_results = search_with_config(query, hybrid_config)
    for hit in hybrid_results[:3]:
        print(f"  [{hit.score:.2f}] {hit.text[:60]}")


# Example 3: Metadata Filtering
def example_metadata_filtering():
    """Filter by document source and chunk properties."""
    from retrieve_v2 import search, store_stats

    print("\n" + "=" * 60)
    print("Example 3: Metadata Filtering")
    print("=" * 60)

    print("\nStore Statistics:")
    stats = store_stats()
    print(f"Total chunks: {stats['total_chunks']}")
    print(f"Sources: {stats['sources']}")

    query = "pricing"

    # Filter by source
    print(f"\nSearch in specific source:")
    for source in list(stats['sources'].keys())[:2]:
        print(f"\n  Source: {source}")
        hits = search(query, filters={"source": source}, top_k=2)
        for hit in hits:
            print(f"    [{hit.score:.2f}] {hit.text[:50]}")

    # Filter by size
    print(f"\nSearch with size filter (200-1000 chars):")
    hits = search(
        query,
        filters={"chars": {"$gte": 200, "$lte": 1000}},
        top_k=3,
    )
    for hit in hits:
        print(f"  [{hit.score:.2f}] {len(hit.text)} chars: {hit.text[:40]}")


# Example 4: Search Presets
def example_search_presets():
    """Use SearchConfig presets for common scenarios."""
    from retrieve_v2 import search_with_config, SearchConfig

    print("\n" + "=" * 60)
    print("Example 4: Search Configuration Presets")
    print("=" * 60)

    query = "annual licensing and enterprise discounts"

    configs = {
        "Sales Query": SearchConfig.for_sales_query(),
        "Exact Match": SearchConfig.for_exact_match(),
        "Semantic Only": SearchConfig.for_semantic(),
    }

    for name, config in configs.items():
        print(f"\n{name}:")
        print(f"  Weights: semantic={config.semantic_weight}, keyword={config.keyword_weight}")
        print(f"  Settings: top_k={config.top_k}, min_score={config.min_score}")

        hits = search_with_config(query, config)
        for hit in hits[:2]:
            print(f"    [{hit.score:.2f}] {hit.text[:50]}")


# Example 5: Backup Management
def example_backups():
    """Create, list, and restore backups."""
    from retrieve_v2 import (
        create_backup,
        restore_backup,
        list_backups,
        search,
    )

    print("\n" + "=" * 60)
    print("Example 5: Backup & Recovery")
    print("=" * 60)

    # List existing backups
    backups = list_backups()
    print(f"\nAvailable backups: {len(backups)}")
    for b in backups[:3]:
        print(f"  {b['name']}: {b['points']} points, {b['size_mb']} MB")

    # Create a new backup
    print("\nCreating backup...")
    backup_path = create_backup("example-snapshot")
    print(f"  Created: {backup_path}")

    # Search after backup
    hits = search("pricing", top_k=2)
    print(f"\nSearched after backup: {len(hits)} results")

    # In production, restore with: restore_backup("example-snapshot")


# Example 6: Advanced Scenarios
def example_advanced():
    """Advanced usage patterns."""
    from retrieve_v2 import search, format_context

    print("\n" + "=" * 60)
    print("Example 6: Advanced Scenarios")
    print("=" * 60)

    # Multi-filter search
    print("\nScenario 1: Multi-filter search")
    hits = search(
        "pricing tiers",
        filters={
            "source": "pricing-guide.md",
            "chars": {"$gte": 100},
        },
        top_k=5,
    )
    print(f"Results: {len(hits)} hits")

    # Generate formatted context for LLM
    print("\nScenario 2: Format results for LLM context")
    context = format_context(hits)
    print(context[:200] + "...\n")

    # Search with custom weights
    print("Scenario 3: Custom hybrid weights for specific query type")
    hits = search(
        "non-profit discount program",
        semantic_weight=0.5,
        keyword_weight=0.5,
        top_k=10,
    )
    print(f"Results: {len(hits)} hits with balanced weights")


# Example 7: Cache Management
def example_cache_management():
    """Monitor and manage the embedding cache."""
    from retrieve_v2 import cache_stats, clear_embedding_cache, search
    from embedding_cache import get_cache

    print("\n" + "=" * 60)
    print("Example 7: Embedding Cache Management")
    print("=" * 60)

    # Warm up cache with common queries
    print("\nWarming cache with common sales queries...")
    common_queries = [
        "pricing",
        "annual license",
        "enterprise discount",
        "non-profit pricing",
    ]

    for q in common_queries:
        search(q, top_k=2)

    # Show stats
    stats = cache_stats()
    print(f"\nCache Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Save cache to disk
    print("\nSaving cache to disk...")
    cache = get_cache()
    cache.save()
    print("  Done. Cache persists across sessions.")

    # Clear if needed
    print("\nClearing cache (next queries will re-embed)...")
    clear_embedding_cache()
    print("  Cache cleared.")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Vector Database at Scale: Examples")
    print("=" * 60)

    try:
        example_basic_search()
        example_hybrid_search()
        example_metadata_filtering()
        example_search_presets()
        example_backups()
        example_advanced()
        example_cache_management()

        print("\n" + "=" * 60)
        print("All examples completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
