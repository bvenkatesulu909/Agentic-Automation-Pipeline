# CrewAI Tool Execution Tracer - Quick Start Guide

Get up and running in 5 minutes with the CrewAI Tool Execution Tracer.

## Installation

```bash
# Core dependencies (optional, based on what you need)
pip install opentelemetry-exporter-otlp  # For OpenTelemetry
pip install requests                      # For Datadog
pip install langfuse                      # For Langfuse
```

## 1-Minute Quickstart

### Basic Tracing

```python
from crewai_tool_tracer import ToolExecutionTracer, traced_tool

# Create tracer
tracer = ToolExecutionTracer(name="my-crew")

# Add @traced_tool decorator to any tool
@traced_tool(tracer, agent_name="research_agent", task_name="search")
def search_web(query: str) -> str:
    # Your tool implementation
    return search_results

# Use tools normally - tracing is automatic!
result = search_web("What is AI?")

# Get metrics
metrics = tracer.get_tool_metrics()
print(f"Executed {metrics.total_executions} tools")
print(f"Success rate: {1 - metrics.error_rate:.1%}")
```

That's it! Your tools are now traced.

## Common Patterns

### Pattern 1: Quick Integration (Decorator)

```python
from crewai_tool_tracer import ToolExecutionTracer, traced_tool

tracer = ToolExecutionTracer(name="crew")

@traced_tool(tracer, agent_name="agent1", task_name="task1")
def my_tool(param):
    return result
```

### Pattern 2: Production Setup

```python
from crewai_tool_tracer import (
    ToolExecutionTracer,
    StructuredLogger,
    DatadogExporter,
    ToolExecutionMonitor,
)

# Setup
tracer = ToolExecutionTracer(name="prod-crew")
logger = StructuredLogger(log_file="crew.log")
monitor = ToolExecutionMonitor(tracer)

# Set performance thresholds
monitor.set_max_duration("search", 5000)  # 5 seconds
monitor.set_min_success_rate("search", 0.95)  # 95%

# Decorate tools
@traced_tool(tracer, agent_name="agent", task_name="task")
def search(query):
    return results

# Periodically check SLOs
violations = monitor.check_slos()

# Export to Datadog
exporter = DatadogExporter()
exporter.export(tracer.get_all_spans())
```

### Pattern 3: Async Tools

```python
from crewai_tool_tracer import AsyncToolExecutionTracer
from crewai_tool_tracer.decorators import traced_async_tool

tracer = AsyncToolExecutionTracer(name="async-crew")

@traced_async_tool(tracer, agent_name="agent", task_name="task")
async def async_search(query):
    return await fetch_results(query)
```

### Pattern 4: Wrap Existing Tools

```python
from crewai_tool_tracer import ToolExecutionTracer
from crewai_tool_tracer.decorators import create_traced_tools

tracer = ToolExecutionTracer(name="crew")

# Wrap existing tools without modifying them
traced_tools = create_traced_tools(
    tools=[tool1, tool2, tool3],
    tracer=tracer,
    agent_name="agent",
    task_name="task",
)

agent = Agent(tools=traced_tools)
```

### Pattern 5: Task-Level Tracing

```python
from crewai_tool_tracer.integration import trace_crewai_execution

with trace_crewai_execution(tracer, "agent", "task", logger):
    result = agent.execute_task(task)
    # All tool calls are automatically traced

metrics = tracer.get_tool_metrics()
```

## Getting Metrics

```python
# All executions
metrics = tracer.get_tool_metrics()

# Specific tool
metrics = tracer.get_tool_metrics(tool_name="web_search")

# Specific agent
metrics = tracer.get_tool_metrics(agent_name="research_agent")

# Time-based
from datetime import datetime, timedelta
start = datetime.utcnow() - timedelta(hours=1)
end = datetime.utcnow()
metrics = tracer.get_tool_metrics(time_range=(start, end))

# Combine filters
metrics = tracer.get_tool_metrics(
    tool_name="web_search",
    agent_name="research_agent",
    time_range=(start, end),
)

# Access metrics
print(f"Total: {metrics.total_executions}")
print(f"Success rate: {1 - metrics.error_rate:.1%}")
print(f"Avg duration: {metrics.average_duration_ms:.0f}ms")
print(f"Min/Max: {metrics.min_duration_ms:.0f}ms / {metrics.max_duration_ms:.0f}ms")
```

## Structured Logging

```python
from crewai_tool_tracer import StructuredLogger

logger = StructuredLogger(
    name="crew",
    log_file="crew_execution.log",
)

# Logs are JSON-formatted and go to both console and file
# Useful for parsing with log aggregation tools (ELK, Splunk, Datadog)
```

## Export Options

### Export to JSON (Local Analysis)

```python
tracer.export_to_json("traces.json")
```

### Export to OpenTelemetry

```python
from crewai_tool_tracer import OTelExporter

otel = OTelExporter(
    endpoint="http://localhost:4317",
    service_name="my-crew",
)
otel.export(tracer.get_all_spans())
```

### Export to Datadog

