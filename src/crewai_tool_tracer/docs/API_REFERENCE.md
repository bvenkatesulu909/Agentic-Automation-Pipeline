# CrewAI Tool Execution Tracer - API Reference

Complete API documentation for all classes, methods, and functions.

## Core Tracer

### ToolExecutionTracer

Main tracer class for tracking tool executions.

```python
class ToolExecutionTracer:
    """
    Main tracer class for tracking CrewAI tool executions.
    
    Manages spans, metrics collection, and export capabilities.
    """
```

#### Methods

##### `__init__(name, enable_structured_logging, max_spans)`

Initialize the tracer.

```python
tracer = ToolExecutionTracer(
    name="my-crew",
    enable_structured_logging=True,
    max_spans=10000,
)
```

**Parameters:**
- `name` (str): Identifier for tracer instance
- `enable_structured_logging` (bool): Enable JSON structured logging
- `max_spans` (int): Maximum spans to keep in memory

##### `trace_tool_call(...) -> str`

Start tracing a tool call.

```python
span_id = tracer.trace_tool_call(
    tool_name="web_search",
    input_data={"query": "python"},
    agent_name="research_agent",
    task_name="search_task",
    tags={"batch": "exp1"},
    metadata={"model": "gpt-4"},
)
```

**Parameters:**
- `tool_name` (str): Name of tool being called
- `input_data` (Dict[str, Any]): Input to the tool
- `agent_name` (str): Name of executing agent
- `task_name` (str): Name of executing task
- `tags` (Optional[Dict[str, str]]): String tags for span
- `metadata` (Optional[Dict[str, Any]]): Additional metadata

**Returns:** `str` - Unique span ID

##### `record_tool_result(...)`

Record tool execution result.

```python
tracer.record_tool_result(
    span_id=span_id,
    result={"answer": "Python is..."},
    duration_ms=245.5,
    success=True,
)
```

**Parameters:**
- `span_id` (str): Span ID from trace_tool_call()
- `result` (Any): Result from tool
- `duration_ms` (float): Execution duration in ms
- `success` (bool): Whether execution succeeded
- `error` (Optional[Exception]): Exception if failed

##### `get_tool_metrics(...) -> ToolMetrics`

Calculate aggregated metrics.

```python
metrics = tracer.get_tool_metrics(
    time_range=(start_time, end_time),
    tool_name="web_search",
    agent_name="research_agent",
)
```

**Parameters:**
- `time_range` (Optional[Tuple[datetime, datetime]]): Time filter
- `tool_name` (Optional[str]): Tool name filter
- `agent_name` (Optional[str]): Agent name filter

**Returns:** `ToolMetrics` - Aggregated statistics

##### `get_span(span_id) -> Optional[ToolSpan]`

Retrieve a specific span.

```python
span = tracer.get_span(span_id)
print(f"Tool: {span.tool_name}, Status: {span.status}")
```

##### `get_all_spans() -> List[ToolSpan]`

Get all recorded spans.

```python
all_spans = tracer.get_all_spans()
for span in all_spans:
    print(f"{span.tool_name}: {span.duration_ms}ms")
```

##### `export_to_json(filepath, spans)`

Export spans to JSON file.

```python
tracer.export_to_json(
    filepath="traces.json",
    spans=None,  # None = all spans
)
```

##### `clear_spans()`

Clear all recorded spans.

```python
tracer.clear_spans()
```

### ToolSpan

Dataclass representing a single tool execution.

```python
@dataclass
class ToolSpan:
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
```

**Methods:**
- `to_dict() -> Dict[str, Any]`: Convert to JSON-serializable dict

### ToolMetrics

Aggregated metrics for tool executions.

```python
@dataclass
class ToolMetrics:
    total_executions: int
    successful_executions: int
    failed_executions: int
    total_duration_ms: float
    average_duration_ms: float
    min_duration_ms: Optional[float]
    max_duration_ms: Optional[float]
    error_rate: float
    tools_executed: Dict[str, int]
    agents_involved: Dict[str, int]
    time_range_start: Optional[datetime]
    time_range_end: Optional[datetime]
```

**Methods:**
- `to_dict() -> Dict[str, Any]`: Convert to dict

### SpanStatus

Enum for span status.

```python
class SpanStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"
```

## Async Support

### AsyncToolExecutionTracer

Extended tracer with async/await support.

```python
class AsyncToolExecutionTracer(ToolExecutionTracer):
    """Tracer with proper async context propagation."""
```

**Additional Methods:**

##### `trace_async_tool_call(...) -> str`

Start tracing async tool call (async version).

```python
span_id = await tracer.trace_async_tool_call(
    tool_name="async_search",
    input_data={"query": "python"},
    agent_name="async_agent",
    task_name="search_task",
)
```

##### `record_async_tool_result(...)`

Record async tool result (async version).

```python
await tracer.record_async_tool_result(
    span_id=span_id,
    result=result,
    duration_ms=duration,
    success=True,
)
```

##### `get_current_span_id() -> Optional[str]`

Get current span ID in context.

```python
current_id = tracer.get_current_span_id()
```

### ToolChainTracker

