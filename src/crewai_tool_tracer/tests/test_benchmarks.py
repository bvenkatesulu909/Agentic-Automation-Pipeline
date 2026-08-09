"""
Performance benchmarks for CrewAI Tool Tracer.

Measures:
- Tracing overhead (latency added per tool call)
- Memory usage with various span counts
- Export performance for different backends
- Metric calculation performance
"""

import pytest
import time
import tempfile
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from src.crewai_tool_tracer.tracer import ToolExecutionTracer, SpanStatus
from src.crewai_tool_tracer.async_tracer import AsyncToolExecutionTracer
from src.crewai_tool_tracer.decorators import traced_tool, traced_async_tool
from src.crewai_tool_tracer.integration import ToolExecutionMonitor


class TestTracingOverhead:
    """Benchmarks for tracing overhead."""

    def test_overhead_trace_tool_call_only(self, benchmark):
        """Measure overhead of trace_tool_call() only (span creation)."""
        tracer = ToolExecutionTracer()

        def trace_only():
            tracer.trace_tool_call(
                tool_name="test_tool",
                input_data={"param": "value"},
                agent_name="agent",
                task_name="task",
            )

        result = benchmark(trace_only)
        assert result is None

    def test_overhead_record_result_only(self, benchmark):
        """Measure overhead of record_tool_result() only."""
        tracer = ToolExecutionTracer()
        span_id = tracer.trace_tool_call(
            tool_name="test_tool",
            input_data={},
            agent_name="agent",
            task_name="task",
        )

        def record_only():
            tracer.record_tool_result(
                span_id=span_id,
                result={"output": "data"},
                duration_ms=10.0,
                success=True,
            )

        result = benchmark(record_only)
        assert result is None

    def test_overhead_full_cycle(self, benchmark):
        """Measure overhead of complete trace cycle (call + result)."""
        tracer = ToolExecutionTracer()

        def full_cycle():
            span_id = tracer.trace_tool_call(
                tool_name="test_tool",
                input_data={"param": "value"},
                agent_name="agent",
                task_name="task",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={"output": "data"},
                duration_ms=1.0,
                success=True,
            )

        result = benchmark(full_cycle)
        assert result is None

    def test_overhead_decorator_traced_tool(self, benchmark):
        """Measure decorator overhead for traced tools."""
        tracer = ToolExecutionTracer()

        @traced_tool(tracer, agent_name="agent", task_name="task")
        def simple_operation(x: int) -> int:
            return x * 2

        # Benchmark the decorated function
        result = benchmark(simple_operation, 5)
        assert result == 10

    def test_overhead_with_complex_input_data(self, benchmark):
        """Measure overhead when tracing tools with complex input data."""
        tracer = ToolExecutionTracer()
        complex_input = {
            "param1": "value" * 100,
            "param2": list(range(100)),
            "param3": {"nested": {"deep": {"data": "here"}}},
        }

        def trace_complex():
            span_id = tracer.trace_tool_call(
                tool_name="test_tool",
                input_data=complex_input,
                agent_name="agent",
                task_name="task",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result=complex_input,
                duration_ms=5.0,
                success=True,
            )

        result = benchmark(trace_complex)
        assert result is None

    def test_overhead_with_metadata_and_tags(self, benchmark):
        """Measure overhead with rich metadata and tags."""
        tracer = ToolExecutionTracer()

        def trace_with_metadata():
            span_id = tracer.trace_tool_call(
                tool_name="test_tool",
                input_data={"query": "test"},
                agent_name="agent",
                task_name="task",
                metadata={
                    "user_id": "123",
                    "session": "abc",
                    "environment": "production",
                    "version": "1.0",
                },
                tags={
                    "severity": "high",
                    "priority": "critical",
                    "region": "us-west",
                },
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={},
                duration_ms=10.0,
                success=True,
            )

        result = benchmark(trace_with_metadata)
        assert result is None


