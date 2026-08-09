# LangGraph HITL State Manager - Integration Guide

## Quick Start

### 1. Basic Setup

```python
from langgraph_hitl_contrib.state_manager import HITLStateManager
from langgraph_hitl_contrib.checkpoint_restorer import CheckpointRestorer

# In-memory storage (development)
state_manager = HITLStateManager()
restorer = CheckpointRestorer(state_manager)

# With persistent storage (production)
from ragstack.db.store import SQLAlchemyApprovalStore

store = SQLAlchemyApprovalStore("sqlite:///workflows.db")
state_manager = HITLStateManager(storage_backend=store)
```

### 2. Create Workflow Checkpoints

```python
# During workflow execution
checkpoint = state_manager.create_checkpoint(
    workflow_id="workflow_123",
    node_name="approval",
    state_snapshot=current_state,
    status=WorkflowStatus.PAUSED_FOR_HUMAN,
    metadata={"reviewer": "alice@example.com"}
)
```

### 3. Resume with Modifications

```python
# Human reviews and modifies state
result = state_manager.resume_from_checkpoint(
    workflow_id="workflow_123",
    checkpoint_id=checkpoint.checkpoint_id,
    graph=workflow_graph,
    state_modifications={'approved': True}
)
```

## Advanced Integration Scenarios

### Scenario 1: Web API Endpoints for Workflow Management

```python
from fastapi import FastAPI, HTTPException
from datetime import datetime

app = FastAPI()

state_manager = HITLStateManager(storage_backend=approval_store)
restorer = CheckpointRestorer(state_manager)

@app.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    """Get workflow status and checkpoint history."""
    try:
        workflow = state_manager.restore_workflow(workflow_id)
        return {
            "id": workflow.workflow_id,
            "status": workflow.status.value,
            "current_node": workflow.current_node,
            "checkpoints": [
                {
                    "id": cp.checkpoint_id,
                    "node": cp.node_name,
                    "status": cp.status.value,
                    "time": cp.timestamp.isoformat(),
                }
                for cp in workflow.checkpoints
            ],
        }
    except ValueError:
        raise HTTPException(status_code=404, detail="Workflow not found")

@app.post("/workflows/{workflow_id}/checkpoint/{checkpoint_id}/approve")
def approve_checkpoint(workflow_id: str, checkpoint_id: str, body: dict):
    """Approve a checkpoint and resume workflow."""
    try:
        restorer.resume_workflow(
            workflow_id=workflow_id,
            checkpoint_id=checkpoint_id,
            graph=workflow_graph,
            execution_hook=lambda e, d: log_event(e, d)
        )
        return {"status": "approved", "workflow_id": workflow_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/workflows/{workflow_id}/checkpoint/{checkpoint_id}/modify")
def modify_and_resume(workflow_id: str, checkpoint_id: str, modifications: dict):
    """Modify state and resume workflow."""
    try:
        result = state_manager.resume_from_checkpoint(
            workflow_id=workflow_id,
            checkpoint_id=checkpoint_id,
            graph=workflow_graph,
            state_modifications=modifications,
        )
        return {"status": "resumed", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/workflows/{workflow_id}/compare/{cp1}/{cp2}")
def compare_checkpoints_endpoint(workflow_id: str, cp1: str, cp2: str):
    """Compare two checkpoints."""
    try:
        workflow = state_manager.restore_workflow(workflow_id)
        checkpoint1 = next(cp for cp in workflow.checkpoints if cp.checkpoint_id == cp1)
        checkpoint2 = next(cp for cp in workflow.checkpoints if cp.checkpoint_id == cp2)
        
        diff = restorer.compare_checkpoints(checkpoint1, checkpoint2)
        return diff
    except (ValueError, StopIteration):
        raise HTTPException(status_code=404, detail="Checkpoint not found")

@app.post("/workflows/{workflow_id}/whatif")
def scenario_analysis(workflow_id: str, scenario: dict):
    """Execute what-if scenario."""
    try:
        result = state_manager.execute_what_if_scenario(
            workflow_id=workflow_id,
            checkpoint_id=scenario["checkpoint_id"],
            graph=workflow_graph,
            scenario_name=scenario["name"],
            modifications=scenario.get("modifications", {})
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### Scenario 2: Celery Task with Crash Recovery

```python
from celery import Celery, Task
from celery.exceptions import SoftTimeLimitExceeded

