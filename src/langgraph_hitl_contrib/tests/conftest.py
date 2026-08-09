"""
Pytest configuration and shared fixtures for HITL State Manager tests.

This module provides:
- Common fixtures for state manager testing
- Mock graph implementations
- Test data generators
- Pytest hooks for test execution
"""

import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock

from ..state_manager import (
    HITLStateManager,
    HITLWorkflowState,
    CheckpointRecord,
    WorkflowStatus,
)


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "hitl: mark test as HITL-specific",
    )
    config.addinivalue_line(
        "markers",
        "benchmark: mark test as benchmark",
    )
    config.addinivalue_line(
        "markers",
        "scale: mark test as scale test",
    )


# ============================================================================
# SESSION-LEVEL FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """Create a temporary directory for test data."""
    return tmp_path_factory.mktemp("test_data")


# ============================================================================
# MODULE-LEVEL FIXTURES
# ============================================================================

@pytest.fixture
def state_manager():
    """Create a fresh state manager instance for each test."""
    return HITLStateManager()


@pytest.fixture
def state_manager_with_heartbeat():
    """Create state manager with extended heartbeat timeout."""
    return HITLStateManager(heartbeat_timeout_seconds=600)


# ============================================================================
# WORKFLOW STATE FIXTURES
# ============================================================================

@pytest.fixture
def sample_workflow_state():
    """Create a sample workflow state for testing."""
    return HITLWorkflowState(
        workflow_id="wf_test_001",
        status=WorkflowStatus.CREATED,
        current_node="process_input",
        state_data={
            "input": "test data",
            "processed": False,
            "metadata": {"source": "test"},
        },
    )


@pytest.fixture
def sample_workflow_state_running():
    """Create a running workflow state."""
    return HITLWorkflowState(
        workflow_id="wf_test_002",
        status=WorkflowStatus.RUNNING,
        current_node="analysis",
        state_data={
            "processed": True,
            "analysis_in_progress": True,
        },
    )


@pytest.fixture
def sample_workflow_state_paused():
    """Create a paused workflow state awaiting human review."""
    return HITLWorkflowState(
        workflow_id="wf_test_003",
        status=WorkflowStatus.PAUSED_FOR_HUMAN,
        current_node="review",
        state_data={
            "processed": True,
            "analysis_complete": True,
            "review_required": True,
        },
    )


# ============================================================================
# CHECKPOINT FIXTURES
# ============================================================================

@pytest.fixture
def sample_checkpoint():
    """Create a sample checkpoint record."""
    checkpoint = CheckpointRecord(
        checkpoint_id="ckpt_test_001",
        workflow_id="wf_test_001",
        timestamp=datetime.utcnow(),
        status=WorkflowStatus.PAUSED_FOR_HUMAN,
        node_name="review",
        state_snapshot={
            "input": "test data",
            "processed": True,
            "analysis_result": "Complete",
            "confidence": 0.95,
        },
        metadata={"source": "test", "version": 1},
    )
    checkpoint.state_hash = checkpoint.compute_hash()
    return checkpoint


@pytest.fixture
def sample_checkpoint_approved():
    """Create an approved checkpoint."""
    checkpoint = CheckpointRecord(
        checkpoint_id="ckpt_test_approved_001",
        workflow_id="wf_test_001",
        timestamp=datetime.utcnow(),
        status=WorkflowStatus.HUMAN_APPROVED,
        node_name="review",
        state_snapshot={
            "data": "approved_data",
            "decision": "approved",
        },
        metadata={"approved_by": "reviewer@example.com"},
        human_approved=True,
        human_feedback="Looks good!",
    )
    checkpoint.state_hash = checkpoint.compute_hash()
    return checkpoint


@pytest.fixture
def sample_checkpoint_rejected():
    """Create a rejected checkpoint."""
    checkpoint = CheckpointRecord(
        checkpoint_id="ckpt_test_rejected_001",
        workflow_id="wf_test_001",
        timestamp=datetime.utcnow(),
        status=WorkflowStatus.HUMAN_REJECTED,
        node_name="review",
        state_snapshot={
            "data": "rejected_data",
            "decision": "rejected",
        },
        metadata={"rejected_by": "reviewer@example.com"},
        human_feedback="Does not meet criteria",
    )
    checkpoint.state_hash = checkpoint.compute_hash()
    return checkpoint


# ============================================================================
# MOCK GRAPH FIXTURES
# ============================================================================

@pytest.fixture
def mock_graph():
    """Create a mock LangGraph graph for testing."""
    mock = Mock()
    mock.invoke = Mock(return_value={"result": "success"})
    return mock


@pytest.fixture
def mock_graph_with_side_effect():
    """Create a mock graph that tracks invocations."""
    mock = Mock()
    invocations = []

    def invoke_side_effect(state):
        invocations.append(state.copy() if isinstance(state, dict) else state)
        return state

    mock.invoke = Mock(side_effect=invoke_side_effect)
    mock.invocations = invocations
    return mock


@pytest.fixture
def mock_graph_error():
    """Create a mock graph that raises an error."""
    mock = Mock()
    mock.invoke = Mock(side_effect=RuntimeError("Workflow execution failed"))
    return mock


# ============================================================================
# DATA GENERATORS
# ============================================================================

@pytest.fixture
def generate_workflow():
    """Factory fixture for creating workflows."""
    def _generate(
        workflow_id: str,
        status: WorkflowStatus = WorkflowStatus.CREATED,
        state_data: Dict[str, Any] = None,
    ):
        return HITLWorkflowState(
            workflow_id=workflow_id,
            status=status,
            current_node="test_node",
            state_data=state_data or {},
        )
    return _generate


@pytest.fixture
def generate_checkpoint():
    """Factory fixture for creating checkpoints."""
    def _generate(
        checkpoint_id: str,
        workflow_id: str,
        node_name: str = "test_node",
        state_snapshot: Dict[str, Any] = None,
        status: WorkflowStatus = WorkflowStatus.PAUSED_FOR_HUMAN,
    ):
        checkpoint = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            status=status,
            node_name=node_name,
            state_snapshot=state_snapshot or {"test": "data"},
        )
        checkpoint.state_hash = checkpoint.compute_hash()
        return checkpoint
    return _generate


# ============================================================================
# PYTEST HOOKS
# ============================================================================

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_makereport(item, call):
    """
    Make test reports include execution time.

    This hook is called after each test phase (setup, call, teardown)
    and can be used to modify the report.
    """
    if call.when == "call":
        item.execution_time = call.stop - call.start


@pytest.fixture(autouse=True)
def reset_module_state():
    """
    Reset module state between tests to prevent cross-test contamination.

    Runs before and after each test.
    """
    yield
    # Cleanup after test if needed
    pass


# ============================================================================
# UTILITY FIXTURES
# ============================================================================

@pytest.fixture
def capture_logs(caplog):
    """
    Fixture to capture and inspect log messages during tests.

    Usage:
        def test_something(capture_logs):
            # test code
            assert "Expected message" in capture_logs.text
    """
    import logging
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.fixture
def benchmark_timer():
    """
    Simple timer fixture for manual benchmarking.

    Usage:
        def test_performance(benchmark_timer):
            start, end = benchmark_timer()
            # code to time
            elapsed = end() - start()
    """
    import time

    class Timer:
        def __call__(self):
            start_time = time.perf_counter()

            def end():
                return time.perf_counter() - start_time

            return start_time, end

    return Timer()