Track tool execution dependencies and chains.

```python
class ToolChainTracker:
    """Tracks dependencies between tool executions."""
```

**Methods:**

##### `__init__(tracer)`

Initialize tracker.

```python
tracker = ToolChainTracker(tracer)
```

##### `link_spans(parent_span_id, child_span_id)`

Link child span to parent (dependency).

```python
tracker.link_spans(parent_id, child_id)
```

##### `get_execution_chain(span_id) -> list`

Get full execution chain for a span.

```python
chain = tracker.get_execution_chain(span_id)
# Returns: [ancestor_id, ..., span_id, ..., descendant_id]
```

##### `get_agent_chains(agent_name) -> Dict[str, list]`

Get all execution chains for an agent.

```python
chains = tracker.get_agent_chains("research_agent")
# Returns: {root_span_id: [span_id_1, span_id_2, ...], ...}
```

##### `analyze_chain_metrics(chain) -> Dict[str, Any]`

Analyze metrics for a chain.

```python
metrics = tracker.analyze_chain_metrics(chain)
# Returns: {
#     "chain_length": 5,
#     "total_duration_ms": 1500.0,
#     "success_rate": 0.95,
#     "bottleneck_tool": "web_search",
#     ...
# }
```

## Decorators

### @traced_tool

Decorator for synchronous tools.

```python
@traced_tool(
    tracer,
    agent_name="research_agent",
    task_name="search_task",
    tool_name="web_search",  # Optional, defaults to function name
)
def search(query: str) -> str:
    return results
```

**Features:**
- Automatic span creation and completion
- Duration measurement
- Exception capture
- Input/output logging

### @traced_async_tool

Decorator for async tools.

```python
@traced_async_tool(
    tracer,
    agent_name="async_agent",
    task_name="search_task",
)
async def async_search(query: str) -> str:
    return await fetch_results(query)
```

### ToolWrapper

Wrapper class for runtime tool wrapping.

```python
class ToolWrapper:
    def __init__(
        self,
        tool: Callable,
        tracer: ToolExecutionTracer,
        agent_name: str,
        task_name: str,
        tool_name: Optional[str] = None,
    ):
        """Wrap a tool with automatic tracing."""
```

**Example:**
```python
original = get_tool()
wrapped = ToolWrapper(original, tracer, "agent", "task")
result = wrapped(param="value")
```

### create_traced_tools

Create traced versions of multiple tools.

```python
traced_tools = create_traced_tools(
    tools=[tool1, tool2, tool3],
    tracer=tracer,
    agent_name="research_agent",
    task_name="search_task",
)
```

## Structured Logging

### StructuredLogger

JSON-formatted event logger.

```python
class StructuredLogger:
    """JSON-formatted logger for tool execution events."""
```

#### Methods

##### `__init__(name, log_file, level)`

Initialize logger.

```python
logger = StructuredLogger(
    name="crew-logger",
    log_file="crew.log",
    level=LogLevel.INFO,
)
```

**Parameters:**
- `name` (str): Logger name
- `log_file` (Optional[str]): File path for logging
- `level` (LogLevel): Minimum log level

##### `log_tool_call(...)`

Log tool call event.

```python
logger.log_tool_call(
    tool_name="web_search",
    agent_name="research_agent",
    task_name="search_task",
    input_data={"query": "python"},
    span_id="uuid",
    metadata={"retry": 1},
)
```

##### `log_tool_result(...)`

Log tool result event.

```python
logger.log_tool_result(
    tool_name="web_search",
    span_id="uuid",
    result={"answer": "..."},
    duration_ms=245.5,
    success=True,
    error=None,
)
```

##### `log_agent_event(...)`

Log agent-level event.

```python
logger.log_agent_event(
    event_type="agent.start",
    agent_name="research_agent",
    task_name="search_task",
    message="Starting task",
    metadata={"priority": "high"},
)
```

##### `log_error(...)`

Log error event.

```python
logger.log_error(
    error_message="Tool execution failed",
    agent_name="research_agent",
    tool_name="web_search",
    span_id="uuid",
)
```

### LogLevel

Enum for log levels.

```python
class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
```

### LogAggregator

Aggregates logs from file for analysis.

```python
class LogAggregator:
    """Loads and analyzes JSON logs from file."""
```

**Methods:**

##### `load_logs() -> int`

Load logs from file.

```python
count = aggregator.load_logs()
```

##### `get_logs_by_event_type(event_type) -> list`

Filter logs by event type.

```python
results = aggregator.get_logs_by_event_type("tool.result")
```

##### `get_logs_by_tool(tool_name) -> list`

Filter logs by tool name.

```python
logs = aggregator.get_logs_by_tool("web_search")
```

##### `get_logs_by_agent(agent_name) -> list`

Filter logs by agent name.

```python
logs = aggregator.get_logs_by_agent("research_agent")
```

##### `get_summary_stats() -> Dict[str, Any]`

Get summary statistics.

```python
stats = aggregator.get_summary_stats()
# Returns: {
#     "total_tool_calls": 100,
#     "successful_executions": 95,
#     "failed_executions": 5,
#     "average_duration_ms": 234.5,
#     ...
# }
```

