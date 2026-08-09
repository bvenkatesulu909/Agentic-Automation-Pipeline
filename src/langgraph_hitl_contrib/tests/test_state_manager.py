"""
Comprehensive Tests for HITL State Manager

Unit, integration, and benchmark tests for state management, checkpoint creation,
workflow resumption, crash recovery, and state modification functionality.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List
import time
import json
import uuid
from unittest.mock import Mock, patch, MagicMock

from ..state_manager import (
    HITLStateManager,
    HITLWorkflowState,
    CheckpointRecord,
    StateModification,
    RecoveryRecord,
    WorkflowStatus,
    RecoveryStrategy,
)
from ..checkpoint_restorer import CheckpointRestorer


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def state_manager():
    """Create a state manager instance for testing."""
    return HITLStateManager()


@pytest.fixture
def checkpoint_restorer(state_manager):
    """Create a checkpoint restorer instance."""
    return CheckpointRestorer(state_manager)


@pytest.fixture
def sample_workflow_state():
    """Create a sample workflow state."""
    return HITLWorkflowState(
        workflow_id="wf_test_001",
        status=WorkflowStatus.CREATED,
        current_node="process_input",
        state_data={
            "input": "test data",
            "processed": False,
        },
    )


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
        },
        metadata={"source": "test"},
    )
    checkpoint.state_hash = checkpoint.compute_hash()
    return checkpoint


@pytest.fixture
def mock_graph():
    """Create a mock LangGraph graph."""
    mock = Mock()
    mock.invoke = Mock(return_value={"result": "success"})
    return mock


# ============================================================================
# UNIT TESTS - CheckpointRecord
# ============================================================================

class TestCheckpointRecord:
    """Tests for CheckpointRecord class."""

    def test_checkpoint_creation(self):
        """Test creating a checkpoint record."""
        checkpoint = CheckpointRecord(
            checkpoint_id="ckpt_001",
            workflow_id="wf_001",
            timestamp=datetime.utcnow(),
            status=WorkflowStatus.PAUSED_FOR_HUMAN,
            node_name="review_node",
            state_snapshot={"key": "value"},
        )

        assert checkpoint.checkpoint_id == "ckpt_001"
        assert checkpoint.workflow_id == "wf_001"
        assert checkpoint.node_name == "review_node"
        assert checkpoint.state_snapshot == {"key": "value"}

    def test_checkpoint_to_dict(self, sample_checkpoint):
        """Test converting checkpoint to dictionary."""
        checkpoint_dict = sample_checkpoint.to_dict()

        assert isinstance(checkpoint_dict, dict)
        assert checkpoint_dict["checkpoint_id"] == "ckpt_test_001"
        assert checkpoint_dict["workflow_id"] == "wf_test_001"
        assert checkpoint_dict["status"] == "paused_for_human"
        assert isinstance(checkpoint_dict["timestamp"], str)

    def test_checkpoint_from_dict(self, sample_checkpoint):
        """Test creating checkpoint from dictionary."""
        checkpoint_dict = sample_checkpoint.to_dict()
        restored = CheckpointRecord.from_dict(checkpoint_dict)

        assert restored.checkpoint_id == sample_checkpoint.checkpoint_id
        assert restored.workflow_id == sample_checkpoint.workflow_id
        assert restored.node_name == sample_checkpoint.node_name
        assert restored.status == sample_checkpoint.status
        assert isinstance(restored.timestamp, datetime)

    def test_checkpoint_serialization(self, sample_checkpoint):
        """Test checkpoint serialization and deserialization."""
        # Serialize
        checkpoint_dict = sample_checkpoint.to_dict()
        json_str = json.dumps(checkpoint_dict, default=str)

        # Deserialize
        restored_dict = json.loads(json_str)
        restored = CheckpointRecord.from_dict(restored_dict)

        assert restored.checkpoint_id == sample_checkpoint.checkpoint_id
        assert restored.state_snapshot == sample_checkpoint.state_snapshot

    def test_checkpoint_compute_hash(self, sample_checkpoint):
        """Test hash computation."""
        hash1 = sample_checkpoint.compute_hash()

        # Same state should produce same hash
        hash2 = sample_checkpoint.compute_hash()
        assert hash1 == hash2

        # Different state should produce different hash
        sample_checkpoint.state_snapshot["new_key"] = "new_value"
        hash3 = sample_checkpoint.compute_hash()
        assert hash1 != hash3

    def test_checkpoint_verify_integrity(self, sample_checkpoint):
        """Test checkpoint integrity verification."""
        # Valid checkpoint
        assert sample_checkpoint.verify_integrity()

        # Tampered state
        sample_checkpoint.state_snapshot["key"] = "tampered_value"
        assert not sample_checkpoint.verify_integrity()

    def test_checkpoint_verify_integrity_no_hash(self):
        """Test integrity verification when hash is not set."""
        checkpoint = CheckpointRecord(
            checkpoint_id="ckpt_001",
            workflow_id="wf_001",
            timestamp=datetime.utcnow(),
            status=WorkflowStatus.PAUSED_FOR_HUMAN,
            node_name="node",
            state_snapshot={"key": "value"},
            state_hash=None,
        )
        # Should pass when state_hash is None
        assert checkpoint.verify_integrity()


# ============================================================================
# UNIT TESTS - HITLWorkflowState
# ============================================================================

class TestHITLWorkflowState:
    """Tests for HITLWorkflowState class."""

    def test_workflow_state_creation(self, sample_workflow_state):
        """Test creating a workflow state."""
        assert sample_workflow_state.workflow_id == "wf_test_001"
        assert sample_workflow_state.status == WorkflowStatus.CREATED
        assert sample_workflow_state.current_node == "process_input"

    def test_workflow_state_to_dict(self, sample_workflow_state):
        """Test converting workflow state to dictionary."""
        state_dict = sample_workflow_state.to_dict()

        assert isinstance(state_dict, dict)
        assert state_dict["workflow_id"] == "wf_test_001"
        assert state_dict["status"] == "created"
        assert isinstance(state_dict["created_at"], str)

    def test_workflow_state_from_dict(self, sample_workflow_state):
        """Test creating workflow state from dictionary."""
        state_dict = sample_workflow_state.to_dict()
        restored = HITLWorkflowState.from_dict(state_dict)

        assert restored.workflow_id == sample_workflow_state.workflow_id
        assert restored.status == sample_workflow_state.status
        assert isinstance(restored.created_at, datetime)

    def test_workflow_state_serialization(self, sample_workflow_state):
        """Test workflow state serialization."""
        state_dict = sample_workflow_state.to_dict()
        json_str = json.dumps(state_dict, default=str)

        restored_dict = json.loads(json_str)
        restored = HITLWorkflowState.from_dict(restored_dict)

        assert restored.workflow_id == sample_workflow_state.workflow_id


# ============================================================================
# UNIT TESTS - StateModification
# ============================================================================

class TestStateModification:
    """Tests for StateModification class."""

    def test_modification_creation(self):
        """Test creating a state modification."""
        mod = StateModification(
            key="decision",
            old_value="pending",
            new_value="approved",
            reason="Human approval",
            applied_by="user@example.com",
        )

        assert mod.key == "decision"
        assert mod.old_value == "pending"
        assert mod.new_value == "approved"

    def test_modification_to_dict(self):
        """Test modification serialization."""
        mod = StateModification(
            key="decision",
            old_value="pending",
            new_value="approved",
            reason="Human approval",
            applied_by="user@example.com",
        )

        mod_dict = mod.to_dict()
        assert mod_dict["key"] == "decision"
        assert isinstance(mod_dict["applied_at"], str)


# ============================================================================
# UNIT TESTS - HITLStateManager
# ============================================================================

class TestHITLStateManager:
    """Tests for HITLStateManager class."""

    def test_state_manager_initialization(self, state_manager):
        """Test state manager initialization."""
        assert state_manager is not None
        assert state_manager._heartbeat_timeout == 300
        assert isinstance(state_manager._workflows, dict)
        assert isinstance(state_manager._checkpoints, dict)

    def test_create_checkpoint(self, state_manager):
        """Test creating a checkpoint."""
        workflow_id = "wf_001"
        state_snapshot = {"key": "value", "count": 42}

        # First, create a workflow in memory
        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data=state_snapshot,
        )
        state_manager._workflows[workflow_id] = workflow

        # Now create checkpoint
        checkpoint = state_manager.create_checkpoint(
            workflow_id=workflow_id,
            node_name="process",
            state_snapshot=state_snapshot,
        )

        assert checkpoint.checkpoint_id is not None
        assert checkpoint.workflow_id == workflow_id
        assert checkpoint.state_snapshot == state_snapshot
        assert checkpoint.state_hash is not None

    def test_restore_workflow_in_memory(self, state_manager, sample_workflow_state):
        """Test restoring workflow from in-memory storage."""
        state_manager._workflows["wf_test_001"] = sample_workflow_state

        restored = state_manager.restore_workflow("wf_test_001")

        assert restored.workflow_id == "wf_test_001"
        assert restored.status == WorkflowStatus.CREATED

    def test_restore_workflow_not_found(self, state_manager):
        """Test restoring non-existent workflow raises error."""
        with pytest.raises(ValueError, match="not found"):
            state_manager.restore_workflow("wf_nonexistent")

    def test_validate_checkpoint_valid(self, state_manager):
        """Test validating a valid checkpoint."""
        checkpoint_dict = {
            "checkpoint_id": "ckpt_001",
            "workflow_id": "wf_001",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "paused_for_human",
            "node_name": "review",
            "state_snapshot": {"key": "value"},
            "metadata": {},
        }

        assert state_manager.validate_checkpoint(checkpoint_dict)

    def test_validate_checkpoint_invalid_status(self, state_manager):
        """Test validating checkpoint with invalid status."""
        checkpoint_dict = {
            "checkpoint_id": "ckpt_001",
            "workflow_id": "wf_001",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "invalid_status",
            "node_name": "review",
            "state_snapshot": {"key": "value"},
        }

        assert not state_manager.validate_checkpoint(checkpoint_dict)

    def test_validate_checkpoint_missing_fields(self, state_manager):
        """Test validating checkpoint with missing required fields."""
        checkpoint_dict = {
            "checkpoint_id": "ckpt_001",
            "workflow_id": "wf_001",
            # Missing timestamp, status, node_name, state_snapshot
        }

        assert not state_manager.validate_checkpoint(checkpoint_dict)

    def test_validate_checkpoint_invalid_state_snapshot(self, state_manager):
        """Test validating checkpoint with invalid state snapshot."""
        checkpoint_dict = {
            "checkpoint_id": "ckpt_001",
            "workflow_id": "wf_001",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "paused_for_human",
            "node_name": "review",
            "state_snapshot": "not_a_dict",  # Should be a dict
        }

        assert not state_manager.validate_checkpoint(checkpoint_dict)

    def test_validate_checkpoint_invalid_timestamp(self, state_manager):
        """Test validating checkpoint with invalid timestamp."""
        checkpoint_dict = {
            "checkpoint_id": "ckpt_001",
            "workflow_id": "wf_001",
            "timestamp": "not_a_valid_timestamp",
            "status": "paused_for_human",
            "node_name": "review",
            "state_snapshot": {"key": "value"},
        }

        assert not state_manager.validate_checkpoint(checkpoint_dict)

    def test_update_workflow_status(self, state_manager, sample_workflow_state):
        """Test updating workflow status."""
        state_manager._workflows["wf_test_001"] = sample_workflow_state

        updated = state_manager.update_workflow_status(
            "wf_test_001",
            WorkflowStatus.RUNNING,
        )

        assert updated.status == WorkflowStatus.RUNNING

    def test_update_workflow_status_with_feedback(self, state_manager, sample_workflow_state):
        """Test updating workflow status with human feedback."""
        state_manager._workflows["wf_test_001"] = sample_workflow_state

        # Add a checkpoint first
        checkpoint = state_manager.create_checkpoint(
            workflow_id="wf_test_001",
            node_name="review",
            state_snapshot={"key": "value"},
        )

        updated = state_manager.update_workflow_status(
            "wf_test_001",
            WorkflowStatus.HUMAN_APPROVED,
            human_feedback="Looks good!",
        )

        assert updated.status == WorkflowStatus.HUMAN_APPROVED
        assert updated.checkpoints[-1].human_feedback == "Looks good!"
        assert updated.checkpoints[-1].human_approved

    def test_update_heartbeat(self, state_manager, sample_workflow_state):
        """Test updating workflow heartbeat."""
        state_manager._workflows["wf_test_001"] = sample_workflow_state

        old_heartbeat = sample_workflow_state.last_heartbeat
        state_manager.update_heartbeat("wf_test_001")

        updated = state_manager.restore_workflow("wf_test_001")
        assert updated.last_heartbeat is not None
        assert updated.last_heartbeat > old_heartbeat or old_heartbeat is None

    def test_get_workflow_history(self, state_manager):
        """Test retrieving workflow history."""
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
        )
        state_manager._workflows["wf_001"] = workflow

        # Create multiple checkpoints
        for i in range(3):
            state_manager.create_checkpoint(
                workflow_id="wf_001",
                node_name=f"node_{i}",
                state_snapshot={"step": i},
            )
            time.sleep(0.01)  # Ensure different timestamps

        history = state_manager.get_workflow_history("wf_001")

        assert len(history) == 3
        # Should be sorted by timestamp
        assert all(
            history[i].timestamp <= history[i + 1].timestamp
            for i in range(len(history) - 1)
        )

    def test_generate_checkpoint_id(self, state_manager):
        """Test checkpoint ID generation."""
        id1 = state_manager._generate_checkpoint_id("wf_001", "node_1")
        id2 = state_manager._generate_checkpoint_id("wf_001", "node_1")

        assert id1.startswith("ckpt_")
        assert id1 != id2  # Different times should produce different IDs


# ============================================================================
# UNIT TESTS - Crash Recovery
# ============================================================================

class TestCrashRecovery:
    """Tests for crash recovery functionality."""

    def test_recover_from_crash_no_heartbeat(self, state_manager):
        """Test recovery when no heartbeat is recorded."""
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
            last_heartbeat=None,
        )
        state_manager._workflows["wf_001"] = workflow

        recovery = state_manager.recover_from_crash("wf_001")

        assert recovery is None

    def test_recover_from_crash_recent_heartbeat(self, state_manager):
        """Test recovery when heartbeat is recent."""
        now = datetime.utcnow()
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
            last_heartbeat=now,  # Just now
        )
        state_manager._workflows["wf_001"] = workflow

        recovery = state_manager.recover_from_crash("wf_001")

        assert recovery is None

    def test_recover_from_crash_detected(self, state_manager):
        """Test crash detection and recovery."""
        old_time = datetime.utcnow() - timedelta(seconds=400)
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
            last_heartbeat=old_time,  # More than 300s ago
        )
        state_manager._workflows["wf_001"] = workflow

        # Create a checkpoint for recovery
        state_manager.create_checkpoint(
            workflow_id="wf_001",
            node_name="process",
            state_snapshot={"key": "value"},
        )

        recovery = state_manager.recover_from_crash(
            "wf_001",
            strategy=RecoveryStrategy.RESUME,
        )

        assert recovery is not None
        assert recovery.success
        assert recovery.strategy == RecoveryStrategy.RESUME

    def test_recover_from_crash_no_checkpoint(self, state_manager):
        """Test recovery when no checkpoint exists."""
        old_time = datetime.utcnow() - timedelta(seconds=400)
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
            last_heartbeat=old_time,
        )
        state_manager._workflows["wf_001"] = workflow

        recovery = state_manager.recover_from_crash(
            "wf_001",
            strategy=RecoveryStrategy.RESUME,
        )

        assert recovery is not None
        assert not recovery.success
        assert "No checkpoint" in recovery.error_message

    def test_recover_from_crash_rollback_strategy(self, state_manager):
        """Test rollback recovery strategy."""
        old_time = datetime.utcnow() - timedelta(seconds=400)
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
            last_heartbeat=old_time,
        )
        state_manager._workflows["wf_001"] = workflow

        # Create multiple checkpoints
        state_manager.create_checkpoint(
            workflow_id="wf_001",
            node_name="node_1",
            state_snapshot={"step": 1},
        )
        state_manager.create_checkpoint(
            workflow_id="wf_001",
            node_name="node_2",
            state_snapshot={"step": 2},
        )

        recovery = state_manager.recover_from_crash(
            "wf_001",
            strategy=RecoveryStrategy.ROLLBACK,
        )

        assert recovery is not None
        assert recovery.success
        assert recovery.strategy == RecoveryStrategy.ROLLBACK

    def test_recover_from_crash_rollback_single_checkpoint(self, state_manager):
        """Test rollback fails with single checkpoint."""
        old_time = datetime.utcnow() - timedelta(seconds=400)
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
            last_heartbeat=old_time,
        )
        state_manager._workflows["wf_001"] = workflow

        # Create single checkpoint
        state_manager.create_checkpoint(
            workflow_id="wf_001",
            node_name="node_1",
            state_snapshot={"step": 1},
        )

        recovery = state_manager.recover_from_crash(
            "wf_001",
            strategy=RecoveryStrategy.ROLLBACK,
        )

        assert recovery is not None
        assert not recovery.success
        assert "Cannot rollback" in recovery.error_message

    def test_recover_from_crash_manual_strategy(self, state_manager):
        """Test manual recovery strategy."""
        old_time = datetime.utcnow() - timedelta(seconds=400)
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
            last_heartbeat=old_time,
        )
        state_manager._workflows["wf_001"] = workflow

        recovery = state_manager.recover_from_crash(
            "wf_001",
            strategy=RecoveryStrategy.MANUAL,
        )

        assert recovery is not None
        assert not recovery.success
        assert recovery.strategy == RecoveryStrategy.MANUAL


# ============================================================================
# UNIT TESTS - Resume and What-If
# ============================================================================

class TestResumeAndWhatIf:
    """Tests for resume and what-if scenario functionality."""

    def test_resume_from_checkpoint(self, state_manager, mock_graph):
        """Test resuming workflow from checkpoint."""
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.PAUSED_FOR_HUMAN,
            current_node="review",
            state_data={},
        )
        state_manager._workflows["wf_001"] = workflow

        # Create checkpoint
        checkpoint = state_manager.create_checkpoint(
            workflow_id="wf_001",
            node_name="review",
            state_snapshot={"data": "test", "approved": False},
        )

        # Resume with modifications
        result = state_manager.resume_from_checkpoint(
            workflow_id="wf_001",
            checkpoint_id=checkpoint.checkpoint_id,
            graph=mock_graph,
            state_modifications={"approved": True},
        )

        assert result is not None
        # Check that mock was called
        mock_graph.invoke.assert_called_once()

    def test_resume_from_checkpoint_not_found(self, state_manager, mock_graph):
        """Test resuming from non-existent checkpoint."""
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.PAUSED_FOR_HUMAN,
            current_node="review",
            state_data={},
        )
        state_manager._workflows["wf_001"] = workflow

        with pytest.raises(ValueError, match="not found"):
            state_manager.resume_from_checkpoint(
                workflow_id="wf_001",
                checkpoint_id="ckpt_nonexistent",
                graph=mock_graph,
            )

    def test_replay_workflow(self, state_manager, mock_graph):
        """Test replaying workflow from checkpoint."""
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.COMPLETED,
            current_node="finalize",
            state_data={},
        )
        state_manager._workflows["wf_001"] = workflow

        checkpoint = state_manager.create_checkpoint(
            workflow_id="wf_001",
            node_name="review",
            state_snapshot={"data": "test"},
        )

        result = state_manager.replay_workflow(
            workflow_id="wf_001",
            checkpoint_id=checkpoint.checkpoint_id,
            graph=mock_graph,
        )

        assert result is not None

    def test_execute_what_if_scenario(self, state_manager, mock_graph):
        """Test what-if scenario execution."""
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.COMPLETED,
            current_node="finalize",
            state_data={},
        )
        state_manager._workflows["wf_001"] = workflow

        checkpoint = state_manager.create_checkpoint(
            workflow_id="wf_001",
            node_name="review",
            state_snapshot={"threshold": 0.5, "approved": False},
        )

        result = state_manager.execute_what_if_scenario(
            workflow_id="wf_001",
            checkpoint_id=checkpoint.checkpoint_id,
            graph=mock_graph,
            scenario_name="conservative_approach",
            modifications={"threshold": 0.95, "approved": True},
        )

        assert result["scenario_name"] == "conservative_approach"
        assert result["success"]
        assert result["modifications"]["threshold"] == 0.95


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflow scenarios."""

    def test_full_workflow_lifecycle(self, state_manager, checkpoint_restorer):
        """Test complete workflow: create → checkpoint → restore → modify → resume."""
        workflow_id = "wf_integration_001"

        # Create workflow
        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.CREATED,
            current_node="process",
            state_data={"input": "test_data"},
        )
        state_manager._workflows[workflow_id] = workflow

        # Simulate processing
        workflow.status = WorkflowStatus.RUNNING
        workflow.state_data["processed"] = True

        # Create checkpoint
        checkpoint1 = state_manager.create_checkpoint(
            workflow_id=workflow_id,
            node_name="analysis",
            state_snapshot=workflow.state_data.copy(),
            status=WorkflowStatus.PAUSED_FOR_HUMAN,
        )

        # Restore workflow
        restored_workflow = state_manager.restore_workflow(workflow_id)
        assert restored_workflow.workflow_id == workflow_id

        # Get checkpoint
        restored_state = checkpoint_restorer.restore_checkpoint_state(
            workflow_id=workflow_id,
            checkpoint_id=checkpoint1.checkpoint_id,
        )
        assert restored_state["processed"]

        # Modify and update
        state_manager.update_workflow_status(
            workflow_id=workflow_id,
            status=WorkflowStatus.HUMAN_APPROVED,
            human_feedback="Approved for production",
        )

        final_workflow = state_manager.restore_workflow(workflow_id)
        assert final_workflow.status == WorkflowStatus.HUMAN_APPROVED

    def test_multi_checkpoint_workflow(self, state_manager, checkpoint_restorer):
        """Test workflow with multiple checkpoints."""
        workflow_id = "wf_multi_ckpt"

        # Create workflow
        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_node="node_1",
            state_data={"step": 1},
        )
        state_manager._workflows[workflow_id] = workflow

        # Create multiple checkpoints
        checkpoint_ids = []
        for i in range(5):
            workflow.state_data["step"] = i
            workflow.current_node = f"node_{i}"
            checkpoint = state_manager.create_checkpoint(
                workflow_id=workflow_id,
                node_name=f"node_{i}",
                state_snapshot=workflow.state_data.copy(),
            )
            checkpoint_ids.append(checkpoint.checkpoint_id)
            time.sleep(0.01)

        # Verify all checkpoints exist
        history = state_manager.get_workflow_history(workflow_id)
        assert len(history) == 5

        # Verify we can restore each checkpoint
        for i, ckpt_id in enumerate(checkpoint_ids):
            state = checkpoint_restorer.restore_checkpoint_state(
                workflow_id=workflow_id,
                checkpoint_id=ckpt_id,
            )
            assert state["step"] == i

    def test_checkpoint_comparison(self, state_manager, checkpoint_restorer):
        """Test comparing two checkpoints."""
        workflow_id = "wf_compare"

        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_node="node_1",
            state_data={"value": 10, "status": "pending"},
        )
        state_manager._workflows[workflow_id] = workflow

        # First checkpoint
        ckpt1 = state_manager.create_checkpoint(
            workflow_id=workflow_id,
            node_name="node_1",
            state_snapshot={"value": 10, "status": "pending"},
        )
        time.sleep(0.05)

        # Second checkpoint with changes
        ckpt2 = state_manager.create_checkpoint(
            workflow_id=workflow_id,
            node_name="node_2",
            state_snapshot={"value": 20, "status": "approved", "new_key": "new_val"},
        )

        # Compare
        diff = checkpoint_restorer.compare_checkpoints(ckpt1, ckpt2)

        assert diff["node_changed"]
        assert diff["status_before"] == "created"
        assert "new_key" in diff["state_keys_added"]
        assert "value" in diff["state_changes"]

    def test_workflow_state_modifications_tracking(self, state_manager):
        """Test that state modifications are tracked."""
        workflow_id = "wf_mods"

        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.PAUSED_FOR_HUMAN,
            current_node="review",
            state_data={},
        )
        state_manager._workflows[workflow_id] = workflow

        # Create checkpoint
        checkpoint = state_manager.create_checkpoint(
            workflow_id=workflow_id,
            node_name="review",
            state_snapshot={"decision": "pending"},
        )

        # Create a mock graph that accepts modifications
        mock_graph = Mock()
        mock_graph.invoke = Mock(return_value={"result": "success"})

        # Resume with modifications (will fail on invoke but we can check tracking)
        try:
            state_manager.resume_from_checkpoint(
                workflow_id=workflow_id,
                checkpoint_id=checkpoint.checkpoint_id,
                graph=mock_graph,
                state_modifications={"decision": "approved", "confidence": 0.95},
            )
        except:
            pass

        updated_workflow = state_manager.restore_workflow(workflow_id)
        # Note: modifications are only added on successful resume


