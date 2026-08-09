# CrewAI Tool Execution Tracer - Integration Guide

Complete guide for integrating the ToolExecutionTracer with CrewAI agents, tasks, and tools.

## Quick Start

### Installation

```bash
pip install opentelemetry-exporter-otlp  # For OpenTelemetry
pip install requests  # For Datadog
pip install langfuse  # For Langfuse
```

### Basic Setup

```python
from crewai import Agent, Task, Crew
from crewai_tool_tracer import (
    ToolExecutionTracer,
    StructuredLogger,
    OTelExporter,
)

# Initialize tracer and logger
tracer = ToolExecutionTracer(name="my-crew")
logger = StructuredLogger(name="my-crew-logger", log_file="crew_execution.log")

# Optional: Setup exporters
otel_exporter = OTelExporter(
    endpoint="http://localhost:4317",
    service_name="crewai-agents",
)
```

## Integration Patterns

### Pattern 1: Decorator-Based (Recommended for Quick Integration)

The simplest approach - just add a decorator to your tools.

```python
from crewai_tool_tracer.decorators import traced_tool

@traced_tool(
    tracer,
    agent_name="research_agent",
    task_name="search_task",
)
def search_web(query: str) -> str:
    """Search the web for information."""
    # Your implementation
    return search_results

# Use the tool directly in CrewAI
agent = Agent(
    role="Researcher",
    goal="Find information",
    tools=[search_web],  # Works as-is
)
```

**Advantages:**
- Minimal code changes
- Works with existing tools
- Automatic input/output capture

**Disadvantages:**
- Requires decorator on each tool

### Pattern 2: Hook-Based (Recommended for Production)

Use CrewAI's `@on()` decorator hooks for automatic tracing without modifying tools.

```python
from crewai import Agent, Task, Crew
from crewai_tool_tracer.integration import CrewAIToolHook

# Initialize hook
hook = CrewAIToolHook(tracer, logger=logger)

# Define your agent
class ResearchAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tool_hook = hook
        self._last_span_id = None

    @on(PRE_TOOL_CALL)
    def log_tool_call(self, tool_name: str, tool_args: Dict, **kwargs):
        """Called before each tool execution."""
        self._last_span_id = self.tool_hook.on_tool_call_pre(
            tool_name=tool_name,
            tool_args=tool_args,
            agent_name=self.name,
            task_name=self.current_task.name if hasattr(self, 'current_task') else "unknown",
        )
        return self._last_span_id

    @on(POST_TOOL_CALL)
    def log_tool_result(self, tool_result: Any, **kwargs):
        """Called after each tool execution."""
        if self._last_span_id:
            self.tool_hook.on_tool_call_post(
                span_id=self._last_span_id,
                tool_result=tool_result,
                error=kwargs.get('error'),
            )
```

**Advantages:**
- No tool modifications needed
- Automatic context extraction
- Production-ready error handling
- Structured logging included

**Disadvantages:**
- Requires CrewAI hook support
- More setup code

### Pattern 3: Context Manager (For Task-Level Tracing)

Track an entire task execution with automatic tool context.

```python
from crewai_tool_tracer.integration import trace_crewai_execution

def execute_research_task():
    """Execute a research task with full tracing."""
    
    with trace_crewai_execution(
        tracer,
        agent_name="research_agent",
        task_name="find_competitor_info",
        logger_instance=logger,
    ):
        # All tool executions within this block are automatically traced
        result = research_agent.execute_task(competitor_research_task)
        return result

# Metrics and logs are automatically collected
metrics = tracer.get_tool_metrics(agent_name="research_agent")
print(f"Research tasks completed: {metrics.total_executions}")
print(f"Success rate: {1 - metrics.error_rate:.1%}")
```

**Advantages:**
- Task-level correlation
- Automatic success/error tracking
- Clean, readable code

**Disadvantages:**
- Requires manual context wrapping
- Limited to sequential execution

### Pattern 4: Tool Wrapper (For Dynamic Tool Wrapping)

Wrap tools at runtime without decorators.

```python
from crewai_tool_tracer.decorators import create_traced_tools

# Get your original tools
original_tools = [search_tool, calculate_tool, database_tool]

# Wrap them
traced_tools = create_traced_tools(
    original_tools,
    tracer,
    agent_name="research_agent",
    task_name="analysis",
)

# Use traced versions
agent = Agent(
    role="Analyst",
    goal="Analyze data",
    tools=traced_tools,  # Now traced
)
```

**Advantages:**
- No tool modification needed
- Dynamic wrapping at runtime
- Works with third-party tools

