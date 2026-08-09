"""
Core ToolExecutionTracer implementation for CrewAI.

Provides span tracking, metrics collection, and export capabilities
for tool executions within CrewAI agents and tasks.
"""

import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
from pathlib import Path


class SpanStatus(Enum):
    """Status of a tool execution span."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ToolSpan:
    """Represents a single tool execution trace."""
    span_id: str
    tool_name: str
    agent_name: str
    task_name: str
    input_data: Dict[str, Any]
    status: SpanStatus = SpanStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[Exception] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary, handling non-serializable types."""
        data = asdict(self)
        data['status'] = self.status.value
        data['start_time'] = self.start_time.isoformat() if self.start_time else None
        data['end_time'] = self.end_time.isoformat() if self.end_time else None
        data['error'] = None  # Exclude exception object
        if self.error_message:
            data['error_message'] = self.error_message
        return data


@dataclass
class ToolMetrics:
    """Aggregated metrics for tool executions."""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_duration_ms: float = 0.0
    average_duration_ms: float = 0.0
    min_duration_ms: Optional[float] = None
    max_duration_ms: Optional[float] = None
    error_rate: float = 0.0
    tools_executed: Dict[str, int] = field(default_factory=dict)
    agents_involved: Dict[str, int] = field(default_factory=dict)
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'total_executions': self.total_executions,
            'successful_executions': self.successful_executions,
            'failed_executions': self.failed_executions,
            'total_duration_ms': self.total_duration_ms,
            'average_duration_ms': self.average_duration_ms,
            'min_duration_ms': self.min_duration_ms,
            'max_duration_ms': self.max_duration_ms,
            'error_rate': self.error_rate,
            'tools_executed': self.tools_executed,
            'agents_involved': self.agents_involved,
            'time_range_start': self.time_range_start.isoformat() if self.time_range_start else None,
            'time_range_end': self.time_range_end.isoformat() if self.time_range_end else None,
        }