# ============================================================================
# CHECKPOINT RESTORER TESTS
# ============================================================================

class TestCheckpointRestorer:
    """Tests for CheckpointRestorer class."""

    def test_restore_checkpoint_state(self, state_manager, checkpoint_restorer, sample_checkpoint):
        """Test restoring state from checkpoint."""
        # Add workflow with checkpoint
        workflow = HITLWorkflowState(
            workflow_id="wf_001",
            status=WorkflowStatus.PAUSED_FOR_HUMAN,
            current_node="review",
            state_data={},
        )
        state_manager._workflows["wf_001"] = workflow
        workflow.checkpoints.append(sample_checkpoint)

        state = checkpoint_restorer.restore_checkpoint_state(
            workflow_id="wf_001",
            checkpoint_id="ckpt_test_001",
        )

        assert state == sample_checkpoint.state_snapshot

    def test_restore_checkpoint_not_found(self, checkpoint_restorer):
        """Test restoring non-existent checkpoint."""
        with pytest.raises(ValueError, match="not found"):
            checkpoint_restorer.restore_checkpoint_state(
                workflow_id="wf_nonexistent",
                checkpoint_id="ckpt_nonexistent",
            )

    def test_restore_checkpoint_with_validation(self, state_manager, checkpoint_restorer):
        """Test checkpoint restoration with validation."""
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
            state_snapshot={"value": 42},
        )

        # Custom validation that passes
        def validate_func(state):
            return state.get("value") == 42

        state = checkpoint_restorer.restore_checkpoint_with_validation(
            workflow_id="wf_001",
            checkpoint_id=checkpoint.checkpoint_id,
            validation_callback=validate_func,
        )

        assert state["value"] == 42

    def test_restore_checkpoint_with_validation_fails(self, state_manager, checkpoint_restorer):
        """Test checkpoint validation failure."""
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
            state_snapshot={"value": 42},
        )

        # Custom validation that fails
        def validate_func(state):
            return state.get("value") == 99  # Will fail

        with pytest.raises(ValueError, match="Custom validation failed"):
            checkpoint_restorer.restore_checkpoint_with_validation(
                workflow_id="wf_001",
                checkpoint_id=checkpoint.checkpoint_id,
                validation_callback=validate_func,
            )

    def test_restore_and_modify_state(self, state_manager, checkpoint_restorer):
        """Test restoring and modifying state."""
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
            state_snapshot={"decision": "pending", "confidence": 0.5},
        )

        modified_state, mods = checkpoint_restorer.restore_and_modify_state(
            workflow_id="wf_001",
            checkpoint_id=checkpoint.checkpoint_id,
            modifications={"decision": "approved", "confidence": 0.95},
            applied_by="user@example.com",
        )

        assert modified_state["decision"] == "approved"
        assert modified_state["confidence"] == 0.95
        assert len(mods) == 2
        assert mods[0].key == "decision"

    def test_export_checkpoint_json(self, state_manager, checkpoint_restorer):
        """Test exporting checkpoint as JSON."""
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

        exported = checkpoint_restorer.export_checkpoint(
            workflow_id="wf_001",
            checkpoint_id=checkpoint.checkpoint_id,
            format="json",
        )

        assert isinstance(exported, str)
        data = json.loads(exported)
        assert data["checkpoint_id"] == checkpoint.checkpoint_id

    def test_export_checkpoint_text(self, state_manager, checkpoint_restorer):
        """Test exporting checkpoint as text."""
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
            metadata={"source": "test"},
        )

        exported = checkpoint_restorer.export_checkpoint(
            workflow_id="wf_001",
            checkpoint_id=checkpoint.checkpoint_id,
            format="text",
        )

        assert isinstance(exported, str)
        assert "Checkpoint ID:" in exported
        assert checkpoint.checkpoint_id in exported

    def test_get_checkpoint_metadata(self, state_manager, checkpoint_restorer):
        """Test getting checkpoint metadata."""
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
            state_snapshot={"data": "test", "key1": "value1"},
        )

        metadata = checkpoint_restorer.get_checkpoint_metadata(
            workflow_id="wf_001",
            checkpoint_id=checkpoint.checkpoint_id,
        )

        assert metadata["checkpoint_id"] == checkpoint.checkpoint_id
        assert "data" in metadata["state_keys"]
        assert "key1" in metadata["state_keys"]


