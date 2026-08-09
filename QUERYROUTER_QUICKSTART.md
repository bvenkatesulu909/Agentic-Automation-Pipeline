# QueryRouter Quick Start Guide

## Installation

The QueryRouter package is located in `src/llamaindex_query_router/` and requires only Python 3.7+.

```bash
# No external dependencies required - uses only Python stdlib
cd src/llamaindex_query_router
```

## Basic Usage

### 1. Initialize the Router

```python
from src.llamaindex_query_router import QueryRouter

router = QueryRouter()
```

### 2. Analyze and Route a Query

```python
query = "What is machine learning?"

# Step 1: Extract features
features = router.analyze_query(query)

# Step 2: Determine routing strategy
strategy = router.route_strategy(features)

# Step 3: Get weights for hybrid strategy
bm25_weight, semantic_weight = router.get_weights(strategy)

print(f"Query: {query}")
print(f"Strategy: {strategy.value}")
print(f"Weights: BM25={bm25_weight:.0%}, Semantic={semantic_weight:.0%}")
```

**Output:**
```
Query: What is machine learning?
Strategy: semantic
Weights: BM25=0%, Semantic=100%
```

### 3. Get Routing Explanation

```python
explanation = router.explain_routing_decision(query)
print(explanation)
```

**Output:**
```
Query: 'What is machine learning?'
Strategy: SEMANTIC (semantic embedding-based search)
Reasoning: Is a what-question
```

## Integration with Retrieval

### Example: Multi-Strategy Retriever

```python
from src.llamaindex_query_router import QueryRouter, RoutingStrategy

class MultiStrategyRetriever:
    def __init__(self, bm25_engine, vector_engine):
        self.router = QueryRouter()
        self.bm25_engine = bm25_engine
        self.vector_engine = vector_engine
    
    def retrieve(self, query: str, top_k: int = 10):
        # Analyze query
        features = self.router.analyze_query(query)
        strategy = self.router.route_strategy(features)
        
        # Route to appropriate strategy
        if strategy == RoutingStrategy.BM25:
            return self.bm25_engine.retrieve(query, top_k)
        
        elif strategy == RoutingStrategy.SEMANTIC:
            return self.vector_engine.retrieve(query, top_k)
        
        elif strategy == RoutingStrategy.HYBRID:
            # Combine both strategies
            bm25_weight, semantic_weight = self.router.get_weights(strategy)
            bm25_results = self.bm25_engine.retrieve(query, top_k)
            semantic_results = self.vector_engine.retrieve(query, top_k)
            return self._combine_results(
                bm25_results, semantic_results,
                bm25_weight, semantic_weight
            )
    
    def _combine_results(self, bm25_results, semantic_results, 
                        bm25_weight, semantic_weight):
        # Combine and re-rank results based on weights
        combined = {}
        for doc in bm25_results:
            combined[doc.id] = doc.score * bm25_weight
        for doc in semantic_results:
            if doc.id in combined:
                combined[doc.id] += doc.score * semantic_weight
            else:
                combined[doc.id] = doc.score * semantic_weight
        
        # Sort by combined score
        sorted_docs = sorted(
            combined.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        return sorted_docs

# Usage
retriever = MultiStrategyRetriever(bm25_engine, vector_engine)
results = retriever.retrieve("What are transformers in NLP?")
```

## Query Examples

### Different Query Types

| Query | Type | Strategy | Why |
|-------|------|----------|-----|
| `"machine learning" AND deep learning` | Structured | BM25 | Boolean operators |
| `What is AI?` | Question | SEMANTIC | Natural language |
| `'"neural networks"'` | Exact phrase | BM25 | Quotes indicate precision |
| `How do transformers work?` | Question | SEMANTIC | Question + length > 3 |
| `NLP techniques and tools` | Technical | BM25 | Acronyms present |
| `tell me about Python frameworks` | General | HYBRID | Mixed query type |

### Testing Different Queries

```python
from src.llamaindex_query_router import QueryRouter

router = QueryRouter()

test_queries = [
    "What is artificial intelligence?",
    '"machine learning" algorithms',
    "python AND java OR rust",
    "tell me about NLP",
    "deep learning frameworks"
]

for query in test_queries:
    features = router.analyze_query(query)
    strategy = router.route_strategy(features)
    print(f"{query:40} -> {strategy.value}")
```

**Output:**
```
What is artificial intelligence?       -> semantic
"machine learning" algorithms          -> bm25
python AND java OR rust                -> bm25
tell me about NLP                       -> hybrid
deep learning frameworks                -> hybrid
```

## Advanced Features

### Verbose Mode for Debugging

```python
router = QueryRouter(verbose=True)
features = router.analyze_query("Tell me about machine learning")
strategy = router.route_strategy(features)
```