```python
from crewai_tool_tracer import DatadogExporter
import os

dd = DatadogExporter(
    api_key=os.getenv("DD_API_KEY"),
    service_name="my-crew",
)
dd.export(tracer.get_all_spans())
```

### Export to Langfuse

```python
from crewai_tool_tracer import LangfuseExporter
import os

lf = LangfuseExporter(
    api_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
)
lf.export(tracer.get_all_spans())
```

### Export to Multiple Platforms

```python
from crewai_tool_tracer import CompositeExporter

composite = CompositeExporter([otel, dd, lf])
composite.export(tracer.get_all_spans())
```

## Performance Monitoring

```python
from crewai_tool_tracer.integration import ToolExecutionMonitor

monitor = ToolExecutionMonitor(tracer)

# Set thresholds
monitor.set_max_duration("search", 5000)  # 5 seconds
monitor.set_min_success_rate("search", 0.95)  # 95%

# Check for violations
violations = monitor.check_slos()

if violations:
    for v in violations:
        print(f"⚠️  {v['message']}")
    # Send alert, scale resources, etc.
else:
    print("✅ All SLOs met")
```

## Tool Chain Tracking

```python
from crewai_tool_tracer.async_tracer import ToolChainTracker

tracker = ToolChainTracker(tracer)

# Link dependent tools
tracker.link_spans(parent_span_id, child_span_id)

# Analyze chains
chains = tracker.get_agent_chains("research_agent")
for root, chain in chains.items():
    metrics = tracker.analyze_chain_metrics(chain)
    print(f"Chain: {metrics['tools_in_chain']}")
    print(f"Total time: {metrics['total_duration_ms']:.0f}ms")
    print(f"Bottleneck: {metrics['bottleneck_tool']}")
```

## Multi-Agent Context

```python
from crewai_tool_tracer.integration import ExecutionContextManager

ctx = ExecutionContextManager(tracer)

for agent in agents:
    with ctx.as_context_manager(agent.name, task.name):
        agent.execute_task(task)
        # Tools automatically traced with agent/task context
```

## Environment Variables

```bash
# Set these for automatic configuration
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export DD_API_KEY=your_datadog_api_key
export LANGFUSE_PUBLIC_KEY=your_public_key
export LANGFUSE_SECRET_KEY=your_secret_key
export LANGFUSE_HOST=https://cloud.langfuse.com
```

## Common Issues

### Tools not being traced
- ✅ Add `@traced_tool` decorator
- ✅ Or use `create_traced_tools()` wrapper

### Missing context (agent_name/task_name)
- ✅ Explicitly pass to decorator: `@traced_tool(tracer, agent_name="x", task_name="y")`
- ✅ Or use context manager: `with trace_crewai_execution(...)`

### Export failures
- ✅ Check credentials in environment variables
- ✅ Verify endpoints are accessible
- ✅ Check API key validity

### Performance degradation
- ✅ Reduce `max_spans` in ToolExecutionTracer
- ✅ Periodically export and clear spans
- ✅ Use async export with CompositeExporter

## Real-World Example

```python
from crewai import Agent, Task, Crew
from crewai_tool_tracer import (
    ToolExecutionTracer,
    StructuredLogger,
    DatadogExporter,
)
from crewai_tool_tracer.decorators import traced_tool
from crewai_tool_tracer.integration import (
    trace_crewai_execution,
    ToolExecutionMonitor,
)

# Setup
tracer = ToolExecutionTracer(name="market-research")
logger = StructuredLogger(log_file="research.log")
monitor = ToolExecutionMonitor(tracer)
exporter = DatadogExporter()

# Set SLOs
monitor.set_max_duration("search", 5000)
monitor.set_min_success_rate("search", 0.9)

# Define tools
@traced_tool(tracer, agent_name="researcher", task_name="research")
def search_web(query: str) -> str:
    # Implementation
    return results

# Create agents
researcher = Agent(
    role="Researcher",
    tools=[search_web],
)

# Execute with tracing
with trace_crewai_execution(tracer, "researcher", "research_task", logger):
    crew = Crew(agents=[researcher], tasks=[...])
    result = crew.kickoff()

# Monitor results
violations = monitor.check_slos()
if violations:
    print(f"⚠️  {len(violations)} SLO violations")

metrics = tracer.get_tool_metrics()
print(f"✅ Executed {metrics.total_executions} tools")

# Export
exporter.export(tracer.get_all_spans())
tracer.export_to_json("traces.json")
```

## Next Steps

1. **Read the Integration Guide**: `docs/CREWAI_INTEGRATION_GUIDE.md`
2. **Check the API Reference**: `docs/API_REFERENCE.md`
3. **Run Examples**: `examples/crewai_complete_integration.py`
4. **Run Tests**: `pytest tests/test_tracer.py -v`

## Support

- 📖 Documentation: See `docs/` directory
- 💡 Examples: See `examples/` directory
- 🧪 Tests: See `tests/` directory
- 🐛 Issues: Check GitHub issues

---

**Happy tracing! 🚀**