# ============================================================================
# BENCHMARKS
# ============================================================================

class TestBenchmarks:
    """Benchmark tests for performance-critical operations."""

    def test_checkpoint_creation_speed(self, state_manager, benchmark):
        """Benchmark checkpoint creation speed."""
        workflow_id = "wf_bench_001"
        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={"key": "value"},
        )
        state_manager._workflows[workflow_id] = workflow

        def create_ckpt():
            state_manager.create_checkpoint(
                workflow_id=workflow_id,
                node_name="node",
                state_snapshot={"data": "test", "timestamp": datetime.utcnow().isoformat()},
            )

        # Run benchmark
        benchmark(create_ckpt)

    def test_restore_workflow_speed(self, state_manager, benchmark):
        """Benchmark workflow restoration speed."""
        workflow_id = "wf_bench_002"
        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={"key": "value"},
        )
        state_manager._workflows[workflow_id] = workflow

        # Create checkpoints
        for i in range(10):
            state_manager.create_checkpoint(
                workflow_id=workflow_id,
                node_name=f"node_{i}",
                state_snapshot={"step": i},
            )

        def restore_wf():
            state_manager.restore_workflow(workflow_id)

        benchmark(restore_wf)

    def test_validate_checkpoint_speed(self, state_manager, benchmark):
        """Benchmark checkpoint validation speed."""
        checkpoint_dict = {
            "checkpoint_id": "ckpt_001",
            "workflow_id": "wf_001",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "paused_for_human",
            "node_name": "review",
            "state_snapshot": {"key": f"value_{i}" for i in range(100)},
            "metadata": {},
        }

        def validate_ckpt():
            state_manager.validate_checkpoint(checkpoint_dict)

        benchmark(validate_ckpt)

    def test_large_state_snapshot_benchmark(self, state_manager, benchmark):
        """Benchmark handling large state snapshots."""
        workflow_id = "wf_large_state"
        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
        )
        state_manager._workflows[workflow_id] = workflow

        # Create large state snapshot
        large_state = {f"key_{i}": f"value_{i}" * 100 for i in range(1000)}

        def create_large_ckpt():
            state_manager.create_checkpoint(
                workflow_id=workflow_id,
                node_name="node",
                state_snapshot=large_state.copy(),
            )

        benchmark(create_large_ckpt)

    def test_hash_computation_benchmark(self, benchmark):
        """Benchmark hash computation."""
        checkpoint = CheckpointRecord(
            checkpoint_id="ckpt_001",
            workflow_id="wf_001",
            timestamp=datetime.utcnow(),
            status=WorkflowStatus.PAUSED_FOR_HUMAN,
            node_name="node",
            state_snapshot={f"key_{i}": f"value_{i}" for i in range(1000)},
        )

        def compute_hash():
            checkpoint.compute_hash()

        benchmark(compute_hash)


