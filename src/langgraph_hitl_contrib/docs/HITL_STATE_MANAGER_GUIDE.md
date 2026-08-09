# LangGraph HITL State Manager Implementation Guide

## Overview

The HITL (Human-In-The-Loop) State Manager provides production-grade workflow state management for LangGraph applications that require human intervention, approval, and oversight. This implementation supports:

- **Checkpoint Management**: Save and restore workflow state at any point
- **Server Crash Recovery**: Automatic detection and recovery from unplanned shutdowns
- **State Mutation**: Modify workflow state before resumption (human overrides)
- **Workflow Replay**: Re-execute workflows for testing and auditing
- **What-If Scenarios**: Test alternative execution paths without modifying original state
- **Comprehensive Audit Trail**: Track all modifications, recoveries, and decisions
- **State Validation**: Ensure checkpoint integrity with hash verification

## Architecture

### Core Components

#### 1. HITLStateManager
Main state management engine with the following responsibilities:
- Restore workflows from persistent storage or memory
- Create and manage checkpoints
- Resume workflows from checkpoints with optional state modifications
- Detect and recover from server crashes
- Support workflow replay and what-if scenarios
- Maintain audit trail and heartbeat monitoring

#### 2. CheckpointRestorer
Specialized utilities for checkpoint operations:
- Restore checkpoint state with validation
- Apply and track state modifications
- Serialize/deserialize state (JSON, text, JSONL)
- Compare checkpoints to identify state changes
- Export checkpoints for audit purposes
- Support complex checkpoint queries with filtering

#### 3. Supporting Data Classes

**CheckpointRecord**: Represents a saved state snapshot
```python
@dataclass
class CheckpointRecord:
    checkpoint_id: str              # Unique identifier
    workflow_id: str                # Associated workflow
    timestamp: datetime             # When checkpoint was created
    status: WorkflowStatus          # Workflow status at checkpoint
    node_name: str                  # Current workflow node
    state_snapshot: Dict[str, Any]  # Full state data
    metadata: Dict[str, Any]        # Additional context
    human_feedback: Optional[str]   # Review notes
    human_approved: bool            # Approval status
    state_hash: Optional[str]       # Integrity verification
    parent_checkpoint_id: Optional[str]  # For what-if branches
    is_replay: bool                 # Replay flag
```

**StateModification**: Tracks state changes during resumption
```python
@dataclass
class StateModification:
    key: str                        # State key that changed
    old_value: Any                  # Previous value
    new_value: Any                  # New value
    reason: str                     # Why it changed
    applied_by: str                 # Who made the change
    applied_at: datetime            # When change occurred
```

**RecoveryRecord**: Documents crash recovery events
```python
@dataclass
class RecoveryRecord:
    recovery_id: str                # Unique recovery event ID
    workflow_id: str                # Affected workflow
    timestamp: datetime             # Recovery time
    crash_detected_at: datetime     # When crash was detected
    strategy: RecoveryStrategy      # Recovery strategy used
    checkpoint_id: str              # Checkpoint used for recovery
    success: bool                   # Whether recovery succeeded
    error_message: Optional[str]    # Error details if failed
```

**HITLWorkflowState**: Complete workflow state representation
- Contains all checkpoints, modifications, and recovery records
- Tracks workflow lifecycle and audit trail
- Maintains heartbeat for crash detection

## Key Features

### 1. Checkpoint Creation and Restoration

**Creating a checkpoint during workflow execution:**
```python
checkpoint = state_manager.create_checkpoint(
    workflow_id="workflow_123",
    node_name="approval_node",
    state_snapshot=current_state,
    status=WorkflowStatus.PAUSED_FOR_HUMAN,
    metadata={
        "execution_id": "exec_001",
        "user_email": "reviewer@example.com",
    }
)
```

**Restoring workflow from checkpoint:**
```python
workflow = state_manager.restore_workflow("workflow_123")
# Load all checkpoints and state
```

### 2. Server Crash Recovery

The system detects server crashes by monitoring heartbeats. If no heartbeat is received within the configured timeout (default: 5 minutes), the workflow is considered crashed.

**Implementation flow:**
1. Periodically call `update_heartbeat()` during execution
2. Detect crashes via `recover_from_crash()`
3. Apply recovery strategy (RESUME, RETRY, ROLLBACK, or MANUAL)
4. Automatically restore workflow to consistent state

