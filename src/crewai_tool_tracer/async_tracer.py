"""
Async-aware tool execution tracing for CrewAI.

Provides support for tracing asynchronous tool executions with
proper correlation and context propagation across async boundaries.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, Coroutine
from functools import wraps
from datetime import datetime
import logging

from .tracer import ToolExecutionTracer, SpanStatus

logger = logging.getLogger(__name__)


class AsyncToolExecutionTracer(ToolExecutionTracer):
    """
    Extended tracer with async/await support for tool executions.

    Properly handles async tool execution with context propagation
    and task correlation.
    """

    def __init__(
        self,
        name: str = "crewai-async-tracer",
        enable_structured_logging: bool = True,
        max_spans: int = 10000,
    ):
        """
        Initialize async tracer.

        Args:
            name: Name identifier for the tracer instance
            enable_structured_logging: Whether to enable JSON structured logging
            max_spans: Maximum number of spans to keep in memory
        """
        super().__init__(name, enable_structured_logging, max_spans)
        self._task_spans: Dict[asyncio.Task, str] = {}  # Map tasks to span IDs
        self._context_var_available = False

        try:
            from contextvars import ContextVar
            self._current_span_id: ContextVar[Optional[str]] = ContextVar('span_id', default=None)
            self._context_var_available = True
        except ImportError:
            logger.warning("contextvars not available, using task-based correlation")

    async def trace_async_tool_call(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        agent_name: str,
        task_name: str,
        tags: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start tracing an async tool call.

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
        # Start tracing using parent method
        span_id = self.trace_tool_call(
            tool_name=tool_name,
            input_data=input_data,
            agent_name=agent_name,
            task_name=task_name,
            tags=tags,
            metadata=metadata,
        )

        # Track current task if available
        try:
            current_task = asyncio.current_task()
            if current_task:
                self._task_spans[current_task] = span_id
                # Clean up when task is done
                current_task.add_done_callback(
                    lambda t: self._task_spans.pop(t, None)
                )
        except RuntimeError:
            # Not in async context
            pass

        # Set context variable if available
        if self._context_var_available:
            self._current_span_id.set(span_id)

        return span_id

    async def record_async_tool_result(
        self,
        span_id: str,
        result: Any = None,
        duration_ms: float = 0.0,
        success: bool = True,
        error: Optional[Exception] = None,
    ) -> None:
        """
        Record the result of an async tool execution.

        Args:
            span_id: The span ID from trace_async_tool_call()
            result: The result returned by the tool
            duration_ms: Execution duration in milliseconds
            success: Whether the tool executed successfully
            error: Optional exception if execution failed
        """
        self.record_tool_result(
            span_id=span_id,
            result=result,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )

    def get_current_span_id(self) -> Optional[str]:
        """
        Get the current span ID in the execution context.

        Returns:
            span_id: Current span ID or None if not in a traced context
        """
        if self._context_var_available:
            try:
                return self._current_span_id.get()
            except LookupError:
                pass

        # Fallback to task-based lookup
        try:
            current_task = asyncio.current_task()
            if current_task:
                return self._task_spans.get(current_task)
        except RuntimeError:
            pass

        return None


def async_traced_tool(
    tracer: AsyncToolExecutionTracer,
    agent_name: str,
    task_name: str,
) -> Callable:
    """
    Decorator for async tool execution with automatic tracing.

    Args:
        tracer: AsyncToolExecutionTracer instance
        agent_name: Name of the agent
        task_name: Name of the task

    Returns:
        Decorator function

    Example:
        @async_traced_tool(tracer, "research_agent", "search_task")
        async def search_web(query: str) -> str:
            # Tool implementation
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            tool_name = func.__name__
            start_time = time.time()

            # Start tracing
            span_id = await tracer.trace_async_tool_call(
                tool_name=tool_name,
                input_data={"args": str(args[:2]) if args else "", "kwargs": kwargs},
                agent_name=agent_name,
                task_name=task_name,
                metadata={"function": func.__qualname__},
            )

            try:
                # Execute async function
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                # Record success
                await tracer.record_async_tool_result(
                    span_id=span_id,
                    result=result,
                    duration_ms=duration_ms,
                    success=True,
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                # Record failure
                await tracer.record_async_tool_result(
                    span_id=span_id,
                    result=None,
                    duration_ms=duration_ms,
                    success=False,
                    error=e,
                )

                raise

        return wrapper

    return decorator


class ToolChainTracker:
    """
    Tracks dependencies and chains between tool executions.

    Useful for understanding tool call sequences and dependencies
    in multi-step workflows.
    """

    def __init__(self, tracer: ToolExecutionTracer):
        """
        Initialize chain tracker.

        Args:
            tracer: ToolExecutionTracer instance
        """
        self.tracer = tracer
        self._chain_map: Dict[str, str] = {}  # Maps span_id to parent span_id
        self._execution_chains: Dict[str, list] = {}  # Maps agent to list of span chains

    def link_spans(self, parent_span_id: str, child_span_id: str) -> None:
        """
        Link a child span to a parent span (indicating dependency).

        Args:
            parent_span_id: ID of the parent/prerequisite span
            child_span_id: ID of the child span that depends on parent
        """
        self._chain_map[child_span_id] = parent_span_id

        # Update span metadata with parent reference
        child_span = self.tracer.get_span(child_span_id)
        if child_span:
            child_span.metadata['parent_span_id'] = parent_span_id

    def get_execution_chain(self, span_id: str) -> list:
        """
        Get the full execution chain for a span (all ancestors and descendants).

        Args:
            span_id: Span ID to trace

        Returns:
            list: Ordered list of span IDs in the chain
        """
        chain = [span_id]

        # Find all ancestors
        current = span_id
        while current in self._chain_map:
            parent = self._chain_map[current]
            chain.insert(0, parent)
            current = parent

        # Find all descendants
        descendants = [s for s, p in self._chain_map.items() if p == span_id]
        for descendant in descendants:
            chain.extend(self.get_execution_chain(descendant)[1:])  # Skip first (already in chain)

        return chain

    def get_agent_chains(self, agent_name: str) -> Dict[str, list]:
        """
        Get all execution chains for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            dict: Maps root span IDs to their full execution chains
        """
        chains = {}

        # Find root spans (those with no parent) for this agent
        for span in self.tracer.get_all_spans():
            if span.agent_name == agent_name and span.span_id not in self._chain_map:
                chains[span.span_id] = self.get_execution_chain(span.span_id)

        return chains

    def analyze_chain_metrics(self, chain: list) -> Dict[str, Any]:
        """
        Analyze metrics for a specific execution chain.

        Args:
            chain: List of span IDs in the chain

        Returns:
            dict: Metrics including total duration, bottlenecks, etc.
        """
        spans = [self.tracer.get_span(sid) for sid in chain]
        spans = [s for s in spans if s]  # Filter out None values

        if not spans:
            return {}

        total_duration = sum(s.duration_ms or 0 for s in spans)
        successful = sum(1 for s in spans if s.status == SpanStatus.SUCCESS)
        failed = sum(1 for s in spans if s.status == SpanStatus.ERROR)

        # Find bottleneck (slowest tool)
        slowest = max(spans, key=lambda s: s.duration_ms or 0)

        return {
            "chain_length": len(spans),
            "total_duration_ms": total_duration,
            "successful_executions": successful,
            "failed_executions": failed,
            "success_rate": successful / len(spans) if spans else 0,
            "bottleneck_tool": slowest.tool_name,
            "bottleneck_duration_ms": slowest.duration_ms or 0,
            "tools_in_chain": [s.tool_name for s in spans],
        }