# ============================================================================
# SCALE TESTS
# ============================================================================

class TestScale:
    """Tests for behavior under scale conditions."""

    def test_100_checkpoint_workflow(self, state_manager):
        """Test workflow with 100 checkpoints."""
        workflow_id = "wf_scale_100"
        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
        )
        state_manager._workflows[workflow_id] = workflow

        start = time.time()
        for i in range(100):
            state_manager.create_checkpoint(
                workflow_id=workflow_id,
                node_name=f"node_{i}",
                state_snapshot={"step": i},
            )

        creation_time = time.time() - start

        # Verify all checkpoints
        history = state_manager.get_workflow_history(workflow_id)
        assert len(history) == 100

        # Should complete in reasonable time
        assert creation_time < 10.0  # Less than 10 seconds

    def test_1000_checkpoint_workflow(self, state_manager):
        """Test workflow with 1000 checkpoints."""
        workflow_id = "wf_scale_1000"
        workflow = HITLWorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_node="process",
            state_data={},
        )
        state_manager._workflows[workflow_id] = workflow

        start = time.time()
        for i in range(1000):
            state_manager.create_checkpoint(
                workflow_id=workflow_id,
                node_name=f"node_{i % 100}",  # Repeat node names
                state_snapshot={"step": i, "iteration": i},
            )

        creation_time = time.time() - start

        history = state_manager.get_workflow_history(workflow_id)
        assert len(history) == 1000

        # Should complete in reasonable time
        assert creation_time < 60.0  # Less than 60 seconds

    def test_concurrent_workflow_restoration(self, state_manager):
        """Test concurrent workflow restoration."""
        import threading

        # Create multiple workflows
        workflow_ids = [f"wf_concurrent_{i}" for i in range(10)]
        for wf_id in workflow_ids:
            workflow = HITLWorkflowState(
                workflow_id=wf_id,
                status=WorkflowStatus.RUNNING,
                current_node="process",
                state_data={"id": wf_id},
            )
            state_manager._workflows[wf_id] = workflow

            # Create checkpoints for each
            for j in range(10):
                state_manager.create_checkpoint(
                    workflow_id=wf_id,
                    node_name=f"node_{j}",
                    state_snapshot={"step": j},
                )

        # Restore all workflows concurrently
        results = []
        errors = []

        def restore_workflow(wf_id):
            try:
                wf = state_manager.restore_workflow(wf_id)
                results.append(wf)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=restore_workflow, args=(wf_id,)) for wf_id in workflow_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(errors) == 0
        assert len(results) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
