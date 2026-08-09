"""Approval gate node for human-in-the-loop workflows.

Implements a LangGraph node that pauses workflow execution and waits for human approval.
Stores approval requests and state snapshots for later resumption.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ApprovalPolicy(str, Enum):
    """Policy for when to require human approval."""

    REQUIRE = "require"  # Always require human approval
    AUTO_IF_UNCERTAIN = "auto_if_uncertain"  # Only require if uncertainty score high
    SKIP = "skip"  # Never require (for testing)


class ApprovalDecision(str, Enum):
    """Human decision at an approval gate."""

    APPROVE = "approve"  # Proceed with workflow
    REJECT = "reject"  # Reject and pause
    MODIFY = "modify"  # Approve with modifications


@dataclass
class ApprovalRequest:
    """A request waiting for human approval."""

    id: str
    workflow_id: str
    node_name: str
    timestamp: datetime
    policy: ApprovalPolicy
    uncertainty_score: float
    uncertainty_reason: str
    state_snapshot: dict  # Full workflow state at gate
    recommended_action: str
    alternative_actions: list[str]
    context_data: dict  # Node-specific context

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["policy"] = self.policy.value
        return d


@dataclass
class ApprovalResponse:
    """Response to an approval request."""

    approval_id: str
    decision: ApprovalDecision
    approved_by: str  # User ID or "system"
    timestamp: datetime
    reasoning: str = ""
    modified_state: dict | None = None  # If MODIFY, new state values

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "approval_id": self.approval_id,
            "decision": self.decision.value,
            "approved_by": self.approved_by,
            "timestamp": self.timestamp.isoformat(),
            "reasoning": self.reasoning,
            "modified_state": self.modified_state,
        }


class ApprovalGate:
    """A pauseable gate in a LangGraph workflow.

    Usage:
        gate = ApprovalGate(
            store=approval_store,
            policy=ApprovalPolicy.AUTO_IF_UNCERTAIN,
        )
        # In LangGraph node function:
        state = gate.evaluate(
            workflow_id=state["workflow_id"],
            node_name="retrieve",
            state=state,
            uncertainty_score=uncertainty_score,
            uncertainty_reason="Low retrieval confidence",
        )
        if state.get("approval_required"):
            return state  # Paused at gate
        # Continue workflow
    """

    def __init__(
        self,
        store: ApprovalStore,
        policy: ApprovalPolicy = ApprovalPolicy.AUTO_IF_UNCERTAIN,
        uncertainty_threshold: float = 0.7,
    ):
        """Initialize approval gate.

        Args:
            store: Backend store for approval requests/responses
            policy: When to require approval
            uncertainty_threshold: Score threshold for AUTO_IF_UNCERTAIN
        """
        self.store = store
        self.policy = policy
        self.uncertainty_threshold = uncertainty_threshold

    def evaluate(
        self,
        workflow_id: str,
        node_name: str,
        state: dict[str, Any],
        uncertainty_score: float = 0.0,
        uncertainty_reason: str = "",
        recommended_action: str = "Review and approve",
        alternative_actions: list[str] | None = None,
        context_data: dict | None = None,
    ) -> dict[str, Any]:
        """Evaluate if gate should pause workflow.

        Returns modified state with approval_required flag if pausing.

        Args:
            workflow_id: Workflow ID
            node_name: Name of the node (for logging)
            state: Current workflow state (will be snapshotted)
            uncertainty_score: Uncertainty score from detector (0-1)
            uncertainty_reason: Human-readable reason
            recommended_action: What should happen next
            alternative_actions: Other options for approver
            context_data: Node-specific context to show human

        Returns:
            Modified state dict, possibly with approval_required=True
        """
        should_require = self._should_require_approval(uncertainty_score)

        if not should_require:
            return state

        # Create approval request
        approval_req = ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            node_name=node_name,
            timestamp=datetime.utcnow(),
            policy=self.policy,
            uncertainty_score=uncertainty_score,
            uncertainty_reason=uncertainty_reason,
            state_snapshot=state.copy(),
            recommended_action=recommended_action,
            alternative_actions=alternative_actions or [recommended_action],
            context_data=context_data or {},
        )

        # Store approval request
        logger.info(
            f"Gate at {node_name}: approval required (score={uncertainty_score:.2f})"
        )
        self.store.save_approval_request(approval_req)

        # Mark state as paused at gate
        state = state.copy()
        state["approval_required"] = True
        state["approval_request_id"] = approval_req.id
        state["approval_context"] = {
            "reason": uncertainty_reason,
            "uncertainty_score": uncertainty_score,
            "recommended_action": recommended_action,
            "alternative_actions": alternative_actions or [recommended_action],
            "awaiting_approval_since": datetime.utcnow().isoformat(),
        }

        return state

    def _should_require_approval(self, uncertainty_score: float) -> bool:
        """Determine if approval is required based on policy and score."""
        if self.policy == ApprovalPolicy.SKIP:
            return False
        elif self.policy == ApprovalPolicy.REQUIRE:
            return True
        elif self.policy == ApprovalPolicy.AUTO_IF_UNCERTAIN:
            return uncertainty_score >= self.uncertainty_threshold
        else:
            return False


class ApprovalStore:
    """Backend store for approval requests and responses.

    Implement as SQLAlchemy models (see db/models.py).
    """

    def save_approval_request(self, request: ApprovalRequest) -> None:
        """Store an approval request."""
        raise NotImplementedError

    def get_approval_request(self, request_id: str) -> ApprovalRequest | None:
        """Retrieve an approval request."""
        raise NotImplementedError

    def list_pending_approvals(self, workflow_id: str | None = None) -> list[ApprovalRequest]:
        """List all pending approval requests."""
        raise NotImplementedError

    def save_approval_response(self, response: ApprovalResponse) -> None:
        """Store a human's approval decision."""
        raise NotImplementedError

    def get_approval_response(self, request_id: str) -> ApprovalResponse | None:
        """Retrieve approval response for a request."""
        raise NotImplementedError


def gate_node_factory(
    store: ApprovalStore,
    policy: ApprovalPolicy = ApprovalPolicy.AUTO_IF_UNCERTAIN,
) -> Callable:
    """Factory to create a LangGraph node function for approval gates.

    Usage in graph builder:
        gate = gate_node_factory(store, ApprovalPolicy.AUTO_IF_UNCERTAIN)
        workflow.add_node("approval_gate_after_retrieval", gate)
        workflow.add_conditional_edges(
            "retrieve",
            gate,
            {"continue": "generate_answer", "pause": END},
        )

    Args:
        store: Approval store backend
        policy: Approval policy

    Returns:
        Node function compatible with LangGraph
    """

    def approval_gate_node(state: dict) -> dict:
        # Extract uncertainty score (should be set by prior node)
        uncertainty_score = state.get("uncertainty_score", 0.0)
        uncertainty_reason = state.get("uncertainty_reason", "")

        gate = ApprovalGate(store, policy=policy)
        modified_state = gate.evaluate(
            workflow_id=state.get("workflow_id", "unknown"),
            node_name="approval_gate",
            state=state,
            uncertainty_score=uncertainty_score,
            uncertainty_reason=uncertainty_reason,
        )

        return modified_state

    return approval_gate_node