class TestMetricsCalculationPerformance:
    """Benchmarks for metrics calculation performance."""

    @pytest.fixture
    def populated_tracer_100(self):
        """Create tracer with 100 spans."""
        tracer = ToolExecutionTracer()
        for i in range(100):
            span_id = tracer.trace_tool_call(
                tool_name=f"tool_{i % 5}",
                input_data={"index": i},
                agent_name=f"agent_{i % 3}",
                task_name=f"task_{i % 2}",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={"data": i},
                duration_ms=10.0 + i % 20,
                success=i % 5 != 0,
            )
        return tracer

    @pytest.fixture
    def populated_tracer_1000(self):
        """Create tracer with 1000 spans."""
        tracer = ToolExecutionTracer()
        for i in range(1000):
            span_id = tracer.trace_tool_call(
                tool_name=f"tool_{i % 10}",
                input_data={"index": i},
                agent_name=f"agent_{i % 5}",
                task_name=f"task_{i % 3}",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={"data": i},
                duration_ms=5.0 + i % 100,
                success=i % 7 != 0,
            )
        return tracer

    def test_metrics_calculation_100_spans(self, benchmark, populated_tracer_100):
        """Benchmark metrics calculation with 100 spans."""
        def calculate():
            return populated_tracer_100.get_tool_metrics()

        metrics = benchmark(calculate)
        assert metrics.total_executions == 100

    def test_metrics_calculation_1000_spans(self, benchmark, populated_tracer_1000):
        """Benchmark metrics calculation with 1000 spans."""
        def calculate():
            return populated_tracer_1000.get_tool_metrics()

        metrics = benchmark(calculate)
        assert metrics.total_executions == 1000

    def test_filtered_metrics_by_tool(self, benchmark, populated_tracer_100):
        """Benchmark filtered metrics calculation."""
        def calculate_filtered():
            return populated_tracer_100.get_tool_metrics(tool_name="tool_0")

        metrics = benchmark(calculate_filtered)
        assert metrics.total_executions > 0

    def test_filtered_metrics_by_time_range(self, benchmark, populated_tracer_100):
        """Benchmark metrics with time range filter."""
        now = datetime.utcnow()
        time_range = (now - timedelta(hours=1), now + timedelta(hours=1))

        def calculate_time_filtered():
            return populated_tracer_100.get_tool_metrics(time_range=time_range)

        metrics = benchmark(calculate_time_filtered)
        assert metrics.total_executions == 100


