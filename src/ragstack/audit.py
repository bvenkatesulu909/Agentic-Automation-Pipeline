"""Immutable audit trail logging for compliance and debugging.

Records every workflow decision, approval, and state transition with:
- Immutable append-only log
- Full context at decision point
- Actor tracking (system/human)
- Timestamp precision
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditLog:
    """A single entry in the immutable audit trail."""

    id: str
    workflow_id: str
    timestamp: datetime
    node_name: str
    action_type: str  # "init", "execute", "approve", "reject", "pause", "resume", "error", "complete"
    actor: str  # "system", "user:{id}", "auto"

    # State before action
    state_before: dict = field(default_factory=dict)

    # Action details
    decision: str = ""  # What decision was made
    reasoning: str = ""  # Why

    # State after action (may be partial)
    state_delta: dict = field(default_factory=dict)

    # Context
    metadata: dict = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_json_line(self) -> str:
        """Convert to JSON for line-based logging."""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """Records all workflow decisions for compliance, debugging, and replay."""

    def __init__(self, log_file: Optional[str] = None):
        """Initialize audit logger.

        Args:
            log_file: Optional file path for persistent audit trail.
                     If None, only in-memory logging is used.
        """
        self.log_file = log_file
        self.in_memory_logs: list[AuditLog] = []

    def log_workflow_start(
        self,
        workflow_id: str,
        user_id: str,
        query: str,
        metadata: dict | None = None,
    ) -> AuditLog:
        """Log workflow initialization.

        Args:
            workflow_id: Unique workflow ID
            user_id: User initiating workflow
            query: The query being processed
            metadata: Additional context

        Returns:
            Created AuditLog entry
        """
        import uuid

        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            node_name="workflow",
            action_type="init",
            actor=f"user:{user_id}",
            decision="start",
            reasoning=f"User initiated query",
            metadata={
                "user_id": user_id,
                "query_length": len(query),
                **(metadata or {}),
            },
        )

        self._persist(entry)
        return entry

    def log_node_execution(
        self,
        workflow_id: str,
        node_name: str,
        state_before: dict,
        state_after: dict,
        metadata: dict | None = None,
    ) -> AuditLog:
        """Log execution of a workflow node.

        Args:
            workflow_id: Workflow ID
            node_name: Name of the node
            state_before: State snapshot before execution
            state_after: State snapshot after execution
            metadata: Additional context (execution time, etc)

        Returns:
            Created AuditLog entry
        """
        import uuid

        state_delta = self._compute_delta(state_before, state_after)

        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            node_name=node_name,
            action_type="execute",
            actor="system",
            state_before=self._state_summary(state_before),
            state_delta=state_delta,
            metadata={
                "node": node_name,
                **(metadata or {}),
            },
        )

        self._persist(entry)
        return entry

    def log_uncertainty_detection(
        self,
        workflow_id: str,
        node_name: str,
        uncertainty_score: float,
        reason: str,
        metadata: dict | None = None,
    ) -> AuditLog:
        """Log uncertainty detection that may trigger approval.

        Args:
            workflow_id: Workflow ID
            node_name: Node where uncertainty detected
            uncertainty_score: Detected score (0-1)
            reason: Why uncertainty detected
            metadata: Additional context

        Returns:
            Created AuditLog entry
        """
        import uuid

        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            node_name=node_name,
            action_type="uncertain",
            actor="system",
            decision="trigger_approval" if uncertainty_score > 0.7 else "continue",
            reasoning=reason,
            metadata={
                "uncertainty_score": uncertainty_score,
                "trigger_threshold": 0.7,
                **(metadata or {}),
            },
        )

        self._persist(entry)
        return entry

    def log_approval_request(
        self,
        workflow_id: str,
        approval_request_id: str,
        uncertainty_score: float,
        reason: str,
        recommended_action: str,
    ) -> AuditLog:
        """Log creation of an approval request (workflow paused).

        Args:
            workflow_id: Workflow ID
            approval_request_id: ID of the approval request
            uncertainty_score: Score that triggered approval
            reason: Why approval needed
            recommended_action: What's recommended

        Returns:
            Created AuditLog entry
        """
        import uuid

        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            node_name="approval_gate",
            action_type="pause",
            actor="system",
            decision="waiting_for_approval",
            reasoning=reason,
            metadata={
                "approval_request_id": approval_request_id,
                "uncertainty_score": uncertainty_score,
                "recommended_action": recommended_action,
            },
        )

        self._persist(entry)
        logger.info(f"[{workflow_id}] Workflow paused: approval required ({reason})")
        return entry

    def log_approval_response(
        self,
        workflow_id: str,
        approval_request_id: str,
        decision: str,  # "approve", "reject", "modify"
        approved_by: str,
        reasoning: str = "",
    ) -> AuditLog:
        """Log human approval decision.

        Args:
            workflow_id: Workflow ID
            approval_request_id: ID of approval request being responded to
            decision: "approve", "reject", or "modify"
            approved_by: User who approved
            reasoning: Optional reasoning for decision

        Returns:
            Created AuditLog entry
        """
        import uuid

        action_type = "approve" if decision == "approve" else "reject"

        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            node_name="approval_gate",
            action_type=action_type,
            actor=f"user:{approved_by}",
            decision=decision,
            reasoning=reasoning,
            metadata={
                "approval_request_id": approval_request_id,
                "approved_by": approved_by,
            },
        )

        self._persist(entry)
        logger.info(f"[{workflow_id}] Approval {decision} by {approved_by}")
        return entry

    def log_workflow_resume(
        self,
        workflow_id: str,
        from_node: str,
        resumed_by: str = "system",
    ) -> AuditLog:
        """Log workflow resumption after approval.

        Args:
            workflow_id: Workflow ID
            from_node: Node where workflow resumes
            resumed_by: Who resumed ("system" or "user:{id}")

        Returns:
            Created AuditLog entry
        """
        import uuid

        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            node_name=from_node,
            action_type="resume",
            actor=resumed_by,
            decision="continue",
            reasoning="Approval granted, resuming workflow",
        )

        self._persist(entry)
        logger.info(f"[{workflow_id}] Workflow resumed at {from_node}")
        return entry

    def log_workflow_complete(
        self,
        workflow_id: str,
        final_state: dict | None = None,
    ) -> AuditLog:
        """Log workflow completion.

        Args:
            workflow_id: Workflow ID
            final_state: Final state snapshot

        Returns:
            Created AuditLog entry
        """
        import uuid

        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            node_name="workflow",
            action_type="complete",
            actor="system",
            decision="success",
            reasoning="Workflow completed successfully",
            state_after=self._state_summary(final_state or {}),
        )

        self._persist(entry)
        logger.info(f"[{workflow_id}] Workflow completed")
        return entry

    def log_error(
        self,
        workflow_id: str,
        node_name: str,
        error_msg: str,
        metadata: dict | None = None,
    ) -> AuditLog:
        """Log workflow error.

        Args:
            workflow_id: Workflow ID
            node_name: Node where error occurred
            error_msg: Error message
            metadata: Additional context

        Returns:
            Created AuditLog entry
        """
        import uuid

        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            node_name=node_name,
            action_type="error",
            actor="system",
            decision="failed",
            reasoning=error_msg,
            error_message=error_msg,
            metadata=metadata or {},
        )

        self._persist(entry)
        logger.error(f"[{workflow_id}] Error at {node_name}: {error_msg}")
        return entry

    def get_workflow_trail(self, workflow_id: str) -> list[AuditLog]:
        """Retrieve complete audit trail for a workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            List of AuditLog entries in chronological order
        """
        # In-memory implementation; override in database-backed subclass
        return [entry for entry in self.in_memory_logs if entry.workflow_id == workflow_id]

    def _persist(self, entry: AuditLog) -> None:
        """Persist audit entry (memory and optional file)."""
        self.in_memory_logs.append(entry)

        if self.log_file:
            try:
                with open(self.log_file, "a") as f:
                    f.write(entry.to_json_line() + "\n")
            except IOError as e:
                logger.error(f"Failed to write audit log to file: {e}")

    @staticmethod
    def _state_summary(state: dict) -> dict:
        """Create a summary of state for audit trail."""
        summary = {}
        for key, value in state.items():
            if key in ["audit_trail", "checkpoints"]:
                continue
            elif isinstance(value, (str, int, float, bool, type(None))):
                summary[key] = value
            elif isinstance(value, (list, dict)):
                summary[key] = f"<{type(value).__name__} with {len(value)} items>"
            else:
                summary[key] = f"<{type(value).__name__}>"
        return summary

    @staticmethod
    def _compute_delta(before: dict, after: dict) -> dict:
        """Compute what changed between two state snapshots."""
        delta = {}

        # New or changed keys
        for key, after_val in after.items():
            if key not in before:
                delta[key] = {"added": after_val}
            elif before[key] != after_val:
                delta[key] = {
                    "before": before[key],
                    "after": after_val,
                }

        # Removed keys
        for key in before:
            if key not in after:
                delta[key] = {"removed": True}

        return delta
