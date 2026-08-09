"""SQLAlchemy models for HITL workflow persistence.

Stores:
- Workflow state snapshots
- Approval requests and responses
- Audit trail entries
- Checkpoint history
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class WorkflowModel(Base):
    """Persistent workflow record."""

    __tablename__ = "workflows"

    id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=False)
    query = Column(Text, nullable=True)
    status = Column(String(50), default="pending")  # pending, running, paused, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Current state (JSON)
    state_json = Column(Text, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Relationships
    approvals = relationship("ApprovalRequestModel", back_populates="workflow")
    audit_entries = relationship("AuditEntryModel", back_populates="workflow")
    checkpoints = relationship("CheckpointModel", back_populates="workflow")

    def to_dict(self) -> dict:
        """Convert to dict."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "query": self.query,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ApprovalRequestModel(Base):
    """Approval request waiting for human decision."""

    __tablename__ = "approval_requests"

    id = Column(String(255), primary_key=True)
    workflow_id = Column(String(255), ForeignKey("workflows.id"), nullable=False)
    node_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Uncertainty that triggered approval
    uncertainty_score = Column(Float, nullable=False)
    uncertainty_reason = Column(Text, nullable=True)

    # Approval policy
    policy = Column(String(50), nullable=False)  # require, auto_if_uncertain, skip

    # Context for human reviewer
    recommended_action = Column(Text, nullable=False)
    alternative_actions = Column(Text, nullable=True)  # JSON array
    context_data = Column(Text, nullable=True)  # JSON

    # State snapshot at time of request
    state_snapshot = Column(Text, nullable=True)  # Full state JSON

    # Response tracking
    responded_at = Column(DateTime, nullable=True)
    response_id = Column(String(255), nullable=True)  # FK to ApprovalResponseModel

    # Relationship
    workflow = relationship("WorkflowModel", back_populates="approvals")

    def to_dict(self) -> dict:
        """Convert to dict."""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "node_name": self.node_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "uncertainty_score": self.uncertainty_score,
            "uncertainty_reason": self.uncertainty_reason,
            "policy": self.policy,
            "recommended_action": self.recommended_action,
            "alternative_actions": json.loads(self.alternative_actions or "[]"),
            "context_data": json.loads(self.context_data or "{}"),
            "responded": self.responded_at is not None,
        }


class ApprovalResponseModel(Base):
    """Human response to an approval request."""

    __tablename__ = "approval_responses"

    id = Column(String(255), primary_key=True)
    approval_request_id = Column(String(255), ForeignKey("approval_requests.id"), nullable=False)
    decision = Column(String(50), nullable=False)  # approve, reject, modify
    approved_by = Column(String(255), nullable=False)  # user_id
    created_at = Column(DateTime, default=datetime.utcnow)
    reasoning = Column(Text, nullable=True)

    # Modified state (if decision is "modify")
    modified_state = Column(Text, nullable=True)  # JSON


class AuditEntryModel(Base):
    """Immutable audit trail entry."""

    __tablename__ = "audit_entries"

    id = Column(String(255), primary_key=True)
    workflow_id = Column(String(255), ForeignKey("workflows.id"), nullable=False)
    node_name = Column(String(255), nullable=False)
    action_type = Column(String(50), nullable=False)  # execute, approve, reject, pause, resume, error
    actor = Column(String(255), nullable=False)  # system, user:{id}, auto
    created_at = Column(DateTime, default=datetime.utcnow)

    # Decision and reasoning
    decision = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)

    # State changes
    state_before = Column(Text, nullable=True)  # JSON summary
    state_delta = Column(Text, nullable=True)  # JSON of changes
    state_after = Column(Text, nullable=True)  # JSON summary

    # Metadata
    metadata = Column(Text, nullable=True)  # JSON

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Relationship
    workflow = relationship("WorkflowModel", back_populates="audit_entries")

    def to_dict(self) -> dict:
        """Convert to dict."""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "node_name": self.node_name,
            "action_type": self.action_type,
            "actor": self.actor,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "error_message": self.error_message,
        }


class CheckpointModel(Base):
    """Workflow state snapshot at a decision point."""

    __tablename__ = "checkpoints"

    id = Column(String(255), primary_key=True)
    workflow_id = Column(String(255), ForeignKey("workflows.id"), nullable=False)
    node_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    reason = Column(Text, nullable=True)

    # Full state snapshot
    state = Column(Text, nullable=False)  # JSON

    # Relationship
    workflow = relationship("WorkflowModel", back_populates="checkpoints")

    def to_dict(self) -> dict:
        """Convert to dict."""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "node_name": self.node_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reason": self.reason,
        }