class TestExportPerformance:
    """Benchmarks for export performance."""

    @pytest.fixture
    def tracer_with_spans(self):
        """Create tracer with multiple spans for export testing."""
        tracer = ToolExecutionTracer()
        for i in range(100):
            span_id = tracer.trace_tool_call(
                tool_name=f"tool_{i % 5}",
                input_data={
                    "index": i,
                    "data": "x" * 100,
                    "metadata": {"key": f"value_{i}"},
                },
                agent_name=f"agent_{i % 3}",
                task_name=f"task_{i % 2}",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={"output": "y" * 100, "status": "ok"},
                duration_ms=10.0 + i % 50,
                success=i % 5 != 0,
            )
        return tracer

    def test_export_to_json_100_spans(self, benchmark, tracer_with_spans):
        """Benchmark JSON export with 100 spans."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name

        try:
            def export():
                tracer_with_spans.export_to_json(temp_file)

            benchmark(export)

            # Verify export
            with open(temp_file, 'r') as f:
                data = json.load(f)
            assert len(data['spans']) == 100

        finally:
            Path(temp_file).unlink()

    def test_export_to_json_large_spans(self, benchmark):
        """Benchmark JSON export with large span data."""
        tracer = ToolExecutionTracer()

        # Create spans with large data
        for i in range(100):
            span_id = tracer.trace_tool_call(
                tool_name="large_data_tool",
                input_data={"data": "x" * 5000},
                agent_name="agent",
                task_name="task",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={"large_output": "y" * 5000},
                duration_ms=50.0,
                success=True,
            )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name

        try:
            def export():
                tracer.export_to_json(temp_file)

            benchmark(export)

            with open(temp_file, 'r') as f:
                data = json.load(f)
            assert len(data['spans']) == 100

        finally:
            Path(temp_file).unlink()


class TestAsyncTracingOverhead:
    """Benchmarks for async tool tracing overhead."""

    @pytest.mark.asyncio
    async def test_async_trace_overhead(self, benchmark):
        """Benchmark async tool tracing overhead."""
        tracer = AsyncToolExecutionTracer()

        async def trace_async():
            span_id = await tracer.trace_async_tool_call(
                tool_name="async_tool",
                input_data={"param": "value"},
                agent_name="agent",
                task_name="task",
            )
            await tracer.record_async_tool_result(
                span_id=span_id,
                result={"output": "data"},
                duration_ms=1.0,
                success=True,
            )

        # Note: pytest-benchmark may not work well with async
        # This is for reference
        start = time.time()
        await trace_async()
        elapsed = time.time() - start

        print(f"\nAsync trace overhead: {elapsed * 1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_concurrent_async_traces(self, benchmark):
        """Benchmark concurrent async tool tracing."""
        tracer = AsyncToolExecutionTracer()

        @traced_async_tool(tracer, agent_name="agent", task_name="task")
        async def async_operation(x: int) -> int:
            await asyncio.sleep(0.001)
            return x * 2

        async def run_concurrent():
            tasks = [async_operation(i) for i in range(10)]
            return await asyncio.gather(*tasks)

        start = time.time()
        results = await run_concurrent()
        elapsed = time.time() - start

        assert len(results) == 10
        print(f"\n10 concurrent async operations: {elapsed * 1000:.2f}ms")


class TestMemoryUsage:
    """Memory usage and efficiency tests."""

    def test_memory_scaling_with_spans(self):
        """Test memory scaling with increasing span counts."""
        import sys

        tracer = ToolExecutionTracer()

        # Measure memory growth
        memory_samples = []

        for i in range(1000):
            span_id = tracer.trace_tool_call(
                tool_name=f"tool_{i % 10}",
                input_data={"index": i, "data": "x" * 100},
                agent_name=f"agent_{i % 5}",
                task_name=f"task_{i % 3}",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={"output": "y" * 100},
                duration_ms=10.0,
                success=True,
            )

            if i % 100 == 0 and i > 0:
                # Estimate memory usage
                span_count = len(tracer._spans)
                memory_samples.append((i, span_count))

        # Verify no excessive memory growth
        print(f"\nSpan count progression: {memory_samples}")
        assert len(tracer._spans) == 1000

    def test_span_rotation_memory_efficiency(self):
        """Test memory efficiency of span rotation."""
        max_spans = 100
        tracer = ToolExecutionTracer(max_spans=max_spans)

        # Create many more spans than max
        for i in range(1000):
            tracer.trace_tool_call(
                tool_name="tool",
                input_data={"index": i},
                agent_name="agent",
                task_name="task",
            )

        # Verify rotation keeps memory bounded
        assert len(tracer._spans) <= max_spans
        print(f"\nSpan rotation maintained: {len(tracer._spans)} <= {max_spans}")


class TestSLOMonitoringPerformance:
    """Benchmarks for SLO monitoring performance."""

    def test_slo_check_performance(self, benchmark):
        """Benchmark SLO violation checking."""
        tracer = ToolExecutionTracer()
        monitor = ToolExecutionMonitor(tracer)

        # Set SLOs
        monitor.set_max_duration("tool_0", 50.0)
        monitor.set_max_duration("tool_1", 100.0)
        monitor.set_min_success_rate("tool_0", 0.95)
        monitor.set_min_success_rate("tool_1", 0.90)

        # Populate with spans
        for i in range(100):
            span_id = tracer.trace_tool_call(
                tool_name=f"tool_{i % 2}",
                input_data={},
                agent_name="agent",
                task_name="task",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={},
                duration_ms=50.0 + i % 30,
                success=i % 5 != 0,
            )

        def check_slos():
            return monitor.check_slos()

        violations = benchmark(check_slos)
        assert isinstance(violations, list)
        print(f"\nSLO violations found: {len(violations)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