**Example:**
```python
# During workflow execution
state_manager.update_heartbeat(workflow_id)

# After server restart
recovery = state_manager.recover_from_crash(
    workflow_id=workflow_id,
    strategy=RecoveryStrategy.RESUME
)

if recovery and recovery.success:
    print(f"Recovered from crash using checkpoint {recovery.checkpoint_id}")
```

**Recovery Strategies:**
- `RESUME`: Continue from last checkpoint
- `RETRY`: Retry the last failed operation
- `ROLLBACK`: Revert to previous checkpoint
- `MANUAL`: Require human intervention

### 3. State Mutation Before Resumption

Allows human reviewers to modify state before resuming workflow. All modifications are tracked for audit purposes.

**Example:**
```python
# Restore and modify state
modified_state, modifications = restorer.restore_and_modify_state(
    workflow_id="workflow_123",
    checkpoint_id="ckpt_xyz",
    modifications={
        'decision': 'approve',
        'confidence': 0.95,
    },
    applied_by="user:alice@example.com"
)

# modifications contains StateModification records for audit trail
for mod in modifications:
    print(f"Modified {mod.key}: {mod.old_value} -> {mod.new_value}")
```

**Tracking modifications:**
All state modifications are automatically recorded in the workflow's `state_modifications` list, providing a complete audit trail of all human interventions.

### 4. Workflow Replay

Re-execute a workflow from a checkpoint without modifying original state. Useful for:
- Testing what-if scenarios
- Auditing workflow behavior
- Debugging issues
- Generating reports

**Example:**
```python
result = state_manager.replay_workflow(
    workflow_id="workflow_123",
    checkpoint_id="ckpt_xyz",
    graph=workflow_graph,
    execution_hook=lambda event, data: print(f"{event}: {data}")
)
```

The replay execution includes `_is_replay: True` and `_replay_checkpoint_id` in the state, allowing nodes to detect and handle replay mode differently if needed.

### 5. What-If Scenario Analysis

Test alternative execution paths by modifying state at a checkpoint and re-executing without affecting the original workflow.

**Example:**
```python
scenario = state_manager.execute_what_if_scenario(
    workflow_id="workflow_123",
    checkpoint_id="ckpt_xyz",
    graph=workflow_graph,
    scenario_name="aggressive_approval",
    modifications={
        'confidence_threshold': 0.5,
        'approval_level': 'low',
    }
)

print(f"Scenario: {scenario['scenario_name']}")
print(f"Success: {scenario['success']}")
print(f"Execution time: {scenario['execution_time']:.2f}s")
```

**Returns:**
```python
{
    'scenario_name': str,           # Scenario name
    'result': Any,                  # Workflow result
    'modifications': Dict,          # Applied modifications
    'execution_time': float,        # Seconds to execute
    'success': bool,                # Whether it succeeded
    'error': Optional[str],         # Error message if failed
}
```

### 6. State Validation and Integrity

**Checkpoint validation:**
```python
is_valid = state_manager.validate_checkpoint(checkpoint_dict)
```

Validates:
- All required fields present
- Correct data types
- Valid enum values
- Proper timestamp format
- State snapshot integrity

**State hash verification:**
```python
# Checkpoints automatically compute and store state hash
checkpoint.state_hash == checkpoint.compute_hash()  # True if valid

# Verify integrity on restoration
if not checkpoint.verify_integrity():
    raise ValueError("Checkpoint state has been corrupted")
```

### 7. Checkpoint Comparison

Compare two checkpoints to identify state changes:

**Detailed comparison:**
```python
diff = restorer.compare_checkpoints(checkpoint1, checkpoint2)

print(f"Time elapsed: {diff['time_difference']} seconds")
print(f"Status changed: {diff['status_changed']}")
print(f"State keys added: {diff['state_keys_added']}")
print(f"State changes: {diff['state_changes']}")
```

**Human-readable diff:**
```python
summary = restorer.get_state_diff_summary(checkpoint1, checkpoint2)
print(summary)
```

### 8. Checkpoint Export and Import

**Export formats:**
- JSON: Complete structured data
- JSONL: Single-line JSON for streaming
- Text: Human-readable format

