# LlamaIndex Query Router - Integration Guide

## Overview

The QueryRouter provides intelligent query analysis and routing to optimal retrieval strategies (BM25, semantic, or hybrid search). It integrates seamlessly with the `retrieve_v2.py` module to automatically select the best search weights based on query characteristics.

## Features

- **Intelligent Feature Extraction**: Analyzes query specificity, temporal markers, reasoning keywords, and structural patterns
- **Decision Tree-Based Routing**: Uses multi-criteria scoring to determine optimal strategy
- **Confidence Scoring**: Returns confidence levels with routing decisions
- **Domain-Specific Customization**: Pre-configured domains for technical, conversational, entity, and conceptual queries
- **Transparent Explanations**: Provides human-readable reasoning for routing decisions
- **Performance Caching**: Caches routing decisions for repeated queries

## Architecture

### Query Features

The router extracts the following features from queries:

1. **Structural Patterns**
   - Exact phrases (quoted text)
   - Boolean operators (AND/OR/NOT)
   - Special characters
   - Acronyms
   - Numerical values

2. **Linguistic Characteristics**
   - Query length (token count)
   - Keyword density
   - Entity count (proper nouns)
   - Question type (what/how/why/when/where)
   - Average word length

3. **Advanced Features**
   - **Specificity Score**: 0-1 indicating how specific/targeted the query is
   - **Temporal Markers**: Time-related keywords (dates, time expressions)
   - **Reasoning Keywords**: Analytical intent (explain, analyze, compare, etc.)

### Routing Strategies

1. **BM25**: Keyword-based lexical search
   - Best for: Exact phrases, acronyms, technical terms, product names
   - Speed: Fast
   - Recall: Good for structured queries

2. **Semantic**: Dense embedding-based search
   - Best for: Natural language questions, conceptual matching, paraphrasing
   - Speed: Slower (requires embedding)
   - Recall: Good for semantic similarity

3. **Hybrid**: Combined BM25 + semantic search
   - Best for: General queries, mixed patterns, robust coverage
   - Customizable weights for different domains

## Integration with retrieve_v2.py

### Basic Usage

```python
from ragstack.retrieve_v2 import search
from llamaindex_query_router import QueryRouter

# Initialize router
router = QueryRouter(verbose=True)

# Analyze query and get weights
query = "What are the best practices for machine learning?"
features = router.analyze_query(query)
decision = router.route_query(features)

bm25_weight, semantic_weight = decision.weights.bm25_weight, decision.weights.semantic_weight

# Use optimal weights for search
results = search(
    query,
    top_k=5,
    semantic_weight=semantic_weight,
    keyword_weight=bm25_weight,
)

# Print routing explanation
print(router.explain_routing_decision(query))
```

### Domain-Specific Routing

```python
# Create router for technical domain
router_technical = QueryRouter(domain="technical")

# For conversational queries
router_conversational = QueryRouter(domain="conversational")

# Available domains: technical, conversational, entity_search, conceptual
```

### Custom Domain Configuration

```python
from llamaindex_query_router import QueryRouter, create_domain_config

custom_config = create_domain_config(
    name="medical",
    description="Medical/healthcare domain",
    bm25_weight=0.7,
    semantic_weight=0.3,
    threshold_specificity=0.65,
    enable_temporal_boost=False,
)

router_medical = QueryRouter(domain_config=custom_config)
```

## API Reference

### QueryRouter

```python
class QueryRouter:
    def __init__(
        self,
        verbose: bool = False,
        domain: str | None = None,
        domain_config: DomainConfig | None = None,
    )
```

#### Methods

- `analyze_query(query: str) -> QueryFeatures`: Extract features from query
- `route_query(features: QueryFeatures) -> RoutingDecision`: Get routing decision with confidence
- `route_strategy(features: QueryFeatures) -> RoutingStrategy`: Get strategy only (backward compatible)
- `get_weights_for_query(query: str) -> tuple[float, float]`: Get (bm25_weight, semantic_weight)
- `explain_routing_decision(query: str) -> str`: Get human-readable explanation
- `clear_cache()`: Clear cached routing decisions
- `get_cache_stats() -> dict`: Get cache statistics

### RoutingDecision

```python
@dataclass
class RoutingDecision:
    strategy: RoutingStrategy          # Selected strategy
    confidence: float                  # 0.0-1.0 confidence score
    weights: StrategyWeights           # Weights for hybrid strategy
    reasoning: list[str]               # Reasons for decision
    alternative_strategies: list[...]  # Alternative strategies considered
```

