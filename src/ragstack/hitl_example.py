"""Example: Human-in-the-loop workflow for Q&A with approval gates.

This example demonstrates:
1. Setting up uncertainty detection
2. Creating approval gates
3. Running a workflow with pause/resume
4. Querying audit trail
"""

from __future__ import annotations

import logging
from datetime import datetime

from .uncertainty import detector_for_qa_queries
from .approval import ApprovalPolicy, ApprovalGate, ApprovalRequest, ApprovalResponse, ApprovalDecision
from .workflow_state import HITLWorkflowState
from .audit import AuditLogger
from .db import SQLAlchemyApprovalStore
from .pdf_qa.models import RetrievalResult, QAResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_basic_uncertainty_detection():
    """Example 1: Basic uncertainty detection."""
    print("\n=== Example 1: Uncertainty Detection ===\n")

    detector = detector_for_qa_queries()

    # Simulate retrieval results
    class MockChunk:
        def __init__(self, score: float):
            self.final_score = score
            self.text = f"Sample chunk with score {score}"

    # Scenario 1: High confidence retrieval
    chunks_high_confidence = [
        MockChunk(0.95),
        MockChunk(0.92),
        MockChunk(0.88),
    ]

    uncertainty_high = detector.evaluate_retrieval(chunks_high_confidence)
    print(f"High confidence retrieval:")
    print(f"  Uncertainty: {uncertainty_high.score:.2f}")
    print(f"  Confidence: {uncertainty_high.confidence:.2f}")
    print(f"  Reason: {uncertainty_high.reason}")
    print(f"  Should gate: {detector.should_gate(uncertainty_high)}\n")

    # Scenario 2: Low confidence retrieval
    chunks_low_confidence = [
        MockChunk(0.35),
        MockChunk(0.25),
        MockChunk(0.15),
    ]

    uncertainty_low = detector.evaluate_retrieval(chunks_low_confidence)
    print(f"Low confidence retrieval:")
    print(f"  Uncertainty: {uncertainty_low.score:.2f}")
    print(f"  Confidence: {uncertainty_low.confidence:.2f}")
    print(f"  Reason: {uncertainty_low.reason}")
    print(f"  Should gate: {detector.should_gate(uncertainty_low)}\n")


def example_approval_workflow():
    """Example 2: Approval workflow with pause/resume."""
    print("\n=== Example 2: Approval Workflow ===\n")

    # Initialize components
    store = SQLAlchemyApprovalStore("sqlite:///example_hitl.db")
    detector = detector_for_qa_queries()
    gate = ApprovalGate(store, policy=ApprovalPolicy.AUTO_IF_UNCERTAIN)
    audit_logger = AuditLogger()

    # Create workflow state
    workflow_id = "workflow_001"
    state = {
        "query": "What is machine learning?",
        "retrieved_chunks": [],
    }

    hitl_state = HITLWorkflowState(
        workflow_id=workflow_id,
        base_state=state,
        user_id="user_123",
    )

    # Log workflow start
    audit_logger.log_workflow_start(
        workflow_id=workflow_id,
        user_id="user_123",
        query="What is machine learning?",
    )

    # Simulate retrieval with low confidence
    class MockChunk:
        def __init__(self, score: float):
            self.final_score = score
            self.text = f"Sample chunk"

    retrieved_chunks = [
        MockChunk(0.45),
        MockChunk(0.35),
        MockChunk(0.25),
    ]

    # Evaluate uncertainty
    uncertainty = detector.evaluate_retrieval(retrieved_chunks)

    print(f"Workflow: {workflow_id}")
    print(f"Query: {state['query']}")
    print(f"Uncertainty Score: {uncertainty.score:.2f}")
    print(f"Reason: {uncertainty.reason}\n")

    # Evaluate if approval needed
    if detector.should_gate(uncertainty):
        print("⚠️  Approval required due to high uncertainty\n")

        # Create approval request
        state_modified = gate.evaluate(
            workflow_id=workflow_id,
            node_name="retrieve",
            state=hitl_state.to_dict(),
            uncertainty_score=uncertainty.score,
            uncertainty_reason=uncertainty.reason,
            recommended_action="Review retrieved documents before generating answer",
            alternative_actions=[
                "Proceed with generation",
                "Fetch more documents",
            ],
        )

        hitl_state_modified = HITLWorkflowState.from_dict(state_modified)
        print(f"✋ Workflow paused at approval gate")
        print(f"Approval Request ID: {state_modified.get('approval_request_id')}")
        print(f"Awaiting approval since: {state_modified.get('approval_context', {}).get('awaiting_approval_since')}\n")

        # Simulate human approval
        print("👤 Human reviews and approves...\n")
        approval_id = state_modified.get("approval_request_id")

        response = ApprovalResponse(
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approved_by="reviewer_456",
            timestamp=datetime.utcnow(),
            reasoning="Documents look relevant, proceeding with generation",
        )

        store.save_approval_response(response)
        audit_logger.log_approval_response(
            workflow_id=workflow_id,
            approval_request_id=approval_id,
            decision="approve",
            approved_by="reviewer_456",
            reasoning="Documents look relevant, proceeding with generation",
        )

        # Resume workflow
        hitl_state_modified.resume_from_approval(
            approval_decision="approve",
            approved_by="reviewer_456",
            reasoning="Documents look relevant, proceeding with generation",
        )

        print(f"✅ Workflow resumed by human approval")
        print(f"Ready to continue with generation step\n")
    else:
        print("✅ Confidence sufficient, no approval needed")
        print("Proceeding directly to generation\n")


