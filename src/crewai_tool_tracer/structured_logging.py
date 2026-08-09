"""
Structured logging for CrewAI tool executions.

Provides JSON-formatted logging for tool execution events,
enabling easier parsing and analysis by log aggregation tools.
"""

import json
import logging
import sys
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pathlib import Path


class LogLevel(Enum):
    """Log levels for structured logging."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredLogger:
    """
    JSON-formatted logger for tool execution events.

    Outputs structured logs that can be easily parsed by log aggregation
    tools like Datadog, Splunk, ELK, etc.
    """

    def __init__(
        self,
        name: str = "crewai-tool-tracer",
        log_file: Optional[str] = None,
        level: LogLevel = LogLevel.INFO,
    ):
        """
        Initialize structured logger.

        Args:
            name: Logger name
            log_file: Optional file path for logging output
            level: Minimum log level
        """
        self.name = name
        self.log_file = log_file
        self.level = level
        self._logger = logging.getLogger(name)
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup logging handlers for console and file output."""
        self._logger.setLevel(self.level.value)

        # Remove existing handlers
        self._logger.handlers = []

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(JSONFormatter())
        self._logger.addHandler(console_handler)

        # File handler (if log_file specified)
        if self.log_file:
            Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setFormatter(JSONFormatter())
            self._logger.addHandler(file_handler)

    def log_tool_call(
        self,
        tool_name: str,
        agent_name: str,
        task_name: str,
        input_data: Dict[str, Any],
        span_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log a tool call event.

        Args:
            tool_name: Name of the tool
            agent_name: Name of the agent
            task_name: Name of the task
            input_data: Input to the tool
            span_id: Unique span identifier
            metadata: Optional additional metadata
        """
        event = {
            "event_type": "tool.call",
            "timestamp": datetime.utcnow().isoformat(),
            "tool_name": tool_name,
            "agent_name": agent_name,
            "task_name": task_name,
            "span_id": span_id,
            "input": self._serialize_data(input_data),
        }

        if metadata:
            event["metadata"] = metadata

        self._logger.info("Tool call initiated", extra={"event": event})

    def log_tool_result(
        self,
        tool_name: str,
        span_id: str,
        result: Any,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log a tool result event.

        Args:
            tool_name: Name of the tool
            span_id: Unique span identifier
            result: Result from the tool
            duration_ms: Execution duration in milliseconds
            success: Whether execution was successful
            error: Error message if execution failed
            metadata: Optional additional metadata
        """
        event = {
            "event_type": "tool.result",
            "timestamp": datetime.utcnow().isoformat(),
            "tool_name": tool_name,
            "span_id": span_id,
            "duration_ms": duration_ms,
            "success": success,
            "result": self._serialize_data(result),
        }

        if error:
            event["error"] = error

        if metadata:
            event["metadata"] = metadata

        log_level = "INFO" if success else "WARNING"
        if log_level == "INFO":
            self._logger.info("Tool execution completed", extra={"event": event})
        else:
            self._logger.warning("Tool execution failed", extra={"event": event})

    def log_agent_event(
        self,
        event_type: str,
        agent_name: str,
        task_name: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an agent-level event.

        Args:
            event_type: Type of event (e.g., "agent.start", "agent.complete")
            agent_name: Name of the agent
            task_name: Name of the task
            message: Event description
            metadata: Optional additional metadata
        """
        event = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "agent_name": agent_name,
            "task_name": task_name,
            "message": message,
        }

        if metadata:
            event["metadata"] = metadata

        self._logger.info(f"Agent event: {event_type}", extra={"event": event})

    def log_error(
        self,
        error_message: str,
        agent_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an error event.

        Args:
            error_message: Error description
            agent_name: Optional agent name
            tool_name: Optional tool name
            span_id: Optional span identifier
            metadata: Optional additional metadata
        """
        event = {
            "event_type": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "error_message": error_message,
        }

        if agent_name:
            event["agent_name"] = agent_name

        if tool_name:
            event["tool_name"] = tool_name

        if span_id:
            event["span_id"] = span_id

        if metadata:
            event["metadata"] = metadata

        self._logger.error("Error occurred", extra={"event": event})

    def _serialize_data(self, data: Any) -> Any:
        """
        Safely serialize data for JSON logging.

        Handles common types and converts unsupported types to strings.
        """
        if data is None:
            return None

        if isinstance(data, (str, int, float, bool)):
            return data

        if isinstance(data, dict):
            return {k: self._serialize_data(v) for k, v in data.items()}

        if isinstance(data, (list, tuple)):
            return [self._serialize_data(item) for item in data]

        # Convert other types to string
        return str(data)


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON-structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat(),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Include structured event if present
        if hasattr(record, "event"):
            log_data["event"] = record.event
        else:
            # Fallback for non-structured logs
            log_data["message"] = record.getMessage()

        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class LogAggregator:
    """
    Aggregates logs from multiple sources for analysis.

    Useful for collecting and summarizing tool execution logs.
    """

    def __init__(self, log_file: str):
        """
        Initialize log aggregator.

        Args:
            log_file: Path to JSON log file
        """
        self.log_file = log_file
        self._logs = []

    def load_logs(self) -> int:
        """
        Load logs from file.

        Returns:
            int: Number of logs loaded
        """
        self._logs = []

        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        self._logs.append(log_entry)
                    except json.JSONDecodeError:
                        continue

        except FileNotFoundError:
            pass

        return len(self._logs)

    def get_logs_by_event_type(self, event_type: str) -> list:
        """Get logs filtered by event type."""
        return [log for log in self._logs if log.get("event", {}).get("event_type") == event_type]

    def get_logs_by_tool(self, tool_name: str) -> list:
        """Get logs filtered by tool name."""
        return [log for log in self._logs if log.get("event", {}).get("tool_name") == tool_name]

    def get_logs_by_agent(self, agent_name: str) -> list:
        """Get logs filtered by agent name."""
        return [log for log in self._logs if log.get("event", {}).get("agent_name") == agent_name]

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics from logs."""
        if not self._logs:
            return {}

        tool_calls = self.get_logs_by_event_type("tool.call")
        tool_results = self.get_logs_by_event_type("tool.result")

        successful = len([log for log in tool_results if log.get("event", {}).get("success", False)])
        failed = len([log for log in tool_results if not log.get("event", {}).get("success", True)])

        durations = [log.get("event", {}).get("duration_ms", 0) for log in tool_results]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_tool_calls": len(tool_calls),
            "total_tool_results": len(tool_results),
            "successful_executions": successful,
            "failed_executions": failed,
            "average_duration_ms": avg_duration,
            "total_logs": len(self._logs),
        }
