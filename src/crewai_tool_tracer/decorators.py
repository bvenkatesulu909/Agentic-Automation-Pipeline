"""
Decorator utilities for easy CrewAI tool execution tracing.

Provides decorators for automatic tracing of sync and async tools,
with minimal code modifications required.
"""

import time
import functools
from typing import Callable, Any, Optional, Dict
import logging

from .tracer import ToolExecutionTracer

logger = logging.getLogger(__name__)


def traced_tool(
    tracer: ToolExecutionTracer,
    agent_name: Optional[str] = None,
    task_name: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> Callable:
    """
    Decorator for synchronous tool execution with automatic tracing.

    Automatically captures tool name, inputs, outputs, duration, and errors.
    Minimal invasiveness - just add decorator to existing tools.

    Args:
        tracer: ToolExecutionTracer instance
        agent_name: Name of the agent (optional, can be inferred)
        task_name: Name of the task (optional, can be inferred)
        tool_name: Name of the tool (optional, defaults to function name)

    Returns:
        Decorator function

    Example:
        @traced_tool(tracer, agent_name="research_agent", task_name="search")
        def web_search(query: str) -> str:
            # Tool implementation
            return search_results

    Features:
        - Automatic span creation and completion
        - Duration measurement
        - Exception capture with full context
        - Input/output logging
        - Metadata enrichment
    """

    def decorator(func: Callable) -> Callable:
        tool_name_to_use = tool_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Extract agent and task names if not provided
            agent_context = agent_name or _extract_context_var('agent_name') or 'unknown_agent'
            task_context = task_name or _extract_context_var('task_name') or 'unknown_task'

            start_time = time.time()

            # Start tracing
            span_id = tracer.trace_tool_call(
                tool_name=tool_name_to_use,
                input_data={
                    "args": _serialize_args(args),
                    "kwargs": kwargs,
                },
                agent_name=agent_context,
                task_name=task_context,
                metadata={
                    "function_module": func.__module__,
                    "function_qualname": func.__qualname__,
                },
            )

            try:
                # Execute the actual function
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                # Record success
                tracer.record_tool_result(
                    span_id=span_id,
                    result=_serialize_result(result),
                    duration_ms=duration_ms,
                    success=True,
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                # Record failure with full context
                tracer.record_tool_result(
                    span_id=span_id,
                    result=None,
                    duration_ms=duration_ms,
                    success=False,
                    error=e,
                )

                # Re-raise the exception
                raise

        return wrapper

    return decorator


def traced_async_tool(
    tracer: 'AsyncToolExecutionTracer',
    agent_name: Optional[str] = None,
    task_name: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> Callable:
    """
    Decorator for asynchronous tool execution with automatic tracing.

    Handles async/await syntax with proper context propagation.

    Args:
        tracer: AsyncToolExecutionTracer instance
        agent_name: Name of the agent (optional, can be inferred)
        task_name: Name of the task (optional, can be inferred)
        tool_name: Name of the tool (optional, defaults to function name)

    Returns:
        Decorator function

    Example:
        @traced_async_tool(tracer, agent_name="research_agent", task_name="search")
        async def async_web_search(query: str) -> str:
            # Async tool implementation
            return await search_results

    Features:
        - Async/await support
        - Task correlation across async boundaries
        - Duration measurement
        - Exception capture
        - Input/output logging
    """

    def decorator(func: Callable) -> Callable:
        tool_name_to_use = tool_name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Extract agent and task names if not provided
            agent_context = agent_name or _extract_context_var('agent_name') or 'unknown_agent'
            task_context = task_name or _extract_context_var('task_name') or 'unknown_task'

            start_time = time.time()

            # Start async tracing
            span_id = await tracer.trace_async_tool_call(
                tool_name=tool_name_to_use,
                input_data={
                    "args": _serialize_args(args),
                    "kwargs": kwargs,
                },
                agent_name=agent_context,
                task_name=task_context,
                metadata={
                    "function_module": func.__module__,
                    "function_qualname": func.__qualname__,
                    "async": True,
                },
            )

            try:
                # Execute the async function
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                # Record success
                await tracer.record_async_tool_result(
                    span_id=span_id,
                    result=_serialize_result(result),
                    duration_ms=duration_ms,
                    success=True,
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                # Record failure with full context
                await tracer.record_async_tool_result(
                    span_id=span_id,
                    result=None,
                    duration_ms=duration_ms,
                    success=False,
                    error=e,
                )

                # Re-raise the exception
                raise

        return wrapper

    return decorator


class ToolWrapper:
    """
    Wrapper class for tools with automatic tracing.

    Useful for wrapping existing tools or integrating with tool factories.

    Example:
        original_tool = get_tool_from_crewai()
        traced = ToolWrapper(original_tool, tracer, "research_agent", "search")
        result = traced(query="what is Python?")
    """

    def __init__(
        self,
        tool: Callable,
        tracer: ToolExecutionTracer,
        agent_name: str,
        task_name: str,
        tool_name: Optional[str] = None,
    ):
        """
        Initialize tool wrapper.

        Args:
            tool: The original tool function
            tracer: ToolExecutionTracer instance
            agent_name: Name of the agent
            task_name: Name of the task
            tool_name: Optional tool name (defaults to function name)
        """
        self.tool = tool
        self.tracer = tracer
        self.agent_name = agent_name
        self.task_name = task_name
        self.tool_name = tool_name or (
            getattr(tool, 'name', None) or
            getattr(tool, '__name__', 'unknown_tool')
        )

    def __call__(self, *args, **kwargs) -> Any:
        """Execute wrapped tool with tracing."""
        start_time = time.time()

        # Start tracing
        span_id = self.tracer.trace_tool_call(
            tool_name=self.tool_name,
            input_data={
                "args": _serialize_args(args),
                "kwargs": kwargs,
            },
            agent_name=self.agent_name,
            task_name=self.task_name,
        )

        try:
            # Execute tool
            result = self.tool(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000

            # Record success
            self.tracer.record_tool_result(
                span_id=span_id,
                result=_serialize_result(result),
                duration_ms=duration_ms,
                success=True,
            )

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # Record failure
            self.tracer.record_tool_result(
                span_id=span_id,
                result=None,
                duration_ms=duration_ms,
                success=False,
                error=e,
            )

            raise

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to wrapped tool."""
        return getattr(self.tool, name)


def _serialize_args(args: tuple) -> str:
    """Safely serialize function arguments for logging."""
    try:
        # Only serialize first 2 args to avoid huge logs
        if len(args) <= 2:
            return str(args)
        return f"({args[0]}, {args[1]}, ... {len(args) - 2} more)"
    except Exception as e:
        logger.debug(f"Failed to serialize args: {e}")
        return str(type(args))


def _serialize_result(result: Any) -> Any:
    """Safely serialize function result for logging."""
    try:
        if isinstance(result, (str, int, float, bool, type(None))):
            return result
        if isinstance(result, (list, dict)):
            # Truncate large results
            result_str = str(result)
            if len(result_str) > 1000:
                return result_str[:1000] + "... (truncated)"
            return result
        return str(result)[:1000]  # Truncate to 1000 chars
    except Exception as e:
        logger.debug(f"Failed to serialize result: {e}")
        return f"<{type(result).__name__}>"


def _extract_context_var(var_name: str) -> Optional[str]:
    """
    Extract a context variable from the execution context.

    Attempts to extract from multiple sources for flexibility.
    """
    try:
        # Try contextvars first
        from contextvars import copy_context
        ctx = copy_context()
        for var in ctx:
            if var_name in str(var):
                return str(ctx[var])
    except Exception:
        pass

    return None


def create_traced_tools(
    tools: list,
    tracer: ToolExecutionTracer,
    agent_name: str,
    task_name: str,
) -> list:
    """
    Create traced versions of multiple tools.

    Convenience function for wrapping multiple tools at once.

    Args:
        tools: List of tool functions
        tracer: ToolExecutionTracer instance
        agent_name: Name of the agent
        task_name: Name of the task

    Returns:
        list: List of wrapped tool functions

    Example:
        tools = [tool1, tool2, tool3]
        traced_tools = create_traced_tools(tools, tracer, "agent_1", "task_1")
    """
    return [
        ToolWrapper(tool, tracer, agent_name, task_name)
        for tool in tools
    ]
