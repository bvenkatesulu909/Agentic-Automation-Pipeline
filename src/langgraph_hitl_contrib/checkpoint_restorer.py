"""
Checkpoint Restorer - Handles restoration and resumption of workflows from checkpoints.

This module provides comprehensive utilities for:
- Loading and validating checkpoint states
- Restoring workflow execution from specific points
- Modifying state before resumption
- Comparing checkpoint states
- Exporting checkpoints for audit/debugging
- Supporting workflow replay and what-if scenarios

The restorer acts as a bridge between persistent storage and workflow execution,
ensuring data integrity and supporting human-in-the-loop decision making.
"""

from typing import Any, Dict, List, Optional, Callable, Tuple
from datetime import datetime
import logging
import json

from .state_manager import (
    CheckpointRecord,
    HITLWorkflowState,
    HITLStateManager,
    WorkflowStatus,
    StateModification,
)

logger = logging.getLogger(__name__)


class CheckpointRestorer:
    """
    Restores and resumes workflows from saved checkpoints.

    Handles the complete process of loading checkpoint state, validating integrity,
    applying modifications, and resuming workflow execution at specific points.
    Also supports replay and what-if scenario testing.
    """

    def __init__(self, state_manager: HITLStateManager):
        """
        Initialize the checkpoint restorer.

        Args:
            state_manager: The HITL state manager instance for accessing workflows
                         and checkpoints.
        """
        self.state_manager = state_manager

    def restore_checkpoint_state(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> Dict[str, Any]:
        """
        Restore the state from a specific checkpoint.

        Loads and validates the checkpoint state, ensuring integrity before
        returning it for resumption or inspection.

        Args:
            workflow_id: The workflow ID.
            checkpoint_id: The checkpoint ID.

        Returns:
            Dict[str, Any]: The state snapshot from the checkpoint.

        Raises:
            ValueError: If checkpoint not found or invalid.

        Example:
            state = restorer.restore_checkpoint_state("workflow_123", "ckpt_xyz")
            print(f"State keys: {list(state.keys())}")
        """
        workflow = self.state_manager.restore_workflow(workflow_id)
        checkpoint = self._find_checkpoint(workflow, checkpoint_id)

        if not checkpoint:
            raise ValueError(
                f"Checkpoint {checkpoint_id} not found for workflow {workflow_id}"
            )

        # Validate checkpoint integrity
        if not self.state_manager.validate_checkpoint(checkpoint.to_dict()):
            raise ValueError(f"Checkpoint {checkpoint_id} failed validation")

        # Verify state hash if available
        if not checkpoint.verify_integrity():
            logger.warning(
                f"Checkpoint {checkpoint_id} integrity check failed. "
                f"Expected hash: {checkpoint.state_hash}, "
                f"Computed hash: {checkpoint.compute_hash()}"
            )
            raise ValueError(
                f"Checkpoint {checkpoint_id} state integrity verification failed"
            )

        logger.info(
            f"Restored checkpoint {checkpoint_id} for workflow {workflow_id}"
        )
        return checkpoint.state_snapshot.copy()

    def restore_checkpoint_with_validation(
        self,
        workflow_id: str,
        checkpoint_id: str,
        validation_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Restore checkpoint state with custom validation.

        Allows callers to provide additional validation logic beyond the
        standard integrity checks.

        Args:
            workflow_id: The workflow ID.
            checkpoint_id: The checkpoint ID.
            validation_callback: Optional callback(state) -> bool for custom validation.

        Returns:
            The validated state snapshot.

        Raises:
            ValueError: If checkpoint not found or validation fails.
        """
        state = self.restore_checkpoint_state(workflow_id, checkpoint_id)

        if validation_callback:
            if not validation_callback(state):
                raise ValueError(
                    f"Custom validation failed for checkpoint {checkpoint_id}"
                )
            logger.info(f"Custom validation passed for checkpoint {checkpoint_id}")

        return state

    def restore_and_modify_state(
        self,
        workflow_id: str,
        checkpoint_id: str,
        modifications: Dict[str, Any],
        applied_by: str = "system",
    ) -> Tuple[Dict[str, Any], List[StateModification]]:
        """
        Restore checkpoint state and apply modifications.

        Restores state and applies transformations while tracking all changes
        for audit purposes.

        Args:
            workflow_id: The workflow ID.
            checkpoint_id: The checkpoint ID.
            modifications: Dict of key/value pairs to modify.
            applied_by: Who is applying the modifications (for audit trail).

        Returns:
            Tuple of (modified_state, list of StateModification records).

        Raises:
            ValueError: If checkpoint not found or invalid.

        Example:
            modified_state, mods = restorer.restore_and_modify_state(
                workflow_id="workflow_123",
                checkpoint_id="ckpt_xyz",
                modifications={'decision': 'approve', 'confidence': 0.95},
                applied_by="user:alice@example.com"
            )
        """
        state = self.restore_checkpoint_state(workflow_id, checkpoint_id)
        state_mods = []

        for key, new_value in modifications.items():
            old_value = state.get(key)
            state[key] = new_value

            # Record modification
            mod = StateModification(
                key=key,
                old_value=old_value,
                new_value=new_value,
                reason=f"Modification during resumption",
                applied_by=applied_by,
            )
            state_mods.append(mod)

            logger.info(
                f"Modified state key '{key}' from {old_value} to {new_value} "
                f"by {applied_by}"
            )

        return state, state_mods

    def deserialize_state_from_json(
        self,
        json_str: str,
        schema: Optional[Dict[str, type]] = None,
    ) -> Dict[str, Any]:
        """
        Deserialize state from JSON string with optional schema validation.

        Safely parses JSON and optionally validates against a schema.

        Args:
            json_str: The JSON string to deserialize.
            schema: Optional dict mapping keys to expected types for validation.

        Returns:
            Deserialized state dictionary.

        Raises:
            ValueError: If JSON is invalid or schema validation fails.

        Example:
            json_state = '{"key": "value", "count": 42}'
            state = restorer.deserialize_state_from_json(
                json_state,
                schema={'key': str, 'count': int}
            )
        """
        try:
            state = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in state deserialization: {str(e)}")

        if not isinstance(state, dict):
            raise ValueError(f"Deserialized state must be a dict, got {type(state)}")

        # Validate schema if provided
        if schema:
            for key, expected_type in schema.items():
                if key not in state:
                    raise ValueError(f"Missing required key in state: {key}")
                if not isinstance(state[key], expected_type):
                    raise ValueError(
                        f"Key '{key}' has wrong type. "
                        f"Expected {expected_type}, got {type(state[key])}"
                    )

        logger.info(f"Successfully deserialized state with {len(state)} keys")
        return state

    def resume_workflow(
        self,
        workflow_id: str,
        checkpoint_id: str,
        graph: Any,
        execution_hook: Optional[Callable] = None,
    ) -> Any:
        """
        Resume workflow execution from a checkpoint.

        This is a convenience wrapper around state_manager.resume_from_checkpoint()
        that follows the restorer's validation and logging patterns.

        Args:
            workflow_id: The workflow ID.
            checkpoint_id: The checkpoint ID to resume from.
            graph: The LangGraph StateGraph instance.
            execution_hook: Optional callback during execution.

        Returns:
            The result from continuing workflow execution.

        Raises:
            ValueError: If workflow or checkpoint not found.
        """
        # Restore state from checkpoint
        state = self.restore_checkpoint_state(workflow_id, checkpoint_id)

        logger.info(
            f"Resuming workflow {workflow_id} from checkpoint {checkpoint_id}"
        )

        # Call execution hook if provided
        if execution_hook:
            execution_hook("resume_start", {"workflow_id": workflow_id})

        # Continue execution
        try:
            result = graph.invoke(state)
            logger.info(f"Successfully resumed workflow {workflow_id}")

            if execution_hook:
                execution_hook("resume_complete", {"result": result})

            return result
        except Exception as e:
            logger.error(f"Error resuming workflow {workflow_id}: {str(e)}")

            if execution_hook:
                execution_hook("resume_error", {"error": str(e)})

            raise

    def get_checkpoint_at_node(
        self,
        workflow_id: str,
        node_name: str,
    ) -> Optional[CheckpointRecord]:
        """
        Get the latest checkpoint at a specific workflow node.

        Args:
            workflow_id: The workflow ID.
            node_name: The node name.

        Returns:
            CheckpointRecord or None if no checkpoint found.
        """
        history = self.state_manager.get_workflow_history(workflow_id)
        matching_checkpoints = [cp for cp in history if cp.node_name == node_name]

        if matching_checkpoints:
            return matching_checkpoints[-1]  # Return latest
        return None

    def get_checkpoints_after_time(
        self,
        workflow_id: str,
        timestamp: datetime,
    ) -> List[CheckpointRecord]:
        """
        Get all checkpoints created after a specific time.

        Args:
            workflow_id: The workflow ID.
            timestamp: The cutoff timestamp.

        Returns:
            List of checkpoints after the specified time.
        """
        history = self.state_manager.get_workflow_history(workflow_id)
        return [cp for cp in history if cp.timestamp > timestamp]

    def get_checkpoints_before_time(
        self,
        workflow_id: str,
        timestamp: datetime,
    ) -> List[CheckpointRecord]:
        """
        Get all checkpoints created before a specific time.

        Args:
            workflow_id: The workflow ID.
            timestamp: The cutoff timestamp.

        Returns:
            List of checkpoints before the specified time.
        """
        history = self.state_manager.get_workflow_history(workflow_id)
        return [cp for cp in history if cp.timestamp <= timestamp]

    def get_approved_checkpoints(
        self,
        workflow_id: str,
    ) -> List[CheckpointRecord]:
        """
        Get all human-approved checkpoints for a workflow.

        Args:
            workflow_id: The workflow ID.

        Returns:
            List of approved checkpoints.
        """
        history = self.state_manager.get_workflow_history(workflow_id)
        return [cp for cp in history if cp.human_approved]

    def get_rejected_checkpoints(
        self,
        workflow_id: str,
    ) -> List[CheckpointRecord]:
        """
        Get all rejected checkpoints for a workflow.

        Args:
            workflow_id: The workflow ID.

        Returns:
            List of rejected checkpoints.
        """
        history = self.state_manager.get_workflow_history(workflow_id)
        return [
            cp for cp in history
            if cp.status == WorkflowStatus.HUMAN_REJECTED
        ]

    def rollback_to_checkpoint(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> HITLWorkflowState:
        """
        Rollback workflow state to a previous checkpoint.

        Args:
            workflow_id: The workflow ID.
            checkpoint_id: The checkpoint to rollback to.

        Returns:
            HITLWorkflowState: Updated workflow state after rollback.
        """
        workflow = self.state_manager.restore_workflow(workflow_id)
        checkpoint = self._find_checkpoint(workflow, checkpoint_id)

        if not checkpoint:
            raise ValueError(
                f"Checkpoint {checkpoint_id} not found for workflow {workflow_id}"
            )

        # Reset workflow to checkpoint state
        workflow.state_data = checkpoint.state_snapshot.copy()
        workflow.current_node = checkpoint.node_name
        workflow.status = WorkflowStatus.PAUSED_FOR_HUMAN
        workflow.updated_at = datetime.utcnow()

        logger.info(
            f"Rolled back workflow {workflow_id} to checkpoint {checkpoint_id}"
        )
        return workflow

    def list_checkpoints(
        self,
        workflow_id: str,
        status_filter: Optional[WorkflowStatus] = None,
        node_filter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[CheckpointRecord]:
        """
        List checkpoints for a workflow with optional filters.

        Args:
            workflow_id: The workflow ID.
            status_filter: Filter by workflow status.
            node_filter: Filter by node name.
            limit: Limit number of results (None for all).

        Returns:
            List of matching checkpoint records.
        """
        history = self.state_manager.get_workflow_history(workflow_id)

        if status_filter:
            history = [cp for cp in history if cp.status == status_filter]

        if node_filter:
            history = [cp for cp in history if cp.node_name == node_filter]

        if limit:
            history = history[-limit:]

        return history

    def compare_checkpoints(
        self,
        checkpoint1: CheckpointRecord,
        checkpoint2: CheckpointRecord,
    ) -> Dict[str, Any]:
        """
        Compare two checkpoints to identify state differences.

        Args:
            checkpoint1: First checkpoint.
            checkpoint2: Second checkpoint.

        Returns:
            Dict with detailed comparison results including:
            - time_difference: Seconds between checkpoints
            - status_changed: Whether workflow status changed
            - node_changed: Whether execution node changed
            - state_keys_added: New keys in state
            - state_keys_removed: Deleted keys in state
            - state_changes: Changed values with before/after
        """
        diff = {
            "checkpoint1_id": checkpoint1.checkpoint_id,
            "checkpoint2_id": checkpoint2.checkpoint_id,
            "checkpoint1_node": checkpoint1.node_name,
            "checkpoint2_node": checkpoint2.node_name,
            "time_difference": (
                checkpoint2.timestamp - checkpoint1.timestamp
            ).total_seconds(),
            "status_changed": checkpoint1.status != checkpoint2.status,
            "status_before": checkpoint1.status.value,
            "status_after": checkpoint2.status.value,
            "node_changed": checkpoint1.node_name != checkpoint2.node_name,
            "state_keys_added": sorted(
                set(checkpoint2.state_snapshot.keys())
                - set(checkpoint1.state_snapshot.keys())
            ),
            "state_keys_removed": sorted(
                set(checkpoint1.state_snapshot.keys())
                - set(checkpoint2.state_snapshot.keys())
            ),
        }

        # Identify changed values
        changed_keys = {}
        common_keys = set(checkpoint1.state_snapshot.keys()) & set(
            checkpoint2.state_snapshot.keys()
        )

        for key in common_keys:
            val1 = checkpoint1.state_snapshot[key]
            val2 = checkpoint2.state_snapshot[key]
            if val1 != val2:
                changed_keys[key] = {
                    "before": val1,
                    "after": val2,
                    "changed": True,
                }

        diff["state_changes"] = changed_keys
        diff["total_changes"] = len(changed_keys)
        return diff

    def get_state_diff_summary(
        self,
        checkpoint1: CheckpointRecord,
        checkpoint2: CheckpointRecord,
    ) -> str:
        """
        Get a human-readable summary of differences between checkpoints.

        Args:
            checkpoint1: First checkpoint.
            checkpoint2: Second checkpoint.

        Returns:
            Formatted string with diff summary.
        """
        diff = self.compare_checkpoints(checkpoint1, checkpoint2)

        lines = [
            f"Checkpoint Comparison",
            f"{'='*60}",
            f"From: {diff['checkpoint1_id']} ({diff['checkpoint1_node']})",
            f"To:   {diff['checkpoint2_id']} ({diff['checkpoint2_node']})",
            f"Time elapsed: {diff['time_difference']:.1f} seconds",
            f"",
        ]

        if diff['status_changed']:
            lines.append(
                f"Status: {diff['status_before']} -> {diff['status_after']}"
            )

        if diff['node_changed']:
            lines.append(f"Node: {diff['checkpoint1_node']} -> {diff['checkpoint2_node']}")

        if diff['state_keys_added']:
            lines.append(f"Added keys: {', '.join(diff['state_keys_added'])}")

        if diff['state_keys_removed']:
            lines.append(f"Removed keys: {', '.join(diff['state_keys_removed'])}")

        if diff['state_changes']:
            lines.append(f"Changed keys: {diff['total_changes']}")
            for key, change in diff['state_changes'].items():
                lines.append(f"  {key}: {change['before']} -> {change['after']}")

        return "\n".join(lines)

    def export_checkpoint(
        self,
        workflow_id: str,
        checkpoint_id: str,
        format: str = "json",
    ) -> str:
        """
        Export a checkpoint to a string format.

        Args:
            workflow_id: The workflow ID.
            checkpoint_id: The checkpoint ID.
            format: Export format ("json", "text", or "jsonl").

        Returns:
            Exported checkpoint as string.

        Raises:
            ValueError: If checkpoint not found or format invalid.
        """
        workflow = self.state_manager.restore_workflow(workflow_id)
        checkpoint = self._find_checkpoint(workflow, checkpoint_id)

        if not checkpoint:
            raise ValueError(
                f"Checkpoint {checkpoint_id} not found for workflow {workflow_id}"
            )

        if format == "json":
            return json.dumps(checkpoint.to_dict(), indent=2, default=str)

        elif format == "jsonl":
            # JSON Lines format (one JSON object per line)
            return json.dumps(checkpoint.to_dict(), default=str)

        elif format == "text":
            # Human-readable text format
            lines = [
                f"Checkpoint ID: {checkpoint.checkpoint_id}",
                f"Workflow ID: {checkpoint.workflow_id}",
                f"Timestamp: {checkpoint.timestamp.isoformat()}",
                f"Status: {checkpoint.status.value}",
                f"Node: {checkpoint.node_name}",
                f"Human Approved: {checkpoint.human_approved}",
                f"State Hash: {checkpoint.state_hash}",
                "",
                "State Snapshot:",
            ]

            for key, value in checkpoint.state_snapshot.items():
                value_str = str(value)
                if len(value_str) > 80:
                    value_str = value_str[:77] + "..."
                lines.append(f"  {key}: {value_str}")

            if checkpoint.human_feedback:
                lines.append("")
                lines.append(f"Human Feedback: {checkpoint.human_feedback}")

            if checkpoint.metadata:
                lines.append("")
                lines.append("Metadata:")
                for key, value in checkpoint.metadata.items():
                    lines.append(f"  {key}: {value}")

            return "\n".join(lines)

        else:
            raise ValueError(f"Unsupported export format: {format}")

    def import_checkpoint_from_json(
        self,
        workflow_id: str,
        json_str: str,
    ) -> CheckpointRecord:
        """
        Import a checkpoint from JSON string.

        Args:
            workflow_id: The workflow ID (for validation).
            json_str: The JSON string containing checkpoint data.

        Returns:
            CheckpointRecord imported from JSON.

        Raises:
            ValueError: If JSON is invalid or doesn't match workflow.
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in checkpoint import: {str(e)}")

        if data.get('workflow_id') != workflow_id:
            raise ValueError(
                f"Checkpoint workflow_id {data.get('workflow_id')} "
                f"does not match expected workflow_id {workflow_id}"
            )

        checkpoint = CheckpointRecord.from_dict(data)

        logger.info(
            f"Successfully imported checkpoint {checkpoint.checkpoint_id} "
            f"for workflow {workflow_id}"
        )
        return checkpoint

    def get_checkpoint_metadata(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> Dict[str, Any]:
        """
        Get metadata for a checkpoint without loading full state.

        Useful for quick inspection without loading large state snapshots.

        Args:
            workflow_id: The workflow ID.
            checkpoint_id: The checkpoint ID.

        Returns:
            Dict with checkpoint metadata.

        Raises:
            ValueError: If checkpoint not found.
        """
        workflow = self.state_manager.restore_workflow(workflow_id)
        checkpoint = self._find_checkpoint(workflow, checkpoint_id)

        if not checkpoint:
            raise ValueError(
                f"Checkpoint {checkpoint_id} not found for workflow {workflow_id}"
            )

        return {
            'checkpoint_id': checkpoint.checkpoint_id,
            'workflow_id': checkpoint.workflow_id,
            'timestamp': checkpoint.timestamp.isoformat(),
            'status': checkpoint.status.value,
            'node_name': checkpoint.node_name,
            'human_approved': checkpoint.human_approved,
            'state_hash': checkpoint.state_hash,
            'metadata': checkpoint.metadata,
            'state_keys': list(checkpoint.state_snapshot.keys()),
            'state_size_bytes': len(json.dumps(checkpoint.state_snapshot).encode()),
        }

    def list_checkpoint_metadata(
        self,
        workflow_id: str,
    ) -> List[Dict[str, Any]]:
        """
        List metadata for all checkpoints without loading full states.

        Args:
            workflow_id: The workflow ID.

        Returns:
            List of checkpoint metadata dicts.
        """
        history = self.state_manager.get_workflow_history(workflow_id)
        return [
            {
                'checkpoint_id': cp.checkpoint_id,
                'timestamp': cp.timestamp.isoformat(),
                'status': cp.status.value,
                'node_name': cp.node_name,
                'human_approved': cp.human_approved,
                'state_hash': cp.state_hash,
            }
            for cp in history
        ]

    def _find_checkpoint(
        self,
        workflow: HITLWorkflowState,
        checkpoint_id: str,
    ) -> Optional[CheckpointRecord]:
        """
        Find a checkpoint within a workflow.

        Args:
            workflow: The workflow state.
            checkpoint_id: The checkpoint ID to find.

        Returns:
            CheckpointRecord or None.
        """
        for checkpoint in workflow.checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        return None