**Output:**
```
Query Features for: 'Tell me about machine learning'
  Length: 5 tokens
  Has Quotes: False
  Boolean Operators: False
  Special Chars: False
  Keyword Density: 0.60
  Entity Count: 0
  Is Question: False (tell)
  Avg Word Length: 5.40
  Acronyms: False
  Numbers: False

Routing 'Tell me about machine learning' to: semantic
```

### Cache Management

```python
router = QueryRouter()

# Route multiple queries
queries = [
    "What is AI?",
    "machine learning algorithms",
    "python frameworks"
]

for q in queries:
    features = router.analyze_query(q)
    router.route_strategy(features)

# Check cache statistics
stats = router.get_cache_stats()
print(f"Cached queries: {stats['cached_queries']}")
print(f"BM25 routes: {stats['bm25_count']}")
print(f"Semantic routes: {stats['semantic_count']}")
print(f"Hybrid routes: {stats['hybrid_count']}")

# Clear cache if needed
router.clear_cache()
```

## Testing

### Run Test Suite

```bash
# Run all tests
pytest tests/test_query_router.py -v

# Run specific test class
pytest tests/test_query_router.py::TestQueryRouter -v

# Run with coverage
pytest tests/test_query_router.py --cov=src.llamaindex_query_router
```

### Sample Test Output

```
test_query_router.py::TestQueryFeatureExtractor::test_extract_features_basic_query PASSED
test_query_router.py::TestQueryRouter::test_route_strategy_question PASSED
test_query_router.py::TestQueryRouter::test_route_strategy_quoted_phrase PASSED
test_query_router.py::TestQueryRouter::test_route_strategy_boolean_query PASSED
test_query_router.py::TestQueryRouter::test_get_weights_hybrid PASSED
...

======================== 27 passed in 0.45s ========================
```

## Running Examples

```bash
python examples/query_routing_example.py
```

This runs 6 comprehensive examples demonstrating:
1. Basic query routing
2. Routing different query types
3. Routing explanations
4. Query caching
5. Integration with retrieval
6. Detailed feature analysis

## Performance Tips

### 1. Use Caching
The router caches routing decisions by query string. For repeated queries, reuse the router instance.

```python
# Good: Reuse router instance
router = QueryRouter()
for query in query_list:
    strategy = router.route_strategy(router.analyze_query(query))

# Avoid: Creating new router for each query
for query in query_list:
    router = QueryRouter()  # Don't do this!
    strategy = router.route_strategy(router.analyze_query(query))
```

### 2. Monitor Cache Growth
For long-running applications, monitor cache size:

```python
stats = router.get_cache_stats()
if stats['cached_queries'] > 10000:
    router.clear_cache()
    print("Cache cleared")
```

### 3. Batch Analysis
Analyze multiple queries at once:

```python
queries = [q1, q2, q3, q4, q5]
strategies = []

for query in queries:
    features = router.analyze_query(query)
    strategies.append(router.route_strategy(features))
```

## Troubleshooting

### Issue: Always routing to HYBRID

**Cause**: Query doesn't match specific patterns
**Solution**: Check query features in verbose mode

```python
router = QueryRouter(verbose=True)
features = router.analyze_query("your query")
```

### Issue: Cache not working

**Cause**: Creating new router instances
**Solution**: Reuse the same router instance

```python
# Correct
router = QueryRouter()
for query in queries:
    router.analyze_query(query)

# Incorrect
for query in queries:
    router = QueryRouter()  # New instance loses cache!
    router.analyze_query(query)
```

## Next Steps

1. **Explore Examples**: See `examples/query_routing_example.py`
2. **Read Docs**: See `docs/QUERY_ROUTER_CONTRIBUTION.md`
3. **Run Tests**: Execute `pytest tests/test_query_router.py -v`
4. **Integrate**: Use the router in your RAG pipeline

## API Reference

### QueryRouter

```python
class QueryRouter:
    def __init__(self, verbose: bool = False)
    def analyze_query(query: str) -> QueryFeatures
    def route_strategy(features: QueryFeatures) -> RoutingStrategy
    def get_weights(strategy: RoutingStrategy) -> Tuple[float, float]
    def explain_routing_decision(query: str) -> str
    def clear_cache() -> None
    def get_cache_stats() -> Dict[str, int]
```

### RoutingStrategy

```python
class RoutingStrategy(Enum):
    BM25 = "bm25"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
```

### QueryFeatures

```python
@dataclass
class QueryFeatures:
    query: str
    length: int
    has_quotes: bool
    has_boolean_operators: bool
    has_special_chars: bool
    keyword_density: float
    entity_count: int
    is_question: bool
    question_type: str
    avg_word_length: float
    contains_acronyms: bool
    contains_numbers: bool
```

## Support

For issues or questions, refer to:
- `docs/QUERY_ROUTER_CONTRIBUTION.md` - Full documentation
- `examples/query_routing_example.py` - Usage examples
- `tests/test_query_router.py` - Test cases showing usage patterns
