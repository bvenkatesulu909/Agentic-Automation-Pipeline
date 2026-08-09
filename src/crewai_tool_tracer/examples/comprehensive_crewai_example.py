"""
Comprehensive example: Real CrewAI agent with Tool Tracer integration.

This example demonstrates:
- Setting up a tracer with structured logging
- Using decorators to trace tool execution
- Tracing async tools
- Integrating with CrewAI agents using hooks
- Monitoring SLOs
- Exporting traces to multiple backends
"""

import asyncio
import time
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.crewai_tool_tracer import (
    ToolExecutionTracer,
    AsyncToolExecutionTracer,
    StructuredLogger,
    OTelExporter,
    DatadogExporter,
    LangfuseExporter,
    CompositeExporter,
)
from src.crewai_tool_tracer.decorators import traced_tool, traced_async_tool
from src.crewai_tool_tracer.async_tracer import ToolChainTracker
from src.crewai_tool_tracer.integration import (
    CrewAIToolHook,
    ToolExecutionMonitor,
    ExecutionContextManager,
    trace_crewai_execution,
)


# ============================================================================
# Example 1: Basic Tool Implementation with Decorators
# ============================================================================

def example_decorated_tools():
    """Example using @traced_tool decorator for automatic tracing."""
    print("=" * 70)
    print("Example 1: Tool Tracing with Decorators")
    print("=" * 70)

    # Initialize tracer and logger
    tracer = ToolExecutionTracer(name="research-agent-tracer")
    logger = StructuredLogger(name="research-logger")

    # Define tools with automatic tracing via decorator
    @traced_tool(tracer, agent_name="research_agent", task_name="find_info")
    def search_web(query: str) -> Dict[str, Any]:
        """Simulated web search tool."""
        print(f"  > Searching web for: {query}")
        time.sleep(0.2)  # Simulate network call
        return {
            "results": [
                {"title": "Result 1", "url": "http://example.com/1"},
                {"title": "Result 2", "url": "http://example.com/2"},
            ],
            "query": query,
        }

    @traced_tool(tracer, agent_name="research_agent", task_name="find_info")
    def summarize_content(content: str) -> str:
        """Simulated content summarization tool."""
        print(f"  > Summarizing {len(content)} characters")
        time.sleep(0.1)  # Simulate processing
        return f"Summary of content about: {content[:50]}..."

    # Execute tools and observe automatic tracing
    print("\nExecuting tools with automatic tracing...")
    results = search_web("Python machine learning")
    summary = summarize_content(json.dumps(results))

    print(f"\nSearch returned: {len(results['results'])} results")
    print(f"Summary: {summary[:60]}...")

    # View traces
    print("\nRecorded Spans:")
    for span in tracer.get_all_spans():
        print(
            f"  - {span.tool_name}: {span.status.value} "
            f"({span.duration_ms:.1f}ms)"
        )

    # Get metrics
    metrics = tracer.get_tool_metrics()
    print(f"\nMetrics:")
    print(f"  Total executions: {metrics.total_executions}")
    print(f"  Success rate: {(1 - metrics.error_rate):.1%}")
    print(f"  Avg duration: {metrics.average_duration_ms:.1f}ms")


# ============================================================================
# Example 2: Async Tool Tracing
# ============================================================================

