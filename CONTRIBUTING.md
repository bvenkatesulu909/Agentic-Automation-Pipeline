# Contributing to RAGStack & CrewAI Observability

Thank you for your interest in contributing to the RAGStack and CrewAI observability tools! This document provides guidelines and instructions for contributing to all components, including QueryRouter and Tool Tracer.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
  - [QueryRouter Contributions](#queryrouter-contributions)
  - [Tool Tracer Contributions](#tool-tracer-contributions)
- [Testing](#testing)
- [Code Style](#code-style)
- [Documentation](#documentation)
- [Submitting Changes](#submitting-changes)
- [Commit Message Guidelines](#commit-message-guidelines)

---

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please:

- Be respectful and constructive in all interactions
- Welcome diverse perspectives and experiences
- Focus on what is best for the community
- Show empathy towards other community members

---

## Getting Started

### Prerequisites

- Python 3.9+
- Git
- pip (Python package manager)
- Virtual environment tool (venv or conda)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ragstack.git
   cd ragstack
   ```
3. Add upstream remote:
   ```bash
   git remote add upstream https://github.com/original-repo/ragstack.git
   ```

### Create a Branch

Always create a feature branch for your work:

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
# or
git checkout -b docs/your-docs-update
```

Branch naming conventions:
- `feature/` - New features or enhancements
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test additions or improvements
- `chore/` - Maintenance tasks

---

## Development Setup

### Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -e ".[dev,test,router]"
```

This installs:
- Core package in editable mode
- Development tools (black, flake8, mypy)
- Testing framework (pytest)
- Router-specific dependencies

### Verify Setup

```bash
pytest tests/test_query_router.py::TestQueryRouter::test_router_initialization -v
```

---

## Making Changes

### Areas for Contribution

#### 1. Feature Extraction (`src/ragstack/router.py`)

Adding new query characteristics:

```python
# Add field to QueryFeatures dataclass
@dataclass
class QueryFeatures:
    # ... existing fields ...
    your_new_feature: bool = False  # Document what this detects

# Add extraction logic to ComplexityEstimator.estimate()
def estimate(self, question: str, context_chars: int = 0) -> int:
    # ... existing logic ...
    
    # Your feature detection (0-N points)
    if your_feature_detected(question):
        score += points_for_feature
    
    return min(100, score)

# Add tests
def test_extract_features_your_feature(self):
    query = "Query with your feature"
    features = self.extractor.extract_features(query)
    assert features.your_new_feature is True
```

#### 2. Routing Logic

Extending the routing decision tree:

```python
# Add new routing rule
# Example: Route queries with "urgent" keyword to expensive tier

def route(self, question: str, context_chars: int = 0) -> RoutingDecision:
    complexity = self.estimator.estimate(question, context_chars)
    
    # NEW: Check for urgency keywords
    if "urgent" in question.lower() or "critical" in question.lower():
        tier = ModelTier.EXPENSIVE
        reason = "Urgent/critical query requires premium model"
    elif complexity < self.config.cheap_threshold:
        # ... existing logic
```

**Guidelines:**
- Document the rule and its rationale
- Add unit tests covering the new rule
- Include edge cases in tests
- Update routing decision explanations
- Benchmark performance impact

#### 3. Model Configuration

Adding new models:

```python
from src.ragstack.router import ModelConfig, ModelTier, RouterConfig

# Update preset functions or create custom config
new_model = ModelConfig(
    name="gpt-4o-mini",
    tier=ModelTier.CHEAP,
    cost_per_1k_input=0.00015,
    cost_per_1k_output=0.00060,
    description="Cost-effective model for basic tasks",
    max_input_tokens=128000,
)

config = RouterConfig(
    cheap_models=[new_model],
    medium_models=[...],
    expensive_models=[...],
)
```

**Guidelines:**
- Verify cost data from official sources
- Include model max_input_tokens
- Add to appropriate tier based on cost/quality
- Update benchmarks with new model data
- Document any special handling needed

#### 4. Metrics and Monitoring

Adding new metrics:

```python
from src.ragstack.metrics import MetricHistogram, MetricsCollector

# In MetricsCollector.__init__:
self.your_new_metric = MetricHistogram(
    "ragstack_your_metric_name",
    "Human-readable description",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0],
)

# Recording the metric
collector.your_new_metric.observe(value)

# In get_metrics_text():
lines.append(self.your_new_metric.to_prometheus())
```

**Guidelines:**
- Use Prometheus naming conventions
- Choose appropriate metric type (Counter/Gauge/Histogram)
- Document metric purpose and range
- Add tests for metric collection
- Include in Prometheus export

#### 5. Documentation

Updating documentation:

```markdown
# In docs/QUERY_ROUTER_CONTRIBUTION.md

## Your Feature Section

Brief description of what your feature does.

### Usage

```python
# Example code showing the feature
```

### Performance

Benchmark data or performance characteristics.

### Testing

How to test the feature.
```

**Guidelines:**
- Clear, concise explanations
- Working code examples
- Performance benchmarks where applicable
- Links to related concepts
- Update table of contents if needed

---

## Tool Tracer Contributions

### Areas for Contribution

#### 1. Core Tracer Enhancements (`src/crewai_tool_tracer/tracer.py`)

Adding new observability features to ToolExecutionTracer:

```python
# Add new metric to ToolMetrics dataclass
@dataclass
class ToolMetrics:
    # ... existing fields ...
    your_new_metric: float = 0.0  # Document what this tracks

# Add calculation logic to get_tool_metrics()
def get_tool_metrics(self, ...):
    metrics = ToolMetrics()
    # ... existing logic ...
    
    # Your new metric calculation
    metrics.your_new_metric = self._calculate_metric(filtered_spans)
    
    return metrics

# Add tests
def test_your_new_metric(self):
    tracer = ToolExecutionTracer()
    # Create spans...
    metrics = tracer.get_tool_metrics()
    assert metrics.your_new_metric > 0
```

#### 2. Async Support Enhancements (`src/crewai_tool_tracer/async_tracer.py`)

Extending async tracing capabilities:

```python
# Add new async tracing feature
async def trace_parallel_tools(
    self,
    tools: List[Callable],
    tool_names: List[str],
    agent_name: str,
    task_name: str,
) -> List[str]:
    """Trace multiple concurrent tool executions."""
    span_ids = []
    tasks = []
    
    for tool, tool_name in zip(tools, tool_names):
        span_id = await self.trace_async_tool_call(
            tool_name=tool_name,
            input_data={},
            agent_name=agent_name,
            task_name=task_name,
        )
        span_ids.append(span_id)
        tasks.append(tool())
    
    results = await asyncio.gather(*tasks)
    # Record results...
    return span_ids

# Test async behavior
@pytest.mark.asyncio
async def test_parallel_tracing():
    tracer = AsyncToolExecutionTracer()
    # Your test here
```

**Guidelines:**
- Preserve context across async boundaries
- Handle task cancellation gracefully
- Test with multiple concurrent operations
- Document context propagation strategy

#### 3. New Exporters (`src/crewai_tool_tracer/exporters.py`)

Adding support for new observability backends:

```python
from src.crewai_tool_tracer.tracer import BaseExporter, ToolSpan

class NewBackendExporter(BaseExporter):
    """Export spans to NewBackend platform."""
    
    def __init__(self, api_key: str, endpoint: Optional[str] = None):
        self.api_key = api_key
        self.endpoint = endpoint or "https://api.newbackend.com"
    
    def export(self, spans: List[ToolSpan]) -> bool:
        """Export spans to NewBackend."""
        try:
            data = self._convert_spans(spans)
            response = requests.post(
                f"{self.endpoint}/traces",
                json=data,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Export to NewBackend failed: {e}")
            return False
    
    def _convert_spans(self, spans: List[ToolSpan]) -> Dict[str, Any]:
        """Convert ToolSpan to NewBackend format."""
        return {
            "traces": [
                {
                    "id": span.span_id,
                    "name": span.tool_name,
                    "duration": span.duration_ms,
                    "status": span.status.value,
                    "metadata": span.metadata,
                }
                for span in spans
            ]
        }

# Add tests
def test_new_backend_exporter():
    exporter = NewBackendExporter(api_key="test_key")
    spans = [create_test_span()]
    assert exporter.export(spans) is True
```

**Guidelines:**
- Inherit from `BaseExporter`
- Handle API errors gracefully
- Support batch export
- Add authentication via env vars
- Include timeout handling
- Write comprehensive tests

#### 4. Chain Tracking Enhancements (`src/crewai_tool_tracer/async_tracer.py`)

Improving tool dependency tracking:

```python
# Add new chain analysis methods
def get_critical_path(self, chain: List[str]) -> Dict[str, Any]:
    """Get critical path (slowest sequential path) in execution chain."""
    spans = [self.tracer.get_span(sid) for sid in chain]
    # Calculate critical path...
    return {"path": [...], "duration_ms": total}

def get_tool_dependencies(self, tool_name: str) -> Set[str]:
    """Get tools that depend on this tool."""
    dependencies = set()
    for span in self.tracer.get_all_spans():
        if span.metadata.get("parent_tool") == tool_name:
            dependencies.add(span.tool_name)
    return dependencies

# Test dependency tracking
def test_critical_path_analysis():
    tracker = ToolChainTracker(tracer)
    chain = [span1_id, span2_id, span3_id]
    analysis = tracker.analyze_chain_metrics(chain)
    assert "bottleneck_tool" in analysis
```

#### 5. Structured Logging Enhancements

Extending JSON logging capabilities:

```python
# Add new log event types
def log_tool_timeout(
    self,
    tool_name: str,
    span_id: str,
    timeout_ms: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log tool execution timeout."""
    self._log_event(
        event_type="tool.timeout",
        properties={
            "tool_name": tool_name,
            "span_id": span_id,
            "timeout_ms": timeout_ms,
            **metadata,
        },
    )

def log_metric_observation(
    self,
    metric_name: str,
    value: float,
    agent_name: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log custom metric observation."""
    self._log_event(
        event_type="metric.observation",
        properties={
            "metric_name": metric_name,
            "value": value,
            "agent_name": agent_name,
            **metadata,
        },
    )
```

#### 6. Performance Optimization

Improving tracer efficiency:

```python
# Add result caching for frequently accessed metrics
from functools import lru_cache

class CachedToolExecutionTracer(ToolExecutionTracer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metrics_cache = {}
        self._cache_timestamp = None
    
    def get_tool_metrics(self, **filters) -> ToolMetrics:
        """Get metrics with caching."""
        cache_key = hash(frozenset(filters.items()))
        
        # Return cached result if fresh (< 1 second old)
        if (cache_key in self._metrics_cache and 
            time.time() - self._cache_timestamp < 1.0):
            return self._metrics_cache[cache_key]
        
        # Calculate fresh metrics
        metrics = super().get_tool_metrics(**filters)
        self._metrics_cache[cache_key] = metrics
        self._cache_timestamp = time.time()
        
        return metrics
```

**Guidelines:**
- Profile before optimizing
- Maintain backward compatibility
- Add benchmarks to test suite
- Document performance impact

---

## Testing

### Running Tests

#### QueryRouter Tests

```bash
# Run all tests
pytest tests/test_query_router.py -v

# Run specific test class
pytest tests/test_query_router.py::TestQueryRouter -v

# Run specific test
pytest tests/test_query_router.py::TestQueryRouter::test_router_initialization -v

# Run with coverage
pytest tests/test_query_router.py --cov=src.ragstack.router --cov-report=html

# Run benchmarks
pytest tests/test_query_router.py::TestBenchmarks -v
```

#### Tool Tracer Tests

```bash
# Run all Tool Tracer tests
pytest src/crewai_tool_tracer/tests/test_tracer.py -v

# Run specific test class
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolExecutionTracer -v

# Run with coverage
pytest src/crewai_tool_tracer/tests/ --cov=src.crewai_tool_tracer --cov-report=html

# Run async tests
pytest src/crewai_tool_tracer/tests/test_tracer.py -v -k async
```

### Writing Tests

#### Test Structure

```python
import pytest
from src.ragstack.router import QueryRouter, RoutingStrategy

class TestYourFeature:
    """Test your new feature."""
    
    def setup_method(self):
        """Set up before each test."""
        self.router = QueryRouter()
    
    def test_feature_basic(self):
        """Test basic functionality."""
        query = "Test query"
        result = self.router.analyze_query(query)
        assert result is not None
    
    def test_feature_edge_case(self):
        """Test edge cases."""
        query = ""  # Empty
        result = self.router.analyze_query(query)
        assert result.length == 0
    
    def test_feature_performance(self):
        """Test performance characteristics."""
        import time
        query = "Long query " * 100
        start = time.time()
        self.router.analyze_query(query)
        elapsed = time.time() - start
        assert elapsed < 0.01  # Should be fast
```

#### Test Coverage Requirements

- All new functions/methods must have unit tests
- Test both happy path and edge cases
- Test error conditions and validations
- Aim for >80% code coverage
- Performance tests for critical paths

```bash
# Check coverage
pytest tests/test_query_router.py --cov=src.ragstack.router --cov-report=term-missing
```

### Integration Tests

```python
def test_end_to_end_routing(self):
    """Test complete routing pipeline."""
    router = QueryRouter()
    
    query = "What is machine learning?"
    features = router.analyze_query(query)
    strategy = router.route_strategy(features)
    weights = router.get_weights(strategy)
    explanation = router.explain_routing_decision(query)
    
    # Verify complete pipeline works
    assert features.query == query
    assert isinstance(strategy, RoutingStrategy)
    assert len(weights) == 2
    assert query in explanation
```

---

## Code Style

### Style Guide

We follow PEP 8 with some customizations:

```python
# Use type hints
def analyze_query(query: str) -> QueryFeatures:
    """Analyze a query and extract features.
    
    Args:
        query: The user's query string
        
    Returns:
        QueryFeatures with extracted characteristics
        
    Raises:
        ValueError: If query is None
    """
    if query is None:
        raise ValueError("query cannot be None")
    
    return QueryFeatures(...)

# Use dataclasses for data structures
@dataclass
class QueryFeatures:
    query: str
    length: int
    # ...

# Use enums for fixed sets of values
class RoutingStrategy(Enum):
    BM25 = "bm25"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"

# Document complex logic with comments
# When calculating complexity, we weight:
# - Question length (more complex for longer)
# - Keywords (more complex for more keywords)
# - Context size (more complex with more context)
score = calculate_score(...)
```

### Code Formatting

```bash
# Format code with black
black src/ragstack/router.py tests/

# Sort imports with isort
isort src/ragstack/router.py tests/

# Check code style
flake8 src/ragstack/router.py

# Type checking
mypy src/ragstack/router.py
```

### Line Length

- Maximum line length: 88 characters (Black default)
- Break long lines logically:

```python
# Good
decision = RoutingDecision(
    model=selected_model,
    complexity_score=score,
    estimated_cost=cost,
    reason=reasoning,
)

# Avoid
decision = RoutingDecision(model=selected_model, complexity_score=score, estimated_cost=cost, reason=reasoning)
```

### Naming Conventions

```python
# Classes: PascalCase
class QueryRouter:
    pass

# Functions/methods: snake_case
def analyze_query(query: str) -> QueryFeatures:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_QUERY_LENGTH = 1000
DEFAULT_COMPLEXITY_THRESHOLD = 50

# Private/internal: leading underscore
def _internal_helper():
    pass
```

---

## Documentation

### Docstring Format

Use Google-style docstrings:

```python
def route_query(
    self,
    question: str,
    context_chars: int = 0,
) -> RoutingDecision:
    """Route a question to an appropriate model.
    
    Analyzes query complexity and selects the best-fitting
    model tier based on complexity thresholds and available
    models.
    
    Args:
        question: The user's question string
        context_chars: Size of retrieved context in characters
        
    Returns:
        RoutingDecision containing selected model, complexity
        score, estimated cost, and reasoning
        
    Raises:
        ValueError: If question is empty
        
    Examples:
        >>> router = ModelRouter(preset_anthropic_only())
        >>> decision = router.route("What is 2+2?")
        >>> print(decision.model.name)
        claude-3-5-haiku-20241022
    """
```

### Inline Comments

Use for complex logic:

```python
# Calculate complexity score with weighted factors:
# - Length (0-30 points): More words = more complex
# - Keywords (0-40 points): Reasoning words = more complex
# - Context (0-20 points): More context = more complex
score = (length_score * 0.3 + 
         keyword_score * 0.4 + 
         context_score * 0.3)
```

### README/Main Documentation

When updating main documentation:

1. Keep examples working and up-to-date
2. Include expected output for code examples
3. Add cross-references to related sections
4. Update table of contents
5. Verify links are correct

---

## Submitting Changes

### Before Submitting

1. **Run tests:**
   ```bash
   pytest tests/test_query_router.py -v
   ```

2. **Check code style:**
   ```bash
   black src/ragstack/router.py tests/
   isort src/ragstack/router.py tests/
   flake8 src/ragstack/router.py
   ```

3. **Run type checking:**
   ```bash
   mypy src/ragstack/router.py
   ```

4. **Check coverage:**
   ```bash
   pytest tests/test_query_router.py --cov=src.ragstack.router
   ```

5. **Update documentation:**
   - Add docstrings to new functions
   - Update QUERY_ROUTER_CONTRIBUTION.md if needed
   - Add examples to docstrings

### Create a Pull Request

1. **Push your branch:**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create PR on GitHub:**
   - Give it a descriptive title
   - Reference any related issues (#123)
   - Describe changes in detail
   - Include before/after examples if applicable

3. **PR Template:**
   ```markdown
   ## Description
   Brief description of changes
   
   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Documentation update
   - [ ] Performance improvement
   
   ## Related Issues
   Closes #123
   
   ## Testing
   How to test these changes
   
   ## Performance Impact
   Benchmark results if applicable
   
   ## Checklist
   - [ ] Tests added/updated
   - [ ] Documentation updated
   - [ ] Code follows style guide
   - [ ] No breaking changes
   ```

### Review Process

1. Wait for code review from maintainers
2. Respond to review comments
3. Push updates to your branch (no force push)
4. Request review again if requested
5. Merge once approved

---

## Commit Message Guidelines

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type

- `feat:` A new feature
- `fix:` A bug fix
- `docs:` Documentation only changes
- `style:` Changes that don't affect code meaning
- `refactor:` Code change that neither fixes bug nor adds feature
- `perf:` Code change that improves performance
- `test:` Adding missing or correcting tests
- `chore:` Changes to build process or dependencies

### Scope

Component being changed:
- `router` - Routing logic
- `metrics` - Metrics/monitoring
- `features` - Feature extraction
- `tests` - Test suite

### Subject

- Use imperative mood ("add feature" not "added feature")
- Don't capitalize first letter
- No period at the end
- Limit to 50 characters

### Body

- Explain what and why, not how
- Wrap at 72 characters
- Use bullet points where appropriate

### Footer

Link to related issues:
```
Closes #123
Fixes #456
```

### Examples

```
feat(router): add urgency-based routing for critical queries

Add detection of urgent/critical keywords in queries and
automatically route them to the expensive tier for better quality.

Closes #456

---

fix(metrics): correct cost calculation for hybrid models

Fixed bug where hybrid model costs were calculated twice,
leading to inflated cost estimates.

Fixes #123

---

docs(router): update integration guide with retrieve_v2 example

Add complete integration example showing how to use QueryRouter
with the retrieve_v2 function for end-to-end RAG.

---

perf(router): cache routing decisions for identical queries

Implement LRU cache for routing decisions to reduce latency
on repeated queries by 99%.
```

---

## Questions or Need Help?

- Open an issue on GitHub
- Check existing issues for similar questions
- Review existing code and tests
- Ask in pull request comments

---

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes for significant changes
- Given credit in documentation

---

Thank you for contributing! Your work helps make QueryRouter better for everyone.
