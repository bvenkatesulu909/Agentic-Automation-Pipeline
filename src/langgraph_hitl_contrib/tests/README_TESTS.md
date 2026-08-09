# HITL State Manager - Comprehensive Test Suite

This directory contains comprehensive unit tests, integration tests, and benchmarks for the LangGraph HITL (Human-in-the-Loop) State Manager.

## Test Organization

### Unit Tests
Tests for individual components in isolation:

- **CheckpointRecord**: Testing checkpoint creation, serialization, hashing, and integrity verification
- **HITLWorkflowState**: Testing workflow state management and serialization
- **StateModification**: Testing state modification tracking
- **HITLStateManager**: Testing checkpoint creation, workflow restoration, status updates
- **CrashRecovery**: Testing crash detection and recovery strategies
- **ResumeAndWhatIf**: Testing workflow resumption and what-if scenarios

### Integration Tests
End-to-end workflow scenarios:

- **Full workflow lifecycle**: Create → Checkpoint → Restore → Modify → Resume
- **Multi-checkpoint workflows**: Multiple checkpoints across workflow execution
- **Checkpoint comparison**: Comparing state changes between checkpoints
- **State modification tracking**: Verifying audit trails

### Checkpoint Restorer Tests
Tests for the CheckpointRestorer component:

- **State restoration**: Recovering state from checkpoints
- **Custom validation**: User-defined checkpoint validation
- **State modification**: Restoring and modifying state atomically
- **Export/import**: Checkpoint serialization in various formats
- **Metadata retrieval**: Quick checkpoint inspection without full state loading

### Scale Tests
Tests with large datasets:

- **100 checkpoint workflow**: Creates 100 checkpoints and verifies all
- **1000 checkpoint workflow**: Creates 1000 checkpoints and verifies performance
- **Concurrent restoration**: Multiple workflows restored concurrently

### Benchmark Tests
Performance benchmarks:

- **Checkpoint creation speed**: Time to create a checkpoint
- **Workflow restoration speed**: Time to restore a workflow
- **Checkpoint validation speed**: Time to validate a checkpoint
- **Large state handling**: Performance with large state snapshots (1000+ keys)
- **Hash computation**: Performance of integrity hash computation

## Running Tests

### Run All Tests
```bash
pytest src/langgraph_hitl_contrib/tests/test_state_manager.py -v
```

### Run Specific Test Class
```bash
pytest src/langgraph_hitl_contrib/tests/test_state_manager.py::TestCheckpointRecord -v
```

### Run Unit Tests Only
```bash
pytest src/langgraph_hitl_contrib/tests/test_state_manager.py -m unit
```

### Run Integration Tests Only
```bash
pytest src/langgraph_hitl_contrib/tests/test_state_manager.py::TestIntegration -v
```

### Run Scale Tests
```bash
pytest src/langgraph_hitl_contrib/tests/test_state_manager.py::TestScale -v
```

### Run Benchmarks
```bash
pytest src/langgraph_hitl_contrib/tests/test_state_manager.py::TestBenchmarks -v --benchmark-only
```

### Run Tests Without Slow Tests
```bash
pytest src/langgraph_hitl_contrib/tests/test_state_manager.py -m "not slow"
```

## Test Coverage

The test suite covers:

### Checkpoint Record
- ✓ Creation and initialization
- ✓ Serialization (to/from dict and JSON)
- ✓ Hash computation and integrity verification
- ✓ State snapshot tampering detection

### Workflow State
- ✓ State creation and management
- ✓ Serialization and deserialization
- ✓ Metadata tracking
- ✓ Checkpoint history management

### State Manager Core
- ✓ Checkpoint creation with hash computation
- ✓ Workflow restoration (in-memory and persistent)
- ✓ Status updates with human feedback
- ✓ Heartbeat tracking
- ✓ Workflow history retrieval

### Crash Recovery
- ✓ Crash detection via heartbeat timeout
- ✓ Recovery strategies (RESUME, RETRY, ROLLBACK, MANUAL)
- ✓ Recovery recording and audit trail
- ✓ Error handling for recovery failures

### Workflow Resumption
- ✓ Resume from checkpoint with state validation
- ✓ State modification during resumption
- ✓ Execution hook callbacks
- ✓ Error handling during resumption

### What-If Scenarios
- ✓ Scenario execution from checkpoints
- ✓ State modification for scenarios
- ✓ Scenario result tracking
- ✓ Execution time measurement

