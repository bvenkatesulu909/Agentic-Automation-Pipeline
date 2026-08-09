# CrewAI Tool Execution Tracer - Contribution Guide

## Overview

The CrewAI Tool Execution Tracer is a comprehensive observability system designed to trace and monitor tool executions within CrewAI agents. This guide covers the architecture, API, and contribution guidelines for this module.

## Project Structure

```
src/crewai_tool_tracer/
├── __init__.py                 # Package exports
├── tracer.py                   # Core ToolExecutionTracer implementation
├── exporters.py                # OTEL, Datadog, Langfuse exporters
├── structured_logging.py       # JSON structured logging system
├── tests/
│   └── test_tracer.py         # Unit tests
├── examples/
│   └── tool_tracer_example.py # Integration examples
└── docs/
    └── TOOL_TRACER_CONTRIBUTION.md  # This file
```

## Core Components

### 1. ToolExecutionTracer

The main class for tracing tool executions. Manages spans, metrics collection, and exports.

**Key Methods:**

- `trace_tool_call(tool_name, input, agent_name, task_name) -> span_id`
  - Starts tracing a tool call
  - Returns unique span ID for tracking
  - Records input data, agent, and task context

- `record_tool_result(span_id, result, duration_ms, success, error)`
  - Records completion of a tool call
  - Captures result data, execution time, and error information
  - Updates span status

- `get_tool_metrics(time_range, tool_name, agent_name) -> ToolMetrics`
  - Aggregates metrics across spans
  - Supports filtering by time range, tool name, and agent name
  - Returns: total executions, success rate, duration statistics, tools used

- `export_to_otel(spans)`
  - Exports spans to OpenTelemetry backend
  - Converts spans to OTEL trace format
  - Supports batch export

**Data Classes:**

- `ToolSpan`: Represents a single tool execution
  - Fields: span_id, tool_name, agent_name, task_name, input_data, status, timings, result, error, metadata, tags
  - Status values: PENDING, RUNNING, SUCCESS, ERROR, CANCELLED

- `ToolMetrics`: Aggregated statistics
  - Fields: total_executions, successful_executions, failed_executions, duration stats, error_rate, tool/agent breakdown

### 2. StructuredLogger

JSON-formatted logger for event-based logging.

**Key Methods:**

- `log_tool_call(tool_name, agent_name, task_name, input_data, span_id, metadata)`
  - Logs the start of a tool execution

- `log_tool_result(tool_name, span_id, result, duration_ms, success, error, metadata)`
  - Logs completion of a tool execution

- `log_agent_event(event_type, agent_name, task_name, message, metadata)`
  - Logs agent-level events

- `log_error(error_message, agent_name, tool_name, span_id, metadata)`
  - Logs errors with context

**Log Format:**

All logs are JSON-formatted for easy parsing:

```json
{
  "timestamp": "2024-08-09T10:30:45.123456",
  "logger": "crewai-tool-tracer",
  "level": "INFO",
  "message": "Tool execution completed",
  "event": {
    "event_type": "tool.result",
    "tool_name": "web_search",
    "span_id": "123e4567-e89b-12d3-a456-426614174000",
    "duration_ms": 245.5,
    "success": true
  }
}
```

### 3. Exporters

Multi-backend support for trace export.

#### OTelExporter
- Exports to OpenTelemetry collectors
- Supports both gRPC and HTTP endpoints
- Automatic resource and instrumentation setup

#### DatadogExporter
- Sends traces to Datadog APM
- Automatic span conversion to Datadog format
- Supports custom tags and metadata

#### LangfuseExporter
- Integrates with Langfuse for LLM observability
- Creates traces for tool executions
- Includes execution metrics and error tracking

#### CompositeExporter
- Sends to multiple backends simultaneously
- Useful for redundancy and multi-platform monitoring

## Integration with CrewAI

### Basic Integration Pattern

```python
from crewai import Agent, Task, Crew
from crewai_tool_tracer import ToolExecutionTracer, StructuredLogger
import time

# Initialize tracer and logger
tracer = ToolExecutionTracer(name="my-crew")
logger = StructuredLogger(name="my-crew-logger")

# Wrap tools with tracing
def traced_tool_call(tool, tool_name, agent_name, task_name):
    def wrapper(*args, **kwargs):
        # Start trace
        span_id = tracer.trace_tool_call(
            tool_name=tool_name,
            input_data={"args": str(args), "kwargs": kwargs},
            agent_name=agent_name,
            task_name=task_name,
        )
        
        start_time = time.time()
        try:
            # Execute tool
            result = tool(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            
            # Record success
            tracer.record_tool_result(
                span_id=span_id,
                result=result,
                duration_ms=duration_ms,
                success=True,
            )
            
            logger.log_tool_result(
                tool_name=tool_name,
                span_id=span_id,
                result=result,
                duration_ms=duration_ms,
                success=True,
            )
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            # Record failure
            tracer.record_tool_result(
                span_id=span_id,
                result=None,
                duration_ms=duration_ms,
                success=False,
                error=e,
            )
            
            logger.log_error(
                error_message=str(e),
                tool_name=tool_name,
                span_id=span_id,
            )
            
            raise
    
    return wrapper

# Use in agent creation
agent = Agent(
    role="Research Agent",
    goal="Find information",
    tools=[...],  # Pass traced tools here
)
```