**Disadvantages:**
- Additional wrapper objects
- Slight performance overhead

### Pattern 5: Async Tool Tracing

For agents using async tools.

```python
from crewai_tool_tracer import AsyncToolExecutionTracer
from crewai_tool_tracer.decorators import traced_async_tool

tracer = AsyncToolExecutionTracer(name="async-crew")

@traced_async_tool(
    tracer,
    agent_name="async_agent",
    task_name="concurrent_search",
)
async def async_search_web(query: str) -> str:
    """Async web search."""
    result = await fetch_search_results(query)
    return result

# Use in async agent
agent = Agent(
    role="Researcher",
    goal="Research topics",
    tools=[async_search_web],
    allow_async_execution=True,
)
```

**Features:**
- Proper async/await support
- Context propagation across async boundaries
- Task correlation for concurrent tools

## Advanced Features

### Tool Chain Tracking

Track dependencies and execution order of tool calls.

```python
from crewai_tool_tracer.async_tracer import ToolChainTracker

chain_tracker = ToolChainTracker(tracer)

# In your workflow, link related tool executions
span_id_1 = tracer.trace_tool_call(...)
# Execute tool 1
tracer.record_tool_result(span_id=span_id_1, ...)

# Tool 2 depends on Tool 1
span_id_2 = tracer.trace_tool_call(...)
chain_tracker.link_spans(span_id_1, span_id_2)
# Execute tool 2
tracer.record_tool_result(span_id=span_id_2, ...)

# Analyze execution chains
chains = chain_tracker.get_agent_chains("research_agent")
for root_span, chain in chains.items():
    metrics = chain_tracker.analyze_chain_metrics(chain)
    print(f"Chain: {metrics['tools_in_chain']}")
    print(f"Total duration: {metrics['total_duration_ms']:.0f}ms")
    print(f"Success rate: {metrics['success_rate']:.1%}")
    print(f"Bottleneck: {metrics['bottleneck_tool']} ({metrics['bottleneck_duration_ms']:.0f}ms)")
```

### Performance Monitoring with SLOs

Monitor tool performance and enforce Service Level Objectives.

```python
from crewai_tool_tracer.integration import ToolExecutionMonitor

monitor = ToolExecutionMonitor(tracer)

# Set performance thresholds
monitor.set_max_duration("web_search", 5000)  # 5 seconds max
monitor.set_max_duration("database_query", 2000)  # 2 seconds max
monitor.set_min_success_rate("web_search", 0.95)  # 95% success minimum
monitor.set_min_success_rate("database_query", 0.99)  # 99% success minimum

# Periodically check SLOs
def check_performance():
    violations = monitor.check_slos()
    
    if violations:
        for violation in violations:
            if violation['type'] == 'duration_slo':
                print(f"⚠️  {violation['message']}")
                # Trigger alert/investigation
            elif violation['type'] == 'success_rate_slo':
                print(f"❌ {violation['message']}")
                # Escalate issue
    else:
        print("✅ All SLOs met")

# Call periodically (e.g., in a monitoring task)
check_performance()
```

### Exporting to Multiple Platforms

Send traces to multiple observability platforms simultaneously.

```python
from crewai_tool_tracer import (
    OTelExporter,
    DatadogExporter,
    LangfuseExporter,
    CompositeExporter,
)

# Create individual exporters
otel = OTelExporter(
    endpoint="http://localhost:4317",
    service_name="crewai-agents",
)

datadog = DatadogExporter(
    api_key="YOUR_DD_API_KEY",
    service_name="crewai-agents",
)

langfuse = LangfuseExporter(
    api_key="YOUR_LANGFUSE_API_KEY",
    secret_key="YOUR_LANGFUSE_SECRET",
)

# Combine into composite exporter
composite = CompositeExporter([otel, datadog, langfuse])

# Export to all platforms at once
spans = tracer.get_all_spans()
success = composite.export(spans)

if success:
    print("✅ Traces exported to all platforms")
else:
    print("⚠️  Some exports failed - check logs")
```

### Context Management for Multi-Agent Scenarios

Automatically manage agent/task context in complex workflows.

```python
from crewai_tool_tracer.integration import ExecutionContextManager

ctx_mgr = ExecutionContextManager(tracer)

agents = [research_agent, analysis_agent, writing_agent]
tasks = [research_task, analysis_task, writing_task]

for agent, task in zip(agents, tasks):
    # Set context for this agent/task combination
    with ctx_mgr.as_context_manager(agent.name, task.name):
        # All tool executions automatically have this context
        result = agent.execute_task(task)
        
        # Get metrics specific to this agent/task
        metrics = tracer.get_tool_metrics(
            agent_name=agent.name,
        )
        print(f"{agent.name}: {metrics.total_executions} tools executed")
```

