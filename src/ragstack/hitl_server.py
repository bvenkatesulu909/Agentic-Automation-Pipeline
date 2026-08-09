"""FastAPI server for managing human-in-the-loop workflows.

Provides:
- REST API for workflow management
- WebSocket for real-time updates
- Approval request/response handling
- Audit trail queries
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional, Any

from fastapi import FastAPI, HTTPException, WebSocket, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .approval import ApprovalStore, ApprovalRequest, ApprovalResponse, ApprovalDecision
from .audit import AuditLogger
from .workflow_state import HITLWorkflowState

logger = logging.getLogger(__name__)


# Pydantic models for API

class WorkflowStatusResponse(BaseModel):
    """Status of a workflow."""

    workflow_id: str
    status: str  # pending, running, paused, completed, failed
    created_at: str
    updated_at: str
    is_pending_approval: bool = False
    approval_context: Optional[dict] = None
    last_error: Optional[str] = None


class ApprovalRequestResponse(BaseModel):
    """Approval request details for API."""

    id: str
    workflow_id: str
    node_name: str
    created_at: str
    uncertainty_score: float
    uncertainty_reason: str
    recommended_action: str
    alternative_actions: list[str]
    context_data: dict


class ApprovalDecisionRequest(BaseModel):
    """Human's approval decision."""

    decision: str = Field(..., description="approve, reject, or modify")
    approved_by: str = Field(..., description="User ID who approved")
    reasoning: str = Field(default="")
    modified_state: Optional[dict] = Field(default=None)


class AuditEntryResponse(BaseModel):
    """Audit trail entry."""

    id: str
    workflow_id: str
    timestamp: str
    node_name: str
    action_type: str
    actor: str
    decision: Optional[str] = None
    reasoning: Optional[str] = None
    error_message: Optional[str] = None


class WorkflowStartRequest(BaseModel):
    """Request to start a workflow."""

    query: str
    user_id: str = Field(default="unknown")
    metadata: Optional[dict] = None


# Server implementation