### Advanced Integration with Tool Decorator

```python
from functools import wraps

def traced_crewai_tool(tracer, agent_name, task_name):
    """Decorator for CrewAI tools to enable automatic tracing."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            span_id = tracer.trace_tool_call(
                tool_name=func.__name__,
                input_data=kwargs,
                agent_name=agent_name,
                task_name=task_name,
            )
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                tracer.record_tool_result(
                    span_id=span_id,
                    result=result,
                    duration_ms=duration_ms,
                    success=True,
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                tracer.record_tool_result(
                    span_id=span_id,
                    result=None,
                    duration_ms=duration_ms,
                    success=False,
                    error=e,
                )
                raise
        return wrapper
    return decorator

# Usage:
@traced_crewai_tool(tracer, "research_agent", "research_task")
def search_web(query: str) -> str:
    # Tool implementation
    pass
```

## API Reference

### ToolExecutionTracer

```python
class ToolExecutionTracer:
    def __init__(
        self,
        name: str = "crewai-tracer",
        enable_structured_logging: bool = True,
        max_spans: int = 10000,
    ) -> None:
        """Initialize tracer."""

    def trace_tool_call(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        agent_name: str,
        task_name: str,
        tags: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start tracing a tool call. Returns span_id."""

    def record_tool_result(
        self,
        span_id: str,
        result: Any = None,
        duration_ms: float = 0.0,
        success: bool = True,
        error: Optional[Exception] = None,
    ) -> None:
        """Record tool execution result."""

    def get_tool_metrics(
        self,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        tool_name: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> ToolMetrics:
        """Get aggregated metrics."""

    def export_to_json(self, filepath: str, spans: Optional[List[ToolSpan]] = None) -> None:
        """Export spans to JSON file."""

    def export_to_otel(self, spans: Optional[List[ToolSpan]] = None) -> None:
        """Export to OpenTelemetry."""

    def export_to_datadog(self, spans: Optional[List[ToolSpan]] = None, api_key: Optional[str] = None) -> None:
        """Export to Datadog."""

    def export_to_langfuse(self, spans: Optional[List[ToolSpan]] = None, api_key: Optional[str] = None) -> None:
        """Export to Langfuse."""
```

## Configuration

### Environment Variables

- `OTEL_EXPORTER_OTLP_ENDPOINT`: OpenTelemetry collector endpoint (default: http://localhost:4317)
- `DD_API_KEY`: Datadog API key
- `LANGFUSE_PUBLIC_KEY`: Langfuse public API key
- `LANGFUSE_SECRET_KEY`: Langfuse secret API key
- `LANGFUSE_HOST`: Langfuse host (default: https://cloud.langfuse.com)

## Testing

Run tests with pytest:

```bash
pytest src/crewai_tool_tracer/tests/test_tracer.py -v
```

Test coverage includes:
- Basic tracing functionality
- Metrics calculation and filtering
- JSON export
- Structured logging
- Exporter initialization and conversion

## Performance Considerations

1. **Memory Management**: By default, keeps last 10,000 spans. Configure with `max_spans` parameter.
2. **Async Export**: Use CompositeExporter for multi-backend export without blocking.
3. **Metrics Calculation**: Filtered metrics use in-memory filtering. For large datasets, consider periodic export and clearing.

## Contributing

### Guidelines

1. **Code Style**: Follow PEP 8
2. **Type Hints**: All functions must have type hints
3. **Tests**: Add tests for new features (minimum 80% coverage)
4. **Documentation**: Update docstrings and README
5. **Error Handling**: Use logging for errors, not silent failures

### Adding New Exporters

To add a new exporter:

1. Create class inheriting from `BaseExporter`
2. Implement `export(spans: List[ToolSpan]) -> bool` method
3. Add tests in `test_tracer.py`
4. Export in `__init__.py`

Example:

```python
class CustomExporter(BaseExporter):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def export(self, spans: List[ToolSpan]) -> bool:
        """Export spans to custom backend."""
        try:
            # Convert spans and send to backend
            data = self._convert_spans(spans)
            self._send_to_backend(data)
            return True
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False
    
    def _convert_spans(self, spans: List[ToolSpan]) -> Dict[str, Any]:
        """Convert ToolSpan to custom format."""
        pass
    
    def _send_to_backend(self, data: Dict[str, Any]) -> None:
        """Send data to backend."""
        pass
```

## Examples

See `examples/tool_tracer_example.py` for comprehensive examples including:
- Basic tracing
- Structured logging
- Multiple tool tracking
- Filtered metrics
- JSON export
- CrewAI integration patterns

## License

This contribution follows the same license as the main CrewAI project.

## Support

For issues, questions, or feature requests, please open an issue on GitHub or contact the maintainers.