def example_audit_trail_query():
    """Example 3: Querying audit trail."""
    print("\n=== Example 3: Audit Trail ===\n")

    audit_logger = AuditLogger()

    # Log some workflow activities
    workflow_id = "workflow_002"

    audit_logger.log_workflow_start(
        workflow_id=workflow_id,
        user_id="user_789",
        query="How do I train a neural network?",
    )

    audit_logger.log_uncertainty_detection(
        workflow_id=workflow_id,
        node_name="retrieve",
        uncertainty_score=0.65,
        reason="Moderate confidence in retrieval results",
    )

    audit_logger.log_approval_request(
        workflow_id=workflow_id,
        approval_request_id="apr_001",
        uncertainty_score=0.65,
        reason="Moderate confidence in retrieval results",
        recommended_action="Review and approve",
    )

    audit_logger.log_approval_response(
        workflow_id=workflow_id,
        approval_request_id="apr_001",
        decision="approve",
        approved_by="reviewer_101",
        reasoning="Results look good",
    )

    audit_logger.log_workflow_resume(
        workflow_id=workflow_id,
        from_node="retrieve",
        resumed_by="system",
    )

    audit_logger.log_workflow_complete(workflow_id=workflow_id)

    # Query and display audit trail
    trail = audit_logger.get_workflow_trail(workflow_id)

    print(f"Audit Trail for {workflow_id}:\n")
    for i, entry in enumerate(trail, 1):
        print(f"{i}. [{entry.timestamp.strftime('%H:%M:%S')}] {entry.action_type.upper()}")
        print(f"   Node: {entry.node_name}")
        print(f"   Actor: {entry.actor}")
        if entry.decision:
            print(f"   Decision: {entry.decision}")
        if entry.reasoning:
            print(f"   Reasoning: {entry.reasoning}")
        print()


def example_hitl_state_management():
    """Example 4: HITL state management with checkpoints."""
    print("\n=== Example 4: State Management ===\n")

    workflow_id = "workflow_003"
    base_state = {
        "query": "What are transformers in machine learning?",
        "retrieved_chunks": [],
        "response": None,
    }

    # Create HITL state
    hitl_state = HITLWorkflowState(
        workflow_id=workflow_id,
        base_state=base_state,
        user_id="user_999",
    )

    print(f"Workflow: {workflow_id}")
    print(f"Initial state keys: {list(hitl_state.state.keys())}\n")

    # Add audit entry
    hitl_state.add_audit_entry(
        node_name="retrieve",
        action_type="execute",
        actor="system",
        metadata={"query_length": len(base_state["query"])},
    )

    # Create checkpoint
    checkpoint = hitl_state.checkpoint(
        node_name="retrieve",
        reason="After retrieval step",
    )

    print(f"✓ Created checkpoint {checkpoint.id}")
    print(f"  Node: {checkpoint.node_name}")
    print(f"  Reason: {checkpoint.reason}")
    print(f"  State snapshot size: {len(checkpoint.state)} keys\n")

    # Set approval pending
    hitl_state.set_approval_pending(
        approval_request_id="apr_003",
        uncertainty_score=0.75,
        reason="High uncertainty in response",
        recommended_action="Review answer",
        alternatives=["Reject and retry", "Accept as-is"],
    )

    print(f"✓ Marked as pending approval")
    print(f"  Approval context: {hitl_state['approval_context']}\n")

    # Resume from approval
    hitl_state.resume_from_approval(
        approval_decision="approve",
        approved_by="reviewer_xyz",
        reasoning="Answer is accurate",
    )

    print(f"✓ Resumed after approval\n")

    # Display audit trail
    print(f"Audit trail ({len(hitl_state.audit_trail)} entries):")
    for entry in hitl_state.audit_trail:
        print(f"  - {entry.action_type} by {entry.actor} at {entry.node_name}")


if __name__ == "__main__":
    print("""
╔═════════════════════════════════════════════════╗
║  HITL Workflow Examples                         ║
║  Human-in-the-Loop Approval System              ║
╚═════════════════════════════════════════════════╝
    """)

    # Run examples
    example_basic_uncertainty_detection()
    example_approval_workflow()
    example_audit_trail_query()
    example_hitl_state_management()

    print("\n✅ All examples completed!")
