#!/bin/bash
# Script to run CrewAI Tool Tracer tests and benchmarks

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  CrewAI Tool Tracer - Test Suite Runner                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest is not installed. Installing test dependencies..."
    pip install pytest pytest-asyncio pytest-benchmark pytest-cov
fi

# Parse command line arguments
TEST_TYPE=${1:-all}
VERBOSE=${2:--v}

case $TEST_TYPE in
    all)
        echo "Running all tests and benchmarks..."
        echo ""
        echo "▶ Unit Tests"
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolExecutionTracer $VERBOSE
        echo ""
        echo "▶ Async Tests"
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestAsyncTracer $VERBOSE
        echo ""
        echo "▶ Decorator Tests"
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestDecoratedTools $VERBOSE
        echo ""
        echo "▶ Chain Tests"
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolChainTracker $VERBOSE
        echo ""
        echo "▶ Integration Tests"
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestIntegration $VERBOSE
        echo ""
        echo "▶ Edge Case Tests"
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestEdgeCases $VERBOSE
        echo ""
        echo "▶ Memory Tests"
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestMemoryEfficiency $VERBOSE
        ;;

    unit)
        echo "Running unit tests..."
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolExecutionTracer $VERBOSE
        ;;

    async)
        echo "Running async tests..."
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestAsyncTracer $VERBOSE
        ;;

    decorators)
        echo "Running decorator tests..."
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestDecoratedTools $VERBOSE
        ;;

    chains)
        echo "Running chain tracking tests..."
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolChainTracker $VERBOSE
        ;;

    integration)
        echo "Running integration tests..."
        pytest src/crewai_tool_tracer/tests/test_tracer.py::TestIntegration $VERBOSE
        ;;

    benchmarks)
        echo "Running performance benchmarks..."
        pytest src/crewai_tool_tracer/tests/test_benchmarks.py $VERBOSE --benchmark-only
        ;;

    coverage)
        echo "Running tests with coverage report..."
        pytest src/crewai_tool_tracer/tests/ --cov=src.crewai_tool_tracer --cov-report=html --cov-report=term-missing
        echo ""
        echo "✓ Coverage report generated in htmlcov/index.html"
        ;;

    examples)
        echo "Running example scripts..."
        echo ""
        echo "▶ Basic Tool Tracer Example"
        python src/crewai_tool_tracer/examples/tool_tracer_example.py
        echo ""
        echo "▶ Comprehensive CrewAI Example"
        python src/crewai_tool_tracer/examples/comprehensive_crewai_example.py
        ;;

    *)
        echo "Unknown test type: $TEST_TYPE"
        echo ""
        echo "Usage: $0 [test_type] [verbose_flag]"
        echo ""
        echo "Test Types:"
        echo "  all          - Run all tests and benchmarks"
        echo "  unit         - Run unit tests only"
        echo "  async        - Run async tests only"
        echo "  decorators   - Run decorator tests only"
        echo "  chains       - Run chain tracking tests only"
        echo "  integration  - Run integration tests only"
        echo "  benchmarks   - Run performance benchmarks only"
        echo "  coverage     - Run tests with coverage report"
        echo "  examples     - Run example scripts"
        echo ""
        echo "Verbose Flag:"
        echo "  -v           - Verbose output (default)"
        echo "  -vv          - Very verbose output"
        echo "  -q           - Quiet output"
        exit 1
        ;;
esac

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  Test Execution Completed                                  ║"
echo "╚════════════════════════════════════════════════════════════╝"
