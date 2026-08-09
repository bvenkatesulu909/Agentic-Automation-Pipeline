# CrewAI Tool Execution Tracer - Enhanced Quick Start Guide

Get fully set up and productive with the CrewAI Tool Execution Tracer in 15 minutes or less.

## Table of Contents

1. [Installation](#installation)
2. [Your First Trace (2 minutes)](#your-first-trace)
3. [5 Common Usage Patterns](#5-common-usage-patterns)
4. [API Method Cheat Sheet](#api-method-cheat-sheet)
5. [Common Issues and Solutions](#common-issues-and-solutions)
6. [Exporter Setup](#exporter-setup)
7. [Performance Monitoring](#performance-monitoring)
8. [Real-World Workflow](#real-world-workflow)

---

## Installation

### Step 1: Install Core Package

```bash
# Minimal installation (no exporters)
pip install crewai-tool-tracer

# Or install with all optional dependencies
pip install crewai-tool-tracer[all]
```

### Step 2: Optional - Install Specific Exporters

```bash
# For OpenTelemetry
pip install opentelemetry-exporter-otlp opentelemetry-api

# For Datadog
pip install requests

# For Langfuse
pip install langfuse
```

### Step 3: Verify Installation

```python
from crewai_tool_tracer import ToolExecutionTracer, traced_tool
print("✅ CrewAI Tool Execution Tracer installed successfully!")
```

---

## Your First Trace

### The Simplest Possible Setup

Copy and paste this example, change one line, and you're done:

```python
from crewai_tool_tracer import ToolExecutionTracer, traced_tool

# 1. Create a tracer
tracer = ToolExecutionTracer(name="my-crew")

# 2. Decorate your tool
@traced_tool(tracer, agent_name="agent", task_name="task")
def my_tool(query: str) -> str:
    return f"Result for: {query}"

# 3. Use it normally
result = my_tool("test query")

# 4. Check metrics
metrics = tracer.get_tool_metrics()
print(f"Executed {metrics.total_executions} tools")
print(f"Success rate: {1 - metrics.error_rate:.1%}")

# Output:
# Executed 1 tools
# Success rate: 100.0%
```

**That's it!** Your tools are now being traced.

### Understanding What Just Happened

```
When you called my_tool("test query"):

1. @traced_tool decorator caught the call
2. Created a unique span ID
3. Recorded: tool_name, inputs, agent_name, task_name
4. Measured execution time (0.15ms overhead)
5. Recorded result and success status
6. All data available via tracer.get_tool_metrics()
```

---

## 5 Common Usage Patterns

### Pattern 1: Quick Integration (Best for Existing Tools)

**Scenario**: You have existing CrewAI tools and want tracing with minimal changes.

```python
from crewai_tool_tracer import ToolExecutionTracer, traced_tool

tracer = ToolExecutionTracer(name="crew")

# Just add @traced_tool decorator
@traced_tool(tracer, agent_name="researcher", task_name="search")
def search_web(query: str) -> list:
    """Search the web."""
    return search_results

# Use tools normally
agent = Agent(tools=[search_web])
# Tracing happens automatically!
```

**Advantages**:
- Minimal code changes
- Works with existing tools
- No context manager needed

---

### Pattern 2: Production Setup with SLOs

**Scenario**: Production environment where you need to monitor SLO compliance.

```python
from crewai_tool_tracer import (
    ToolExecutionTracer,
    StructuredLogger,
    DatadogExporter,
    traced_tool,
)
from crewai_tool_tracer.integration import ToolExecutionMonitor

# Setup components
tracer = ToolExecutionTracer(name="prod-crew", max_spans=50000)
logger = StructuredLogger(log_file="/var/log/crew.jsonl")
monitor = ToolExecutionMonitor(tracer)
exporter = DatadogExporter()

# Define SLOs
monitor.set_max_duration("search", 5000)  # 5 seconds
monitor.set_min_success_rate("search", 0.95)  # 95%

# Decorate critical tools
@traced_tool(tracer, agent_name="researcher", task_name="search")
def search(query: str) -> dict:
    return search_results

# Periodic monitoring
import schedule

def check_slos():
    violations = monitor.check_slos()
    if violations:
        for v in violations:
            send_alert(v['message'])
        exporter.export(tracer.get_all_spans())
        tracer.clear_spans()

schedule.every(5).minutes.do(check_slos)

# In your application loop:
while True:
    schedule.run_pending()
    time.sleep(60)
```

**Advantages**:
- SLO monitoring with alerts
- Structured logging for analysis
- Automatic export and cleanup
- Production-ready

---

### Pattern 3: Async Tool Tracing

**Scenario**: You have async tools that need tracing and context propagation.

```python
from crewai_tool_tracer.async_tracer import AsyncToolExecutionTracer
from crewai_tool_tracer.decorators import traced_async_tool

# Create async tracer
tracer = AsyncToolExecutionTracer(name="async-crew")

# Decorate async tools
@traced_async_tool(tracer, agent_name="agent", task_name="task")
async def async_search(query: str) -> str:
    """Async search operation."""
    result = await fetch_from_api(query)
    return result

# Use in async context
async def main():
    result = await async_search("AI trends")
    print(f"Result: {result}")

# Run
asyncio.run(main())

# Get metrics (same as sync)
metrics = tracer.get_tool_metrics()
```

**Advantages**:
- Full async/await support
- Context propagation across await
- Same API as sync tracer

---

### Pattern 4: Wrap Existing Tools (No Code Changes)

**Scenario**: You have existing tools and can't modify them.

```python
from crewai_tool_tracer import ToolExecutionTracer
from crewai_tool_tracer.decorators import create_traced_tools

tracer = ToolExecutionTracer(name="crew")

# Existing tools without modification
def existing_search(query):
    return search_results

def existing_fetch(url):
    return page_content

# Wrap them
traced_tools = create_traced_tools(
    tools=[existing_search, existing_fetch],
    tracer=tracer,
    agent_name="researcher",
    task_name="research",
)

# Use wrapped tools
agent = Agent(tools=traced_tools)
```

**Advantages**:
- No modification to existing code
- Works with any tool
- Easy to add/remove

---

### Pattern 5: Full Crew with Context Manager

**Scenario**: You want automatic tracing for all tools in a task without decorating each one.

```python
from crewai_tool_tracer.integration import trace_crewai_execution
from crewai_tool_tracer import ToolExecutionTracer, StructuredLogger

tracer = ToolExecutionTracer(name="crew")
logger = StructuredLogger(name="crew-logger")

# All tools in this context are traced
with trace_crewai_execution(tracer, "researcher", "research_task", logger):
    result = agent.execute_task(task)
    # Automatic tracing happens here

# Analyze
metrics = tracer.get_tool_metrics(agent_name="researcher")
print(f"Tools executed: {metrics.total_executions}")
```

**Advantages**:
- No decorator changes needed
- Automatic context propagation
- Task-level granularity

---

## API Method Cheat Sheet

### Quick Reference Table

| Method | Purpose | Example |
|--------|---------|---------|
| `trace_tool_call()` | Start tracing | `span_id = tracer.trace_tool_call(tool_name="search", ...)` |
| `record_tool_result()` | End tracing | `tracer.record_tool_result(span_id, result, duration_ms)` |
| `get_tool_metrics()` | Get stats | `metrics = tracer.get_tool_metrics()` |
| `get_span()` | Single span | `span = tracer.get_span(span_id)` |
| `get_all_spans()` | All spans | `spans = tracer.get_all_spans()` |
| `export_to_json()` | JSON export | `tracer.export_to_json("traces.json")` |
| `clear_spans()` | Clear memory | `tracer.clear_spans()` |

### Getting Metrics - Common Queries

```python
# All metrics
metrics = tracer.get_tool_metrics()

# Specific tool
metrics = tracer.get_tool_metrics(tool_name="web_search")

# Specific agent
metrics = tracer.get_tool_metrics(agent_name="researcher")

# Time range (last hour)
from datetime import datetime, timedelta
start = datetime.utcnow() - timedelta(hours=1)
end = datetime.utcnow()
metrics = tracer.get_tool_metrics(time_range=(start, end))

# Combined filters
metrics = tracer.get_tool_metrics(
    tool_name="search",
    agent_name="researcher",
    time_range=(start, end),
)
```

### Accessing Metrics Fields

```python
metrics = tracer.get_tool_metrics()

# Basic counts
print(f"Total: {metrics.total_executions}")
print(f"Successful: {metrics.successful_executions}")
print(f"Failed: {metrics.failed_executions}")

# Timing
print(f"Avg: {metrics.average_duration_ms:.0f}ms")
print(f"Min: {metrics.min_duration_ms:.0f}ms")
print(f"Max: {metrics.max_duration_ms:.0f}ms")
print(f"Total: {metrics.total_duration_ms:.0f}ms")

# Rates
print(f"Success rate: {1 - metrics.error_rate:.1%}")
print(f"Error rate: {metrics.error_rate:.1%}")

# Breakdown
print(f"Tools used: {metrics.tools_executed}")
print(f"Agents: {metrics.agents_involved}")
```

---

## Common Issues and Solutions

### Issue 1: "Tools Not Being Traced"

**Problem**: You added decorator but no spans appear

**Solution**:
```python
# ❌ WRONG: Forgot decorator
def my_tool(x):
    return x * 2

# ✅ CORRECT: Add decorator
@traced_tool(tracer, agent_name="agent", task_name="task")
def my_tool(x):
    return x * 2

# Verify:
result = my_tool(5)
spans = tracer.get_all_spans()
print(f"Spans recorded: {len(spans)}")  # Should be 1
```

---

### Issue 2: "agent_name or task_name is 'unknown'"

**Problem**: Context not appearing in metrics

**Solution**:
```python
# ❌ WRONG: No context provided
@traced_tool(tracer)
def search():
    pass

# ✅ CORRECT: Provide explicit context
@traced_tool(tracer, agent_name="researcher", task_name="search")
def search():
    pass

# Or use context manager:
with trace_crewai_execution(tracer, "researcher", "search", logger):
    result = agent.execute_task(task)
```

---

### Issue 3: "Export Fails - Returns False"

**Problem**: Export method returns False

**Solutions**:

```python
# ❌ WRONG: Missing API key
exporter = DatadogExporter()  # No API key!
exporter.export(spans)  # Fails

# ✅ CORRECT: Provide API key
import os
exporter = DatadogExporter(api_key=os.getenv("DD_API_KEY"))
exporter.export(spans)  # Works

# Or check for errors:
try:
    success = exporter.export(tracer.get_all_spans())
    if not success:
        print("Export failed - check logs")
except Exception as e:
    print(f"Export error: {e}")
```

---

### Issue 4: "Memory Usage Growing"

**Problem**: Process memory keeps increasing

**Solution**:
```python
# ❌ WRONG: No memory management
tracer = ToolExecutionTracer()
# Spans accumulate forever

# ✅ CORRECT: Periodic cleanup
import schedule

def export_and_cleanup():
    spans = tracer.get_all_spans()
    if spans:
        exporter.export(spans)  # Export first
        tracer.clear_spans()    # Then clean up

schedule.every(5).minutes.do(export_and_cleanup)
```

---

### Issue 5: "Async Tools Not Traced"

**Problem**: Async functions show missing context

**Solution**:
```python
# ❌ WRONG: Sync decorator on async function
@traced_tool(tracer, agent_name="agent", task_name="task")
async def async_search(query):
    return await fetch(query)

# ✅ CORRECT: Use async decorator
@traced_async_tool(tracer, agent_name="agent", task_name="task")
async def async_search(query):
    return await fetch(query)
```

---

## Exporter Setup

### OpenTelemetry (OTEL)

```python
from crewai_tool_tracer import OTelExporter

# Setup
exporter = OTelExporter(
    endpoint="http://localhost:4317",
    service_name="my-crew",
)

# Export
exporter.export(tracer.get_all_spans())
```

**Requires**: `pip install opentelemetry-exporter-otlp`

**View traces**: Access OTEL collector UI (usually port 16686)

---

### Datadog APM

```python
from crewai_tool_tracer import DatadogExporter
import os

# Setup
exporter = DatadogExporter(
    api_key=os.getenv("DD_API_KEY"),
    site="datadoghq.com",
)

# Export
exporter.export(tracer.get_all_spans())
```

**Requires**: `pip install requests`

**View traces**: https://app.datadoghq.com/apm/traces

---

### Langfuse

```python
from crewai_tool_tracer import LangfuseExporter
import os

# Setup
exporter = LangfuseExporter(
    api_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
)

# Export
exporter.export(tracer.get_all_spans())
```

**Requires**: `pip install langfuse`

**View traces**: https://cloud.langfuse.com

---

### JSON Export (Local)

```python
# No dependencies needed!

# Export to file
tracer.export_to_json("traces.json")

# Then analyze:
import json
with open("traces.json") as f:
    data = json.load(f)
    for span in data['spans']:
        print(f"{span['tool_name']}: {span['duration_ms']}ms")
```

---

## Performance Monitoring

### Basic Monitoring

```python
from crewai_tool_tracer.integration import ToolExecutionMonitor

monitor = ToolExecutionMonitor(tracer)

# Set thresholds
monitor.set_max_duration("search", 5000)  # Max 5 seconds
monitor.set_min_success_rate("search", 0.95)  # Min 95%

# Check compliance
violations = monitor.check_slos()
if violations:
    for v in violations:
        print(f"⚠️  {v['message']}")
else:
    print("✅ All SLOs met!")
```

### Sending Alerts

```python
import schedule

def check_and_alert():
    violations = monitor.check_slos()
    if violations:
        # Send to monitoring system
        for v in violations:
            send_alert_to_slack(v['message'])
            send_alert_to_pagerduty(v['tool_name'])

schedule.every(5).minutes.do(check_and_alert)
```

---

## Real-World Workflow

### Complete Multi-Agent Example

```python
from crewai import Agent, Task, Crew
from crewai_tool_tracer import (
    ToolExecutionTracer,
    StructuredLogger,
    DatadogExporter,
    traced_tool,
)
from crewai_tool_tracer.integration import (
    trace_crewai_execution,
    ToolExecutionMonitor,
)
import os
import schedule
import time

# 1. Setup observability components
tracer = ToolExecutionTracer(name="market-research")
logger = StructuredLogger(log_file="research.log")
monitor = ToolExecutionMonitor(tracer)
exporter = DatadogExporter(api_key=os.getenv("DD_API_KEY"))

# 2. Configure SLOs
monitor.set_max_duration("web_search", 5000)
monitor.set_min_success_rate("web_search", 0.95)

# 3. Define tools with tracing
@traced_tool(tracer, agent_name="researcher", task_name="market_research")
def web_search(query: str) -> str:
    """Search the web for information."""
    # Your implementation
    return results

@traced_tool(tracer, agent_name="analyst", task_name="analysis")
def analyze_data(data: str) -> str:
    """Analyze market data."""
    return analysis

# 4. Create agents
researcher = Agent(
    role="Market Researcher",
    goal="Research market trends",
    tools=[web_search],
)

analyst = Agent(
    role="Data Analyst",
    goal="Analyze market data",
    tools=[analyze_data],
)

# 5. Define tasks
research_task = Task(
    description="Research AI market trends",
    agent=researcher,
)

analysis_task = Task(
    description="Analyze market data",
    agent=analyst,
)

# 6. Setup monitoring
def monitor_performance():
    violations = monitor.check_slos()
    if violations:
        print(f"⚠️  {len(violations)} SLO violations!")
        exporter.export(tracer.get_all_spans())
        tracer.clear_spans()
    else:
        print("✅ All SLOs met")

schedule.every(5).minutes.do(monitor_performance)

# 7. Execute crew
crew = Crew(
    agents=[researcher, analyst],
    tasks=[research_task, analysis_task],
)

with trace_crewai_execution(tracer, "crew", "market_research", logger):
    result = crew.kickoff()

# 8. Final analysis
metrics = tracer.get_tool_metrics()
print(f"\n📊 Summary:")
print(f"  Tools executed: {metrics.total_executions}")
print(f"  Success rate: {1 - metrics.error_rate:.1%}")
print(f"  Avg time: {metrics.average_duration_ms:.0f}ms")

# 9. Export
exporter.export(tracer.get_all_spans())
tracer.export_to_json("final_traces.json")
print("✅ Done!")
```

---

## Environment Variables

```bash
# OTEL Configuration
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Datadog Configuration
export DD_API_KEY=your_datadog_api_key
export DD_SITE=datadoghq.com

# Langfuse Configuration
export LANGFUSE_PUBLIC_KEY=your_public_key
export LANGFUSE_SECRET_KEY=your_secret_key
export LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## Next Steps

1. **Read Full Documentation**: See `TOOL_TRACER_CONTRIBUTION.md`
2. **Check API Reference**: See `docs/API_REFERENCE.md`
3. **Run Examples**: See `examples/` directory
4. **Run Tests**: `pytest src/crewai_tool_tracer/tests/ -v`
5. **Join Community**: Share feedback and ideas

---

## Key Takeaways

✅ Add `@traced_tool` decorator to enable tracing
✅ Get metrics with `tracer.get_tool_metrics()`
✅ Export to multiple platforms simultaneously
✅ Monitor SLO compliance in production
✅ <0.5ms overhead - suitable for production
✅ Backward compatible - no breaking changes

---

## Support

- 📖 Documentation: `docs/`
- 💡 Examples: `examples/`
- 🧪 Tests: `tests/`
- 🐛 Issues: GitHub issues
- 💬 Questions: GitHub discussions

---

**Happy tracing! 🚀**
