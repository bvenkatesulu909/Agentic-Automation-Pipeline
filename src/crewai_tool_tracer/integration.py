"""
Comprehensive CrewAI integration utilities.

Provides hooks, context managers, and utilities for integrating the
ToolExecutionTracer with CrewAI agents, tasks, and tool execution pipelines.
"""

import time
import logging
from typing import Callable, Optional, Any, Dict
from contextlib import contextmanager
from datetime import datetime

from .tracer import ToolExecutionTracer, SpanStatus
from .structured_logging import StructuredLogger

logger = logging.getLogger(__name__)


class CrewAIToolHook:
    """
    Hook-based integration with CrewAI tool execution events.

    Integrates with CrewAI's @on(PRE_TOOL_CALL) and @on(POST_TOOL_CALL) events
    to automatically trace tool executions without modifying tool code.

    This is the recommended approach for CrewAI integration as it requires
    no changes to existing tools or agents.

    Usage:
        from crewai import Agent, Task, Crew
        from crewai_tool_tracer import ToolExecutionTracer
        from crewai_tool_tracer.integration import CrewAIToolHook

        tracer = ToolExecutionTracer(name="my_crew")
        hook = CrewAIToolHook(tracer, logger=None)

        # Then in your Crew definition:
        # hook.register_on_tool_call_pre(agent)
        # hook.register_on_tool_call_post(agent)
    """

    def __init__(
        self,
        tracer: ToolExecutionTracer,
        logger: Optional[StructuredLogger] = None,
    ):
        """
        Initialize CrewAI tool hook.

        Args:
            tracer: ToolExecutionTracer instance
            logger: Optional StructuredLogger for event logging
        """
        self.tracer = tracer
        self.logger = logger
        self._execution_state: Dict[str, Dict[str, Any]] = {}  # Track in-flight executions

    def on_tool_call_pre(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        agent_name: str,
        task_name: str,
        **kwargs,
    ) -> str:
        """
        PRE_TOOL_CALL hook handler.

        Should be called before tool execution starts.

        Args:
            tool_name: Name of the tool
            tool_args: Arguments passed to the tool
            agent_name: Name of the executing agent
            task_name: Name of the executing task
            **kwargs: Additional context from CrewAI

        Returns:
            str: Span ID for correlation with POST hook

        Example (CrewAI decorator style):
            @on(PRE_TOOL_CALL)
            def on_tool_start(self, tool_name: str, tool_args: Dict[str, Any], **kwargs):
                span_id = hook.on_tool_call_pre(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    agent_name=self.name,
                    task_name=self.current_task.name,
                )
                return span_id
        """
        span_id = self.tracer.trace_tool_call(
            tool_name=tool_name,
            input_data=tool_args,
            agent_name=agent_name,
            task_name=task_name,
            metadata={
                "hook_type": "PRE_TOOL_CALL",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Store execution state for correlation
        self._execution_state[span_id] = {
            "tool_name": tool_name,
            "agent_name": agent_name,
            "task_name": task_name,
            "start_time": time.time(),
        }

        # Log if logger available
        if self.logger:
            self.logger.log_tool_call(
                tool_name=tool_name,
                agent_name=agent_name,
                task_name=task_name,
                input_data=tool_args,
                span_id=span_id,
            )

        logger.debug(f"Tool execution started: {span_id} ({tool_name})")
        return span_id

    def on_tool_call_post(
        self,
        span_id: str,
        tool_result: Any,
        error: Optional[Exception] = None,
        **kwargs,
    ) -> None:
        """
        POST_TOOL_CALL hook handler.

        Should be called after tool execution completes.

        Args:
            span_id: Span ID returned from on_tool_call_pre
            tool_result: Result returned by the tool
            error: Optional exception if tool failed
            **kwargs: Additional context from CrewAI

        Example (CrewAI decorator style):
            @on(POST_TOOL_CALL)
            def on_tool_end(self, tool_result: Any, **kwargs):
                span_id = getattr(self, '_last_span_id', None)
                if span_id:
                    hook.on_tool_call_post(
                        span_id=span_id,
                        tool_result=tool_result,
                        error=None,
                    )
        """
        if span_id not in self._execution_state:
            logger.warning(f"No execution state found for span: {span_id}")
            return

        state = self._execution_state.pop(span_id)
        duration_ms = (time.time() - state["start_time"]) * 1000

        # Record result
        self.tracer.record_tool_result(
            span_id=span_id,
            result=tool_result,
            duration_ms=duration_ms,
            success=error is None,
            error=error,
        )

        # Log if logger available
        if self.logger:
            self.logger.log_tool_result(
                tool_name=state["tool_name"],
                span_id=span_id,
                result=tool_result,
                duration_ms=duration_ms,
                success=error is None,
                error=str(error) if error else None,
            )

        status = "success" if error is None else "error"
        logger.debug(f"Tool execution completed: {span_id} ({status})")


class CrewAITaskContext:
    """
    Context manager for tracing CrewAI task executions.

    Automatically tags all tool calls within a task with the task context.

    Usage:
        with CrewAITaskContext(tracer, "research_agent", "find_info"):
            # All tool calls within this block are tagged with task context
            agent.execute_task(task)
    """

    def __init__(
        self,
        tracer: ToolExecutionTracer,
        agent_name: str,
        task_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize task context.

        Args:
            tracer: ToolExecutionTracer instance
            agent_name: Name of the agent
            task_name: Name of the task
            metadata: Optional task-level metadata
        """
        self.tracer = tracer
        self.agent_name = agent_name
        self.task_name = task_name
        self.metadata = metadata or {}
        self._task_span_id: Optional[str] = None
        self._original_tracer_state = {}

    def __enter__(self) -> "CrewAITaskContext":
        """Enter task context."""
        # Could optionally create a top-level task span
        self._task_span_id = self.tracer.trace_tool_call(
            tool_name="task",
            input_data={"task_name": self.task_name},
            agent_name=self.agent_name,
            task_name=self.task_name,
            metadata=self.metadata,
        )
        logger.debug(f"Entering task context: {self.task_name} ({self._task_span_id})")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit task context."""
        if self._task_span_id:
            self.tracer.record_tool_result(
                span_id=self._task_span_id,
                result={"task": self.task_name},
                duration_ms=0,
                success=exc_type is None,
                error=exc_val,
            )
        logger.debug(f"Exiting task context: {self.task_name}")


@contextmanager
def trace_crewai_execution(
    tracer: ToolExecutionTracer,
    agent_name: str,
    task_name: str,
    logger_instance: Optional[StructuredLogger] = None,
):
    """
    Context manager for tracing CrewAI agent execution.

    Provides automatic logging and error handling for tool executions.

    Args:
        tracer: ToolExecutionTracer instance
        agent_name: Name of the agent
        task_name: Name of the task
        logger_instance: Optional StructuredLogger instance

    Usage:
        with trace_crewai_execution(tracer, "search_agent", "research_task"):
            result = agent.execute_task(task)

    Yields:
        CrewAITaskContext: Context object for manual correlation
    """
    context = CrewAITaskContext(tracer, agent_name, task_name)

    try:
        with context:
            if logger_instance:
                logger_instance.log_agent_event(
                    event_type="agent.start",
                    agent_name=agent_name,
                    task_name=task_name,
                    message=f"Starting task execution",
                )

            yield context

            if logger_instance:
                logger_instance.log_agent_event(
                    event_type="agent.complete",
                    agent_name=agent_name,
                    task_name=task_name,
                    message=f"Task execution completed successfully",
                )

    except Exception as e:
        if logger_instance:
            logger_instance.log_error(
                error_message=str(e),
                agent_name=agent_name,
                tool_name=None,
                metadata={"task_name": task_name},
            )

        logger.error(f"Error during task execution: {e}")
        raise


class ToolExecutionMonitor:
    """
    Monitors and enforces SLOs/constraints on tool executions.

    Useful for ensuring tool performance meets requirements or
    triggering alerts when performance degrades.

    Example:
        monitor = ToolExecutionMonitor(tracer)
        monitor.set_max_duration("web_search", 5000)  # 5 seconds
        monitor.set_min_success_rate("database_query", 0.95)  # 95%

        # Then periodically:
        violations = monitor.check_slos()
        if violations:
            alert_team(violations)
    """

    def __init__(self, tracer: ToolExecutionTracer):
        """
        Initialize execution monitor.

        Args:
            tracer: ToolExecutionTracer instance
        """
        self.tracer = tracer
        self._max_duration: Dict[str, float] = {}
        self._min_success_rate: Dict[str, float] = {}
        self._violations: list = []

    def set_max_duration(self, tool_name: str, max_ms: float) -> None:
        """
        Set maximum execution duration for a tool.

        Args:
            tool_name: Name of the tool
            max_ms: Maximum duration in milliseconds
        """
        self._max_duration[tool_name] = max_ms

    def set_min_success_rate(self, tool_name: str, min_rate: float) -> None:
        """
        Set minimum success rate for a tool.

        Args:
            tool_name: Name of the tool
            min_rate: Minimum success rate (0.0-1.0)
        """
        self._min_success_rate[tool_name] = min_rate

    def check_slos(self) -> list:
        """
        Check if current metrics violate any configured SLOs.

        Returns:
            list: List of SLO violations
        """
        self._violations = []

        # Check duration SLOs
        for tool_name, max_duration in self._max_duration.items():
            metrics = self.tracer.get_tool_metrics(tool_name=tool_name)

            if metrics.max_duration_ms and metrics.max_duration_ms > max_duration:
                self._violations.append({
                    "type": "duration_slo",
                    "tool_name": tool_name,
                    "max_allowed_ms": max_duration,
                    "actual_ms": metrics.max_duration_ms,
                    "message": f"{tool_name} exceeded max duration: {metrics.max_duration_ms:.0f}ms > {max_duration:.0f}ms",
                })

        # Check success rate SLOs
        for tool_name, min_rate in self._min_success_rate.items():
            metrics = self.tracer.get_tool_metrics(tool_name=tool_name)

            if metrics.total_executions > 0:
                actual_rate = metrics.successful_executions / metrics.total_executions
                if actual_rate < min_rate:
                    self._violations.append({
                        "type": "success_rate_slo",
                        "tool_name": tool_name,
                        "min_allowed_rate": min_rate,
                        "actual_rate": actual_rate,
                        "message": f"{tool_name} success rate below threshold: {actual_rate:.1%} < {min_rate:.1%}",
                    })

        return self._violations

    def get_violations(self) -> list:
        """Get last recorded SLO violations."""
        return self._violations


class ExecutionContextManager:
    """
    Manages execution context for multi-agent scenarios.

    Tracks which agent and task are currently executing to automatically
    populate tracer context without explicit parameters.

    Example:
        ctx_mgr = ExecutionContextManager(tracer)

        for agent in agents:
            ctx_mgr.set_context(agent.name, current_task.name)
            agent.execute()
            # Tools automatically traced with agent/task context
    """

    def __init__(self, tracer: ToolExecutionTracer):
        """
        Initialize context manager.

        Args:
            tracer: ToolExecutionTracer instance
        """
        self.tracer = tracer
        self._current_agent: Optional[str] = None
        self._current_task: Optional[str] = None

    def set_context(self, agent_name: str, task_name: str) -> None:
        """
        Set current execution context.

        Args:
            agent_name: Name of the currently executing agent
            task_name: Name of the currently executing task
        """
        self._current_agent = agent_name
        self._current_task = task_name
        logger.debug(f"Context set: {agent_name} executing {task_name}")

    def get_context(self) -> tuple:
        """
        Get current execution context.

        Returns:
            tuple: (agent_name, task_name)
        """
        return (self._current_agent, self._current_task)

    def clear_context(self) -> None:
        """Clear current execution context."""
        self._current_agent = None
        self._current_task = None

    def as_context_manager(self, agent_name: str, task_name: str):
        """
        Return context manager for executing with given context.

        Usage:
            with ctx_mgr.as_context_manager("agent_1", "task_1"):
                # Execute with this context
                pass
        """
        return _ContextScope(self, agent_name, task_name)


class _ContextScope:
    """Internal context scope for ExecutionContextManager."""

    def __init__(self, mgr: ExecutionContextManager, agent_name: str, task_name: str):
        self.mgr = mgr
        self.agent_name = agent_name
        self.task_name = task_name
        self._previous_context = None

    def __enter__(self):
        self._previous_context = self.mgr.get_context()
        self.mgr.set_context(self.agent_name, self.task_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._previous_context[0]:
            self.mgr.set_context(*self._previous_context)
        else:
            self.mgr.clear_context()
