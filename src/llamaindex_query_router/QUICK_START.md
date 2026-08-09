# LlamaIndex Query Router - Quick Start Guide

## Installation

Already installed in `src/llamaindex_query_router/`

## 5-Minute Quick Start

### Basic Usage

```python
from llamaindex_query_router import QueryRouter

# Create router
router = QueryRouter(verbose=True)

# Analyze and route a query
query = "What are the best machine learning practices?"
features = router.analyze_query(query)
decision = router.route_query(features)

# Get results
print(f"Strategy: {decision.strategy.value}")
print(f"Confidence: {decision.confidence:.2%}")
print(f"Reasoning: {decision.reasoning}")
print(f"Weights: BM25={decision.weights.bm25_weight:.1%}, Semantic={decision.weights.semantic_weight:.1%}")
```

### Integration with retrieve_v2

```python
from ragstack.retrieve_v2 import search
from llamaindex_query_router import QueryRouter

router = QueryRouter(domain="technical")
query = "API documentation for v3.0"

# Get routing decision
decision = router.route_query(router.analyze_query(query))

# Search with optimized weights
results = search(
    query,
    top_k=10,
    semantic_weight=decision.weights.semantic_weight,
    keyword_weight=decision.weights.bm25_weight,
)
```

### Using the Integration Wrapper

```python
from llamaindex_query_router.retrieve_v2_integration import smart_search, routed_search

# Simple smart search
results = smart_search("machine learning basics", domain="conversational")

# With full routing details
result = routed_search(
    "API documentation",
    domain="technical",
    top_k=10,
    explain=True  # Prints routing explanation
)
print(f"Strategy: {result['strategy']}")
print(f"Confidence: {result['confidence']:.2%}")
```

## Domain Options

| Domain | Best For | BM25 % | Semantic % |
|--------|----------|--------|-----------|
| **technical** | API docs, SDKs, code | 65 | 35 |
| **conversational** | FAQs, natural language | 35 | 65 |
| **entity_search** | Names, products, places | 75 | 25 |
| **conceptual** | Why/how, explanations | 25 | 75 |

## Query Types → Strategies

| Query Type | Example | Strategy | Why |
|-----------|---------|----------|-----|
| Exact phrase | `"machine learning"` | BM25 | Exact match needed |
| Boolean | `python AND (AI OR ML)` | BM25 | Structured query |
| Acronyms | `REST API v3.0` | BM25 | Keywords critical |
| Natural question | `What is machine learning?` | Semantic | Natural language |
| Reasoning | `Explain how neural nets work` | Semantic | Concept understanding |
| General query | `machine learning` | Hybrid | Balanced approach |

## API Cheat Sheet

### QueryRouter

```python
# Create
router = QueryRouter(domain="technical", verbose=True)

# Analyze
features = router.analyze_query(query)

# Route
decision = router.route_query(features)  # Returns RoutingDecision
strategy = router.route_strategy(features)  # Returns RoutingStrategy (legacy)

# Explain
explanation = router.explain_routing_decision(query)  # Returns str
print(explanation)

# Weights
weights = router.get_weights_for_query(query)  # Returns (bm25, semantic)

# Cache
stats = router.get_cache_stats()  # Returns dict with statistics
router.clear_cache()  # Clear cached decisions
```

### RoutingDecision

```python
decision.strategy              # RoutingStrategy enum (BM25, SEMANTIC, HYBRID)
decision.confidence           # float (0.0-1.0) confidence in decision
decision.weights              # StrategyWeights with bm25_weight, semantic_weight
decision.reasoning            # List[str] of reasons for the decision
decision.alternative_strategies  # List of (strategy, score) tuples
```

### QueryFeatures

```python
features.query                # Original query string
features.length              # Token count
features.specificity_score   # 0-1 score (specific vs general)
features.keyword_density     # 0-1 keyword ratio
features.has_temporal        # Has time-related keywords
features.temporal_markers    # List of time keywords
features.has_reasoning_keywords  # Has analytical keywords
features.reasoning_keywords  # List of analytical keywords
# ... plus 11 more structural features
```

## Common Patterns

### Pattern 1: Automatic Routing
```python
from llamaindex_query_router.retrieve_v2_integration import smart_search

results = smart_search(query)  # Fully automatic
```

### Pattern 2: Domain-Specific Search
```python
router = QueryRouter(domain="technical")
for query in queries:
    decision = router.route_query(router.analyze_query(query))
    results = search(query, semantic_weight=decision.weights.semantic_weight)
```

### Pattern 3: Routing with Fallback
```python
decision = router.route_query(features)
if decision.confidence < 0.7:  # Low confidence
    # Use hybrid or manual review
    results = search(query, use_hybrid=True)
else:
    results = search(query, semantic_weight=decision.weights.semantic_weight)
```

### Pattern 4: Batch Processing
```python
from llamaindex_query_router.retrieve_v2_integration import RoutedSearcher

searcher = RoutedSearcher(domain="conversational")
for query in batch:
    result = searcher.search(query)
    # Process result.hits with result.routing_decision
```

## Performance Tips

1. **Reuse Router Instance** - Router caches decisions
   ```python
   router = QueryRouter()  # Create once
   for query in queries:
       router.route_query(router.analyze_query(query))
   ```

2. **Monitor Confidence** - Use low-confidence decisions as signals
   ```python
   if decision.confidence < 0.6:
       # May need manual review or hybrid search
   ```

3. **Use Domain Presets** - Improves accuracy for known domains
   ```python
   router = QueryRouter(domain="technical")  # vs generic
   ```

4. **Batch Operations** - Process multiple queries efficiently
   ```python
   results = searcher.batch_search(queries)
   ```

## Troubleshooting

### Problem: All queries route to HYBRID
- **Cause**: Queries are mixed/general
- **Solution**: Use domain-specific router if queries are known

### Problem: Low confidence scores
- **Cause**: Queries don't match strong patterns
- **Solution**: Use hybrid strategy as fallback, or create custom domain config

### Problem: Wrong routing decision
- **Cause**: Query features don't align with strategy
- **Solution**: Use `explain_routing_decision()` to debug, review reasoning

### Problem: Performance issues
- **Cause**: Cache not being used
- **Solution**: Reuse router instance, avoid creating new routers per query

## Files Reference

| File | Purpose | Key Classes |
|------|---------|------------|
| `feature_extractor.py` | Query analysis | `QueryFeatureExtractor`, `QueryFeatures` |
| `routing_strategies.py` | Strategy definitions | `RoutingStrategy`, `StrategyWeights`, `DomainConfig` |
| `router.py` | Main routing logic | `QueryRouter`, `RoutingDecision` |
| `retrieve_v2_integration.py` | Wrapper for retrieve_v2 | `RoutedSearcher`, convenience functions |
| `retrieve_integration_example.py` | Usage examples | 8 complete examples |
| `INTEGRATION_GUIDE.md` | Detailed guide | Architecture, API, patterns |

## Next Steps

1. Read `INTEGRATION_GUIDE.md` for detailed documentation
2. Run `retrieve_integration_example.py` to see all features
3. Start with `smart_search()` for automatic routing
4. Customize with domain configs if needed

## Support Files

- **IMPLEMENTATION_SUMMARY.md** - Technical details of implementation
- **INTEGRATION_GUIDE.md** - Complete API and architecture guide
- **QUICK_START.md** - This file
