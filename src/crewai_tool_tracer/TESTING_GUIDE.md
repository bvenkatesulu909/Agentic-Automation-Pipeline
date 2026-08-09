# CrewAI Tool Tracer - Testing and Benchmarks Guide

Complete guide for running tests, benchmarks, and examples for the CrewAI Tool Tracer.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Running Tests](#running-tests)
3. [Running Benchmarks](#running-benchmarks)
4. [Running Examples](#running-examples)
5. [Test Organization](#test-organization)
6. [Benchmark Results](#benchmark-results)
7. [Coverage Reports](#coverage-reports)

## Quick Start

### Install Test Dependencies

```bash
pip install pytest pytest-asyncio pytest-benchmark pytest-cov
```

### Run All Tests

```bash
# Run all tests with verbose output
pytest src/crewai_tool_tracer/tests/ -v

# Run specific test file
pytest src/crewai_tool_tracer/tests/test_tracer.py -v

# Run specific test class
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolExecutionTracer -v

# Run specific test function
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolExecutionTracer::test_trace_tool_call -v
```

## Running Tests

### Unit Tests

Core functionality tests for tracing, metrics, and span management:

```bash
# All unit tests
pytest src/crewai_tool_tracer/tests/test_tracer.py -m unit

# Specific unit test categories
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolExecutionTracer
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestDecoratedTools
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestAsyncTracer
```

### Integration Tests

Tests for CrewAI hooks, context managers, and integration components:

```bash
# All integration tests
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestIntegration -v

# Specific integration tests
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestIntegration::test_crewai_tool_hook_pre -v
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestIntegration::test_tool_execution_monitor_duration_slo -v
```

### Async Tests

Tests for async tool execution and correlation:

```bash
# All async tests
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestAsyncTracer -v

# With asyncio output
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestAsyncTracer -v -s
```

### Decorator Tests

Tests for @traced_tool and @traced_async_tool decorators:

```bash
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestDecoratedTools -v
```

### Tool Chain Tests

Tests for tracking tool execution dependencies and chains:

```bash
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolChainTracker -v
```

### Edge Cases and Error Handling

```bash
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestEdgeCases -v
```

### Memory Efficiency Tests

```bash
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestMemoryEfficiency -v
```

## Running Benchmarks

Comprehensive performance benchmarks measure overhead and efficiency:

### Run All Benchmarks

```bash
# Run with benchmark output
pytest src/crewai_tool_tracer/tests/test_benchmarks.py -v

# Run with sorted results
pytest src/crewai_tool_tracer/tests/test_benchmarks.py --benchmark-sort=mean

# Compare with baseline
pytest src/crewai_tool_tracer/tests/test_benchmarks.py --benchmark-compare=0001
```

### Specific Benchmark Categories

#### Tracing Overhead Benchmarks

Measures the performance impact of the tracer:

```bash
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestTracingOverhead -v

# Individual benchmarks:
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestTracingOverhead::test_overhead_trace_tool_call_only
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestTracingOverhead::test_overhead_full_cycle
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestTracingOverhead::test_overhead_decorator_traced_tool
```

Expected overhead:
- `trace_tool_call()`: ~0.05-0.1ms per call
- `record_tool_result()`: ~0.02-0.05ms per call
- Decorated tool: ~0.1-0.2ms overhead
- With metadata/tags: ~0.1-0.3ms overhead

#### Metrics Calculation Benchmarks

```bash
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestMetricsCalculationPerformance -v

# Specific tests:
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestMetricsCalculationPerformance::test_metrics_calculation_100_spans
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestMetricsCalculationPerformance::test_metrics_calculation_1000_spans
```

Expected performance:
- 100 spans: ~1-5ms calculation time
- 1000 spans: ~10-50ms calculation time
- Filtered metrics: ~0.5-5ms depending on filter selectivity

#### Export Performance Benchmarks

```bash
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestExportPerformance -v

# Specific export tests:
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestExportPerformance::test_export_to_json_100_spans
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestExportPerformance::test_export_to_json_large_spans
```

Expected performance:
- JSON export 100 spans: ~5-20ms
- JSON export with large data: ~20-100ms
- OTEL export: ~10-50ms per batch (depends on network)
- Datadog export: ~50-200ms per batch (network dependent)

#### Memory Efficiency Tests

```bash
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestMemoryUsage -v
```

Expected memory usage:
- Per span: ~500 bytes (varies with metadata size)
- 1000 spans: ~500KB-1MB
- Span rotation maintains bounded memory

#### SLO Monitoring Performance

```bash
pytest src/crewai_tool_tracer/tests/test_benchmarks.py::TestSLOMonitoringPerformance -v
```

Expected performance:
- SLO check with 100 spans: ~2-10ms
- Scales linearly with span count

### Benchmark Options

```bash
# Save results
pytest src/crewai_tool_tracer/tests/test_benchmarks.py --benchmark-only --benchmark-json=results.json

# Compare multiple runs
pytest src/crewai_tool_tracer/tests/test_benchmarks.py --benchmark-compare=results.json

# Disable benchmarks and run as regular tests
pytest src/crewai_tool_tracer/tests/test_benchmarks.py --benchmark-disable

# Minimum number of rounds
pytest src/crewai_tool_tracer/tests/test_benchmarks.py --benchmark-min-rounds=10
```

## Running Examples

### Basic Example

Demonstrates core tracing functionality:

```bash
python src/crewai_tool_tracer/examples/tool_tracer_example.py
```

Output shows:
- Basic tool tracing
- Structured logging
- Multiple tool execution
- Filtered metrics
- JSON export
- CrewAI integration patterns

### Comprehensive Example

Full-featured example with all capabilities:

```bash
python src/crewai_tool_tracer/examples/comprehensive_crewai_example.py
```

Demonstrates:
1. **Decorated Tools** - Using @traced_tool decorator
2. **Async Tools** - Async tool execution with proper tracing
3. **Tool Chains** - Tracking dependencies between tools
4. **CrewAI Hooks** - PRE/POST tool call event integration
5. **SLO Monitoring** - Monitoring performance SLOs
6. **Multi-Export** - Exporting to multiple observability platforms
7. **Context Managers** - Task-level execution context
8. **Structured Logging** - JSON logging for analytics

## Test Organization

### Test Files Structure

```
tests/
├── test_tracer.py          # Main test suite
│   ├── TestToolExecutionTracer       # Core tracer tests
│   ├── TestDecoratedTools            # Decorator tests
│   ├── TestAsyncTracer               # Async support tests
│   ├── TestToolChainTracker          # Chain tracking tests
│   ├── TestIntegration               # CrewAI integration tests
│   ├── TestStructuredLogger          # Logging tests
│   ├── TestExporters                 # Export functionality tests
│   ├── TestBenchmarks                # Basic benchmarks
│   ├── TestMemoryEfficiency          # Memory tests
│   └── TestEdgeCases                 # Edge case handling
│
├── test_benchmarks.py       # Comprehensive performance benchmarks
│   ├── TestTracingOverhead           # Overhead measurements
│   ├── TestMetricsCalculationPerformance
│   ├── TestExportPerformance
│   ├── TestAsyncTracingOverhead
│   ├── TestMemoryUsage
│   └── TestSLOMonitoringPerformance
│
└── pytest.ini               # Pytest configuration
```

### Test Markers

Run tests by marker:

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Async tests only
pytest -m async

# Slow tests only
pytest -m slow

# Exclude slow tests
pytest -m "not slow"

# SLO tests only
pytest -m slo
```

## Benchmark Results

### Expected Performance Metrics

#### Tracing Overhead

| Operation | Overhead | Notes |
|-----------|----------|-------|
| trace_tool_call() | 0.05-0.1ms | Span creation only |
| record_tool_result() | 0.02-0.05ms | Result recording |
| Full cycle | 0.1-0.2ms | Both operations |
| Decorator overhead | 0.1-0.2ms | Per tool call |
| With metadata | 0.1-0.3ms | Increases with data size |

#### Metrics Calculation

| Spans | Time | Complexity |
|-------|------|-----------|
| 100 | ~1-5ms | O(n) |
| 1000 | ~10-50ms | O(n) |
| 10000 | ~100-500ms | O(n) |

#### Memory Usage

| Scenario | Memory | Notes |
|----------|--------|-------|
| 100 spans | ~50KB | ~500 bytes/span |
| 1000 spans | ~500KB | Variable with metadata |
| 10000 spans | ~5MB | With rotation enabled |

#### Export Performance

| Format | 100 Spans | 1000 Spans | Notes |
|--------|-----------|-----------|-------|
| JSON | 5-20ms | 50-200ms | Local file I/O |
| OTEL | 10-50ms | 100-500ms | Network dependent |
| Datadog | 50-200ms | 500-2000ms | API rate limits |
| Langfuse | 50-200ms | 500-2000ms | Batch processing |

## Coverage Reports

Generate and view coverage reports:

```bash
# Generate coverage report
pytest src/crewai_tool_tracer/tests/ --cov=src.crewai_tool_tracer --cov-report=html

# View HTML report
open htmlcov/index.html  # macOS
start htmlcov/index.html # Windows
xdg-open htmlcov/index.html # Linux

# Terminal coverage report
pytest src/crewai_tool_tracer/tests/ --cov=src.crewai_tool_tracer --cov-report=term-missing
```

### Coverage Goals

- **Core tracer**: 95%+ coverage
- **Decorators**: 90%+ coverage
- **Integration**: 85%+ coverage
- **Exporters**: 80%+ coverage
- **Overall**: 90%+ coverage target

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests and Benchmarks

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, '3.10', 3.11]

    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt

      - name: Run tests
        run: |
          pytest src/crewai_tool_tracer/tests/ -v --cov

      - name: Run benchmarks
        run: |
          pytest src/crewai_tool_tracer/tests/test_benchmarks.py -v
```

## Troubleshooting

### Common Issues

**Async test failures**
- Ensure pytest-asyncio is installed: `pip install pytest-asyncio`
- Check asyncio_mode in pytest.ini

**Benchmark timeouts**
- Increase timeout in pytest.ini
- Reduce benchmark rounds with `--benchmark-min-rounds=3`

**Memory test failures**
- May vary by system resources
- Run in isolation if needed

**Import errors**
- Ensure PYTHONPATH includes src directory
- Run from project root

## Performance Optimization Tips

1. **Span Rotation**: Use `max_spans` parameter to limit memory usage
2. **Batch Exports**: Export spans in batches for better performance
3. **Filtered Metrics**: Use filters to calculate metrics on subsets
4. **Async Tools**: Use async tracing for I/O-bound operations
5. **Metadata**: Keep metadata/tags reasonable in size

## Further Reading

- See `QUICK_START.md` for basic usage
- See `IMPLEMENTATION_SUMMARY.md` for architecture details
- See examples in `examples/` directory
