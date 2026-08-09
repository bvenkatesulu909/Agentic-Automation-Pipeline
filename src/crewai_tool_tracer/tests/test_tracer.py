"""
Comprehensive tests and benchmarks for CrewAI Tool Execution Tracer.

Tests core tracing functionality, metrics calculation, export capabilities,
async support, decorators, and integration with CrewAI components.
"""

import pytest
import json
import tempfile
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import uuid

from src.crewai_tool_tracer.tracer import (
    ToolExecutionTracer,
    ToolSpan,
    ToolMetrics,
    SpanStatus,
)
from src.crewai_tool_tracer.async_tracer import AsyncToolExecutionTracer, ToolChainTracker
from src.crewai_tool_tracer.structured_logging import StructuredLogger, LogLevel
from src.crewai_tool_tracer.exporters import (
    OTelExporter,
    DatadogExporter,
    LangfuseExporter,
    CompositeExporter,
)
from src.crewai_tool_tracer.decorators import traced_tool, traced_async_tool, ToolWrapper, create_traced_tools
from src.crewai_tool_tracer.integration import (
    CrewAIToolHook,
    CrewAITaskContext,
    trace_crewai_execution,
    ToolExecutionMonitor,
    ExecutionContextManager,
)


class TestToolExecutionTracer:
    """Tests for ToolExecutionTracer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracer = ToolExecutionTracer(name="test-tracer")

    def test_initialization(self):
        """Test tracer initialization."""
        assert self.tracer.name == "test-tracer"
        assert len(self.tracer._spans) == 0
        assert self.tracer.enable_structured_logging is True

    def test_trace_tool_call(self):
        """Test tracing a tool call."""
        span_id = self.tracer.trace_tool_call(
            tool_name="calculator",
            input_data={"expression": "2 + 2"},
            agent_name="math_agent",
            task_name="solve_math",
        )

        assert span_id is not None
        assert isinstance(span_id, str)
        assert len(span_id) > 0

        span = self.tracer.get_span(span_id)
        assert span is not None
        assert span.tool_name == "calculator"
        assert span.agent_name == "math_agent"
        assert span.task_name == "solve_math"
        assert span.status == SpanStatus.RUNNING

    def test_span_id_generation(self):
        """Test that span IDs are unique and properly formatted."""
        span_ids = set()
        for i in range(100):
            span_id = self.tracer.trace_tool_call(
                tool_name="tool",
                input_data={},
                agent_name="agent",
                task_name="task",
            )
            span_ids.add(span_id)
            # Verify UUID format (simple check)
            assert len(span_id) == 36  # UUID4 format length
            assert span_id.count('-') == 4  # UUID has 4 hyphens

        # All IDs should be unique
        assert len(span_ids) == 100

    def test_record_tool_result_success(self):
        """Test recording a successful tool result."""
        span_id = self.tracer.trace_tool_call(
            tool_name="calculator",
            input_data={"expression": "2 + 2"},
            agent_name="math_agent",
            task_name="solve_math",
        )

        self.tracer.record_tool_result(
            span_id=span_id,
            result={"answer": 4},
            duration_ms=15.5,
            success=True,
        )

        span = self.tracer.get_span(span_id)
        assert span.status == SpanStatus.SUCCESS
        assert span.duration_ms == 15.5
        assert span.result == {"answer": 4}
        assert span.error is None

    def test_record_tool_result_failure(self):
        """Test recording a failed tool result."""
        span_id = self.tracer.trace_tool_call(
            tool_name="calculator",
            input_data={"expression": "invalid"},
            agent_name="math_agent",
            task_name="solve_math",
        )

        error = ValueError("Invalid expression")
        self.tracer.record_tool_result(
            span_id=span_id,
            result=None,
            duration_ms=5.0,
            success=False,
            error=error,
        )

        span = self.tracer.get_span(span_id)
        assert span.status == SpanStatus.ERROR
        assert span.error is error
        assert "Invalid expression" in span.error_message

    def test_timing_and_duration_capture(self):
        """Test accurate timing and duration capture."""
        span_id = self.tracer.trace_tool_call(
            tool_name="slow_tool",
            input_data={},
            agent_name="agent",
            task_name="task",
        )

        start_time = time.time()
        time.sleep(0.1)  # 100ms sleep
        elapsed = (time.time() - start_time) * 1000

        self.tracer.record_tool_result(
            span_id=span_id,
            result={},
            duration_ms=elapsed,
            success=True,
        )

        span = self.tracer.get_span(span_id)
        assert span.start_time is not None
        assert span.end_time is not None
        assert span.duration_ms >= 100  # At least 100ms
        assert span.end_time >= span.start_time

    def test_error_capture_with_context_enrichment(self):
        """Test error capture and context enrichment."""
        span_id = self.tracer.trace_tool_call(
            tool_name="error_tool",
            input_data={"query": "test"},
            agent_name="agent",
            task_name="task",
            metadata={"user_id": "123", "session": "abc"},
            tags={"severity": "high"}
        )

        error = RuntimeError("Connection failed")
        self.tracer.record_tool_result(
            span_id=span_id,
            result=None,
            duration_ms=50.0,
            success=False,
            error=error,
        )

        span = self.tracer.get_span(span_id)
        assert span.error is error
        assert span.error_message == "Connection failed"
        assert span.metadata["user_id"] == "123"
        assert span.tags["severity"] == "high"

    def test_get_all_spans(self):
        """Test retrieving all spans."""
        for i in range(5):
            self.tracer.trace_tool_call(
                tool_name=f"tool_{i}",
                input_data={"index": i},
                agent_name="test_agent",
                task_name="test_task",
            )

        spans = self.tracer.get_all_spans()
        assert len(spans) == 5

    def test_get_tool_metrics_basic(self):
        """Test calculating basic tool metrics."""
        # Create some spans
        for i in range(10):
            span_id = self.tracer.trace_tool_call(
                tool_name="calculator" if i % 2 == 0 else "search",
                input_data={"index": i},
                agent_name="agent_1" if i < 5 else "agent_2",
                task_name="task_1",
            )

            success = i % 3 != 0  # Make some fail
            self.tracer.record_tool_result(
                span_id=span_id,
                result={"data": i},
                duration_ms=10.0 + i,
                success=success,
            )

        metrics = self.tracer.get_tool_metrics()
        assert metrics.total_executions == 10
        assert metrics.successful_executions > 0
        assert metrics.failed_executions > 0
        assert metrics.average_duration_ms > 0
        assert metrics.min_duration_ms is not None
        assert metrics.max_duration_ms is not None

    def test_get_tool_metrics_with_time_range(self):
        """Test metrics calculation with time range filter."""
        span_id = self.tracer.trace_tool_call(
            tool_name="calculator",
            input_data={"expression": "2 + 2"},
            agent_name="math_agent",
            task_name="solve_math",
        )

        self.tracer.record_tool_result(
            span_id=span_id,
            result={"answer": 4},
            duration_ms=15.5,
            success=True,
        )

        now = datetime.utcnow()
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=1)

        # Metrics within range
        metrics = self.tracer.get_tool_metrics(time_range=(past, future))
        assert metrics.total_executions == 1

        # Metrics outside range
        metrics = self.tracer.get_tool_metrics(time_range=(future, future + timedelta(hours=1)))
        assert metrics.total_executions == 0

    def test_get_tool_metrics_filtered_by_tool(self):
        """Test metrics calculation filtered by tool name."""
        for tool in ["calculator", "search", "database"]:
            span_id = self.tracer.trace_tool_call(
                tool_name=tool,
                input_data={},
                agent_name="agent",
                task_name="task",
            )
            self.tracer.record_tool_result(
                span_id=span_id,
                result={},
                duration_ms=10.0,
                success=True,
            )

        metrics = self.tracer.get_tool_metrics(tool_name="calculator")
        assert metrics.total_executions == 1
        assert "calculator" in metrics.tools_executed

    def test_get_tool_metrics_filtered_by_agent(self):
        """Test metrics calculation filtered by agent name."""
        for agent in ["agent_1", "agent_2", "agent_3"]:
            span_id = self.tracer.trace_tool_call(
                tool_name="tool",
                input_data={},
                agent_name=agent,
                task_name="task",
            )
            self.tracer.record_tool_result(
                span_id=span_id,
                result={},
                duration_ms=10.0,
                success=True,
            )

        metrics = self.tracer.get_tool_metrics(agent_name="agent_1")
        assert metrics.total_executions == 1
        assert "agent_1" in metrics.agents_involved

    def test_export_to_json(self):
        """Test exporting spans to JSON file."""
        span_id = self.tracer.trace_tool_call(
            tool_name="calculator",
            input_data={"expression": "2 + 2"},
            agent_name="math_agent",
            task_name="solve_math",
        )

        self.tracer.record_tool_result(
            span_id=span_id,
            result={"answer": 4},
            duration_ms=15.5,
            success=True,
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name

        try:
            self.tracer.export_to_json(temp_file)

            # Verify exported file
            with open(temp_file, 'r') as f:
                data = json.load(f)

            assert data['tracer_name'] == "test-tracer"
            assert len(data['spans']) == 1
            assert data['spans'][0]['tool_name'] == "calculator"

        finally:
            Path(temp_file).unlink()

    def test_max_spans_rotation(self):
        """Test that old spans are rotated when max capacity is reached."""
        tracer = ToolExecutionTracer(name="test-tracer", max_spans=5)

        span_ids = []
        for i in range(10):
            span_id = tracer.trace_tool_call(
                tool_name="tool",
                input_data={"index": i},
                agent_name="agent",
                task_name="task",
            )
            span_ids.append(span_id)

        # Only the last 5 spans should remain
        assert len(tracer._spans) == 5
        assert span_ids[0] not in tracer._spans  # First span should be rotated out

    def test_clear_spans(self):
        """Test clearing all spans."""
        for i in range(5):
            self.tracer.trace_tool_call(
                tool_name="tool",
                input_data={},
                agent_name="agent",
                task_name="task",
            )

        assert len(self.tracer._spans) == 5

        self.tracer.clear_spans()
        assert len(self.tracer._spans) == 0

    def test_span_to_dict_serialization(self):
        """Test ToolSpan to_dict() serialization."""
        span_id = self.tracer.trace_tool_call(
            tool_name="test_tool",
            input_data={"param": "value"},
            agent_name="agent",
            task_name="task",
        )

        self.tracer.record_tool_result(
            span_id=span_id,
            result={"output": "data"},
            duration_ms=25.0,
            success=True,
        )

        span = self.tracer.get_span(span_id)
        span_dict = span.to_dict()

        # Verify serialization handles datetime objects
        assert isinstance(span_dict['start_time'], str)
        assert isinstance(span_dict['end_time'], str)
        assert span_dict['status'] == 'success'
        assert span_dict['tool_name'] == 'test_tool'


class TestDecoratedTools:
    """Tests for decorated tool execution."""

    def test_traced_tool_decorator_success(self):
        """Test traced_tool decorator with successful execution."""
        tracer = ToolExecutionTracer(name="test-tracer")

        @traced_tool(tracer, agent_name="test_agent", task_name="test_task")
        def add_numbers(a: int, b: int) -> int:
            return a + b

        result = add_numbers(2, 3)
        assert result == 5

        # Verify span was created
        spans = tracer.get_all_spans()
        assert len(spans) == 1
        assert spans[0].tool_name == "add_numbers"
        assert spans[0].status == SpanStatus.SUCCESS

    def test_traced_tool_decorator_error(self):
        """Test traced_tool decorator with exception."""
        tracer = ToolExecutionTracer(name="test-tracer")

        @traced_tool(tracer, agent_name="test_agent", task_name="test_task")
        def failing_tool():
            raise ValueError("Tool failed")

        with pytest.raises(ValueError):
            failing_tool()

        # Verify error was captured
        spans = tracer.get_all_spans()
        assert len(spans) == 1
        assert spans[0].status == SpanStatus.ERROR
        assert "Tool failed" in spans[0].error_message

    def test_traced_tool_duration_capture(self):
        """Test that decorator accurately captures duration."""
        tracer = ToolExecutionTracer(name="test-tracer")

        @traced_tool(tracer, agent_name="agent", task_name="task")
        def slow_tool():
            time.sleep(0.05)  # 50ms
            return "done"

        result = slow_tool()
        assert result == "done"

        span = tracer.get_all_spans()[0]
        assert span.duration_ms >= 50  # Should capture at least 50ms

    def test_tool_wrapper_class(self):
        """Test ToolWrapper class."""
        tracer = ToolExecutionTracer(name="test-tracer")

        def original_tool(x):
            return x * 2

        wrapped = ToolWrapper(original_tool, tracer, "agent", "task", tool_name="doubler")
        result = wrapped(5)

        assert result == 10
        span = tracer.get_all_spans()[0]
        assert span.tool_name == "doubler"
        assert span.status == SpanStatus.SUCCESS

    def test_create_traced_tools(self):
        """Test creating multiple traced tools at once."""
        tracer = ToolExecutionTracer(name="test-tracer")

        def tool1():
            return "result1"

        def tool2():
            return "result2"

        tools = [tool1, tool2]
        traced = create_traced_tools(tools, tracer, "agent", "task")

        assert len(traced) == 2
        result1 = traced[0]()
        result2 = traced[1]()

        assert result1 == "result1"
        assert result2 == "result2"
        assert len(tracer.get_all_spans()) == 2


class TestAsyncTracer:
    """Tests for async tool execution tracing."""

    def test_async_tracer_initialization(self):
        """Test async tracer initialization."""
        tracer = AsyncToolExecutionTracer(name="async-tracer")
        assert tracer.name == "async-tracer"
        assert tracer._context_var_available

    @pytest.mark.asyncio
    async def test_trace_async_tool_call(self):
        """Test async tool call tracing."""
        tracer = AsyncToolExecutionTracer()

        span_id = await tracer.trace_async_tool_call(
            tool_name="async_search",
            input_data={"query": "test"},
            agent_name="agent",
            task_name="task",
        )

        assert span_id is not None
        span = tracer.get_span(span_id)
        assert span.tool_name == "async_search"
        assert span.status == SpanStatus.RUNNING

    @pytest.mark.asyncio
    async def test_async_tool_decorator(self):
        """Test traced_async_tool decorator."""
        tracer = AsyncToolExecutionTracer()

        @traced_async_tool(tracer, agent_name="agent", task_name="task")
        async def async_fetch(url: str):
            await asyncio.sleep(0.05)
            return f"data from {url}"

        result = await async_fetch("http://example.com")
        assert "data from" in result

        spans = tracer.get_all_spans()
        assert len(spans) == 1
        assert spans[0].tool_name == "async_fetch"
        assert spans[0].status == SpanStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_async_tool_error_handling(self):
        """Test async tool error handling."""
        tracer = AsyncToolExecutionTracer()

        @traced_async_tool(tracer, agent_name="agent", task_name="task")
        async def async_failing_tool():
            await asyncio.sleep(0.01)
            raise RuntimeError("Async failure")

        with pytest.raises(RuntimeError):
            await async_failing_tool()

        span = tracer.get_all_spans()[0]
        assert span.status == SpanStatus.ERROR

    @pytest.mark.asyncio
    async def test_multiple_concurrent_async_tools(self):
        """Test tracing multiple concurrent async tool executions."""
        tracer = AsyncToolExecutionTracer()

        @traced_async_tool(tracer, agent_name="agent", task_name="task")
        async def concurrent_tool(n: int):
            await asyncio.sleep(0.01 * n)
            return n * 2

        # Run multiple async tasks concurrently
        tasks = [concurrent_tool(i) for i in range(1, 4)]
        results = await asyncio.gather(*tasks)

        assert results == [2, 4, 6]
        assert len(tracer.get_all_spans()) == 3


class TestToolChainTracker:
    """Tests for tool execution chain tracking."""

    def test_link_spans(self):
        """Test linking parent-child spans."""
        tracer = ToolExecutionTracer()
        tracker = ToolChainTracker(tracer)

        parent_id = tracer.trace_tool_call(
            tool_name="parent", input_data={}, agent_name="agent", task_name="task"
        )
        child_id = tracer.trace_tool_call(
            tool_name="child", input_data={}, agent_name="agent", task_name="task"
        )

        tracker.link_spans(parent_id, child_id)

        assert tracker._chain_map[child_id] == parent_id
        child_span = tracer.get_span(child_id)
        assert child_span.metadata['parent_span_id'] == parent_id

    def test_get_execution_chain(self):
        """Test getting full execution chain."""
        tracer = ToolExecutionTracer()
        tracker = ToolChainTracker(tracer)

        # Create chain: A -> B -> C
        a_id = tracer.trace_tool_call(
            tool_name="a", input_data={}, agent_name="agent", task_name="task"
        )
        b_id = tracer.trace_tool_call(
            tool_name="b", input_data={}, agent_name="agent", task_name="task"
        )
        c_id = tracer.trace_tool_call(
            tool_name="c", input_data={}, agent_name="agent", task_name="task"
        )

        tracker.link_spans(a_id, b_id)
        tracker.link_spans(b_id, c_id)

        chain = tracker.get_execution_chain(c_id)
        assert chain == [a_id, b_id, c_id]

    def test_analyze_chain_metrics(self):
        """Test analyzing metrics for a tool chain."""
        tracer = ToolExecutionTracer()
        tracker = ToolChainTracker(tracer)

        # Create and complete a chain
        span_ids = []
        for i in range(3):
            sid = tracer.trace_tool_call(
                tool_name=f"tool_{i}", input_data={}, agent_name="agent", task_name="task"
            )
            tracer.record_tool_result(
                span_id=sid, result={}, duration_ms=10.0 + i, success=True
            )
            span_ids.append(sid)

        # Link them
        for i in range(len(span_ids) - 1):
            tracker.link_spans(span_ids[i], span_ids[i + 1])

        metrics = tracker.analyze_chain_metrics(span_ids)
        assert metrics['chain_length'] == 3
        assert metrics['successful_executions'] == 3
        assert metrics['total_duration_ms'] > 0


class TestIntegration:
    """Tests for CrewAI integration components."""

    def test_crewai_tool_hook_pre(self):
        """Test CrewAI tool hook PRE_TOOL_CALL event."""
        tracer = ToolExecutionTracer()
        hook = CrewAIToolHook(tracer)

        span_id = hook.on_tool_call_pre(
            tool_name="web_search",
            tool_args={"query": "test"},
            agent_name="research_agent",
            task_name="find_info",
        )

        assert span_id is not None
        span = tracer.get_span(span_id)
        assert span.tool_name == "web_search"
        assert span.agent_name == "research_agent"

    def test_crewai_tool_hook_post(self):
        """Test CrewAI tool hook POST_TOOL_CALL event."""
        tracer = ToolExecutionTracer()
        hook = CrewAIToolHook(tracer)

        span_id = hook.on_tool_call_pre(
            tool_name="web_search",
            tool_args={"query": "test"},
            agent_name="research_agent",
            task_name="find_info",
        )

        time.sleep(0.01)
        hook.on_tool_call_post(
            span_id=span_id,
            tool_result="Search results...",
            error=None,
        )

        span = tracer.get_span(span_id)
        assert span.status == SpanStatus.SUCCESS
        assert span.duration_ms > 0

    def test_crewai_tool_hook_error(self):
        """Test CrewAI tool hook error handling."""
        tracer = ToolExecutionTracer()
        hook = CrewAIToolHook(tracer)

        span_id = hook.on_tool_call_pre(
            tool_name="web_search",
            tool_args={"query": "test"},
            agent_name="research_agent",
            task_name="find_info",
        )

        error = RuntimeError("Search failed")
        hook.on_tool_call_post(
            span_id=span_id,
            tool_result=None,
            error=error,
        )

        span = tracer.get_span(span_id)
        assert span.status == SpanStatus.ERROR
        assert "Search failed" in span.error_message

    def test_execution_context_manager(self):
        """Test ExecutionContextManager."""
        tracer = ToolExecutionTracer()
        ctx_mgr = ExecutionContextManager(tracer)

        ctx_mgr.set_context("agent_1", "task_1")
        agent, task = ctx_mgr.get_context()
        assert agent == "agent_1"
        assert task == "task_1"

        ctx_mgr.clear_context()
        agent, task = ctx_mgr.get_context()
        assert agent is None
        assert task is None

    def test_execution_context_as_context_manager(self):
        """Test ExecutionContextManager as context manager."""
        tracer = ToolExecutionTracer()
        ctx_mgr = ExecutionContextManager(tracer)

        with ctx_mgr.as_context_manager("agent_2", "task_2"):
            agent, task = ctx_mgr.get_context()
            assert agent == "agent_2"
            assert task == "task_2"

    def test_tool_execution_monitor_duration_slo(self):
        """Test SLO monitoring for tool duration."""
        tracer = ToolExecutionTracer()
        monitor = ToolExecutionMonitor(tracer)
        monitor.set_max_duration("slow_tool", 10.0)

        span_id = tracer.trace_tool_call(
            tool_name="slow_tool",
            input_data={},
            agent_name="agent",
            task_name="task",
        )
        tracer.record_tool_result(
            span_id=span_id,
            result={},
            duration_ms=15.0,  # Exceeds SLO
            success=True,
        )

        violations = monitor.check_slos()
        assert len(violations) > 0
        assert violations[0]['type'] == 'duration_slo'

    def test_tool_execution_monitor_success_rate_slo(self):
        """Test SLO monitoring for success rate."""
        tracer = ToolExecutionTracer()
        monitor = ToolExecutionMonitor(tracer)
        monitor.set_min_success_rate("flaky_tool", 0.9)

        # Create 10 executions with 70% success rate
        for i in range(10):
            span_id = tracer.trace_tool_call(
                tool_name="flaky_tool",
                input_data={},
                agent_name="agent",
                task_name="task",
            )
            success = i < 7  # First 7 succeed, last 3 fail
            tracer.record_tool_result(
                span_id=span_id,
                result={} if success else None,
                duration_ms=5.0,
                success=success,
            )

        violations = monitor.check_slos()
        assert len(violations) > 0
        assert violations[0]['type'] == 'success_rate_slo'


class TestStructuredLogger:
    """Tests for StructuredLogger class."""

    def test_initialization(self):
        """Test logger initialization."""
        logger = StructuredLogger(name="test-logger")
        assert logger.name == "test-logger"
        assert logger.level == LogLevel.INFO

    def test_log_tool_call(self):
        """Test logging a tool call."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            temp_file = f.name

        try:
            logger = StructuredLogger(log_file=temp_file)
            logger.log_tool_call(
                tool_name="calculator",
                agent_name="math_agent",
                task_name="solve_math",
                input_data={"expression": "2 + 2"},
                span_id="test-span-123",
            )

            # Verify log was written
            with open(temp_file, 'r') as f:
                log_line = f.readline()
                log_data = json.loads(log_line)

            assert log_data['event']['event_type'] == "tool.call"
            assert log_data['event']['tool_name'] == "calculator"

        finally:
            Path(temp_file).unlink()

    def test_log_tool_result(self):
        """Test logging a tool result."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            temp_file = f.name

        try:
            logger = StructuredLogger(log_file=temp_file)
            logger.log_tool_result(
                tool_name="calculator",
                span_id="test-span-123",
                result={"answer": 4},
                duration_ms=15.5,
                success=True,
            )

            # Verify log was written
            with open(temp_file, 'r') as f:
                log_line = f.readline()
                log_data = json.loads(log_line)

            assert log_data['event']['event_type'] == "tool.result"
            assert log_data['event']['success'] is True

        finally:
            Path(temp_file).unlink()


class TestExporters:
    """Tests for exporter classes."""

    def test_otel_exporter_initialization(self):
        """Test OTEL exporter initialization."""
        exporter = OTelExporter(
            endpoint="http://localhost:4317",
            service_name="test-service",
        )
        assert exporter.endpoint == "http://localhost:4317"
        assert exporter.service_name == "test-service"

    def test_datadog_exporter_initialization(self):
        """Test Datadog exporter initialization."""
        exporter = DatadogExporter(
            api_key="test-key",
            service_name="test-service",
        )
        assert exporter.api_key == "test-key"
        assert exporter.service_name == "test-service"

    def test_langfuse_exporter_initialization(self):
        """Test Langfuse exporter initialization."""
        exporter = LangfuseExporter(
            api_key="test-key",
            secret_key="test-secret",
        )
        assert exporter.api_key == "test-key"
        assert exporter.secret_key == "test-secret"

    def test_composite_exporter(self):
        """Test composite exporter."""
        exporter1 = OTelExporter()
        exporter2 = DatadogExporter(api_key="test-key")

        composite = CompositeExporter([exporter1, exporter2])
        assert len(composite.exporters) == 2


class TestBenchmarks:
    """Performance benchmarks for tracing overhead and efficiency."""

    def test_tracing_overhead_single_call(self, benchmark):
        """Benchmark: Measure overhead of a single traced tool call."""
        tracer = ToolExecutionTracer()

        def trace_single_call():
            span_id = tracer.trace_tool_call(
                tool_name="benchmark_tool",
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

        result = benchmark(trace_single_call)
        # Verify it completes successfully
        assert result is None

    def test_tracing_overhead_decorator(self, benchmark):
        """Benchmark: Measure decorator overhead."""
        tracer = ToolExecutionTracer()

        @traced_tool(tracer, agent_name="agent", task_name="task")
        def simple_operation(x: int) -> int:
            return x * 2

        result = benchmark(simple_operation, 5)
        assert result == 10

    def test_metrics_calculation_performance(self, benchmark):
        """Benchmark: Measure metrics calculation with 100s of spans."""
        tracer = ToolExecutionTracer()

        # Pre-populate with 100 spans
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

        def calculate_metrics():
            return tracer.get_tool_metrics()

        metrics = benchmark(calculate_metrics)
        assert metrics.total_executions == 100

    def test_json_export_performance(self, benchmark):
        """Benchmark: Measure JSON export performance with 100s of spans."""
        tracer = ToolExecutionTracer()

        # Pre-populate with 100 spans
        for i in range(100):
            span_id = tracer.trace_tool_call(
                tool_name=f"tool_{i % 5}",
                input_data={"index": i, "data": "x" * 100},
                agent_name=f"agent_{i % 3}",
                task_name=f"task_{i % 2}",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={"output": "y" * 100},
                duration_ms=5.0,
                success=True,
            )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name

        try:
            def export_json():
                tracer.export_to_json(temp_file)

            benchmark(export_json)

            # Verify export succeeded
            with open(temp_file, 'r') as f:
                data = json.load(f)
            assert len(data['spans']) == 100
        finally:
            Path(temp_file).unlink()


class TestMemoryEfficiency:
    """Tests for memory efficiency and span rotation."""

    def test_memory_with_max_spans(self):
        """Test memory efficiency with max_spans rotation."""
        max_spans = 1000
        tracer = ToolExecutionTracer(name="memory-test", max_spans=max_spans)

        # Create many spans
        for i in range(5000):
            span_id = tracer.trace_tool_call(
                tool_name="tool",
                input_data={"index": i, "data": "x" * 100},
                agent_name="agent",
                task_name="task",
            )

        # Verify spans are rotated
        assert len(tracer._spans) <= max_spans
        assert len(tracer._span_order) <= max_spans

    def test_span_order_consistency(self):
        """Test that span order is maintained correctly."""
        tracer = ToolExecutionTracer(max_spans=10)

        span_ids = []
        for i in range(15):
            span_id = tracer.trace_tool_call(
                tool_name="tool",
                input_data={},
                agent_name="agent",
                task_name="task",
            )
            span_ids.append(span_id)

        # Verify last 10 are present
        for span_id in span_ids[-10:]:
            assert tracer.get_span(span_id) is not None

        # Verify first 5 are gone
        for span_id in span_ids[:5]:
            assert tracer.get_span(span_id) is None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unknown_span_id(self):
        """Test handling of unknown span ID."""
        tracer = ToolExecutionTracer()

        with pytest.raises(ValueError):
            tracer.record_tool_result(
                span_id="unknown-span-id",
                result={},
                duration_ms=0,
                success=True,
            )

    def test_empty_input_data(self):
        """Test tool call with empty input data."""
        tracer = ToolExecutionTracer()

        span_id = tracer.trace_tool_call(
            tool_name="tool",
            input_data={},
            agent_name="agent",
            task_name="task",
        )

        span = tracer.get_span(span_id)
        assert span.input_data == {}

    def test_large_result_serialization(self):
        """Test handling of large results in serialization."""
        tracer = ToolExecutionTracer()

        span_id = tracer.trace_tool_call(
            tool_name="tool",
            input_data={},
            agent_name="agent",
            task_name="task",
        )

        # Large result
        large_result = {"data": "x" * 10000}
        tracer.record_tool_result(
            span_id=span_id,
            result=large_result,
            duration_ms=0,
            success=True,
        )

        span = tracer.get_span(span_id)
        assert span.result is not None

    def test_metrics_with_no_spans(self):
        """Test metrics calculation with no spans."""
        tracer = ToolExecutionTracer()
        metrics = tracer.get_tool_metrics()

        assert metrics.total_executions == 0
        assert metrics.successful_executions == 0
        assert metrics.failed_executions == 0
        assert metrics.average_duration_ms == 0.0

    def test_filter_with_no_results(self):
        """Test filtering that returns no results."""
        tracer = ToolExecutionTracer()

        # Create some spans
        for i in range(5):
            span_id = tracer.trace_tool_call(
                tool_name="tool",
                input_data={},
                agent_name="agent",
                task_name="task",
            )
            tracer.record_tool_result(
                span_id=span_id,
                result={},
                duration_ms=5.0,
                success=True,
            )

        # Filter with non-existent tool name
        metrics = tracer.get_tool_metrics(tool_name="nonexistent")
        assert metrics.total_executions == 0


# Fixtures for pytest
@pytest.fixture
def tracer():
    """Provide a ToolExecutionTracer instance."""
    return ToolExecutionTracer(name="pytest-tracer")


@pytest.fixture
def async_tracer():
    """Provide an AsyncToolExecutionTracer instance."""
    return AsyncToolExecutionTracer(name="pytest-async-tracer")


@pytest.fixture
def logger():
    """Provide a StructuredLogger instance."""
    return StructuredLogger(name="pytest-logger")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