## Advanced Examples

### Example 1: Intelligent Search with Routing

```python
from ragstack.retrieve_v2 import search
from llamaindex_query_router import QueryRouter

router = QueryRouter(verbose=True)

queries = [
    "What is machine learning?",
    "exact phrase search",
    "API AND (documentation OR examples)",
    "Compare Python vs JavaScript",
]

for query in queries:
    print(f"\nQuery: {query}")
    
    # Get routing decision
    decision = router.route_query(router.analyze_query(query))
    
    # Perform search with optimized weights
    results = search(
        query,
        top_k=5,
        semantic_weight=decision.weights.semantic_weight,
        keyword_weight=decision.weights.bm25_weight,
    )
    
    print(f"Strategy: {decision.strategy.value}")
    print(f"Confidence: {decision.confidence:.2%}")
    print(f"Results: {len(results)} hits")
```

### Example 2: Domain-Specific Routing

```python
from ragstack.retrieve_v2 import search
from llamaindex_query_router import QueryRouter

# Technical domain for API/SDK documentation
router_tech = QueryRouter(domain="technical")

# Conversational domain for general questions
router_conv = QueryRouter(domain="conversational")

def smart_search(query: str) -> list:
    # Decide which router to use
    if any(term in query.lower() for term in ["api", "sdk", "version", "documentation"]):
        router = router_tech
    else:
        router = router_conv
    
    # Get optimized weights
    bm25_w, semantic_w = router.get_weights_for_query(query)
    
    # Search with optimized weights
    return search(
        query,
        top_k=10,
        semantic_weight=semantic_w,
        keyword_weight=bm25_w,
    )
```

### Example 3: Monitoring Routing Decisions

```python
from llamaindex_query_router import QueryRouter

router = QueryRouter()

# Process batch of queries
queries = ["query1", "query2", "query3", ...]

for query in queries:
    decision = router.route_query(router.analyze_query(query))
    
# Get cache statistics
stats = router.get_cache_stats()
print(f"Cached queries: {stats['cached_queries']}")
print(f"BM25: {stats['bm25_count']}")
print(f"Semantic: {stats['semantic_count']}")
print(f"Hybrid: {stats['hybrid_count']}")
print(f"Avg confidence: {stats['avg_confidence']:.2%}")
```

## Routing Decision Tree

The router uses a multi-criteria decision tree:

```
Query Features
    |
    ├─ Score BM25 suitability
    │   ├─ Exact phrases: +0.25
    │   ├─ Boolean operators: +0.20
    │   ├─ Acronyms: +0.15
    │   ├─ High specificity: +0.10
    │   └─ High keyword density: +0.05
    |
    ├─ Score Semantic suitability
    │   ├─ Natural language question: +0.25
    │   ├─ Reasoning keywords: +0.20
    │   ├─ Good query length: +0.15
    │   ├─ Low keyword density: +0.15
    │   └─ No structured patterns: +0.10
    |
    └─ Score Hybrid suitability
        ├─ Mixed characteristics: +0.20
        ├─ Balanced specificity: +0.15
        ├─ Balanced keyword density: +0.15
        └─ No strong indicators: +0.25
```

## Best Practices

1. **Use Domain Configurations**: Select appropriate domain for your use case
2. **Monitor Confidence Scores**: Use confidence < 0.7 as a signal to review results
3. **Cache Results**: Leverage query caching for repeated queries
4. **Explain Decisions**: Use explanations for debugging and monitoring
5. **Tune Weights**: For specialized domains, create custom configurations

## Performance Considerations

- Feature extraction: ~1-2ms per query
- Routing decision: <1ms (decision tree scoring)
- Caching: O(1) lookup for cached queries
- Memory: ~100 bytes per cached query

## Troubleshooting

### Low Confidence Scores

If confidence is consistently low (<0.6), consider:
- Using a specific domain configuration
- Reviewing query patterns in your dataset
- Creating a custom domain configuration

### Unexpected Routing

To debug routing decisions:
```python
router = QueryRouter(verbose=True)
router.explain_routing_decision("your query here")
```

### Domain Recommendations

- **Technical**: API docs, SDK guides, technical specifications
- **Conversational**: FAQs, general questions, exploratory queries
- **Entity Search**: People, products, places, specific entities
- **Conceptual**: Why/how questions, explanations, analysis requests
