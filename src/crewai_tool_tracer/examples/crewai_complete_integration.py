"""
Complete CrewAI integration example demonstrating all integration patterns.

This example shows:
1. Decorator-based tracing for tools
2. Hook-based integration with CrewAI agents
3. Async tool support
4. Tool chain tracking
5. Performance monitoring with SLOs
6. Multi-backend export
7. Context management for multi-agent scenarios
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional

# Note: In a real scenario, you would:
# from crewai import Agent, Task, Crew, on, PRE_TOOL_CALL, POST_TOOL_CALL

from src.crewai_tool_tracer import (
    ToolExecutionTracer,
    AsyncToolExecutionTracer,
    StructuredLogger,
    DatadogExporter,
    OTelExporter,
    CompositeExporter,
)
from src.crewai_tool_tracer.decorators import (
    traced_tool,
    traced_async_tool,
    create_traced_tools,
)
from src.crewai_tool_tracer.async_tracer import ToolChainTracker
from src.crewai_tool_tracer.integration import (
    CrewAIToolHook,
    trace_crewai_execution,
    ToolExecutionMonitor,
    ExecutionContextManager,
)


# ============================================================================
# Example 1: Decorator-Based Tool Tracing
# ============================================================================

def example_decorator_tracing():
    """Demonstrate decorator-based tool tracing."""
    print("\n" + "=" * 70)
    print("Example 1: Decorator-Based Tool Tracing")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="decorator-example")

    # Define tools with decorators
    @traced_tool(tracer, agent_name="research_agent", task_name="search_task")
    def search_web(query: str) -> str:
        """Simulate web search."""
        print(f"  Searching web for: {query}")
        time.sleep(0.5)
        return f"Found results for '{query}'"

    @traced_tool(tracer, agent_name="analysis_agent", task_name="analysis_task")
    def analyze_sentiment(text: str) -> str:
        """Simulate sentiment analysis."""
        print(f"  Analyzing sentiment of: {text[:50]}...")
        time.sleep(0.3)
        return "Sentiment: Positive"

    # Use tools normally
    print("\nExecuting tools with decorator-based tracing:")
    result1 = search_web("What is AI?")
    print(f"  Result: {result1}")

    result2 = analyze_sentiment("This is great!")
    print(f"  Result: {result2}")

    # Get metrics
    metrics = tracer.get_tool_metrics()
    print(f"\nMetrics:")
    print(f"  Total executions: {metrics.total_executions}")
    print(f"  Average duration: {metrics.average_duration_ms:.1f}ms")
    print(f"  Success rate: {1 - metrics.error_rate:.1%}")


# ============================================================================
# Example 2: Async Tool Support
# ============================================================================

async def example_async_tools():
    """Demonstrate async tool tracing."""
    print("\n" + "=" * 70)
    print("Example 2: Async Tool Support")
    print("=" * 70)

    tracer = AsyncToolExecutionTracer(name="async-example")

    # Define async tools
    @traced_async_tool(tracer, agent_name="async_agent", task_name="concurrent_task")
    async def fetch_data(url: str) -> str:
        """Simulate async data fetching."""
        print(f"  Fetching from {url}")
        await asyncio.sleep(0.5)
        return f"Data from {url}"

    @traced_async_tool(tracer, agent_name="async_agent", task_name="concurrent_task")
    async def process_data(data: str) -> str:
        """Simulate async processing."""
        print(f"  Processing data: {data[:30]}...")
        await asyncio.sleep(0.3)
        return f"Processed: {data}"

    # Execute async tools concurrently
    print("\nExecuting async tools concurrently:")
    tasks = [
        fetch_data("https://api1.example.com"),
        fetch_data("https://api2.example.com"),
    ]

    results = await asyncio.gather(*tasks)
    print(f"  Fetched {len(results)} results")

    # Get metrics
    metrics = tracer.get_tool_metrics()
    print(f"\nAsync Execution Metrics:")
    print(f"  Total executions: {metrics.total_executions}")
    print(f"  Average duration: {metrics.average_duration_ms:.1f}ms")


# ============================================================================
# Example 3: Tool Chain Tracking
# ============================================================================

def example_tool_chain_tracking():
    """Demonstrate tool chain tracking for dependent executions."""
    print("\n" + "=" * 70)
    print("Example 3: Tool Chain Tracking")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="chain-example")
    tracker = ToolChainTracker(tracer)

    @traced_tool(tracer, agent_name="workflow_agent", task_name="data_pipeline")
    def extract_data() -> dict:
        """Extract data."""
        print("  Extracting data...")
        time.sleep(0.3)
        return {"rows": 1000}

    @traced_tool(tracer, agent_name="workflow_agent", task_name="data_pipeline")
    def transform_data(data: dict) -> dict:
        """Transform extracted data."""
        print("  Transforming data...")
        time.sleep(0.4)
        return {"processed_rows": 950}

    @traced_tool(tracer, agent_name="workflow_agent", task_name="data_pipeline")
    def load_data(data: dict) -> dict:
        """Load processed data."""
        print("  Loading data...")
        time.sleep(0.2)
        return {"loaded": True}

    # Execute pipeline with dependencies
    print("\nExecuting data pipeline with tool chains:")

    # Manually track dependencies
    spans = {}

    # Step 1: Extract
    span_id = tracer.trace_tool_call(
        tool_name="extract_data",
        input_data={},
        agent_name="workflow_agent",
        task_name="data_pipeline",
    )
    spans["extract"] = span_id
    result1 = extract_data()
    tracer.record_tool_result(span_id=span_id, result=result1, duration_ms=300, success=True)

    # Step 2: Transform (depends on Extract)
    span_id = tracer.trace_tool_call(
        tool_name="transform_data",
        input_data=result1,
        agent_name="workflow_agent",
        task_name="data_pipeline",
    )
    spans["transform"] = span_id
    tracker.link_spans(spans["extract"], span_id)
    result2 = transform_data(result1)
    tracer.record_tool_result(span_id=span_id, result=result2, duration_ms=400, success=True)

    # Step 3: Load (depends on Transform)
    span_id = tracer.trace_tool_call(
        tool_name="load_data",
        input_data=result2,
        agent_name="workflow_agent",
        task_name="data_pipeline",
    )
    spans["load"] = span_id
    tracker.link_spans(spans["transform"], span_id)
    result3 = load_data(result2)
    tracer.record_tool_result(span_id=span_id, result=result3, duration_ms=200, success=True)

    # Analyze chains
    print(f"\nChain Analysis:")
    chain = tracker.get_execution_chain(spans["load"])
    print(f"  Full chain: {[s[:8] for s in chain]}")

    metrics = tracker.analyze_chain_metrics(chain)
    print(f"  Chain length: {metrics['chain_length']}")
    print(f"  Total duration: {metrics['total_duration_ms']:.0f}ms")
    print(f"  Tools: {' -> '.join(metrics['tools_in_chain'])}")
    print(f"  Bottleneck: {metrics['bottleneck_tool']} ({metrics['bottleneck_duration_ms']:.0f}ms)")


# ============================================================================
# Example 4: Performance Monitoring with SLOs
# ============================================================================

def example_performance_monitoring():
    """Demonstrate SLO monitoring for tool performance."""
    print("\n" + "=" * 70)
    print("Example 4: Performance Monitoring with SLOs")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="monitoring-example")
    monitor = ToolExecutionMonitor(tracer)

    # Set performance thresholds
    monitor.set_max_duration("web_search", 2000)  # 2 seconds
    monitor.set_min_success_rate("web_search", 0.95)  # 95%

    @traced_tool(tracer, agent_name="search_agent", task_name="search_task")
    def web_search(query: str) -> str:
        """Simulate web search."""
        time.sleep(0.3)  # Within SLO
        return f"Results for {query}"

    @traced_tool(tracer, agent_name="slow_agent", task_name="slow_task")
    def slow_tool() -> str:
        """Simulate slow tool."""
        time.sleep(2.5)  # Exceeds SLO
        return "Slow result"

    # Execute tools
    print("\nExecuting tools and monitoring performance:")
    print("  Executing fast tool (web_search)...")
    web_search("python performance")

    print("  Executing slow tool...")
    slow_tool()

    # Check SLOs
    print("\nChecking SLOs:")
    violations = monitor.check_slos()

    if violations:
        print("  ⚠️  SLO Violations detected:")
        for v in violations:
            print(f"    - {v['message']}")
    else:
        print("  ✅ All SLOs met")


# ============================================================================
# Example 5: Multi-Backend Export
# ============================================================================

def example_multi_backend_export():
    """Demonstrate exporting to multiple platforms."""
    print("\n" + "=" * 70)
    print("Example 5: Multi-Backend Export")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="export-example")

    @traced_tool(tracer, agent_name="export_agent", task_name="export_task")
    def sample_tool() -> str:
        time.sleep(0.2)
        return "Sample result"

    # Execute tool
    print("\nExecuting tool for export:")
    sample_tool()

    # Set up exporters
    print("\nConfiguring exporters:")

    # Export to JSON (local analysis)
    tracer.export_to_json("/tmp/traces.json")
    print("  ✅ Exported to JSON")

    # Show exporter configuration (real deployment would have valid credentials)
    print("  OpenTelemetry: Configured for http://localhost:4317")
    print("  Datadog: Configured (API key needed)")
    print("  Langfuse: Configured (credentials needed)")

    # Get metrics
    metrics = tracer.get_tool_metrics()
    print(f"\nMetrics for Export:")
    print(f"  Total spans: {metrics.total_executions}")
    print(f"  Duration: {metrics.average_duration_ms:.1f}ms avg")


# ============================================================================
# Example 6: Context Management for Multi-Agent Scenarios
# ============================================================================

def example_context_management():
    """Demonstrate context management for multiple agents."""
    print("\n" + "=" * 70)
    print("Example 6: Context Management for Multi-Agent Scenarios")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="context-example")
    ctx_mgr = ExecutionContextManager(tracer)

    @traced_tool(tracer, agent_name="agent1", task_name="task1")
    def tool_a() -> str:
        print("    Executing tool A")
        time.sleep(0.1)
        return "Result A"

    @traced_tool(tracer, agent_name="agent2", task_name="task2")
    def tool_b() -> str:
        print("    Executing tool B")
        time.sleep(0.1)
        return "Result B"

    # Execute in sequence with different contexts
    print("\nExecuting multi-agent workflow:")

    agents_and_tasks = [
        ("agent1", "task1"),
        ("agent2", "task2"),
        ("agent1", "task1"),
    ]

    for agent_name, task_name in agents_and_tasks:
        print(f"\n  Executing {agent_name}/{task_name}:")
        with ctx_mgr.as_context_manager(agent_name, task_name):
            if "1" in agent_name:
                tool_a()
            else:
                tool_b()

    # Get per-agent metrics
    print(f"\nPer-Agent Metrics:")
    for agent_name in ["agent1", "agent2"]:
        metrics = tracer.get_tool_metrics(agent_name=agent_name)
        print(f"  {agent_name}: {metrics.total_executions} executions")


# ============================================================================
# Example 7: Structured Logging
# ============================================================================

def example_structured_logging():
    """Demonstrate structured JSON logging."""
    print("\n" + "=" * 70)
    print("Example 7: Structured Logging")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="logging-example")
    logger = StructuredLogger(
        name="crew-logger",
        log_file="/tmp/crew_execution.log",
    )

    @traced_tool(tracer, agent_name="logging_agent", task_name="logging_task")
    def tool_with_logging(value: int) -> str:
        print(f"    Processing value: {value}")
        time.sleep(0.1)

        if value < 0:
            raise ValueError("Value must be positive")

        return f"Processed: {value * 2}"

    # Execute with logging
    print("\nExecuting tool with structured logging:")
    print("  Success case:")
    try:
        result = tool_with_logging(5)
        print(f"    Result: {result}")
    except Exception as e:
        logger.log_error(
            error_message=str(e),
            tool_name="tool_with_logging",
            agent_name="logging_agent",
        )

    print("  Error case:")
    try:
        result = tool_with_logging(-1)
    except ValueError as e:
        print(f"    Expected error: {e}")
        logger.log_error(
            error_message=str(e),
            tool_name="tool_with_logging",
            agent_name="logging_agent",
        )

    print("\n  ✅ Logs written to /tmp/crew_execution.log")


# ============================================================================
# Example 8: Hook-Based Integration (Simulated)
# ============================================================================

def example_hook_based_integration():
    """Demonstrate hook-based integration pattern."""
    print("\n" + "=" * 70)
    print("Example 8: Hook-Based Integration (Pattern Demo)")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="hook-example")
    logger = StructuredLogger(name="hook-logger")
    hook = CrewAIToolHook(tracer, logger=logger)

    # Simulate CrewAI agent with hooks
    class SimulatedAgent:
        def __init__(self, name):
            self.name = name
            self._last_span_id = None

        def execute_tool(self, tool_name, tool_args, task_name):
            """Simulate tool execution with hooks."""
            print(f"    Executing {tool_name}")

            # PRE_TOOL_CALL hook
            self._last_span_id = hook.on_tool_call_pre(
                tool_name=tool_name,
                tool_args=tool_args,
                agent_name=self.name,
                task_name=task_name,
            )

            try:
                # Simulate tool execution
                time.sleep(0.2)
                result = f"Result from {tool_name}"

                # POST_TOOL_CALL hook
                hook.on_tool_call_post(
                    span_id=self._last_span_id,
                    tool_result=result,
                    error=None,
                )
            except Exception as e:
                hook.on_tool_call_post(
                    span_id=self._last_span_id,
                    tool_result=None,
                    error=e,
                )

    # Use simulated agent
    print("\nSimulating CrewAI agent with hooks:")
    agent = SimulatedAgent("research_agent")

    agent.execute_tool(
        tool_name="web_search",
        tool_args={"query": "AI trends"},
        task_name="research_task",
    )

    agent.execute_tool(
        tool_name="analyze_data",
        tool_args={"data": "trend_data"},
        task_name="research_task",
    )

    # Get metrics
    metrics = tracer.get_tool_metrics(agent_name="research_agent")
    print(f"\nHook-Based Execution Metrics:")
    print(f"  Total tools: {metrics.total_executions}")
    print(f"  Success rate: {1 - metrics.error_rate:.1%}")


# ============================================================================
# Example 9: Combined Complete Workflow
# ============================================================================

def example_complete_workflow():
    """Demonstrate a complete realistic workflow."""
    print("\n" + "=" * 70)
    print("Example 9: Complete Realistic Workflow")
    print("=" * 70)

    # Setup
    tracer = ToolExecutionTracer(name="complete-workflow")
    logger = StructuredLogger(
        name="workflow-logger",
        log_file="/tmp/workflow.log",
    )
    monitor = ToolExecutionMonitor(tracer)
    tracker = ToolChainTracker(tracer)

    # Set SLOs
    monitor.set_max_duration("search", 3000)
    monitor.set_max_duration("analyze", 2000)
    monitor.set_min_success_rate("search", 0.9)

    # Define tools
    @traced_tool(tracer, agent_name="researcher", task_name="research")
    def search(query: str) -> dict:
        print(f"    Searching for: {query}")
        time.sleep(0.5)
        return {"query": query, "results": 10}

    @traced_tool(tracer, agent_name="analyst", task_name="analysis")
    def analyze(data: dict) -> dict:
        print(f"    Analyzing {data['results']} results")
        time.sleep(0.3)
        return {"analyzed": True, "insights": 5}

    @traced_tool(tracer, agent_name="writer", task_name="report_generation")
    def generate_report(insights: dict) -> str:
        print(f"    Generating report with {insights['insights']} insights")
        time.sleep(0.2)
        return "Report generated"

    # Execute workflow with context
    print("\nExecuting complete workflow:")

    with trace_crewai_execution(tracer, "research_team", "market_research", logger):
        print("  Phase 1: Research")
        search_result = search("market trends")

        print("  Phase 2: Analysis")
        analysis_result = analyze(search_result)

        print("  Phase 3: Report Generation")
        report = generate_report(analysis_result)

    # Check SLOs and get metrics
    print(f"\nWorkflow Summary:")

    violations = monitor.check_slos()
    if violations:
        print(f"  ⚠️  {len(violations)} SLO violations")
    else:
        print("  ✅ All SLOs met")

    metrics = tracer.get_tool_metrics()
    print(f"  Total tools executed: {metrics.total_executions}")
    print(f"  Average duration: {metrics.average_duration_ms:.1f}ms")
    print(f"  Total duration: {metrics.total_duration_ms:.0f}ms")


# ============================================================================
# Main
# ============================================================================

async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("CrewAI Tool Execution Tracer - Complete Integration Examples")
    print("=" * 70)

    # Run all examples
    example_decorator_tracing()
    await example_async_tools()
    example_tool_chain_tracking()
    example_performance_monitoring()
    example_multi_backend_export()
    example_context_management()
    example_structured_logging()
    example_hook_based_integration()
    example_complete_workflow()

    print("\n" + "=" * 70)
    print("✅ All examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