def create_hitl_server(
    approval_store: ApprovalStore,
    audit_logger: Optional[AuditLogger] = None,
) -> FastAPI:
    """Create FastAPI server for HITL workflow management.

    Args:
        approval_store: Backend for storing approvals
        audit_logger: Audit trail logger

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="HITL Workflow Server",
        description="Human-in-the-loop workflow management API",
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if audit_logger is None:
        audit_logger = AuditLogger()

    # In-memory workflow storage (upgrade to database in production)
    workflows: dict[str, dict] = {}
    approvals: dict[str, dict] = {}

    # Health check
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    # Workflow management endpoints

    @app.post("/workflows/start")
    async def start_workflow(req: WorkflowStartRequest) -> dict:
        """Start a new workflow.

        Args:
            req: Workflow start request

        Returns:
            Workflow status
        """
        import uuid

        workflow_id = str(uuid.uuid4())
        workflows[workflow_id] = {
            "id": workflow_id,
            "status": "running",
            "user_id": req.user_id,
            "query": req.query,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        audit_logger.log_workflow_start(
            workflow_id=workflow_id,
            user_id=req.user_id,
            query=req.query,
            metadata=req.metadata,
        )

        logger.info(f"Started workflow {workflow_id}")
        return {
            "workflow_id": workflow_id,
            "status": "running",
            "message": "Workflow started",
        }

    @app.get("/workflows/{workflow_id}/status")
    async def get_workflow_status(workflow_id: str) -> WorkflowStatusResponse:
        """Get workflow status.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow status details
        """
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        wf = workflows[workflow_id]
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=wf["status"],
            created_at=wf["created_at"],
            updated_at=wf["updated_at"],
            is_pending_approval=wf.get("approval_required", False),
            approval_context=wf.get("approval_context"),
            last_error=wf.get("error"),
        )

    # Approval management endpoints

    @app.get("/approvals/pending")
    async def list_pending_approvals(
        workflow_id: Optional[str] = Query(None),
    ) -> list[ApprovalRequestResponse]:
        """List pending approval requests.

        Args:
            workflow_id: Optional filter by workflow ID

        Returns:
            List of pending approval requests
        """
        pending = []
        for wf_id, wf in workflows.items():
            if workflow_id and wf_id != workflow_id:
                continue
            if wf.get("approval_required"):
                pending.append(
                    ApprovalRequestResponse(
                        id=wf.get("approval_request_id", "unknown"),
                        workflow_id=wf_id,
                        node_name=wf.get("approval_node", "unknown"),
                        created_at=wf.get("approval_created_at", ""),
                        uncertainty_score=wf.get("uncertainty_score", 0.0),
                        uncertainty_reason=wf.get("uncertainty_reason", ""),
                        recommended_action=wf.get("recommended_action", "Review"),
                        alternative_actions=wf.get("alternative_actions", []),
                        context_data=wf.get("approval_context_data", {}),
                    )
                )
        return pending

    @app.post("/workflows/{workflow_id}/approve")
    async def approve_workflow(
        workflow_id: str,
        decision: ApprovalDecisionRequest,
    ) -> dict:
        """Approve a pending workflow.

        Args:
            workflow_id: Workflow ID
            decision: Approval decision

        Returns:
            Confirmation
        """
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        wf = workflows[workflow_id]
        if not wf.get("approval_required"):
            raise HTTPException(status_code=400, detail="Workflow not pending approval")

        # Record approval
        approval_id = wf.get("approval_request_id", "unknown")
        audit_logger.log_approval_response(
            workflow_id=workflow_id,
            approval_request_id=approval_id,
            decision=decision.decision,
            approved_by=decision.approved_by,
            reasoning=decision.reasoning,
        )

        # Update workflow
        wf["approval_required"] = False
        wf["approval_decision"] = decision.decision
        wf["status"] = "running"
        wf["updated_at"] = datetime.utcnow().isoformat()

        logger.info(f"Approved workflow {workflow_id} (decision: {decision.decision})")
        return {
            "workflow_id": workflow_id,
            "approval_decision": decision.decision,
            "message": "Workflow approved and resumed",
        }

    @app.post("/workflows/{workflow_id}/reject")
    async def reject_workflow(
        workflow_id: str,
        decision: ApprovalDecisionRequest,
    ) -> dict:
        """Reject a pending workflow and pause.

        Args:
            workflow_id: Workflow ID
            decision: Rejection details

        Returns:
            Confirmation
        """
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        wf = workflows[workflow_id]
        if not wf.get("approval_required"):
            raise HTTPException(status_code=400, detail="Workflow not pending approval")

        # Record rejection
        approval_id = wf.get("approval_request_id", "unknown")
        audit_logger.log_approval_response(
            workflow_id=workflow_id,
            approval_request_id=approval_id,
            decision="reject",
            approved_by=decision.approved_by,
            reasoning=decision.reasoning,
        )

        # Update workflow
        wf["approval_required"] = True  # Keep paused
        wf["approval_decision"] = "reject"
        wf["updated_at"] = datetime.utcnow().isoformat()

        logger.info(f"Rejected workflow {workflow_id}")
        return {
            "workflow_id": workflow_id,
            "approval_decision": "reject",
            "message": "Workflow rejected and remains paused",
        }

    # Audit trail endpoints

    @app.get("/workflows/{workflow_id}/audit")
    async def get_workflow_audit(workflow_id: str) -> list[AuditEntryResponse]:
        """Get complete audit trail for a workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            List of audit entries
        """
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        entries = audit_logger.get_workflow_trail(workflow_id)
        return [
            AuditEntryResponse(
                id=entry.id,
                workflow_id=entry.workflow_id,
                timestamp=entry.timestamp.isoformat(),
                node_name=entry.node_name,
                action_type=entry.action_type,
                actor=entry.actor,
                decision=entry.decision,
                reasoning=entry.reasoning,
                error_message=entry.error_message,
            )
            for entry in entries
        ]

    # WebSocket for real-time updates

    @app.websocket("/ws/workflows/{workflow_id}")
    async def websocket_workflow_updates(
        websocket: WebSocket,
        workflow_id: str,
    ):
        """WebSocket endpoint for workflow updates.

        Sends:
        - Workflow status changes
        - Approval requests
        - Audit entries

        Args:
            websocket: WebSocket connection
            workflow_id: Workflow ID to monitor
        """
        if workflow_id not in workflows:
            await websocket.close(code=4004, reason="Workflow not found")
            return

        await websocket.accept()
        logger.info(f"WebSocket connected for workflow {workflow_id}")

        try:
            while True:
                # Send current status
                wf = workflows.get(workflow_id)
                if wf:
                    message = {
                        "type": "workflow_update",
                        "workflow_id": workflow_id,
                        "status": wf["status"],
                        "is_pending_approval": wf.get("approval_required", False),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    await websocket.send_json(message)

                # TODO: Implement proper async event loop for real-time updates
                # For now, just send periodic updates
                import asyncio

                await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"WebSocket error for {workflow_id}: {e}")
        finally:
            logger.info(f"WebSocket disconnected for workflow {workflow_id}")

    return app


# Convenience function for running server

def run_hitl_server(
    approval_store: ApprovalStore,
    host: str = "127.0.0.1",
    port: int = 8001,
):
    """Run the HITL workflow server.

    Args:
        approval_store: Backend for storing approvals
        host: Server host
        port: Server port
    """
    import uvicorn

    app = create_hitl_server(approval_store)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    # Placeholder approval store for testing
    class MockApprovalStore(ApprovalStore):
        pass

    run_hitl_server(MockApprovalStore())