app = Celery('workflows')
state_manager = HITLStateManager(storage_backend=approval_store)

class WorkflowTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure - save state for recovery."""
        workflow_id = kwargs.get('workflow_id')
        if workflow_id:
            # Save current state
            workflow = state_manager.restore_workflow(workflow_id)
            workflow.status = WorkflowStatus.FAILED
            state_manager._workflows[workflow_id] = workflow

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Update heartbeat on retry."""
        workflow_id = kwargs.get('workflow_id')
        if workflow_id:
            state_manager.update_heartbeat(workflow_id)

@app.task(bind=True, base=WorkflowTask, soft_time_limit=3600)
def execute_workflow(self, workflow_id: str, checkpoint_id: str = None):
    """Execute workflow with automatic recovery."""
    try:
        # Check for crash recovery
        recovery = state_manager.recover_from_crash(
            workflow_id,
            strategy=RecoveryStrategy.RESUME
        )

        if recovery and recovery.success:
            checkpoint_id = recovery.checkpoint_id

        # Execute workflow
        if checkpoint_id:
            result = state_manager.resume_from_checkpoint(
                workflow_id=workflow_id,
                checkpoint_id=checkpoint_id,
                graph=workflow_graph,
                execution_hook=lambda e, d: send_event(workflow_id, e, d)
            )
        else:
            result = workflow_graph.invoke(initial_state)

        # Send heartbeat periodically
        for i in range(0, len(workflow_steps)):
            state_manager.update_heartbeat(workflow_id)
            # Execute step...
            
        return result

    except SoftTimeLimitExceeded:
        # Time limit exceeded - save state for recovery
        workflow = state_manager.restore_workflow(workflow_id)
        checkpoint = state_manager.create_checkpoint(
            workflow_id=workflow_id,
            node_name=workflow.current_node,
            state_snapshot=workflow.state_data,
            status=WorkflowStatus.FAILED
        )
        self.retry(countdown=300)  # Retry after 5 minutes
```

### Scenario 3: Async Workflow with Streaming Updates

```python
import asyncio
from typing import AsyncGenerator

async def stream_workflow_updates(
    workflow_id: str,
    checkpoint_id: str
) -> AsyncGenerator[str, None]:
    """Stream workflow execution updates via SSE."""
    
    execution_events = []
    
    def event_hook(event_type: str, event_data: dict):
        """Collect events for streaming."""
        execution_events.append({
            'type': event_type,
            'data': event_data,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    # Run workflow in thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: state_manager.resume_from_checkpoint(
            workflow_id=workflow_id,
            checkpoint_id=checkpoint_id,
            graph=workflow_graph,
            execution_hook=event_hook
        )
    )
    
    # Yield events as they occur
    for event in execution_events:
        yield f"data: {json.dumps(event)}\n\n"
    
    # Final result
    yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"

# In FastAPI
@app.get("/workflows/{workflow_id}/stream")
async def stream_workflow(workflow_id: str, checkpoint_id: str):
    """Stream workflow execution updates."""
    return StreamingResponse(
        stream_workflow_updates(workflow_id, checkpoint_id),
        media_type="text/event-stream"
    )
```

### Scenario 4: Scheduled What-If Analysis

```python
from APScheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

def scheduled_scenario_analysis(workflow_template_id: str):
    """Run periodic what-if analysis on workflow template."""
    
    # Get latest workflow
    workflow = state_manager.restore_workflow(workflow_template_id)
    
    if not workflow.checkpoints:
        return
    
    latest_checkpoint = workflow.checkpoints[-1]
    
    # Define scenarios to analyze
    scenarios = [
        {
            "name": "pessimistic",
            "modifications": {"confidence_threshold": 0.99}
        },
        {
            "name": "optimistic",
            "modifications": {"confidence_threshold": 0.50}
        },
        {
            "name": "standard",
            "modifications": {"confidence_threshold": 0.75}
        },
    ]
    
    results = {}
    for scenario in scenarios:
        try:
            result = state_manager.execute_what_if_scenario(
                workflow_id=workflow_template_id,
                checkpoint_id=latest_checkpoint.checkpoint_id,
                graph=workflow_graph,
                scenario_name=scenario["name"],
                modifications=scenario["modifications"]
            )
            results[scenario["name"]] = {
                "success": result["success"],
                "time": result["execution_time"]
            }
        except Exception as e:
            results[scenario["name"]] = {"error": str(e)}
    
    # Store analysis results
    store_analysis_results(workflow_template_id, results)