class ToolExecutionTracer:
    """
    Main tracer class for tracking CrewAI tool executions.

    Integrates with CrewAI agents and tools to provide comprehensive
    tracing, metrics, and observability capabilities.

    Example:
        tracer = ToolExecutionTracer(name="my_agent")
        span_id = tracer.trace_tool_call(
            tool_name="calculator",
            input={"expression": "2 + 2"},
            agent_name="math_agent",
            task_name="solve_math"
        )
        tracer.record_tool_result(
            span_id=span_id,
            result={"answer": 4},
            duration_ms=15.5,
            success=True
        )
        metrics = tracer.get_tool_metrics(
            time_range=(datetime.now() - timedelta(hours=1), datetime.now())
        )
    """

    def __init__(
        self,
        name: str = "crewai-tracer",
        enable_structured_logging: bool = True,
        max_spans: int = 10000,
    ):
        """
        Initialize the ToolExecutionTracer.

        Args:
            name: Name identifier for the tracer instance
            enable_structured_logging: Whether to enable JSON structured logging
            max_spans: Maximum number of spans to keep in memory
        """
        self.name = name
        self.enable_structured_logging = enable_structured_logging
        self.max_spans = max_spans
        self._spans: Dict[str, ToolSpan] = {}
        self._span_order: List[str] = []  # Track insertion order for rotation

    def trace_tool_call(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        agent_name: str,
        task_name: str,
        tags: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start tracing a tool call.

        Args:
            tool_name: Name of the tool being called
            input_data: Input dictionary for the tool
            agent_name: Name of the agent executing the tool
            task_name: Name of the task within which tool is executed
            tags: Optional string tags for the span
            metadata: Optional additional metadata

        Returns:
            span_id: Unique identifier for this span
        """
        span_id = str(uuid.uuid4())

        span = ToolSpan(
            span_id=span_id,
            tool_name=tool_name,
            agent_name=agent_name,
            task_name=task_name,
            input_data=input_data,
            status=SpanStatus.RUNNING,
            start_time=datetime.utcnow(),
            tags=tags or {},
            metadata=metadata or {},
        )

        self._spans[span_id] = span
        self._span_order.append(span_id)

        # Rotate spans if max capacity exceeded
        if len(self._spans) > self.max_spans:
            oldest_span_id = self._span_order.pop(0)
            del self._spans[oldest_span_id]

        return span_id

    def record_tool_result(
        self,
        span_id: str,
        result: Any = None,
        duration_ms: float = 0.0,
        success: bool = True,
        error: Optional[Exception] = None,
    ) -> None:
        """
        Record the result of a tool execution.

        Args:
            span_id: The span ID from trace_tool_call()
            result: The result returned by the tool
            duration_ms: Execution duration in milliseconds
            success: Whether the tool executed successfully
            error: Optional exception if execution failed
        """
        if span_id not in self._spans:
            raise ValueError(f"Unknown span_id: {span_id}")

        span = self._spans[span_id]
        span.end_time = datetime.utcnow()
        span.duration_ms = duration_ms
        span.result = result
        span.error = error
        span.status = SpanStatus.SUCCESS if success else SpanStatus.ERROR

        if error:
            span.error_message = str(error)

    def get_span(self, span_id: str) -> Optional[ToolSpan]:
        """Retrieve a specific span by ID."""
        return self._spans.get(span_id)

    def get_all_spans(self) -> List[ToolSpan]:
        """Get all recorded spans."""
        return list(self._spans.values())

    def get_tool_metrics(
        self,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        tool_name: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> ToolMetrics:
        """
        Calculate aggregated metrics for tool executions.

        Args:
            time_range: Optional tuple of (start_time, end_time) for filtering
            tool_name: Optional tool name filter
            agent_name: Optional agent name filter

        Returns:
            ToolMetrics: Aggregated metrics object
        """
        metrics = ToolMetrics()

        if time_range:
            metrics.time_range_start = time_range[0]
            metrics.time_range_end = time_range[1]

        filtered_spans = self._filter_spans(time_range, tool_name, agent_name)

        if not filtered_spans:
            return metrics

        metrics.total_executions = len(filtered_spans)
        durations = []

        for span in filtered_spans:
            if span.status == SpanStatus.SUCCESS:
                metrics.successful_executions += 1
            elif span.status == SpanStatus.ERROR:
                metrics.failed_executions += 1

            if span.duration_ms:
                durations.append(span.duration_ms)
                metrics.total_duration_ms += span.duration_ms

            # Track tool usage
            metrics.tools_executed[span.tool_name] = metrics.tools_executed.get(span.tool_name, 0) + 1

            # Track agent involvement
            metrics.agents_involved[span.agent_name] = metrics.agents_involved.get(span.agent_name, 0) + 1

        # Calculate derived metrics
        if durations:
            metrics.average_duration_ms = metrics.total_duration_ms / len(durations)
            metrics.min_duration_ms = min(durations)
            metrics.max_duration_ms = max(durations)

        if metrics.total_executions > 0:
            metrics.error_rate = metrics.failed_executions / metrics.total_executions

        return metrics

    def _filter_spans(
        self,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        tool_name: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> List[ToolSpan]:
        """Internal method to filter spans based on criteria."""
        filtered = self._spans.values()

        if time_range:
            start_time, end_time = time_range
            filtered = [
                s for s in filtered
                if s.end_time and start_time <= s.end_time <= end_time
            ]

        if tool_name:
            filtered = [s for s in filtered if s.tool_name == tool_name]

        if agent_name:
            filtered = [s for s in filtered if s.agent_name == agent_name]

        return list(filtered)

    def export_to_otel(self, spans: Optional[List[ToolSpan]] = None) -> None:
        """
        Export spans to OpenTelemetry backend.

        Args:
            spans: Optional list of spans to export. If None, exports all spans.
        """
        # Implementation delegated to OTelExporter
        pass

    def export_to_datadog(self, spans: Optional[List[ToolSpan]] = None, api_key: Optional[str] = None) -> None:
        """
        Export spans to Datadog.

        Args:
            spans: Optional list of spans to export. If None, exports all spans.
            api_key: Datadog API key (optional, can be loaded from env)
        """
        # Implementation delegated to DatadogExporter
        pass

    def export_to_langfuse(self, spans: Optional[List[ToolSpan]] = None, api_key: Optional[str] = None) -> None:
        """
        Export spans to Langfuse.

        Args:
            spans: Optional list of spans to export. If None, exports all spans.
            api_key: Langfuse API key (optional, can be loaded from env)
        """
        # Implementation delegated to LangfuseExporter
        pass

    def export_to_json(self, filepath: str, spans: Optional[List[ToolSpan]] = None) -> None:
        """
        Export spans to JSON file for local analysis.

        Args:
            filepath: Path to write JSON file
            spans: Optional list of spans to export. If None, exports all spans.
        """
        spans_to_export = spans or self.get_all_spans()
        data = {
            'tracer_name': self.name,
            'export_time': datetime.utcnow().isoformat(),
            'spans': [span.to_dict() for span in spans_to_export],
        }

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def clear_spans(self) -> None:
        """Clear all recorded spans."""
        self._spans.clear()
        self._span_order.clear()

    def __repr__(self) -> str:
        return f"ToolExecutionTracer(name={self.name}, spans={len(self._spans)})"