## Exporters

### BaseExporter

Abstract base class for all exporters.

```python
class BaseExporter(ABC):
    @abstractmethod
    def export(self, spans: List[ToolSpan]) -> bool:
        """Export spans to target platform."""
```

### OTelExporter

Export to OpenTelemetry.

```python
class OTelExporter(BaseExporter):
    def __init__(
        self,
        endpoint: Optional[str] = None,
        service_name: str = "crewai-tools",
        service_version: str = "0.1.0",
    ):
        """Initialize OTEL exporter."""
```

**Example:**
```python
otel = OTelExporter(
    endpoint="http://localhost:4317",
    service_name="my-crew",
)
success = otel.export(tracer.get_all_spans())
```

### DatadogExporter

Export to Datadog APM.

```python
class DatadogExporter(BaseExporter):
    def __init__(
        self,
        api_key: Optional[str] = None,
        site: str = "datadoghq.com",
        service_name: str = "crewai-tools",
    ):
        """Initialize Datadog exporter."""
```

**Example:**
```python
dd = DatadogExporter(
    api_key="YOUR_DD_API_KEY",
    site="datadoghq.com",
)
success = dd.export(tracer.get_all_spans())
```

### LangfuseExporter

Export to Langfuse.

```python
class LangfuseExporter(BaseExporter):
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        host: Optional[str] = None,
    ):
        """Initialize Langfuse exporter."""
```

**Example:**
```python
lf = LangfuseExporter(
    api_key="YOUR_LANGFUSE_API_KEY",
    secret_key="YOUR_LANGFUSE_SECRET",
)
success = lf.export(tracer.get_all_spans())
```

### CompositeExporter

Export to multiple platforms simultaneously.

```python
class CompositeExporter(BaseExporter):
    def __init__(self, exporters: List[BaseExporter]):
        """Combine multiple exporters."""
```

**Example:**
```python
composite = CompositeExporter([otel, dd, lf])
success = composite.export(tracer.get_all_spans())
```

## CrewAI Integration

### CrewAIToolHook

Hook-based integration with CrewAI.

```python
class CrewAIToolHook:
    """Integrate with CrewAI @on() hooks."""
```

**Methods:**

##### `on_tool_call_pre(...) -> str`

PRE_TOOL_CALL hook handler.

```python
span_id = hook.on_tool_call_pre(
    tool_name="web_search",
    tool_args={"query": "python"},
    agent_name="research",
    task_name="search",
)
```

**Returns:** `str` - Span ID for correlation

##### `on_tool_call_post(...)`

POST_TOOL_CALL hook handler.

```python
hook.on_tool_call_post(
    span_id=span_id,
    tool_result=result,
    error=None,
)
```

### CrewAITaskContext

Context manager for task execution.

```python
class CrewAITaskContext:
    """Context manager for task-level tracing."""
```

**Example:**
```python
with CrewAITaskContext(tracer, "agent", "task"):
    # Tool calls within block are traced with task context
    agent.execute_task(task)
```

### trace_crewai_execution

Context manager for full execution tracing.

```python
@contextmanager
def trace_crewai_execution(
    tracer: ToolExecutionTracer,
    agent_name: str,
    task_name: str,
    logger_instance: Optional[StructuredLogger] = None,
):
    """Trace complete execution with logging."""
```

**Example:**
```python
with trace_crewai_execution(tracer, "agent", "task", logger):
    result = agent.execute_task(task)
```

### ToolExecutionMonitor

Monitor tool performance against SLOs.

```python
class ToolExecutionMonitor:
    """Monitor execution metrics and enforce SLOs."""
```

**Methods:**

##### `set_max_duration(tool_name, max_ms)`

Set maximum execution time.

```python
monitor.set_max_duration("web_search", 5000)  # 5 seconds
```

##### `set_min_success_rate(tool_name, min_rate)`

Set minimum success rate.

```python
monitor.set_min_success_rate("web_search", 0.95)  # 95%
```

##### `check_slos() -> list`

Check for SLO violations.

```python
violations = monitor.check_slos()
for v in violations:
    print(v['message'])
```

### ExecutionContextManager

Manage agent/task context automatically.

```python
class ExecutionContextManager:
    """Manage execution context for multi-agent scenarios."""
```

**Methods:**

##### `set_context(agent_name, task_name)`

Set current context.

```python
ctx.set_context("research_agent", "search_task")
```

##### `get_context() -> tuple`

Get current context.

```python
agent, task = ctx.get_context()
```

##### `as_context_manager(agent_name, task_name)`

Context manager for scoped context.

```python
with ctx.as_context_manager("agent", "task"):
    # Scoped context
    pass
```

## Environment Variables

All exporters support environment variable configuration:

```bash
# OpenTelemetry
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Datadog
DD_API_KEY=your_api_key

# Langfuse
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com
```

## Exceptions

### ValueError

Raised when:
- Unknown span_id passed to record_tool_result()
- Required parameters missing

### ImportError

Raised when:
- Optional dependencies not installed (handled gracefully)

### Exception

Caught and logged for:
- Export failures
- Serialization errors
- Logger initialization failures