# Schedule to run every night
scheduler.add_job(
    scheduled_scenario_analysis,
    "cron",
    hour=2,
    minute=0,
    args=["workflow_template_001"]
)
scheduler.start()
```

### Scenario 5: Workflow Dashboard with Audit Trail

```python
def get_workflow_dashboard(workflow_id: str) -> dict:
    """Get comprehensive workflow dashboard."""
    
    workflow = state_manager.restore_workflow(workflow_id)
    history = state_manager.get_workflow_history(workflow_id)
    
    # Calculate metrics
    total_checkpoints = len(workflow.checkpoints)
    approval_rate = len([cp for cp in workflow.checkpoints if cp.human_approved]) / max(total_checkpoints, 1)
    avg_time_between_checkpoints = (
        (workflow.updated_at - workflow.created_at).total_seconds() / total_checkpoints
        if total_checkpoints > 0 else 0
    )
    
    return {
        "workflow_id": workflow_id,
        "status": workflow.status.value,
        "metrics": {
            "total_checkpoints": total_checkpoints,
            "approval_rate": approval_rate,
            "avg_time_per_checkpoint": avg_time_between_checkpoints,
            "total_modifications": len(workflow.state_modifications),
            "total_recoveries": len(workflow.recovery_records),
        },
        "timeline": [
            {
                "type": "checkpoint",
                "checkpoint_id": cp.checkpoint_id,
                "node": cp.node_name,
                "status": cp.status.value,
                "time": cp.timestamp.isoformat(),
            }
            for cp in history
        ] + [
            {
                "type": "recovery",
                "recovery_id": r.recovery_id,
                "strategy": r.strategy.value,
                "success": r.success,
                "time": r.timestamp.isoformat(),
            }
            for r in workflow.recovery_records
        ],
        "audit_trail": [
            {
                "type": "modification",
                "key": m.key,
                "old_value": str(m.old_value),
                "new_value": str(m.new_value),
                "applied_by": m.applied_by,
                "time": m.applied_at.isoformat(),
            }
            for m in workflow.state_modifications
        ],
    }
```

### Scenario 6: Compliance and Audit Export

```python
def generate_compliance_report(workflow_id: str, output_path: str):
    """Generate comprehensive compliance report with full audit trail."""
    
    workflow = state_manager.restore_workflow(workflow_id)
    restorer = CheckpointRestorer(state_manager)
    
    with open(output_path, 'w') as f:
        # Header
        f.write(f"WORKFLOW AUDIT REPORT\n")
        f.write(f"{'='*60}\n")
        f.write(f"Workflow ID: {workflow_id}\n")
        f.write(f"Created: {workflow.created_at.isoformat()}\n")
        f.write(f"Updated: {workflow.updated_at.isoformat()}\n")
        f.write(f"Status: {workflow.status.value}\n\n")
        
        # Checkpoint history
        f.write(f"CHECKPOINT HISTORY\n")
        f.write(f"{'='*60}\n")
        for i, cp in enumerate(workflow.checkpoints, 1):
            f.write(f"\n[Checkpoint {i}]\n")
            f.write(f"ID: {cp.checkpoint_id}\n")
            f.write(f"Node: {cp.node_name}\n")
            f.write(f"Status: {cp.status.value}\n")
            f.write(f"Time: {cp.timestamp.isoformat()}\n")
            f.write(f"Human Approved: {cp.human_approved}\n")
            if cp.human_feedback:
                f.write(f"Feedback: {cp.human_feedback}\n")
        
        # State modifications
        f.write(f"\n\nSTATE MODIFICATIONS\n")
        f.write(f"{'='*60}\n")
        for mod in workflow.state_modifications:
            f.write(f"\n{mod.key}:\n")
            f.write(f"  Before: {mod.old_value}\n")
            f.write(f"  After: {mod.new_value}\n")
            f.write(f"  By: {mod.applied_by}\n")
            f.write(f"  Reason: {mod.reason}\n")
            f.write(f"  Time: {mod.applied_at.isoformat()}\n")
        
        # Recovery records
        f.write(f"\n\nRECOVERY EVENTS\n")
        f.write(f"{'='*60}\n")
        for recovery in workflow.recovery_records:
            f.write(f"\n{recovery.recovery_id}:\n")
            f.write(f"  Strategy: {recovery.strategy.value}\n")
            f.write(f"  Success: {recovery.success}\n")
            f.write(f"  Detected: {recovery.crash_detected_at.isoformat()}\n")
            if recovery.error_message:
                f.write(f"  Error: {recovery.error_message}\n")
        
        # Export checkpoint data
        f.write(f"\n\nCHECKPOINT EXPORTS\n")
        f.write(f"{'='*60}\n")
        for cp in workflow.checkpoints:
            f.write(f"\n[{cp.checkpoint_id}]\n")
            export = restorer.export_checkpoint(
                workflow_id, cp.checkpoint_id, format="json"
            )
            f.write(export)
