# LangGraph HITL State Manager - API Reference

Complete API documentation for the HITL State Manager and Checkpoint Restorer.

## Table of Contents

1. [Enums and Constants](#enums-and-constants)
2. [Data Classes](#data-classes)
3. [HITLStateManager](#hitl-state-manager)
4. [CheckpointRestorer](#checkpoint-restorer)
5. [Exceptions](#exceptions)

---

## Enums and Constants

### WorkflowStatus

Enumeration of workflow execution statuses.

```python
class WorkflowStatus(Enum):
    CREATED = "created"              # Workflow created but not started
    RUNNING = "running"              # Workflow currently executing
    PAUSED_FOR_HUMAN = "paused_for_human"  # Waiting for human review
    HUMAN_APPROVED = "human_approved"      # Approved to continue
    HUMAN_REJECTED = "human_rejected"      # Rejected, workflow stopped
    COMPLETED = "completed"          # Successfully finished
    FAILED = "failed"                # Execution failed
    RECOVERED = "recovered"          # Recovered from crash
```

### RecoveryStrategy

Strategy for recovering from server crashes.

```python
class RecoveryStrategy(Enum):
    RESUME = "resume"       # Resume from last checkpoint
    RETRY = "retry"         # Retry the last failed operation
    ROLLBACK = "rollback"   # Rollback to previous checkpoint
    MANUAL = "manual"       # Manual intervention required
```

---

## Data Classes

### CheckpointRecord

Represents a checkpoint in workflow execution history.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `checkpoint_id` | str | Unique checkpoint identifier |
| `workflow_id` | str | Associated workflow ID |
| `timestamp` | datetime | When checkpoint was created |
| `status` | WorkflowStatus | Workflow status at checkpoint |
| `node_name` | str | Current workflow node name |
| `state_snapshot` | Dict[str, Any] | Full state data snapshot |
| `metadata` | Dict[str, Any] | Additional context (default: {}) |
| `human_feedback` | Optional[str] | Human reviewer notes |
| `human_approved` | bool | Whether human approved (default: False) |
| `state_hash` | Optional[str] | SHA256 hash for integrity verification |
| `parent_checkpoint_id` | Optional[str] | Parent checkpoint for what-if branches |
| `is_replay` | bool | Flag indicating replay checkpoint (default: False) |

#### Methods

##### `to_dict() -> Dict[str, Any]`
Convert checkpoint record to dictionary.

**Returns:** Dictionary representation with serialized timestamps

**Example:**
```python
data = checkpoint.to_dict()
json_str = json.dumps(data)
```

##### `from_dict(data: Dict[str, Any]) -> CheckpointRecord`
Create checkpoint record from dictionary.

**Args:**
- `data`: Dictionary with checkpoint data

**Returns:** CheckpointRecord instance

**Raises:** ValueError if data format is invalid

**Example:**
```python
checkpoint = CheckpointRecord.from_dict(data)
```

##### `compute_hash() -> str`
Compute SHA256 integrity hash of state snapshot.

**Returns:** Hexadecimal hash string

**Example:**
```python
hash_value = checkpoint.compute_hash()
```

##### `verify_integrity() -> bool`
Verify checkpoint integrity by comparing stored and computed hashes.

**Returns:** True if hash matches, False otherwise

**Example:**
```python
if not checkpoint.verify_integrity():
    raise ValueError("Checkpoint corrupted")
```

---

### StateModification

Tracks a state modification during resumption.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `key` | str | State key that was modified |
| `old_value` | Any | Previous value |
| `new_value` | Any | New value |
| `reason` | str | Why the change was made |
| `applied_by` | str | Who applied the modification |
| `applied_at` | datetime | When modification occurred |

#### Methods

##### `to_dict() -> Dict[str, Any]`
Convert modification to dictionary.

**Returns:** Dictionary representation

---

### RecoveryRecord

Documents a server crash recovery event.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `recovery_id` | str | Unique recovery event identifier |
| `workflow_id` | str | Affected workflow ID |
| `timestamp` | datetime | When recovery occurred |
| `crash_detected_at` | datetime | When crash was detected |
| `strategy` | RecoveryStrategy | Recovery strategy used |
| `checkpoint_id` | str | Checkpoint used for recovery |
| `success` | bool | Whether recovery succeeded |
| `error_message` | Optional[str] | Error details if failed |
| `metadata` | Dict[str, Any] | Additional context |

#### Methods

##### `to_dict() -> Dict[str, Any]`
Convert recovery record to dictionary.

**Returns:** Dictionary representation

---

### HITLWorkflowState

Represents complete state of a HITL workflow.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | str | Workflow identifier |
| `status` | WorkflowStatus | Current workflow status |
| `current_node` | str | Currently executing node name |
| `state_data` | Dict[str, Any] | Current state data |
| `checkpoints` | List[CheckpointRecord] | All checkpoints (default: []) |
| `created_at` | datetime | When workflow was created |
| `updated_at` | datetime | Last update time |
| `metadata` | Dict[str, Any] | Additional context (default: {}) |
| `state_modifications` | List[StateModification] | All state changes (default: []) |
| `recovery_records` | List[RecoveryRecord] | All recovery events (default: []) |
| `last_heartbeat` | Optional[datetime] | Last heartbeat timestamp |

#### Methods

##### `to_dict() -> Dict[str, Any]`
Convert workflow state to dictionary.

**Returns:** Dictionary representation with all fields serialized

##### `from_dict(data: Dict[str, Any]) -> HITLWorkflowState`
Create workflow state from dictionary.

**Args:**
- `data`: Dictionary with workflow state

**Returns:** HITLWorkflowState instance

---

## HITLStateManager

Main state management engine for HITL workflows.

### Constructor

```python
def __init__(
    self,
    storage_backend: Optional[Any] = None,
    heartbeat_timeout_seconds: int = 300,
)
```

**Args:**
- `storage_backend`: Optional persistence backend (SQLAlchemyApprovalStore, etc.)
- `heartbeat_timeout_seconds`: Timeout for crash detection (default: 300)

**Example:**
```python
manager = HITLStateManager(
    storage_backend=approval_store,
    heartbeat_timeout_seconds=600
)
```

### Methods

#### `restore_workflow(workflow_id: str) -> HITLWorkflowState`

Restore a workflow from storage.

**Args:**
- `workflow_id`: The workflow ID to restore

**Returns:** HITLWorkflowState with all checkpoints

**Raises:**
- `ValueError`: If workflow not found

**Example:**
```python
workflow = manager.restore_workflow("workflow_123")
print(f"Status: {workflow.status.value}")
```

---

#### `resume_from_checkpoint(workflow_id: str, checkpoint_id: str, graph: Any, state_modifications: Optional[Dict[str, Any]] = None, execution_hook: Optional[Callable] = None) -> Any`

Resume workflow from checkpoint with optional state modifications.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Checkpoint to resume from
- `graph`: Compiled LangGraph StateGraph
- `state_modifications`: Optional state changes before resumption
- `execution_hook`: Optional callback function(event_type, event_data)

**Returns:** Result of continued workflow execution

**Raises:**
- `ValueError`: If workflow or checkpoint not found
- `RuntimeError`: If checkpoint validation fails

**Example:**
```python
result = manager.resume_from_checkpoint(
    workflow_id="workflow_123",
    checkpoint_id="ckpt_xyz",
    graph=compiled_graph,
    state_modifications={'approved': True},
    execution_hook=lambda e, d: print(f"{e}: {d}")
)
```

---

#### `recover_from_crash(workflow_id: str, strategy: RecoveryStrategy = RecoveryStrategy.RESUME, execution_hook: Optional[Callable] = None) -> Optional[RecoveryRecord]`

Detect and recover from server crashes using heartbeat timeout.

**Args:**
- `workflow_id`: Workflow to recover
- `strategy`: Recovery strategy (RESUME, RETRY, ROLLBACK, or MANUAL)
- `execution_hook`: Optional callback for recovery events

**Returns:** RecoveryRecord if crash detected, None otherwise

**Raises:**
- `ValueError`: If workflow not found

**Example:**
```python
recovery = manager.recover_from_crash(
    workflow_id="workflow_123",
    strategy=RecoveryStrategy.RESUME
)

if recovery and recovery.success:
    print("Recovery successful")
```

---

#### `replay_workflow(workflow_id: str, checkpoint_id: str, graph: Any, execution_hook: Optional[Callable] = None) -> Any`

Replay workflow from checkpoint without modifying original state.

**Args:**
- `workflow_id`: Workflow to replay
- `checkpoint_id`: Checkpoint to start from
- `graph`: Compiled LangGraph StateGraph
- `execution_hook`: Optional callback for events

**Returns:** Workflow execution result

**Raises:**
- `ValueError`: If workflow or checkpoint not found

**Example:**
```python
result = manager.replay_workflow(
    workflow_id="workflow_123",
    checkpoint_id="ckpt_xyz",
    graph=compiled_graph
)
```

---

#### `execute_what_if_scenario(workflow_id: str, checkpoint_id: str, graph: Any, scenario_name: str, modifications: Dict[str, Any], execution_hook: Optional[Callable] = None) -> Dict[str, Any]`

Execute alternative execution path from checkpoint.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Starting checkpoint
- `graph`: Compiled LangGraph StateGraph
- `scenario_name`: Name for the scenario
- `modifications`: State modifications for scenario
- `execution_hook`: Optional callback for events

**Returns:** Dictionary with:
```python
{
    'scenario_name': str,
    'result': Any,
    'modifications': Dict,
    'execution_time': float,
    'success': bool,
    'error': Optional[str],
}
```

**Raises:**
- `ValueError`: If workflow or checkpoint not found

**Example:**
```python
scenario = manager.execute_what_if_scenario(
    workflow_id="workflow_123",
    checkpoint_id="ckpt_xyz",
    graph=compiled_graph,
    scenario_name="aggressive",
    modifications={'threshold': 0.5}
)

print(f"Success: {scenario['success']}")
print(f"Time: {scenario['execution_time']:.2f}s")
```

---

#### `update_heartbeat(workflow_id: str) -> None`

Update heartbeat for active workflow (crash detection).

**Args:**
- `workflow_id`: Workflow ID

**Example:**
```python
# Call periodically during execution
manager.update_heartbeat("workflow_123")
```

---

#### `create_checkpoint(workflow_id: str, node_name: str, state_snapshot: Dict[str, Any], status: WorkflowStatus = WorkflowStatus.PAUSED_FOR_HUMAN, metadata: Optional[Dict[str, Any]] = None) -> CheckpointRecord`

Create a new checkpoint.

**Args:**
- `workflow_id`: Workflow ID
- `node_name`: Current node name
- `state_snapshot`: State data to snapshot
- `status`: Workflow status (default: PAUSED_FOR_HUMAN)
- `metadata`: Additional context

**Returns:** CheckpointRecord

**Example:**
```python
checkpoint = manager.create_checkpoint(
    workflow_id="workflow_123",
    node_name="approval",
    state_snapshot=state,
    status=WorkflowStatus.PAUSED_FOR_HUMAN,
    metadata={"reviewer": "alice@example.com"}
)
```

---

#### `get_workflow_history(workflow_id: str) -> List[CheckpointRecord]`

Get all checkpoints for a workflow in chronological order.

**Args:**
- `workflow_id`: Workflow ID

**Returns:** List of CheckpointRecord objects

**Raises:**
- `ValueError`: If workflow not found

**Example:**
```python
history = manager.get_workflow_history("workflow_123")
for cp in history:
    print(f"{cp.node_name}: {cp.status.value}")
```

---

#### `validate_checkpoint(checkpoint: Dict[str, Any]) -> bool`

Validate checkpoint for integrity and completeness.

**Args:**
- `checkpoint`: Checkpoint dictionary to validate

**Returns:** True if valid, False otherwise

**Example:**
```python
if not manager.validate_checkpoint(cp_dict):
    raise ValueError("Invalid checkpoint")
```

---

#### `update_workflow_status(workflow_id: str, status: WorkflowStatus, human_feedback: Optional[str] = None) -> HITLWorkflowState`

Update workflow status (usually by human reviewer).

**Args:**
- `workflow_id`: Workflow ID
- `status`: New status
- `human_feedback`: Optional reviewer notes

**Returns:** Updated HITLWorkflowState

**Example:**
```python
workflow = manager.update_workflow_status(
    workflow_id="workflow_123",
    status=WorkflowStatus.HUMAN_APPROVED,
    human_feedback="Looks good to go"
)
```

---

#### `register_recovery_callback(workflow_id: str, callback: Callable[[RecoveryRecord], None]) -> None`

Register callback for recovery events.

**Args:**
- `workflow_id`: Workflow ID
- `callback`: Function(recovery_record) to call on recovery

**Example:**
```python
def on_recovery(recovery: RecoveryRecord):
    print(f"Recovered: {recovery.recovery_id}")

manager.register_recovery_callback("workflow_123", on_recovery)
```

---

## CheckpointRestorer

Utilities for checkpoint operations and analysis.

### Constructor

```python
def __init__(self, state_manager: HITLStateManager)
```

**Args:**
- `state_manager`: HITLStateManager instance to use

**Example:**
```python
restorer = CheckpointRestorer(state_manager)
```

### Methods

#### `restore_checkpoint_state(workflow_id: str, checkpoint_id: str) -> Dict[str, Any]`

Restore state from checkpoint with validation.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Checkpoint ID

**Returns:** State snapshot dictionary

**Raises:**
- `ValueError`: If checkpoint not found or invalid

**Example:**
```python
state = restorer.restore_checkpoint_state("workflow_123", "ckpt_xyz")
```

---

#### `restore_checkpoint_with_validation(workflow_id: str, checkpoint_id: str, validation_callback: Optional[Callable[[Dict[str, Any]], bool]] = None) -> Dict[str, Any]`

Restore checkpoint with custom validation.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Checkpoint ID
- `validation_callback`: Optional validator function

**Returns:** Validated state snapshot

**Raises:**
- `ValueError`: If checkpoint not found or validation fails

**Example:**
```python
def validate_state(state):
    return 'required_key' in state

state = restorer.restore_checkpoint_with_validation(
    "workflow_123",
    "ckpt_xyz",
    validation_callback=validate_state
)
```

---

#### `restore_and_modify_state(workflow_id: str, checkpoint_id: str, modifications: Dict[str, Any], applied_by: str = "system") -> Tuple[Dict[str, Any], List[StateModification]]`

Restore checkpoint and apply state modifications.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Checkpoint ID
- `modifications`: State changes to apply
- `applied_by`: Who is applying changes

**Returns:** Tuple of (modified_state, list of StateModification records)

**Example:**
```python
state, mods = restorer.restore_and_modify_state(
    "workflow_123",
    "ckpt_xyz",
    {'decision': 'approve', 'confidence': 0.95},
    applied_by="user:alice@example.com"
)

for mod in mods:
    print(f"{mod.key}: {mod.old_value} -> {mod.new_value}")
```

---

#### `deserialize_state_from_json(json_str: str, schema: Optional[Dict[str, type]] = None) -> Dict[str, Any]`

Deserialize state from JSON with optional schema validation.

**Args:**
- `json_str`: JSON string
- `schema`: Optional type validation schema

**Returns:** Deserialized state dictionary

**Raises:**
- `ValueError`: If JSON invalid or schema validation fails

**Example:**
```python
state = restorer.deserialize_state_from_json(
    '{"key": "value"}',
    schema={'key': str}
)
```

---

#### `resume_workflow(workflow_id: str, checkpoint_id: str, graph: Any, execution_hook: Optional[Callable] = None) -> Any`

Convenience wrapper to resume workflow from checkpoint.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Checkpoint to resume from
- `graph`: Compiled LangGraph StateGraph
- `execution_hook`: Optional callback for events

**Returns:** Workflow execution result

**Example:**
```python
result = restorer.resume_workflow(
    "workflow_123",
    "ckpt_xyz",
    compiled_graph
)
```

---

#### `get_checkpoint_at_node(workflow_id: str, node_name: str) -> Optional[CheckpointRecord]`

Get latest checkpoint at specific node.

**Args:**
- `workflow_id`: Workflow ID
- `node_name`: Node name to search for

**Returns:** CheckpointRecord or None

**Example:**
```python
cp = restorer.get_checkpoint_at_node("workflow_123", "approval")
if cp:
    print(f"Found checkpoint at approval: {cp.checkpoint_id}")
```

---

#### `get_checkpoints_after_time(workflow_id: str, timestamp: datetime) -> List[CheckpointRecord]`

Get checkpoints created after specific time.

**Args:**
- `workflow_id`: Workflow ID
- `timestamp`: Cutoff time

**Returns:** List of CheckpointRecord objects

**Example:**
```python
from datetime import datetime, timedelta

start = datetime.utcnow() - timedelta(hours=1)
recent = restorer.get_checkpoints_after_time("workflow_123", start)
```

---

#### `get_checkpoints_before_time(workflow_id: str, timestamp: datetime) -> List[CheckpointRecord]`

Get checkpoints created before specific time.

**Args:**
- `workflow_id`: Workflow ID
- `timestamp`: Cutoff time

**Returns:** List of CheckpointRecord objects

---

#### `get_approved_checkpoints(workflow_id: str) -> List[CheckpointRecord]`

Get all human-approved checkpoints.

**Args:**
- `workflow_id`: Workflow ID

**Returns:** List of approved CheckpointRecord objects

**Example:**
```python
approved = restorer.get_approved_checkpoints("workflow_123")
print(f"Approved checkpoints: {len(approved)}")
```

---

#### `get_rejected_checkpoints(workflow_id: str) -> List[CheckpointRecord]`

Get all rejected checkpoints.

**Args:**
- `workflow_id`: Workflow ID

**Returns:** List of rejected CheckpointRecord objects

---

#### `list_checkpoints(workflow_id: str, status_filter: Optional[WorkflowStatus] = None, node_filter: Optional[str] = None, limit: Optional[int] = None) -> List[CheckpointRecord]`

List checkpoints with optional filters.

**Args:**
- `workflow_id`: Workflow ID
- `status_filter`: Filter by status
- `node_filter`: Filter by node name
- `limit`: Maximum results

**Returns:** List of CheckpointRecord objects

**Example:**
```python
paused = restorer.list_checkpoints(
    "workflow_123",
    status_filter=WorkflowStatus.PAUSED_FOR_HUMAN,
    limit=10
)
```

---

#### `rollback_to_checkpoint(workflow_id: str, checkpoint_id: str) -> HITLWorkflowState`

Rollback workflow to previous checkpoint.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Checkpoint to rollback to

**Returns:** Updated HITLWorkflowState

**Example:**
```python
workflow = restorer.rollback_to_checkpoint(
    "workflow_123",
    "ckpt_xyz"
)
```

---

#### `compare_checkpoints(checkpoint1: CheckpointRecord, checkpoint2: CheckpointRecord) -> Dict[str, Any]`

Compare two checkpoints to identify differences.

**Args:**
- `checkpoint1`: First checkpoint
- `checkpoint2`: Second checkpoint

**Returns:** Dictionary with comparison results

**Example:**
```python
diff = restorer.compare_checkpoints(cp1, cp2)
print(f"Changes: {diff['total_changes']}")
```

---

#### `get_state_diff_summary(checkpoint1: CheckpointRecord, checkpoint2: CheckpointRecord) -> str`

Get human-readable diff summary.

**Args:**
- `checkpoint1`: First checkpoint
- `checkpoint2`: Second checkpoint

**Returns:** Formatted string with differences

**Example:**
```python
summary = restorer.get_state_diff_summary(cp1, cp2)
print(summary)
```

---

#### `export_checkpoint(workflow_id: str, checkpoint_id: str, format: str = "json") -> str`

Export checkpoint to string format.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Checkpoint ID
- `format`: Export format ("json", "jsonl", or "text")

**Returns:** Exported checkpoint as string

**Example:**
```python
json_export = restorer.export_checkpoint(
    "workflow_123",
    "ckpt_xyz",
    format="json"
)
```

---

#### `import_checkpoint_from_json(workflow_id: str, json_str: str) -> CheckpointRecord`

Import checkpoint from JSON.

**Args:**
- `workflow_id`: Expected workflow ID
- `json_str`: JSON string with checkpoint data

**Returns:** CheckpointRecord

**Raises:**
- `ValueError`: If JSON invalid or workflow ID mismatch

**Example:**
```python
cp = restorer.import_checkpoint_from_json("workflow_123", json_str)
```

---

#### `get_checkpoint_metadata(workflow_id: str, checkpoint_id: str) -> Dict[str, Any]`

Get checkpoint metadata without loading full state.

**Args:**
- `workflow_id`: Workflow ID
- `checkpoint_id`: Checkpoint ID

**Returns:** Dictionary with checkpoint metadata

**Example:**
```python
metadata = restorer.get_checkpoint_metadata("workflow_123", "ckpt_xyz")
print(f"State size: {metadata['state_size_bytes']} bytes")
```

---

#### `list_checkpoint_metadata(workflow_id: str) -> List[Dict[str, Any]]`

List metadata for all checkpoints.

**Args:**
- `workflow_id`: Workflow ID

**Returns:** List of metadata dictionaries

**Example:**
```python
all_meta = restorer.list_checkpoint_metadata("workflow_123")
for meta in all_meta:
    print(f"{meta['checkpoint_id']}: {meta['state_size_bytes']} bytes")
```

---

## Exceptions

### ValueError

Raised when:
- Workflow not found
- Checkpoint not found
- Checkpoint validation fails
- State deserialization fails
- Custom validation fails
- Invalid parameters

### RuntimeError

Raised when:
- Checkpoint integrity check fails during resumption
- Recovery strategy fails

---

## Constants

### Default Configurations

```python
DEFAULT_HEARTBEAT_TIMEOUT = 300  # 5 minutes
DEFAULT_CHECKPOINT_STATUS = WorkflowStatus.PAUSED_FOR_HUMAN
DEFAULT_RECOVERY_STRATEGY = RecoveryStrategy.RESUME
```

### Storage Keys

```python
WORKFLOW_KEY_TEMPLATE = "workflow:{workflow_id}"
CHECKPOINT_KEY_TEMPLATE = "checkpoint:{checkpoint_id}"
RECOVERY_KEY_TEMPLATE = "recovery:{recovery_id}"
```