async def example_async_tools():
    """Example using async tools with proper tracing."""
    print("\n" + "=" * 70)
    print("Example 2: Async Tool Tracing")
    print("=" * 70)

    tracer = AsyncToolExecutionTracer(name="async-agent-tracer")

    @traced_async_tool(tracer, agent_name="async_agent", task_name="async_task")
    async def fetch_api_data(endpoint: str) -> Dict[str, Any]:
        """Async API call simulation."""
        print(f"  > Fetching from {endpoint}")
        await asyncio.sleep(0.2)  # Simulate async I/O
        return {"endpoint": endpoint, "data": [1, 2, 3]}

    @traced_async_tool(tracer, agent_name="async_agent", task_name="async_task")
    async def process_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Async data processing."""
        print(f"  > Processing data from {data.get('endpoint')}")
        await asyncio.sleep(0.1)  # Simulate processing
        return {"processed": True, "count": len(data.get("data", []))}

    # Execute async tools concurrently
    print("\nExecuting async tools concurrently...")
    tasks = [
        fetch_api_data("/users"),
        fetch_api_data("/posts"),
        fetch_api_data("/comments"),
    ]

    results = await asyncio.gather(*tasks)
    print(f"Fetched data from {len(results)} endpoints")

    # Process results
    processed = await asyncio.gather(*[process_data(r) for r in results])
    print(f"Processed {len(processed)} datasets")

    # View async traces
    print("\nAsync Spans:")
    for span in tracer.get_all_spans():
        print(f"  - {span.tool_name}: {span.duration_ms:.1f}ms")


# ============================================================================
# Example 3: Tool Chain Tracking and Dependency Analysis
# ============================================================================

def example_tool_chains():
    """Example tracking tool execution chains and dependencies."""
    print("\n" + "=" * 70)
    print("Example 3: Tool Chain Tracking")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="chain-tracer")
    tracker = ToolChainTracker(tracer)

    # Simulate a multi-step workflow
    print("\nSimulating multi-step research workflow:")

    # Step 1: Search
    search_span = tracer.trace_tool_call(
        tool_name="web_search",
        input_data={"query": "climate change"},
        agent_name="research_agent",
        task_name="research",
    )
    time.sleep(0.1)
    tracer.record_tool_result(
        span_id=search_span,
        result={"urls": ["url1", "url2"]},
        duration_ms=100,
        success=True,
    )
    print(f"  ✓ Search completed: {search_span}")

    # Step 2: Fetch content (depends on search)
    fetch_span = tracer.trace_tool_call(
        tool_name="fetch_content",
        input_data={"urls": ["url1", "url2"]},
        agent_name="research_agent",
        task_name="research",
    )
    time.sleep(0.15)
    tracer.record_tool_result(
        span_id=fetch_span,
        result={"content": "article content"},
        duration_ms=150,
        success=True,
    )
    tracker.link_spans(search_span, fetch_span)
    print(f"  ✓ Fetch completed: {fetch_span}")

    # Step 3: Summarize (depends on fetch)
    summary_span = tracer.trace_tool_call(
        tool_name="summarize",
        input_data={"content": "article content"},
        agent_name="research_agent",
        task_name="research",
    )
    time.sleep(0.05)
    tracer.record_tool_result(
        span_id=summary_span,
        result={"summary": "summary text"},
        duration_ms=50,
        success=True,
    )
    tracker.link_spans(fetch_span, summary_span)
    print(f"  ✓ Summarize completed: {summary_span}")

    # Analyze the chain
    print("\nChain Analysis:")
    chain = tracker.get_execution_chain(summary_span)
    print(f"  Chain length: {len(chain)} steps")

    chain_metrics = tracker.analyze_chain_metrics(chain)
    print(f"  Total duration: {chain_metrics['total_duration_ms']:.0f}ms")
    print(f"  Success rate: {chain_metrics['success_rate']:.1%}")
    print(f"  Bottleneck: {chain_metrics['bottleneck_tool']} "
          f"({chain_metrics['bottleneck_duration_ms']:.0f}ms)")


# ============================================================================
# Example 4: CrewAI Hook Integration
# ============================================================================

def example_crewai_hooks():
    """Example using CrewAI event hooks for automatic tracing."""
    print("\n" + "=" * 70)
    print("Example 4: CrewAI Event Hook Integration")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="crewai-hook-tracer")
    logger = StructuredLogger(name="crewai-hook-logger")
    hook = CrewAIToolHook(tracer, logger=logger)

    print("\nSimulating CrewAI tool execution events:")

    # Simulate PRE_TOOL_CALL event
    span_id = hook.on_tool_call_pre(
        tool_name="web_search",
        tool_args={"query": "artificial intelligence"},
        agent_name="research_agent",
        task_name="research_task",
    )
    print(f"  > Tool call started: {span_id}")

    # Simulate tool execution
    time.sleep(0.2)

    # Simulate POST_TOOL_CALL event
    hook.on_tool_call_post(
        span_id=span_id,
        tool_result={
            "results": [
                {"title": "AI Article", "url": "http://example.com"},
            ]
        },
        error=None,
    )
    print(f"  > Tool call completed successfully")

    # Simulate error case
    print("\nSimulating tool error:")
    error_span = hook.on_tool_call_pre(
        tool_name="database_query",
        tool_args={"query": "SELECT * FROM users"},
        agent_name="data_agent",
        task_name="data_task",
    )
    print(f"  > Tool call started: {error_span}")

    time.sleep(0.1)
    hook.on_tool_call_post(
        span_id=error_span,
        tool_result=None,
        error=RuntimeError("Database connection failed"),
    )
    print(f"  > Tool call failed")

    # View results
    print("\nExecution Summary:")
    metrics = tracer.get_tool_metrics()
    print(f"  Total calls: {metrics.total_executions}")
    print(f"  Successful: {metrics.successful_executions}")
    print(f"  Failed: {metrics.failed_executions}")


# ============================================================================
# Example 5: SLO Monitoring
# ============================================================================

def example_slo_monitoring():
    """Example monitoring tool execution SLOs."""
    print("\n" + "=" * 70)
    print("Example 5: SLO Monitoring")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="slo-tracer")
    monitor = ToolExecutionMonitor(tracer)

    # Set SLOs
    monitor.set_max_duration("web_search", 500.0)  # 500ms max
    monitor.set_max_duration("database_query", 1000.0)  # 1s max
    monitor.set_min_success_rate("web_search", 0.95)  # 95% success rate

    print("\nConfigured SLOs:")
    print("  - web_search: max 500ms, min 95% success")
    print("  - database_query: max 1000ms")

    # Simulate compliant executions
    print("\nSimulating compliant tool executions...")
    for i in range(5):
        span_id = tracer.trace_tool_call(
            tool_name="web_search",
            input_data={"query": f"query_{i}"},
            agent_name="agent",
            task_name="task",
        )
        tracer.record_tool_result(
            span_id=span_id,
            result={},
            duration_ms=400.0,  # Within SLO
            success=True,
        )

    # Check SLOs
    violations = monitor.check_slos()
    print(f"  SLO violations: {len(violations)}")

    # Simulate SLO violation
    print("\nSimulating SLO violations...")
    for i in range(5):
        span_id = tracer.trace_tool_call(
            tool_name="web_search",
            input_data={"query": f"slow_query_{i}"},
            agent_name="agent",
            task_name="task",
        )
        success = i < 2  # Only first 2 succeed
        tracer.record_tool_result(
            span_id=span_id,
            result={} if success else None,
            duration_ms=600.0,  # Exceeds 500ms SLO
            success=success,
        )

    violations = monitor.check_slos()
    print(f"  SLO violations: {len(violations)}")
    for violation in violations:
        print(f"    - {violation['message']}")


# ============================================================================
# Example 6: Multi-Export to Observability Platforms
# ============================================================================

def example_multi_export():
    """Example exporting traces to multiple observability platforms."""
    print("\n" + "=" * 70)
    print("Example 6: Multi-Platform Export")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="export-tracer")

    # Create some example spans
    print("\nCreating example tool executions...")
    for i in range(3):
        span_id = tracer.trace_tool_call(
            tool_name="sample_tool",
            input_data={"iteration": i},
            agent_name="export_agent",
            task_name="export_task",
            tags={"export": "true"},
        )
        time.sleep(0.05)
        tracer.record_tool_result(
            span_id=span_id,
            result={"output": f"result_{i}"},
            duration_ms=50.0 + i * 10,
            success=i % 3 != 0,
        )

    # Export to JSON (always available)
    print("\nExporting to JSON...")
    tracer.export_to_json("/tmp/crewai_traces.json")
    print("  ✓ Exported to /tmp/crewai_traces.json")

    # Configure composite exporter for multiple backends
    exporters = []

    # OTEL exporter (if OTEL collector is available)
    try:
        otel_exporter = OTelExporter(
            endpoint="http://localhost:4317",
            service_name="crewai-tracer",
        )
        exporters.append(otel_exporter)
        print("\n  • OTEL exporter configured (requires OTEL collector)")
    except Exception as e:
        print(f"\n  • OTEL exporter skipped: {e}")

    # Datadog exporter (if API key is set)
    dd_key = "your-datadog-api-key"  # Set via environment
    if dd_key != "your-datadog-api-key":
        dd_exporter = DatadogExporter(api_key=dd_key)
        exporters.append(dd_exporter)
        print("  • Datadog exporter configured")

    # Langfuse exporter (if keys are set)
    lf_key = "your-langfuse-api-key"
    if lf_key != "your-langfuse-api-key":
        lf_exporter = LangfuseExporter(
            api_key=lf_key,
            secret_key="your-langfuse-secret",
        )
        exporters.append(lf_exporter)
        print("  • Langfuse exporter configured")

    if len(exporters) > 1:
        composite = CompositeExporter(exporters)
        print(f"\nComposite exporter configured with {len(exporters)} backends")
        # In production: composite.export(tracer.get_all_spans())


# ============================================================================
# Example 7: Context Manager Integration
# ============================================================================

def example_context_manager():
    """Example using context managers for task-level tracing."""
    print("\n" + "=" * 70)
    print("Example 7: Context Manager Integration")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="context-tracer")
    ctx_mgr = ExecutionContextManager(tracer)

    print("\nExecuting tasks with context management...")

    # Execute first task
    with ctx_mgr.as_context_manager("research_agent", "research_task"):
        print("  > Running research task")

        # Tools automatically know agent/task context
        span1 = tracer.trace_tool_call(
            tool_name="search",
            input_data={},
            agent_name="research_agent",
            task_name="research_task",
        )
        tracer.record_tool_result(span_id=span1, result={}, duration_ms=50, success=True)

    # Execute second task
    with ctx_mgr.as_context_manager("analysis_agent", "analysis_task"):
        print("  > Running analysis task")

        span2 = tracer.trace_tool_call(
            tool_name="analyze",
            input_data={},
            agent_name="analysis_agent",
            task_name="analysis_task",
        )
        tracer.record_tool_result(span_id=span2, result={}, duration_ms=75, success=True)

    print("\nTask Summary:")
    metrics = tracer.get_tool_metrics()
    print(f"  Total tools executed: {metrics.total_executions}")
    print(f"  Agents involved: {', '.join(metrics.agents_involved.keys())}")


# ============================================================================
# Example 8: Structured Logging and Analytics
# ============================================================================

def example_structured_logging_analytics():
    """Example using structured logging for analytics."""
    print("\n" + "=" * 70)
    print("Example 8: Structured Logging and Analytics")
    print("=" * 70)

    tracer = ToolExecutionTracer(name="analytics-tracer")
    logger = StructuredLogger(name="analytics-logger")

    print("\nLogging structured events for analytics...")

    # Log multiple tool calls
    for i in range(5):
        span_id = tracer.trace_tool_call(
            tool_name="api_call",
            input_data={"endpoint": f"/api/v1/endpoint_{i}"},
            agent_name="api_agent",
            task_name="api_calls",
        )

        logger.log_tool_call(
            tool_name="api_call",
            agent_name="api_agent",
            task_name="api_calls",
            input_data={"endpoint": f"/api/v1/endpoint_{i}"},
            span_id=span_id,
        )

        # Simulate execution
        time.sleep(0.05)

        # Log result
        logger.log_tool_result(
            tool_name="api_call",
            span_id=span_id,
            result={"status": "success", "data": "response"},
            duration_ms=50.0,
            success=True,
        )

    # Log agent-level event
    logger.log_agent_event(
        event_type="agent.complete",
        agent_name="api_agent",
        task_name="api_calls",
        message="Completed all API calls",
    )

    print("  ✓ Logged 5 tool calls and 1 agent event")
    print("\nStructured logs are written in JSON format for analytics pipelines")


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Run all examples."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  CrewAI Tool Tracer - Comprehensive Examples".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")

    # Run synchronous examples
    example_decorated_tools()
    await example_async_tools()
    example_tool_chains()
    example_crewai_hooks()
    example_slo_monitoring()
    example_multi_export()
    example_context_manager()
    example_structured_logging_analytics()

    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)
    print("\nNext Steps:")
    print("  1. Review the traces in /tmp/crewai_traces.json")
    print("  2. Integrate with your CrewAI agents")
    print("  3. Set up observability platform exports")
    print("  4. Configure SLO monitoring for production")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
