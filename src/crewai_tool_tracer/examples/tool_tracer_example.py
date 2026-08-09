"""
Example: Integrating ToolExecutionTracer with CrewAI.

Demonstrates how to use the ToolExecutionTracer with a CrewAI agent
to trace and monitor tool executions.
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict

from src.crewai_tool_tracer import (
    ToolExecutionTracer,
    StructuredLogger,
    OTelExporter,
    DatadogExporter,
    LangfuseExporter,
)


# Example 1: Basic tracer usage
def example_basic_tracing():
    """Basic example of using the ToolExecutionTracer."""
    print("=" * 60)
    print("Example 1: Basic Tool Execution Tracing")
    print("=" * 60)

    # Initialize tracer
    tracer = ToolExecutionTracer(name="basic-example")

    # Simulate tool call and result
    span_id = tracer.trace_tool_call(
        tool_name="web_search",
        input_data={"query": "What is the capital of France?"},
        agent_name="research_agent",
        task_name="find_capital",
    )

    print(f"Started tracing tool call: {span_id}")

    # Simulate tool execution time
    time.sleep(0.5)

    # Record the result
    tracer.record_tool_result(
        span_id=span_id,
        result={"answer": "Paris", "confidence": 0.99},
        duration_ms=500.0,
        success=True,
    )

    print(f"Recorded result for span: {span_id}")

    # Get metrics
    metrics = tracer.get_tool_metrics()
    print(f"\nMetrics:")
    print(f"  Total executions: {metrics.total_executions}")
    print(f"  Successful: {metrics.successful_executions}")
    print(f"  Failed: {metrics.failed_executions}")
    print(f"  Average duration: {metrics.average_duration_ms:.2f} ms")


# Example 2: Structured logging
def example_structured_logging():
    """Example of using structured logging with JSON output."""
    print("\n" + "=" * 60)
    print("Example 2: Structured JSON Logging")
    print("=" * 60)

    # Initialize logger
    logger = StructuredLogger(name="structured-example")

    # Log a tool call
    logger.log_tool_call(
        tool_name="database_query",
        agent_name="data_agent",
        task_name="fetch_records",
        input_data={"table": "users", "limit": 100},
        span_id="span-12345",
    )

    print("Logged tool call event")

    # Log a tool result
    logger.log_tool_result(
        tool_name="database_query",
        span_id="span-12345",
        result={"rows": 100, "columns": 5},
        duration_ms=245.5,
        success=True,
    )

    print("Logged tool result event")

    # Log an agent event
    logger.log_agent_event(
        event_type="agent.complete",
        agent_name="data_agent",
        task_name="fetch_records",
        message="Successfully completed data retrieval task",
    )

    print("Logged agent event")


# Example 3: Multiple tool executions with metrics
def example_multiple_tools():
    """Example tracking multiple tool executions."""
    print("\n" + "=" * 60)
    print("Example 3: Tracking Multiple Tool Executions")
    print("=" * 60)

    tracer = ToolExecutionTracer(name="multi-tool-example")

    # Simulate multiple tool executions
    tools = [
        {"name": "web_search", "duration": 500},
        {"name": "database_query", "duration": 150},
        {"name": "api_call", "duration": 300},
        {"name": "web_search", "duration": 600},
        {"name": "calculator", "duration": 50},
    ]

    for i, tool_config in enumerate(tools):
        # Start tracing
        span_id = tracer.trace_tool_call(
            tool_name=tool_config["name"],
            input_data={"request": f"request_{i}"},
            agent_name="multi_agent",
            task_name="research_task",
            tags={"batch": "experiment_1"},
        )

        # Simulate execution
        time.sleep(tool_config["duration"] / 1000.0)

        # Record result
        success = i % 4 != 0  # Make some fail
        tracer.record_tool_result(
            span_id=span_id,
            result={"data": "sample_result"},
            duration_ms=float(tool_config["duration"]),
            success=success,
            error=Exception("Tool error") if not success else None,
        )

        print(f"Executed {tool_config['name']} - Success: {success}")

    # Get aggregated metrics
    print("\nAggregated Metrics:")
    metrics = tracer.get_tool_metrics()
    print(f"  Total executions: {metrics.total_executions}")
    print(f"  Successful: {metrics.successful_executions}")
    print(f"  Failed: {metrics.failed_executions}")
    print(f"  Error rate: {metrics.error_rate:.2%}")
    print(f"  Avg duration: {metrics.average_duration_ms:.2f} ms")
    print(f"  Min duration: {metrics.min_duration_ms:.2f} ms")
    print(f"  Max duration: {metrics.max_duration_ms:.2f} ms")
    print(f"\nTools used:")
    for tool, count in metrics.tools_executed.items():
        print(f"    {tool}: {count} times")


# Example 4: Filtered metrics
def example_filtered_metrics():
    """Example of filtering metrics by tool and agent."""
    print("\n" + "=" * 60)
    print("Example 4: Filtered Metrics")
    print("=" * 60)

    tracer = ToolExecutionTracer(name="filtered-example")

    # Create spans for different tools and agents
    configs = [
        ("calculator", "math_agent"),
        ("calculator", "math_agent"),
        ("search", "research_agent"),
        ("search", "research_agent"),
        ("database", "data_agent"),
    ]

    for tool_name, agent_name in configs:
        span_id = tracer.trace_tool_call(
            tool_name=tool_name,
            input_data={},
            agent_name=agent_name,
            task_name="test_task",
        )

        tracer.record_tool_result(
            span_id=span_id,
            result={},
            duration_ms=100.0,
            success=True,
        )

    # Get metrics for calculator tool only
    calc_metrics = tracer.get_tool_metrics(tool_name="calculator")
    print(f"Calculator tool metrics:")
    print(f"  Executions: {calc_metrics.total_executions}")

    # Get metrics for math_agent only
    math_metrics = tracer.get_tool_metrics(agent_name="math_agent")
    print(f"\nMath agent metrics:")
    print(f"  Executions: {math_metrics.total_executions}")

    # Get metrics within time range
    now = datetime.utcnow()
    past = now - timedelta(minutes=5)
    future = now + timedelta(minutes=5)

    time_range_metrics = tracer.get_tool_metrics(time_range=(past, future))
    print(f"\nMetrics from last 10 minutes:")
    print(f"  Executions: {time_range_metrics.total_executions}")


# Example 5: JSON export
def example_json_export():
    """Example of exporting traces to JSON file."""
    print("\n" + "=" * 60)
    print("Example 5: JSON Export")
    print("=" * 60)

    tracer = ToolExecutionTracer(name="export-example")

    # Create a few spans
    for i in range(3):
        span_id = tracer.trace_tool_call(
            tool_name="sample_tool",
            input_data={"iteration": i},
            agent_name="sample_agent",
            task_name="sample_task",
        )

        tracer.record_tool_result(
            span_id=span_id,
            result={"output": f"result_{i}"},
            duration_ms=100.0 + i * 50,
            success=True,
        )

    # Export to JSON
    export_path = "/tmp/tool_traces.json"
    tracer.export_to_json(export_path)
    print(f"Exported traces to: {export_path}")

    # Read and display the JSON
    import json
    with open(export_path, 'r') as f:
        data = json.load(f)

    print(f"Exported {len(data['spans'])} spans")


# Example 6: CrewAI integration pattern
def example_crewai_integration():
    """Example showing how to integrate with CrewAI agents."""
    print("\n" + "=" * 60)
    print("Example 6: CrewAI Integration Pattern")
    print("=" * 60)

    # This demonstrates the pattern for integrating with CrewAI
    tracer = ToolExecutionTracer(name="crewai-integration")
    logger = StructuredLogger(name="crewai-logger")

    print("""
    Integration Pattern for CrewAI:

    1. Create tracer instance (typically once per agent)
    2. Wrap tool execution with trace_tool_call()
    3. Record results with record_tool_result()
    4. Use logger for structured event logging
    5. Export metrics periodically

    Example code:

    from crewai_tool_tracer import ToolExecutionTracer

    class InstrumentedTool:
        def __init__(self, original_tool, tracer):
            self.original_tool = original_tool
            self.tracer = tracer

        def __call__(self, *args, **kwargs):
            # Start tracing
            span_id = self.tracer.trace_tool_call(
                tool_name=self.original_tool.name,
                input_data={"args": args, "kwargs": kwargs},
                agent_name=self.agent.name,
                task_name=self.current_task.name,
            )

            try:
                # Execute tool
                result = self.original_tool(*args, **kwargs)

                # Record success
                self.tracer.record_tool_result(
                    span_id=span_id,
                    result=result,
                    duration_ms=elapsed_time,
                    success=True,
                )
                return result

            except Exception as e:
                # Record failure
                self.tracer.record_tool_result(
                    span_id=span_id,
                    result=None,
                    duration_ms=elapsed_time,
                    success=False,
                    error=e,
                )
                raise

    # Then use in agent creation:
    agent = Agent(
        role="Research Agent",
        goal="Find information",
        tools=[InstrumentedTool(tool, tracer) for tool in tools],
    )
    """)


def main():
    """Run all examples."""
    print("\nCrewAI Tool Execution Tracer - Examples\n")

    example_basic_tracing()
    example_structured_logging()
    example_multiple_tools()
    example_filtered_metrics()
    example_json_export()
    example_crewai_integration()

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