**Example:**
```python
# Export
json_str = restorer.export_checkpoint(
    workflow_id, checkpoint_id, format="json"
)

# Import
checkpoint = restorer.import_checkpoint_from_json(
    workflow_id, json_str
)
```

### 9. Query and Filtering

**Get checkpoint at specific node:**
```python
cp = restorer.get_checkpoint_at_node(workflow_id, "approval_node")
```

**Get checkpoints in time range:**
```python
from datetime import datetime, timedelta

start_time = datetime.utcnow() - timedelta(hours=1)
recent = restorer.get_checkpoints_after_time(workflow_id, start_time)
```

**List with filtering:**
```python
paused = restorer.list_checkpoints(
    workflow_id,
    status_filter=WorkflowStatus.PAUSED_FOR_HUMAN
)

approved = restorer.list_checkpoints(
    workflow_id,
    status_filter=WorkflowStatus.HUMAN_APPROVED
)
```

**Get metadata only:**
```python
# Fetch metadata without loading full state
metadata = restorer.get_checkpoint_metadata(workflow_id, checkpoint_id)
print(f"State size: {metadata['state_size_bytes']} bytes")

# List all metadata
all_metadata = restorer.list_checkpoint_metadata(workflow_id)
```

## Integration with Existing Components

### With SQLAlchemyApprovalStore

The state manager is designed to integrate seamlessly with the existing SQLAlchemyApprovalStore:

```python
from ragstack.db.store import SQLAlchemyApprovalStore
from langgraph_hitl_contrib.state_manager import HITLStateManager

# Initialize with database backend
store = SQLAlchemyApprovalStore("sqlite:///hitl_workflows.db")

state_manager = HITLStateManager(storage_backend=store)

# Checkpoints are automatically persisted
checkpoint = state_manager.create_checkpoint(...)
```

### With LangGraph Workflows

```python
from langgraph.graph import StateGraph

# Build workflow
workflow = StateGraph(WorkflowState)
workflow.add_node("analyze", analyze_node)
workflow.add_node("approve", approval_node)
workflow.add_edge("analyze", "approve")

compiled_graph = workflow.compile()

# Integrate checkpoints
state_manager.create_checkpoint(
    workflow_id=workflow_id,
    node_name="approve",
    state_snapshot=state,
    status=WorkflowStatus.PAUSED_FOR_HUMAN
)

# Resume from checkpoint
result = state_manager.resume_from_checkpoint(
    workflow_id=workflow_id,
    checkpoint_id=checkpoint_id,
    graph=compiled_graph
)
```

### With Approval Gates

```python
from ragstack.approval import ApprovalGate, ApprovalPolicy

gate = ApprovalGate(store, policy=ApprovalPolicy.AUTO_IF_UNCERTAIN)

# After gate evaluation
if state.get("approval_required"):
    # Create checkpoint at this point
    checkpoint = state_manager.create_checkpoint(
        workflow_id=state["workflow_id"],
        node_name="approval_gate",
        state_snapshot=state,
        status=WorkflowStatus.PAUSED_FOR_HUMAN
    )
```

## Usage Patterns

### Pattern 1: Basic Workflow with Checkpoint

```python
# Execute workflow
workflow = create_workflow_graph()
result = workflow.invoke(initial_state)

# Create checkpoint at decision point
checkpoint = state_manager.create_checkpoint(
    workflow_id=workflow_id,
    node_name="decision",
    state_snapshot=result,
    status=WorkflowStatus.PAUSED_FOR_HUMAN
)

# Later: Resume after human approval
modified_state = restorer.restore_and_modify_state(
    workflow_id,
    checkpoint_id,
    {'decision': 'approved'}
)
result = workflow.invoke(modified_state)
```

### Pattern 2: Production with Crash Recovery

```python
# In execution loop
while workflow_running:
    try:
        # Process workflow
        result = workflow.invoke(state)

        # Send heartbeat
        state_manager.update_heartbeat(workflow_id)

    except Exception as e:
        # Save state on error
        state_manager.create_checkpoint(
            workflow_id, current_node, state,
            status=WorkflowStatus.FAILED
        )
        raise

# On server restart
recovery = state_manager.recover_from_crash(
    workflow_id,
    strategy=RecoveryStrategy.RESUME
)
```

### Pattern 3: What-If Analysis

