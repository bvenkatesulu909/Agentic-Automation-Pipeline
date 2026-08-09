"""Extended workflow state management for human-in-the-loop workflows.

Adds HITL capabilities to LangGraph state:
- Workflow ID for persistence and tracking
- Approval gates and decision points
- Audit trail with timestamps
- Checkpoint snapshots for resume
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """Record of a decision point or action in workflow."""

    id: str
    workflow_id: str
    timestamp: datetime
    node_name: str
    action_type: str  # "execute", "approve", "reject", "pause", "resume", "error"
    actor: str  # "system", "user:{id}", "auto"
    input_state_summary: dict  # Subset of state (not full snapshot)
    output: Any = None
    metadata: dict = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        if isinstance(d["output"], dict):
            d["output"] = d["output"]
        else:
            d["output"] = str(d["output"]) if d["output"] is not None else None
        return d


@dataclass
class Checkpoint:
    """Snapshot of workflow state at a decision point."""

    id: str
    workflow_id: str
    node_name: str
    timestamp: datetime
    state: dict  # Full state snapshot
    reason: str  # Why this checkpoint was created


class HITLWorkflowState:
    """Extended workflow state with HITL capabilities.

    Wraps LangGraph state dict and adds:
    - Persistent workflow ID
    - Approval tracking
    - Audit trail
    - Checkpoint management

    Usage:
        hitl_state = HITLWorkflowState(
            workflow_id="wf_12345",
            base_state=langgraph_state,
        )
        hitl_state.add_audit_entry(
            node_name="retrieve",
            action_type="execute",
            actor="system",
        )
        hitl_state.checkpoint(node_name="retrieve", reason="after retrieval")
    """

    def __init__(
        self,
        workflow_id: str,
        base_state: dict | None = None,
        user_id: str = "unknown",
    ):
        """Initialize HITL workflow state.

        Args:
            workflow_id: Unique workflow identifier for persistence
            base_state: Initial LangGraph state dict
            user_id: User executing the workflow
        """
        self.workflow_id = workflow_id
        self.user_id = user_id
        self.state = base_state.copy() if base_state else {}

        # Initialize HITL fields if not present
        if "workflow_id" not in self.state:
            self.state["workflow_id"] = workflow_id
        if "user_id" not in self.state:
            self.state["user_id"] = user_id
        if "approval_required" not in self.state:
            self.state["approval_required"] = False
        if "approval_context" not in self.state:
            self.state["approval_context"] = None
        if "audit_trail" not in self.state:
            self.state["audit_trail"] = []
        if "checkpoints" not in self.state:
            self.state["checkpoints"] = []
        if "uncertainty_score" not in self.state:
            self.state["uncertainty_score"] = 0.0
        if "uncertainty_reason" not in self.state:
            self.state["uncertainty_reason"] = ""

    def __getitem__(self, key: str) -> Any:
        """Dict-like access."""
        return self.state[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Dict-like assignment."""
        self.state[key] = value

    def __contains__(self, key: str) -> bool:
        """Dict-like containment check."""
        return key in self.state

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like get."""
        return self.state.get(key, default)

    def copy(self) -> dict:
        """Return a copy of the state dict."""
        return self.state.copy()

    def to_dict(self) -> dict:
        """Convert state to dict for serialization/transmission."""
        output = self.state.copy()
        # Serialize datetime objects in audit trail
        if "audit_trail" in output and isinstance(output["audit_trail"], list):
            output["audit_trail"] = [
                entry.to_dict() if hasattr(entry, "to_dict") else entry
                for entry in output["audit_trail"]
            ]
        return output

    @classmethod
    def from_dict(cls, data: dict) -> HITLWorkflowState:
        """Reconstruct state from dict (e.g., from database)."""
        workflow_id = data.get("workflow_id", "unknown")
        user_id = data.get("user_id", "unknown")
        state_obj = cls(workflow_id=workflow_id, base_state=data.copy(), user_id=user_id)
        return state_obj

    def add_audit_entry(
        self,
        node_name: str,
        action_type: str,
        actor: str = "system",
        output: Any = None,
        metadata: dict | None = None,
        error: str | None = None,
    ) -> AuditEntry:
        """Add entry to audit trail.

        Args:
            node_name: Name of the node/step
            action_type: "execute", "approve", "reject", "pause", "resume", "error"
            actor: "system" or "user:{id}" or "auto"
            output: Result of the action
            metadata: Additional context
            error: Error message if action failed

        Returns:
            Created AuditEntry
        """
        import uuid

        entry = AuditEntry(
            id=str(uuid.uuid4()),
            workflow_id=self.workflow_id,
            timestamp=datetime.utcnow(),
            node_name=node_name,
            action_type=action_type,
            actor=actor,
            input_state_summary=self._state_summary(),
            output=output,
            metadata=metadata or {},
            error=error,
        )

        trail = self.state.get("audit_trail", [])
        if not isinstance(trail, list):
            trail = []
        trail.append(entry)
        self.state["audit_trail"] = trail

        logger.info(
            f"[{self.workflow_id}] Audit: {node_name} {action_type} by {actor}"
        )
        return entry

    def checkpoint(
        self,
        node_name: str,
        reason: str = "checkpoint",
    ) -> Checkpoint:
        """Create a checkpoint snapshot of current state.

        Used for pause/resume and debugging.

        Args:
            node_name: Name of the node where checkpoint occurs
            reason: Why this checkpoint was created

        Returns:
            Created Checkpoint
        """
        import uuid

        checkpoint = Checkpoint(
            id=str(uuid.uuid4()),
            workflow_id=self.workflow_id,
            node_name=node_name,
            timestamp=datetime.utcnow(),
            state=self.state.copy(),  # Full state snapshot
            reason=reason,
        )

        checkpoints = self.state.get("checkpoints", [])
        if not isinstance(checkpoints, list):
            checkpoints = []
        checkpoints.append(checkpoint)
        self.state["checkpoints"] = checkpoints

        logger.debug(f"[{self.workflow_id}] Checkpoint at {node_name}: {reason}")
        return checkpoint

    def set_approval_pending(
        self,
        approval_request_id: str,
        uncertainty_score: float,
        reason: str,
        recommended_action: str,
        alternatives: list[str],
    ) -> None:
        """Mark workflow as waiting for approval.

        Args:
            approval_request_id: ID of the approval request
            uncertainty_score: Uncertainty that triggered approval
            reason: Why approval is needed
            recommended_action: Suggested action for human
            alternatives: Alternative actions
        """
        self.state["approval_required"] = True
        self.state["approval_request_id"] = approval_request_id
        self.state["uncertainty_score"] = uncertainty_score
        self.state["uncertainty_reason"] = reason
        self.state["approval_context"] = {
            "request_id": approval_request_id,
            "uncertainty_score": uncertainty_score,
            "reason": reason,
            "recommended_action": recommended_action,
            "alternative_actions": alternatives,
            "awaiting_since": datetime.utcnow().isoformat(),
        }

        self.add_audit_entry(
            node_name="approval_gate",
            action_type="pause",
            actor="system",
            metadata={
                "reason": reason,
                "uncertainty_score": uncertainty_score,
            },
        )

    def resume_from_approval(
        self,
        approval_decision: str,  # "approve", "reject", "modify"
        approved_by: str,
        reasoning: str = "",
    ) -> None:
        """Record approval response and resume workflow.

        Args:
            approval_decision: "approve", "reject", or "modify"
            approved_by: User ID who approved
            reasoning: Optional reasoning for the decision
        """
        self.state["approval_required"] = False
        self.state["approval_decision"] = approval_decision

        self.add_audit_entry(
            node_name="approval_gate",
            action_type="approve" if approval_decision == "approve" else "reject",
            actor=f"user:{approved_by}",
            metadata={
                "decision": approval_decision,
                "reasoning": reasoning,
            },
        )

    def mark_error(
        self,
        node_name: str,
        error_msg: str,
        actor: str = "system",
    ) -> None:
        """Record error in audit trail."""
        self.state["error"] = error_msg
        self.add_audit_entry(
            node_name=node_name,
            action_type="error",
            actor=actor,
            error=error_msg,
        )

    def _state_summary(self) -> dict:
        """Create summary of state for audit trail (exclude large objects)."""
        summary = {}
        for key, value in self.state.items():
            if key in ["audit_trail", "checkpoints"]:
                continue  # Skip large nested objects
            elif isinstance(value, (str, int, float, bool, type(None))):
                summary[key] = value
            elif isinstance(value, list) and len(value) < 5:
                summary[key] = f"<list[{len(value)}]>"
            elif isinstance(value, dict):
                summary[key] = f"<dict[{len(value)} keys]>"
            else:
                summary[key] = f"<{type(value).__name__}>"
        return summary

    @property
    def audit_trail(self) -> list[AuditEntry]:
        """Get audit trail entries."""
        return self.state.get("audit_trail", [])

    @property
    def is_pending_approval(self) -> bool:
        """Check if workflow is waiting for approval."""
        return self.state.get("approval_required", False)

    @property
    def last_checkpoint(self) -> Checkpoint | None:
        """Get most recent checkpoint."""
        checkpoints = self.state.get("checkpoints", [])
        return checkpoints[-1] if checkpoints else None