### Checkpoint Restorer
- ✓ State restoration with integrity checks
- ✓ Custom validation callbacks
- ✓ State modification tracking
- ✓ Checkpoint export in multiple formats
- ✓ Checkpoint comparison and diff
- ✓ Metadata-only retrieval

### Performance
- ✓ Checkpoint creation speed
- ✓ Workflow restoration with many checkpoints
- ✓ Large state snapshot handling (1000+ keys)
- ✓ Concurrent workflow operations
- ✓ Hash computation performance

## Test Dependencies

The test suite requires:

```bash
pip install pytest pytest-benchmark
```

Optional but recommended:

```bash
pip install pytest-timeout pytest-cov
```

## Performance Benchmarks

Expected performance on modern hardware:

| Operation | Typical Time |
|-----------|-------------|
| Create checkpoint | < 5ms |
| Restore workflow (10 checkpoints) | < 10ms |
| Validate checkpoint | < 2ms |
| Compute state hash | < 5ms |
| Large state (1000 keys) | < 20ms |

## Fixtures

Common test fixtures:

- **state_manager**: HITLStateManager instance with in-memory storage
- **checkpoint_restorer**: CheckpointRestorer instance
- **sample_workflow_state**: Pre-configured workflow state
- **sample_checkpoint**: Pre-configured checkpoint record
- **mock_graph**: Mock LangGraph graph for testing resumption

## Example Test Patterns

### Testing Checkpoint Creation
```python
def test_create_checkpoint(state_manager):
    workflow_id = "wf_001"
    state_snapshot = {"key": "value"}
    
    checkpoint = state_manager.create_checkpoint(
        workflow_id=workflow_id,
        node_name="process",
        state_snapshot=state_snapshot,
    )
    
    assert checkpoint.checkpoint_id is not None
    assert checkpoint.state_hash is not None
```

### Testing Workflow Resumption
```python
def test_resume_from_checkpoint(state_manager, mock_graph):
    workflow = HITLWorkflowState(
        workflow_id="wf_001",
        status=WorkflowStatus.PAUSED_FOR_HUMAN,
        current_node="review",
        state_data={},
    )
    state_manager._workflows["wf_001"] = workflow
    
    checkpoint = state_manager.create_checkpoint(
        workflow_id="wf_001",
        node_name="review",
        state_snapshot={"data": "test"},
    )
    
    result = state_manager.resume_from_checkpoint(
        workflow_id="wf_001",
        checkpoint_id=checkpoint.checkpoint_id,
        graph=mock_graph,
        state_modifications={"approved": True},
    )
    
    assert result is not None
```

### Testing Crash Recovery
```python
def test_crash_recovery(state_manager):
    workflow = HITLWorkflowState(
        workflow_id="wf_001",
        status=WorkflowStatus.RUNNING,
        current_node="process",
        state_data={},
        last_heartbeat=datetime.utcnow() - timedelta(seconds=400),
    )
    state_manager._workflows["wf_001"] = workflow
    
    recovery = state_manager.recover_from_crash(
        "wf_001",
        strategy=RecoveryStrategy.RESUME,
    )
    
    assert recovery.success
```

## Continuous Integration

The test suite is designed to run in CI/CD pipelines:

```bash
# Run all tests with coverage
pytest src/langgraph_hitl_contrib/tests/ --cov=src/langgraph_hitl_contrib --cov-report=html

# Run without slow tests for quick feedback
pytest src/langgraph_hitl_contrib/tests/ -m "not slow"

# Generate JUnit XML for CI systems
pytest src/langgraph_hitl_contrib/tests/ --junit-xml=results.xml
```

## Troubleshooting

### ImportError for langgraph
The example tests require langgraph. Install with:
```bash
pip install langgraph
```

### Benchmark Not Running
Ensure pytest-benchmark is installed:
```bash
pip install pytest-benchmark
```

### Timeout Errors
Increase timeout in pytest.ini:
```ini
timeout = 600
```

## Contributing Tests

When adding new tests:

1. Follow the existing test structure
2. Use appropriate fixtures
3. Add docstrings explaining what is tested
4. Mark tests with appropriate markers (@pytest.mark.unit, @pytest.mark.integration, etc.)
5. Include both happy path and error cases
6. Add benchmarks for performance-sensitive code

## Test Maintenance

Regular maintenance tasks:

- Update benchmarks when performance characteristics change
- Review slow tests and optimize if possible
- Update scale test limits based on performance targets
- Add tests for bug fixes to prevent regression
