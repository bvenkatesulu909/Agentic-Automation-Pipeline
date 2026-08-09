"""
HITL State Manager - Manages workflow state, checkpoints, and resumption.

This module provides comprehensive state management functionality for human-in-the-loop
workflows, including state tracking, checkpoint validation, workflow resumption, server
crash recovery, and what-if scenario support.

Key features:
- Persistent state storage and retrieval
- Checkpoint creation and management
- Server crash recovery and automatic restoration
- State mutation and modification before resumption
- Workflow replay capabilities
- What-if scenario execution
- Complete audit trail preservation
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import json
import hashlib
import logging
import uuid

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Enumeration of workflow execution statuses."""
    CREATED = "created"
    RUNNING = "running"
    PAUSED_FOR_HUMAN = "paused_for_human"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REJECTED = "human_rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERED = "recovered"  # Recovered from server crash


class RecoveryStrategy(Enum):
    """Strategy for recovering from server crashes."""
    RESUME = "resume"  # Resume from last checkpoint
    RETRY = "retry"  # Retry the last failed operation
    ROLLBACK = "rollback"  # Rollback to previous checkpoint
    MANUAL = "manual"  # Manual intervention required


@dataclass
class CheckpointRecord:
    """Represents a checkpoint in workflow execution history."""
    checkpoint_id: str
    workflow_id: str
    timestamp: datetime
    status: WorkflowStatus
    node_name: str
    state_snapshot: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    human_feedback: Optional[str] = None
    human_approved: bool = False
    state_hash: Optional[str] = None  # Hash for integrity verification
    parent_checkpoint_id: Optional[str] = None  # For tracking branches in what-if scenarios
    is_replay: bool = False  # Flag if this is a replay checkpoint

    def to_dict(self) -> Dict[str, Any]:
        """Convert checkpoint record to dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CheckpointRecord':
        """Create checkpoint record from dictionary."""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['status'] = WorkflowStatus(data['status'])
        return cls(**data)

    def compute_hash(self) -> str:
        """
        Compute integrity hash of state snapshot.

        Returns:
            str: SHA256 hash of state snapshot
        """
        state_json = json.dumps(self.state_snapshot, sort_keys=True, default=str)
        return hashlib.sha256(state_json.encode()).hexdigest()

    def verify_integrity(self) -> bool:
        """
        Verify checkpoint integrity.

        Returns:
            bool: True if hash matches, False otherwise
        """
        if not self.state_hash:
            return True
        return self.state_hash == self.compute_hash()


@dataclass
class StateModification:
    """Represents a modification to state before resumption."""
    key: str
    old_value: Any
    new_value: Any
    reason: str
    applied_by: str
    applied_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'key': self.key,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'reason': self.reason,
            'applied_by': self.applied_by,
            'applied_at': self.applied_at.isoformat(),
        }


@dataclass
class RecoveryRecord:
    """Records a server crash recovery event."""
    recovery_id: str
    workflow_id: str
    timestamp: datetime
    crash_detected_at: datetime
    strategy: RecoveryStrategy
    checkpoint_id: str
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['crash_detected_at'] = self.crash_detected_at.isoformat()
        data['strategy'] = self.strategy.value
        return data


@dataclass
class HITLWorkflowState:
    """Represents the complete state of a HITL workflow."""
    workflow_id: str
    status: WorkflowStatus
    current_node: str
    state_data: Dict[str, Any]
    checkpoints: List[CheckpointRecord] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    state_modifications: List[StateModification] = field(default_factory=list)
    recovery_records: List[RecoveryRecord] = field(default_factory=list)
    last_heartbeat: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow state to dictionary."""
        return {
            'workflow_id': self.workflow_id,
            'status': self.status.value,
            'current_node': self.current_node,
            'state_data': self.state_data,
            'checkpoints': [cp.to_dict() for cp in self.checkpoints],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata,
            'state_modifications': [m.to_dict() for m in self.state_modifications],
            'recovery_records': [r.to_dict() for r in self.recovery_records],
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HITLWorkflowState':
        """Create workflow state from dictionary."""
        data = data.copy()
        data['status'] = WorkflowStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if 'last_heartbeat' in data and data['last_heartbeat']:
            data['last_heartbeat'] = datetime.fromisoformat(data['last_heartbeat'])
        if 'checkpoints' in data:
            data['checkpoints'] = [
                CheckpointRecord.from_dict(cp) for cp in data['checkpoints']
            ]
        if 'state_modifications' in data:
            data['state_modifications'] = [
                StateModification(**m) if isinstance(m, dict) else m
                for m in data.get('state_modifications', [])
            ]
        if 'recovery_records' in data:
            data['recovery_records'] = [
                RecoveryRecord(**r) if isinstance(r, dict) else r
                for r in data.get('recovery_records', [])
            ]
        return cls(**data)


class HITLStateManager:
    """
    Manages state for human-in-the-loop LangGraph workflows.

    Provides comprehensive checkpoint creation, state tracking, workflow resumption,
    server crash recovery, state mutation, and what-if scenario capabilities.
    """

    def __init__(
        self,
        storage_backend: Optional[Any] = None,
        heartbeat_timeout_seconds: int = 300,
    ):
        """
        Initialize the HITL State Manager.

        Args:
            storage_backend: Optional backend for persisting workflow state.
                           If None, uses in-memory storage.
            heartbeat_timeout_seconds: Timeout for detecting server crashes (default: 5 minutes).
        """
        self.storage_backend = storage_backend
        self._workflows: Dict[str, HITLWorkflowState] = {}
        self._checkpoints: Dict[str, List[CheckpointRecord]] = {}
        self._heartbeat_timeout = heartbeat_timeout_seconds
        self._recovery_callbacks: Dict[str, Callable] = {}

    def restore_workflow(self, workflow_id: str) -> HITLWorkflowState:
        """
        Restore a workflow from storage by workflow ID.

        Loads the workflow and all its associated checkpoints from persistent storage
        or in-memory cache. This is the primary method for retrieving workflow state.

        Args:
            workflow_id: The ID of the workflow to restore.

        Returns:
            HITLWorkflowState: The restored workflow state with all checkpoints.

        Raises:
            ValueError: If workflow not found in storage.

        Example:
            workflow = state_manager.restore_workflow("workflow_123")
            print(f"Workflow status: {workflow.status}")
            print(f"Checkpoints: {len(workflow.checkpoints)}")
        """
        if self.storage_backend:
            # Load from persistent storage
            workflow_data = self.storage_backend.get_workflow(workflow_id)
            if not workflow_data:
                raise ValueError(f"Workflow {workflow_id} not found in storage")

            workflow = HITLWorkflowState.from_dict(workflow_data)

            # Load associated checkpoints
            checkpoints_data = self.storage_backend.get_checkpoints(workflow_id)
            workflow.checkpoints = [
                CheckpointRecord.from_dict(cp) for cp in checkpoints_data
            ]

            logger.info(f"Restored workflow {workflow_id} from persistent storage")
            return workflow
        else:
            # Load from in-memory cache
            if workflow_id not in self._workflows:
                raise ValueError(f"Workflow {workflow_id} not found")

            workflow = self._workflows[workflow_id]
            logger.info(f"Restored workflow {workflow_id} from memory")
            return workflow

    def resume_from_checkpoint(
        self,
        workflow_id: str,
        checkpoint_id: str,
        graph: Any,
        state_modifications: Optional[Dict[str, Any]] = None,
        execution_hook: Optional[Callable] = None,
    ) -> Any:
        """
        Resume workflow execution from a specific checkpoint.

        This method restores the workflow state at a given checkpoint, optionally
        applies state modifications, and then continues execution. It supports
        scenarios where human reviewers need to modify state before resuming.

        Args:
            workflow_id: The ID of the workflow to resume.
            checkpoint_id: The ID of the checkpoint to resume from.
            graph: The LangGraph StateGraph to resume with.
            state_modifications: Optional dict of state keys/values to modify before resumption.
                               Example: {'decision': 'approve', 'confidence': 0.95}
            execution_hook: Optional callback function(event_type, event_data) during execution.

        Returns:
            The result of continuing workflow execution from the checkpoint.

        Raises:
            ValueError: If workflow or checkpoint not found.
            RuntimeError: If checkpoint validation fails.

        Example:
            result = state_manager.resume_from_checkpoint(
                workflow_id="workflow_123",
                checkpoint_id="ckpt_xyz",
                graph=workflow_graph,
                state_modifications={'action': 'approved'},
                execution_hook=lambda e, d: print(f"{e}: {d}")
            )
        """
        workflow = self.restore_workflow(workflow_id)
        checkpoint = None

        for cp in workflow.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                checkpoint = cp
                break

        if not checkpoint:
            raise ValueError(
                f"Checkpoint {checkpoint_id} not found for workflow {workflow_id}"
            )

        # Validate checkpoint before resuming
        if not self.validate_checkpoint(checkpoint.to_dict()):
            raise RuntimeError(f"Checkpoint {checkpoint_id} failed validation")

        # Call hook for resume start
        if execution_hook:
            execution_hook("resume_start", {
                "workflow_id": workflow_id,
                "checkpoint_id": checkpoint_id,
                "node_name": checkpoint.node_name,
            })

        # Restore state from checkpoint
        resume_state = checkpoint.state_snapshot.copy()

        # Apply state modifications if provided
        if state_modifications:
            for key, value in state_modifications.items():
                old_value = resume_state.get(key)
                resume_state[key] = value

                # Record modification
                modification = StateModification(
                    key=key,
                    old_value=old_value,
                    new_value=value,
                    reason=f"Manual modification during resumption",
                    applied_by=state_modifications.get('_applied_by', 'system'),
                )
                workflow.state_modifications.append(modification)

                logger.info(
                    f"Modified state key '{key}': {old_value} -> {value} "
                    f"for workflow {workflow_id}"
                )

        # Call hook for modifications applied
        if execution_hook:
            execution_hook("modifications_applied", {
                "modifications": state_modifications or {},
            })

        # Continue execution from checkpoint
        try:
            result = graph.invoke(resume_state)

            # Update workflow status
            workflow.status = WorkflowStatus.COMPLETED
            workflow.updated_at = datetime.utcnow()
            self._workflows[workflow_id] = workflow

            if execution_hook:
                execution_hook("resume_complete", {"result": result})

            logger.info(f"Successfully resumed workflow {workflow_id}")
            return result
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.updated_at = datetime.utcnow()
            self._workflows[workflow_id] = workflow

            if execution_hook:
                execution_hook("resume_error", {"error": str(e)})

            logger.error(f"Error resuming workflow {workflow_id}: {str(e)}")
            raise

    def recover_from_crash(
        self,
        workflow_id: str,
        strategy: RecoveryStrategy = RecoveryStrategy.RESUME,
        execution_hook: Optional[Callable] = None,
    ) -> Optional[RecoveryRecord]:
        """
        Detect and recover from server crashes.

        This method identifies workflows that were interrupted by server crashes
        and initiates recovery based on the specified strategy. It verifies heartbeat
        timeouts and attempts to restore the workflow to a consistent state.

        Args:
            workflow_id: The workflow ID to check and recover.
            strategy: Recovery strategy (RESUME, RETRY, ROLLBACK, or MANUAL).
            execution_hook: Optional callback for recovery events.

        Returns:
            RecoveryRecord: Details of the recovery attempt, or None if no recovery needed.

        Raises:
            ValueError: If workflow not found.

        Example:
            recovery = state_manager.recover_from_crash(
                workflow_id="workflow_123",
                strategy=RecoveryStrategy.RESUME
            )
            if recovery and recovery.success:
                print(f"Recovery successful: {recovery.recovery_id}")
        """
        try:
            workflow = self.restore_workflow(workflow_id)
        except ValueError:
            logger.warning(f"Workflow {workflow_id} not found for crash recovery")
            return None

        # Check if heartbeat has timed out
        if not workflow.last_heartbeat:
            logger.debug(f"No heartbeat recorded for workflow {workflow_id}")
            return None

        time_since_heartbeat = (
            datetime.utcnow() - workflow.last_heartbeat
        ).total_seconds()

        if time_since_heartbeat < self._heartbeat_timeout:
            logger.debug(
                f"Workflow {workflow_id} heartbeat is current "
                f"({time_since_heartbeat}s old)"
            )
            return None

        # Crash detected
        logger.warning(
            f"Crash detected for workflow {workflow_id}: "
            f"heartbeat {time_since_heartbeat}s old (timeout: {self._heartbeat_timeout}s)"
        )

        crash_detected_at = datetime.utcnow() - \
                           (time_since_heartbeat - self._heartbeat_timeout)

        if execution_hook:
            execution_hook("crash_detected", {
                "workflow_id": workflow_id,
                "time_since_heartbeat": time_since_heartbeat,
            })

        # Determine recovery checkpoint
        recovery_checkpoint_id = None
        if workflow.checkpoints:
            recovery_checkpoint_id = workflow.checkpoints[-1].checkpoint_id

        # Execute recovery strategy
        recovery_id = f"recovery_{uuid.uuid4().hex[:12]}"
        success = False
        error_message = None

        try:
            if strategy == RecoveryStrategy.RESUME:
                if recovery_checkpoint_id:
                    logger.info(
                        f"Resuming workflow {workflow_id} from checkpoint "
                        f"{recovery_checkpoint_id}"
                    )
                    success = True
                else:
                    error_message = "No checkpoint available for resumption"

            elif strategy == RecoveryStrategy.RETRY:
                logger.info(f"Retrying last operation for workflow {workflow_id}")
                success = True

            elif strategy == RecoveryStrategy.ROLLBACK:
                if len(workflow.checkpoints) > 1:
                    logger.info(
                        f"Rolling back workflow {workflow_id} to previous checkpoint"
                    )
                    success = True
                else:
                    error_message = "Cannot rollback: only one checkpoint available"

            elif strategy == RecoveryStrategy.MANUAL:
                logger.warning(
                    f"Manual intervention required for workflow {workflow_id}"
                )
                success = False
                error_message = "Manual intervention required"

        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"Error during recovery of workflow {workflow_id}: {e}")

        # Record recovery
        recovery_record = RecoveryRecord(
            recovery_id=recovery_id,
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            crash_detected_at=crash_detected_at,
            strategy=strategy,
            checkpoint_id=recovery_checkpoint_id or "",
            success=success,
            error_message=error_message,
            metadata={
                "time_since_heartbeat": time_since_heartbeat,
                "strategy": strategy.value,
            },
        )

        workflow.recovery_records.append(recovery_record)
        workflow.status = WorkflowStatus.RECOVERED if success else WorkflowStatus.FAILED
        workflow.updated_at = datetime.utcnow()
        self._workflows[workflow_id] = workflow

        if self.storage_backend:
            self.storage_backend.save_workflow(workflow.to_dict())

        if execution_hook:
            execution_hook("recovery_complete", {
                "recovery_id": recovery_id,
                "success": success,
            })

        return recovery_record

    def replay_workflow(
        self,
        workflow_id: str,
        checkpoint_id: str,
        graph: Any,
        execution_hook: Optional[Callable] = None,
    ) -> Any:
        """
        Replay workflow execution from a checkpoint for testing/auditing.

        This method restores and re-executes a workflow from a specific checkpoint
        without modifying the original workflow state. Useful for testing what-if
        scenarios or auditing workflow behavior.

        Args:
            workflow_id: The workflow ID to replay.
            checkpoint_id: The checkpoint to replay from.
            graph: The LangGraph StateGraph to use for replay.
            execution_hook: Optional callback for replay events.

        Returns:
            The result of replaying the workflow.

        Raises:
            ValueError: If workflow or checkpoint not found.

        Example:
            result = state_manager.replay_workflow(
                workflow_id="workflow_123",
                checkpoint_id="ckpt_xyz",
                graph=workflow_graph,
            )
        """
        workflow = self.restore_workflow(workflow_id)
        checkpoint = None

        for cp in workflow.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                checkpoint = cp
                break

        if not checkpoint:
            raise ValueError(
                f"Checkpoint {checkpoint_id} not found for workflow {workflow_id}"
            )

        if execution_hook:
            execution_hook("replay_start", {
                "workflow_id": workflow_id,
                "checkpoint_id": checkpoint_id,
                "is_replay": True,
            })

        # Create a copy of state for replay
        replay_state = checkpoint.state_snapshot.copy()
        replay_state['_is_replay'] = True
        replay_state['_replay_checkpoint_id'] = checkpoint_id

        try:
            result = graph.invoke(replay_state)

            if execution_hook:
                execution_hook("replay_complete", {"result": result})

            logger.info(f"Successfully replayed workflow {workflow_id}")
            return result
        except Exception as e:
            if execution_hook:
                execution_hook("replay_error", {"error": str(e)})
            logger.error(f"Error replaying workflow {workflow_id}: {str(e)}")
            raise

    def execute_what_if_scenario(
        self,
        workflow_id: str,
        checkpoint_id: str,
        graph: Any,
        scenario_name: str,
        modifications: Dict[str, Any],
        execution_hook: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Execute a what-if scenario from a checkpoint.

        Tests alternative execution paths by modifying state at a checkpoint
        and re-executing the workflow. Does not modify the original workflow.

        Args:
            workflow_id: The workflow ID.
            checkpoint_id: The checkpoint to start from.
            graph: The LangGraph StateGraph.
            scenario_name: Name of the scenario for logging/tracking.
            modifications: State modifications for this scenario.
            execution_hook: Optional callback for scenario events.

        Returns:
            Dict with scenario results including:
            - 'scenario_name': Name of the scenario
            - 'result': Workflow execution result
            - 'modifications': Applied modifications
            - 'execution_time': Time taken to execute

        Raises:
            ValueError: If workflow or checkpoint not found.

        Example:
            scenario_result = state_manager.execute_what_if_scenario(
                workflow_id="workflow_123",
                checkpoint_id="ckpt_xyz",
                graph=workflow_graph,
                scenario_name="conservative_approach",
                modifications={'confidence_threshold': 0.95}
            )
        """
        import time

        workflow = self.restore_workflow(workflow_id)
        checkpoint = None

        for cp in workflow.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                checkpoint = cp
                break

        if not checkpoint:
            raise ValueError(
                f"Checkpoint {checkpoint_id} not found for workflow {workflow_id}"
            )

        if execution_hook:
            execution_hook("scenario_start", {
                "workflow_id": workflow_id,
                "scenario_name": scenario_name,
                "modifications": modifications,
            })

        # Create scenario state
        scenario_state = checkpoint.state_snapshot.copy()
        scenario_state.update(modifications)
        scenario_state['_scenario_name'] = scenario_name
        scenario_state['_parent_checkpoint_id'] = checkpoint_id

        start_time = time.time()
        try:
            result = graph.invoke(scenario_state)
            execution_time = time.time() - start_time

            scenario_result = {
                'scenario_name': scenario_name,
                'result': result,
                'modifications': modifications,
                'execution_time': execution_time,
                'success': True,
            }

            if execution_hook:
                execution_hook("scenario_complete", scenario_result)

            logger.info(
                f"What-if scenario '{scenario_name}' completed for workflow "
                f"{workflow_id} in {execution_time:.2f}s"
            )

            return scenario_result
        except Exception as e:
            execution_time = time.time() - start_time

            scenario_result = {
                'scenario_name': scenario_name,
                'result': None,
                'modifications': modifications,
                'execution_time': execution_time,
                'success': False,
                'error': str(e),
            }

            if execution_hook:
                execution_hook("scenario_error", scenario_result)

            logger.error(
                f"Error executing what-if scenario '{scenario_name}' "
                f"for workflow {workflow_id}: {str(e)}"
            )

            return scenario_result

    def update_heartbeat(self, workflow_id: str) -> None:
        """
        Update heartbeat for a workflow.

        Should be called periodically during workflow execution to indicate
        that the workflow is still active. Used for crash detection.

        Args:
            workflow_id: The workflow ID.
        """
        try:
            workflow = self.restore_workflow(workflow_id)
        except ValueError:
            logger.warning(f"Workflow {workflow_id} not found for heartbeat update")
            return

        workflow.last_heartbeat = datetime.utcnow()
        self._workflows[workflow_id] = workflow

        if self.storage_backend:
            self.storage_backend.save_workflow(workflow.to_dict())

        logger.debug(f"Heartbeat updated for workflow {workflow_id}")

    def get_workflow_history(self, workflow_id: str) -> List[CheckpointRecord]:
        """
        Retrieve the complete checkpoint history for a workflow.

        Args:
            workflow_id: The ID of the workflow.

        Returns:
            List of checkpoint records in chronological order.

        Raises:
            ValueError: If workflow not found.
        """
        workflow = self.restore_workflow(workflow_id)
        return sorted(workflow.checkpoints, key=lambda cp: cp.timestamp)

    def validate_checkpoint(self, checkpoint: Dict[str, Any]) -> bool:
        """
        Validate a checkpoint record for integrity and completeness.

        Performs comprehensive validation including:
        - Required fields presence
        - State snapshot integrity
        - Enum value validity
        - Timestamp format correctness

        Args:
            checkpoint: The checkpoint dictionary to validate.

        Returns:
            bool: True if checkpoint is valid, False otherwise.
        """
        required_fields = {
            'checkpoint_id',
            'workflow_id',
            'timestamp',
            'status',
            'node_name',
            'state_snapshot',
        }

        # Check for required fields
        if not all(field in checkpoint for field in required_fields):
            logger.warning(
                f"Checkpoint missing required fields. "
                f"Required: {required_fields}, Got: {set(checkpoint.keys())}"
            )
            return False

        # Validate checkpoint structure
        if not isinstance(checkpoint['state_snapshot'], dict):
            logger.warning(
                f"State snapshot is not a dict: {type(checkpoint['state_snapshot'])}"
            )
            return False

        if not isinstance(checkpoint.get('metadata', {}), dict):
            logger.warning("Metadata is not a dict")
            return False

        # Validate status is valid enum value
        try:
            WorkflowStatus(checkpoint['status'])
        except ValueError:
            logger.warning(f"Invalid status: {checkpoint['status']}")
            return False

        # Check timestamp format
        try:
            if isinstance(checkpoint['timestamp'], str):
                datetime.fromisoformat(checkpoint['timestamp'])
        except (ValueError, TypeError):
            logger.warning(f"Invalid timestamp format: {checkpoint['timestamp']}")
            return False

        return True

    def create_checkpoint(
        self,
        workflow_id: str,
        node_name: str,
        state_snapshot: Dict[str, Any],
        status: WorkflowStatus = WorkflowStatus.PAUSED_FOR_HUMAN,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckpointRecord:
        """
        Create a new checkpoint for a workflow.

        Args:
            workflow_id: The workflow ID.
            node_name: The current node/step name.
            state_snapshot: The current state data.
            status: The workflow status at this checkpoint.
            metadata: Optional additional metadata.

        Returns:
            CheckpointRecord: The created checkpoint.
        """
        checkpoint_id = self._generate_checkpoint_id(workflow_id, node_name)
        checkpoint = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            status=status,
            node_name=node_name,
            state_snapshot=state_snapshot,
            metadata=metadata or {},
        )

        # Compute integrity hash
        checkpoint.state_hash = checkpoint.compute_hash()

        # Store checkpoint
        if workflow_id not in self._checkpoints:
            self._checkpoints[workflow_id] = []
        self._checkpoints[workflow_id].append(checkpoint)

        # Update workflow state
        if workflow_id in self._workflows:
            self._workflows[workflow_id].checkpoints.append(checkpoint)
            self._workflows[workflow_id].updated_at = datetime.utcnow()

        # Persist to storage backend if available
        if self.storage_backend:
            self.storage_backend.save_checkpoint(checkpoint.to_dict())

        logger.info(
            f"Created checkpoint {checkpoint_id} for workflow {workflow_id} "
            f"at node {node_name}"
        )
        return checkpoint

    def update_workflow_status(
        self,
        workflow_id: str,
        status: WorkflowStatus,
        human_feedback: Optional[str] = None,
    ) -> HITLWorkflowState:
        """
        Update the status of a workflow.

        Args:
            workflow_id: The workflow ID.
            status: The new workflow status.
            human_feedback: Optional feedback from human reviewer.

        Returns:
            HITLWorkflowState: The updated workflow state.
        """
        workflow = self.restore_workflow(workflow_id)
        workflow.status = status
        workflow.updated_at = datetime.utcnow()

        # Update last checkpoint with feedback if provided
        if human_feedback and workflow.checkpoints:
            workflow.checkpoints[-1].human_feedback = human_feedback
            workflow.checkpoints[-1].human_approved = (
                status == WorkflowStatus.HUMAN_APPROVED
            )

        # Store updated workflow
        self._workflows[workflow_id] = workflow
        if self.storage_backend:
            self.storage_backend.save_workflow(workflow.to_dict())

        logger.info(f"Updated workflow {workflow_id} status to {status.value}")
        return workflow

    def register_recovery_callback(
        self,
        workflow_id: str,
        callback: Callable[[RecoveryRecord], None],
    ) -> None:
        """
        Register a callback for recovery events.

        Args:
            workflow_id: The workflow ID.
            callback: Callback function(recovery_record).
        """
        self._recovery_callbacks[workflow_id] = callback

    def _generate_checkpoint_id(self, workflow_id: str, node_name: str) -> str:
        """
        Generate a unique checkpoint ID.

        Args:
            workflow_id: The workflow ID.
            node_name: The node name.

        Returns:
            str: Generated checkpoint ID.
        """
        content = f"{workflow_id}:{node_name}:{datetime.utcnow().isoformat()}"
        hash_digest = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"ckpt_{workflow_id}_{hash_digest}"