```python
# Get current checkpoint
current_checkpoint = restorer.get_checkpoint_at_node(
    workflow_id, "decision"
)

# Test scenarios
scenarios = [
    ("conservative", {"threshold": 0.99}),
    ("aggressive", {"threshold": 0.50}),
    ("balanced", {"threshold": 0.75}),
]

results = {}
for name, mods in scenarios:
    results[name] = state_manager.execute_what_if_scenario(
        workflow_id, current_checkpoint.checkpoint_id,
        workflow_graph, name, mods
    )

# Compare results without modifying original
```

## Performance Considerations

### Checkpoint Size
- State snapshots should be serializable as JSON
- Large binary objects should be stored separately
- Consider compression for very large states

### Heartbeat Frequency
- Default timeout: 5 minutes
- Adjust based on expected operation duration
- More frequent heartbeats = faster crash detection

### Storage Backend
- In-memory: Fast, not persistent
- SQLite: Good for development/small deployments
- PostgreSQL/MySQL: Recommended for production
- Consider archiving old checkpoints periodically

### State Modifications
- Tracked automatically for audit trail
- Can impact storage size if numerous
- Consider periodic consolidation

## Error Handling

### Checkpoint Not Found
```python
try:
    state = restorer.restore_checkpoint_state(workflow_id, checkpoint_id)
except ValueError as e:
    print(f"Checkpoint error: {e}")
    # Handle: checkpoint was deleted or workflow doesn't exist
```

### State Validation Failure
```python
try:
    state = restorer.restore_checkpoint_with_validation(
        workflow_id, checkpoint_id,
        validation_callback=lambda s: s.get('required_key') is not None
    )
except ValueError as e:
    print(f"Validation error: {e}")
    # Handle: state is missing required data
```

### Recovery Failure
```python
recovery = state_manager.recover_from_crash(workflow_id)
if recovery:
    if not recovery.success:
        print(f"Recovery failed: {recovery.error_message}")
        # Escalate to manual intervention
```

## Audit Trail and Compliance

All workflow state changes are automatically tracked:

```python
workflow = state_manager.restore_workflow(workflow_id)

# View all state modifications
for mod in workflow.state_modifications:
    print(f"{mod.applied_by} changed {mod.key}")
    print(f"  Reason: {mod.reason}")
    print(f"  Time: {mod.applied_at}")

# View all recovery events
for recovery in workflow.recovery_records:
    print(f"Recovery {recovery.recovery_id}")
    print(f"  Strategy: {recovery.strategy.value}")
    print(f"  Success: {recovery.success}")

# Export complete audit trail
export = restorer.export_checkpoint(workflow_id, checkpoint_id, format="json")
```

## Testing

See `tests/test_state_manager.py` for comprehensive test examples covering:
- Checkpoint creation and restoration
- State modifications and tracking
- Crash recovery scenarios
- What-if scenario execution
- Checkpoint comparison and analysis
- State serialization and validation

## Examples

Complete working examples are provided in:
- `examples/hitl_resume_example.py` - Basic workflow resumption
- `examples/hitl_advanced_example.py` - Advanced features (crash recovery, what-if, etc.)

## Troubleshooting

### Checkpoint Integrity Errors
- Verify state is JSON-serializable
- Check for circular references
- Ensure all custom objects have proper serialization

### Heartbeat Not Detected
- Verify `update_heartbeat()` is called regularly
- Check timeout configuration
- Ensure workflow has `last_heartbeat` set

### State Modification Not Applied
- Confirm state keys exist before modification
- Check for type mismatches
- Verify `applied_by` is set correctly

### What-If Scenarios Failing
- Ensure workflow graph can handle modifications
- Test with minimal modifications first
- Check execution hooks for error details

## Best Practices

1. **Create checkpoints at decision points** - Not on every iteration
2. **Use execution hooks for monitoring** - Track workflow progress
3. **Regularly call update_heartbeat()** - Enables crash detection
4. **Validate state before resumption** - Catch issues early
5. **Archive old checkpoints** - Manage storage growth
6. **Document modification reasons** - Support audit trail
7. **Test recovery scenarios** - Ensure crash recovery works
8. **Use what-if for analysis** - Don't skip testing alternatives
9. **Export checkpoints regularly** - Support compliance requirements
10. **Monitor recovery success rate** - Identify systemic issues