```

## Testing Integration

```python
import pytest
from unittest.mock import Mock, patch

def test_workflow_with_checkpoint():
    """Test basic workflow with checkpoint and resumption."""
    state_manager = HITLStateManager()
    
    # Create and execute workflow
    initial_state = {"data": "test"}
    
    checkpoint = state_manager.create_checkpoint(
        workflow_id="test_123",
        node_name="review",
        state_snapshot=initial_state,
        status=WorkflowStatus.PAUSED_FOR_HUMAN
    )
    
    # Verify checkpoint
    assert checkpoint.checkpoint_id
    assert checkpoint.workflow_id == "test_123"
    assert checkpoint.node_name == "review"

def test_crash_recovery():
    """Test server crash detection and recovery."""
    state_manager = HITLStateManager(heartbeat_timeout_seconds=5)
    
    # Set old heartbeat
    workflow = state_manager.restore_workflow("test_123")
    workflow.last_heartbeat = datetime.utcnow() - timedelta(minutes=10)
    state_manager._workflows["test_123"] = workflow
    
    # Detect crash
    recovery = state_manager.recover_from_crash(
        "test_123",
        strategy=RecoveryStrategy.RESUME
    )
    
    assert recovery is not None
    assert recovery.success

def test_state_modification_tracking():
    """Test that state modifications are tracked."""
    state_manager = HITLStateManager()
    restorer = CheckpointRestorer(state_manager)
    
    # Create checkpoint
    checkpoint = state_manager.create_checkpoint(
        workflow_id="test_123",
        node_name="review",
        state_snapshot={"decision": "pending"}
    )
    
    # Modify state
    modified, mods = restorer.restore_and_modify_state(
        "test_123",
        checkpoint.checkpoint_id,
        {"decision": "approved"},
        applied_by="user:test"
    )
    
    assert len(mods) == 1
    assert mods[0].key == "decision"
    assert mods[0].old_value == "pending"
    assert mods[0].new_value == "approved"
```

## Migration from Existing Systems

If migrating from a custom state management system:

1. **Adapt checkpoint format:**
   ```python
   def migrate_checkpoint(old_checkpoint):
       return CheckpointRecord(
           checkpoint_id=old_checkpoint.id,
           workflow_id=old_checkpoint.workflow_id,
           timestamp=old_checkpoint.created_at,
           status=WorkflowStatus(old_checkpoint.status),
           node_name=old_checkpoint.node,
           state_snapshot=old_checkpoint.state,
       )
   ```

2. **Import existing checkpoints:**
   ```python
   for old_cp in existing_checkpoints:
       cp = migrate_checkpoint(old_cp)
       state_manager._checkpoints.setdefault(cp.workflow_id, []).append(cp)
   ```

3. **Verify integrity:**
   ```python
   for workflow_id in all_workflows:
       for cp in state_manager.get_workflow_history(workflow_id):
           assert state_manager.validate_checkpoint(cp.to_dict())
   ```

## Performance Tuning

### For High-Throughput Scenarios
```python
# Use batch operations
batch_checkpoints = []
for state in workflow_states:
    batch_checkpoints.append(
        state_manager.create_checkpoint(...)
    )

# Persist in bulk
if storage_backend:
    storage_backend.save_batch(batch_checkpoints)
```

### For Large State Snapshots
```python
# Compress state before storing
import gzip
import base64

def compress_state(state):
    json_str = json.dumps(state)
    compressed = gzip.compress(json_str.encode())
    return base64.b64encode(compressed).decode()

def decompress_state(compressed):
    decoded = base64.b64decode(compressed.encode())
    decompressed = gzip.decompress(decoded)
    return json.loads(decompressed.decode())
```

## Troubleshooting Common Issues

See the main guide for troubleshooting common integration issues.
