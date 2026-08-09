"""SQLAlchemy-backed approval store for persistent HITL workflows."""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from ..approval import ApprovalStore, ApprovalRequest, ApprovalResponse
from .models import (
    Base,
    WorkflowModel,
    ApprovalRequestModel,
    ApprovalResponseModel,
    AuditEntryModel,
    CheckpointModel,
)

logger = logging.getLogger(__name__)


class SQLAlchemyApprovalStore(ApprovalStore):
    """Database-backed approval store using SQLAlchemy."""

    def __init__(self, database_url: str = "sqlite:///hitl_workflows.db"):
        """Initialize store with database connection.

        Args:
            database_url: SQLAlchemy database URL
                         (default: SQLite file in current directory)
        """
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables
        Base.metadata.create_all(self.engine)
        logger.info(f"Initialized approval store with {database_url}")

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def save_approval_request(self, request: ApprovalRequest) -> None:
        """Store an approval request."""
        with self.get_session() as session:
            model = ApprovalRequestModel(
                id=request.id,
                workflow_id=request.workflow_id,
                node_name=request.node_name,
                created_at=request.timestamp,
                uncertainty_score=request.uncertainty_score,
                uncertainty_reason=request.uncertainty_reason,
                policy=request.policy.value,
                recommended_action=request.recommended_action,
                alternative_actions=json.dumps(request.alternative_actions),
                context_data=json.dumps(request.context_data),
                state_snapshot=json.dumps(request.state_snapshot),
            )
            session.add(model)
            session.commit()
            logger.info(f"Saved approval request {request.id}")

    def get_approval_request(self, request_id: str) -> ApprovalRequest | None:
        """Retrieve an approval request."""
        with self.get_session() as session:
            stmt = select(ApprovalRequestModel).where(ApprovalRequestModel.id == request_id)
            model = session.scalars(stmt).first()

            if not model:
                return None

            return ApprovalRequest(
                id=model.id,
                workflow_id=model.workflow_id,
                node_name=model.node_name,
                timestamp=model.created_at,
                policy=model.policy,
                uncertainty_score=model.uncertainty_score,
                uncertainty_reason=model.uncertainty_reason or "",
                state_snapshot=json.loads(model.state_snapshot or "{}"),
                recommended_action=model.recommended_action,
                alternative_actions=json.loads(model.alternative_actions or "[]"),
                context_data=json.loads(model.context_data or "{}"),
            )

    def list_pending_approvals(self, workflow_id: str | None = None) -> list[ApprovalRequest]:
        """List all pending approval requests."""
        with self.get_session() as session:
            stmt = select(ApprovalRequestModel).where(ApprovalRequestModel.responded_at.is_(None))

            if workflow_id:
                stmt = stmt.where(ApprovalRequestModel.workflow_id == workflow_id)

            models = session.scalars(stmt).all()

            return [
                ApprovalRequest(
                    id=model.id,
                    workflow_id=model.workflow_id,
                    node_name=model.node_name,
                    timestamp=model.created_at,
                    policy=model.policy,
                    uncertainty_score=model.uncertainty_score,
                    uncertainty_reason=model.uncertainty_reason or "",
                    state_snapshot=json.loads(model.state_snapshot or "{}"),
                    recommended_action=model.recommended_action,
                    alternative_actions=json.loads(model.alternative_actions or "[]"),
                    context_data=json.loads(model.context_data or "{}"),
                )
                for model in models
            ]

    def save_approval_response(self, response: ApprovalResponse) -> None:
        """Store a human's approval decision."""
        with self.get_session() as session:
            # Save response
            response_model = ApprovalResponseModel(
                id=response.approval_id,
                approval_request_id=response.approval_id,
                decision=response.decision.value,
                approved_by=response.approved_by,
                created_at=response.timestamp,
                reasoning=response.reasoning,
                modified_state=json.dumps(response.modified_state or {}),
            )
            session.add(response_model)

            # Update approval request
            stmt = select(ApprovalRequestModel).where(
                ApprovalRequestModel.id == response.approval_id
            )
            approval_model = session.scalars(stmt).first()
            if approval_model:
                approval_model.responded_at = response.timestamp
                approval_model.response_id = response.approval_id

            session.commit()
            logger.info(f"Saved approval response {response.approval_id}")

    def get_approval_response(self, request_id: str) -> ApprovalResponse | None:
        """Retrieve approval response for a request."""
        with self.get_session() as session:
            stmt = select(ApprovalResponseModel).where(
                ApprovalResponseModel.approval_request_id == request_id
            )
            model = session.scalars(stmt).first()

            if not model:
                return None

            return ApprovalResponse(
                approval_id=model.id,
                decision=model.decision,
                approved_by=model.approved_by,
                timestamp=model.created_at,
                reasoning=model.reasoning or "",
                modified_state=json.loads(model.modified_state or "{}"),
            )

    def save_audit_entry(self, entry_dict: dict) -> None:
        """Save an audit entry."""
        with self.get_session() as session:
            model = AuditEntryModel(
                id=entry_dict["id"],
                workflow_id=entry_dict["workflow_id"],
                node_name=entry_dict["node_name"],
                action_type=entry_dict["action_type"],
                actor=entry_dict["actor"],
                created_at=entry_dict.get("created_at"),
                decision=entry_dict.get("decision"),
                reasoning=entry_dict.get("reasoning"),
                state_before=json.dumps(entry_dict.get("state_before", {})),
                state_delta=json.dumps(entry_dict.get("state_delta", {})),
                state_after=json.dumps(entry_dict.get("state_after", {})),
                metadata=json.dumps(entry_dict.get("metadata", {})),
                error_message=entry_dict.get("error_message"),
            )
            session.add(model)
            session.commit()

    def get_audit_entries(self, workflow_id: str) -> list[dict]:
        """Get audit entries for a workflow."""
        with self.get_session() as session:
            stmt = (
                select(AuditEntryModel)
                .where(AuditEntryModel.workflow_id == workflow_id)
                .order_by(AuditEntryModel.created_at.asc())
            )
            models = session.scalars(stmt).all()

            return [model.to_dict() for model in models]

    def save_checkpoint(self, checkpoint_dict: dict) -> None:
        """Save a workflow checkpoint."""
        with self.get_session() as session:
            model = CheckpointModel(
                id=checkpoint_dict["id"],
                workflow_id=checkpoint_dict["workflow_id"],
                node_name=checkpoint_dict["node_name"],
                created_at=checkpoint_dict.get("created_at"),
                reason=checkpoint_dict.get("reason"),
                state=json.dumps(checkpoint_dict["state"]),
            )
            session.add(model)
            session.commit()

    def get_checkpoints(self, workflow_id: str) -> list[dict]:
        """Get checkpoints for a workflow."""
        with self.get_session() as session:
            stmt = (
                select(CheckpointModel)
                .where(CheckpointModel.workflow_id == workflow_id)
                .order_by(CheckpointModel.created_at.asc())
            )
            models = session.scalars(stmt).all()

            return [
                {
                    "id": model.id,
                    "workflow_id": model.workflow_id,
                    "node_name": model.node_name,
                    "created_at": model.created_at.isoformat() if model.created_at else None,
                    "reason": model.reason,
                    "state": json.loads(model.state),
                }
                for model in models
            ]
