"""
CrewAI Tool Execution Tracer

A comprehensive tracing and observability system for CrewAI tool executions.
Provides structured logging, metrics collection, and multi-backend export
for integration with OTEL, Datadog, and Langfuse platforms.

Features:
    - Granular per-tool tracing (fills CrewAI observability gap)
    - Third-party platform integration (OpenTelemetry, Datadog, Langfuse)
    - Async execution correlation and tool chain tracking
    - Rich error context with structured logging
    - Decorator-based minimal invasiveness
    - CrewAI hook integration (@on(PRE_TOOL_CALL) and @on(POST_TOOL_CALL))

Quick Start:
    from crewai_tool_tracer import ToolExecutionTracer, StructuredLogger
    from crewai_tool_tracer.decorators import traced_tool

    tracer = ToolExecutionTracer(name="my_crew")
    logger = StructuredLogger(name="my_crew_logger")

    @traced_tool(tracer, agent_name="research", task_name="search")
    def search(query: str) -> str:
        return results
"""

from .tracer import ToolExecutionTracer, ToolSpan, ToolMetrics, SpanStatus
from .structured_logging import StructuredLogger, LogLevel, LogAggregator
from .exporters import (
    OTelExporter,
    DatadogExporter,
    LangfuseExporter,
    CompositeExporter,
    BaseExporter,
)
from .async_tracer import AsyncToolExecutionTracer, ToolChainTracker, async_traced_tool
from .decorators import (
    traced_tool,
    traced_async_tool,
    ToolWrapper,
    create_traced_tools,
)
from .integration import (
    CrewAIToolHook,
    CrewAITaskContext,
    trace_crewai_execution,
    ToolExecutionMonitor,
    ExecutionContextManager,
)

__version__ = "0.1.0"
__author__ = "CrewAI Contributors"

__all__ = [
    # Core tracer
    "ToolExecutionTracer",
    "AsyncToolExecutionTracer",
    "ToolSpan",
    "ToolMetrics",
    "SpanStatus",
    # Structured logging
    "StructuredLogger",
    "LogLevel",
    "LogAggregator",
    # Exporters
    "OTelExporter",
    "DatadogExporter",
    "LangfuseExporter",
    "CompositeExporter",
    "BaseExporter",
    # Async support
    "ToolChainTracker",
    "async_traced_tool",
    # Decorators
    "traced_tool",
    "traced_async_tool",
    "ToolWrapper",
    "create_traced_tools",
    # CrewAI integration
    "CrewAIToolHook",
    "CrewAITaskContext",
    "trace_crewai_execution",
    "ToolExecutionMonitor",
    "ExecutionContextManager",
]