## Complete Example: Multi-Agent Research Workflow

```python
from crewai import Agent, Task, Crew
from crewai_tool_tracer import (
    AsyncToolExecutionTracer,
    StructuredLogger,
    DatadogExporter,
)
from crewai_tool_tracer.decorators import traced_tool
from crewai_tool_tracer.integration import (
    trace_crewai_execution,
    ToolExecutionMonitor,
)

# Setup
tracer = AsyncToolExecutionTracer(name="research-crew")
logger = StructuredLogger(
    name="research-crew",
    log_file="research_execution.log",
)
monitor = ToolExecutionMonitor(tracer)
datadog = DatadogExporter(api_key="YOUR_DD_API_KEY")

# Configure performance thresholds
monitor.set_max_duration("search_web", 5000)
monitor.set_min_success_rate("search_web", 0.9)

# Define traced tools
@traced_tool(tracer, agent_name="researcher", task_name="research")
def search_web(query: str) -> str:
    """Search the web."""
    # Implementation
    return results

@traced_tool(tracer, agent_name="analyst", task_name="analysis")
def analyze_data(data: str) -> str:
    """Analyze data."""
    # Implementation
    return analysis

# Create agents
researcher = Agent(
    role="Research Analyst",
    goal="Find comprehensive information",
    tools=[search_web],
)

analyst = Agent(
    role="Data Analyst",
    goal="Provide insights",
    tools=[analyze_data],
)

# Create tasks
research_task = Task(
    description="Research competitors",
    agent=researcher,
)

analysis_task = Task(
    description="Analyze research findings",
    agent=analyst,
)

# Create crew
crew = Crew(agents=[researcher, analyst], tasks=[research_task, analysis_task])

# Execute with tracing
with trace_crewai_execution(
    tracer,
    agent_name="research_crew",
    task_name="market_research",
    logger_instance=logger,
):
    # Kick off the crew
    result = crew.kickoff()

# Check performance
violations = monitor.check_slos()
if violations:
    for v in violations:
        print(f"⚠️  {v['message']}")

# Get metrics
metrics = tracer.get_tool_metrics()
print(f"\nExecution Summary:")
print(f"  Total tools: {metrics.total_executions}")
print(f"  Success rate: {1 - metrics.error_rate:.1%}")
print(f"  Avg duration: {metrics.average_duration_ms:.0f}ms")

# Export traces
datadog.export(tracer.get_all_spans())
tracer.export_to_json("research_crew_traces.json")
```

## Environment Variables

```bash
# OpenTelemetry
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Datadog
export DD_API_KEY=your_datadog_api_key

# Langfuse
export LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
export LANGFUSE_SECRET_KEY=your_langfuse_secret_key
export LANGFUSE_HOST=https://cloud.langfuse.com
```

## Troubleshooting

### Tools not being traced
- **Issue**: Tools execute but no spans are created
- **Solution**: Ensure decorator is applied or hook is registered before tool execution

### Missing context information
- **Issue**: Spans lack agent_name or task_name
- **Solution**: Explicitly pass agent/task names to decorator or hook handler

### Performance degradation
- **Issue**: Adding tracing slows down execution
- **Solution**: Reduce max_spans or export and clear spans periodically

### Export failures
- **Issue**: Exporters report errors
- **Solution**: Verify API keys and endpoints, check credentials in environment variables

## Performance Considerations

1. **Memory**: Default keeps 10,000 spans. Configure with `max_spans` parameter.
2. **Export**: Use `CompositeExporter` for non-blocking multi-platform export.
3. **Logging**: JSON structured logging has minimal overhead.
4. **Async**: Proper async/await support prevents blocking on I/O.

## Best Practices

1. **Name your agents and tasks**: Always provide meaningful agent_name and task_name
2. **Set up monitoring**: Use ToolExecutionMonitor for production workloads
3. **Export regularly**: Don't let spans accumulate indefinitely
4. **Use context managers**: For cleaner, more maintainable code
5. **Monitor SLOs**: Set and track performance thresholds
6. **Log errors**: Use StructuredLogger for error tracking
7. **Chain tracking**: Use ToolChainTracker for complex workflows

## Next Steps

- See [TOOL_TRACER_CONTRIBUTION.md](TOOL_TRACER_CONTRIBUTION.md) for architecture details
- Check [../examples/tool_tracer_example.py](../examples/tool_tracer_example.py) for more examples
- Review test cases in [../tests/test_tracer.py](../tests/test_tracer.py) for usage patterns
