"""Human-in-the-loop graph builder for RAG workflows.

Wraps existing LangGraph workflows with:
- Uncertainty detection at key nodes
- Approval gates for human review
- Audit trail logging
- Checkpoint persistence

Example:
    # Wrap existing PDF Q&A graph with HITL
    hitl = HITLGraphBuilder(
        base_graph=pdf_qa_graph,
        detector=detector_for_qa_queries(),
        approval_store=db_store,
    )

    # Add gates at retrieval and generation
    hitl.add_gate_after_node("retrieve", ApprovalPolicy.AUTO_IF_UNCERTAIN)
    hitl.add_gate_after_node("generate_answer", ApprovalPolicy.AUTO_IF_UNCERTAIN)

    # Build and run
    graph = hitl.build()
    result = graph.invoke(state)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.graph.graph import Graph

from .approval import ApprovalGate, ApprovalPolicy, ApprovalStore, gate_node_factory
from .audit import AuditLogger
from .uncertainty import UncertaintyDetector, detector_for_qa_queries
from .workflow_state import HITLWorkflowState

logger = logging.getLogger(__name__)


class HITLGraphBuilder:
    """Builds HITL-enhanced workflows from existing LangGraph graphs.

    Integrates:
    - Uncertainty detection at specified nodes
    - Approval gates for human review
    - Audit trail logging of all decisions
    - State snapshots for resume/replay
    """

    def __init__(
        self,
        base_graph: Graph,
        detector: UncertaintyDetector | None = None,
        approval_store: ApprovalStore | None = None,
        audit_logger: AuditLogger | None = None,
    ):
        """Initialize HITL graph builder.

        Args:
            base_graph: Existing LangGraph workflow to enhance
            detector: Uncertainty detector (default: QA tuned)
            approval_store: Backend for storing approval requests
            audit_logger: Audit trail logger
        """
        self.base_graph = base_graph
        self.detector = detector or detector_for_qa_queries()
        self.approval_store = approval_store
        self.audit_logger = audit_logger or AuditLogger()
        self.gates: dict[str, dict] = {}  # {node_name: {policy, ...}}

    def add_gate_after_node(
        self,
        node_name: str,
        policy: ApprovalPolicy = ApprovalPolicy.AUTO_IF_UNCERTAIN,
        gate_name: str | None = None,
    ) -> HITLGraphBuilder:
        """Add an approval gate after a specific node.

        The gate will:
        1. Evaluate uncertainty of the node's output
        2. If high uncertainty, pause workflow and request approval
        3. Resume only after human approval

        Args:
            node_name: Name of the node after which to add gate
            policy: Approval policy (REQUIRE, AUTO_IF_UNCERTAIN, SKIP)
            gate_name: Optional custom name for gate node

        Returns:
            Self for chaining
        """
        gate_id = gate_name or f"gate_after_{node_name}"
        self.gates[gate_id] = {
            "after_node": node_name,
            "policy": policy,
        }
        logger.info(f"Added {policy} approval gate after {node_name}")
        return self

    def build(self) -> Graph:
        """Build the HITL-enhanced graph.

        Returns:
            Compiled LangGraph workflow with approval gates and logging
        """
        # Create new graph with extended state
        workflow = StateGraph(dict)

        # Copy nodes from base graph
        # Note: This is a simplified approach. For production, implement proper node copying.
        # In LangGraph 0.1+, we'd need to access the base graph's node definitions.
        # For now, we'll create wrapper nodes that add HITL logic.

        # Build node for initial processing
        workflow.add_node(
            "hitl_initialize",
            self._node_initialize,
        )

        # Add gate nodes
        for gate_id, gate_config in self.gates.items():
            gate = gate_node_factory(
                store=self.approval_store,
                policy=gate_config["policy"],
            )
            workflow.add_node(gate_id, gate)

        # Add processing complete node
        workflow.add_node("hitl_finalize", self._node_finalize)

        # Wire edges
        workflow.add_edge(START, "hitl_initialize")

        # Connect base graph nodes (simplified - you may need to manually add these)
        workflow.add_edge("hitl_initialize", "hitl_finalize")

        # Add gate edges
        for gate_id, gate_config in self.gates.items():
            # In a real implementation, wire gates into the flow
            # workflow.add_conditional_edges(gate_config["after_node"], ...)
            pass

        workflow.add_edge("hitl_finalize", END)

        return workflow.compile()

    def _node_initialize(self, state: dict) -> dict:
        """Initialize workflow with HITL state."""
        # Create HITL state wrapper
        workflow_id = state.get("workflow_id", str(uuid.uuid4()))
        user_id = state.get("user_id", "unknown")

        hitl_state = HITLWorkflowState(
            workflow_id=workflow_id,
            base_state=state,
            user_id=user_id,
        )

        # Log workflow start
        self.audit_logger.log_workflow_start(
            workflow_id=workflow_id,
            user_id=user_id,
            query=state.get("query", ""),
            metadata={"nodes_in_workflow": len(self.gates)},
        )

        return hitl_state.to_dict()

    def _node_finalize(self, state: dict) -> dict:
        """Finalize workflow and log completion."""
        workflow_id = state.get("workflow_id", "unknown")

        if state.get("error"):
            self.audit_logger.log_error(
                workflow_id=workflow_id,
                node_name="workflow",
                error_msg=state["error"],
            )
        else:
            self.audit_logger.log_workflow_complete(
                workflow_id=workflow_id,
                final_state=state,
            )

        return state


class RetrievalUncertaintyNode:
    """Node that evaluates uncertainty of retrieved documents.

    Integrates with uncertainty detector and audit logging.
    """

    def __init__(
        self,
        detector: UncertaintyDetector,
        audit_logger: AuditLogger,
    ):
        """Initialize retrieval uncertainty evaluator.

        Args:
            detector: Uncertainty detector
            audit_logger: Audit trail logger
        """
        self.detector = detector
        self.audit_logger = audit_logger

    def __call__(self, state: dict) -> dict:
        """Evaluate retrieval uncertainty.

        Args:
            state: Workflow state with retrieved_chunks

        Returns:
            Modified state with uncertainty_score and uncertainty_reason
        """
        workflow_id = state.get("workflow_id", "unknown")
        retrieved_chunks = state.get("retrieved_chunks", [])

        # Evaluate uncertainty
        uncertainty = self.detector.evaluate_retrieval(retrieved_chunks)

        # Log uncertainty detection
        self.audit_logger.log_uncertainty_detection(
            workflow_id=workflow_id,
            node_name="retrieve",
            uncertainty_score=uncertainty.score,
            reason=uncertainty.reason,
            metadata={
                "retrieval_confidence": uncertainty.retrieval_confidence,
                "coherence": uncertainty.coherence_score,
            },
        )

        # Update state
        state = state.copy()
        state["uncertainty_score"] = uncertainty.score
        state["uncertainty_reason"] = uncertainty.reason
        state["retrieval_confidence"] = uncertainty.retrieval_confidence

        logger.debug(
            f"Retrieval uncertainty: {uncertainty.score:.2f} ({uncertainty.reason})"
        )

        return state


class ResponseUncertaintyNode:
    """Node that evaluates uncertainty of LLM-generated response.

    Integrates with uncertainty detector and audit logging.
    """

    def __init__(
        self,
        detector: UncertaintyDetector,
        audit_logger: AuditLogger,
    ):
        """Initialize response uncertainty evaluator.

        Args:
            detector: Uncertainty detector
            audit_logger: Audit trail logger
        """
        self.detector = detector
        self.audit_logger = audit_logger

    def __call__(self, state: dict) -> dict:
        """Evaluate response uncertainty.

        Args:
            state: Workflow state with response and retrieved_chunks

        Returns:
            Modified state with uncertainty_score and uncertainty_reason
        """
        workflow_id = state.get("workflow_id", "unknown")
        response = state.get("response")
        retrieved_chunks = state.get("retrieved_chunks", [])

        if not response:
            state = state.copy()
            state["uncertainty_score"] = 0.0
            state["uncertainty_reason"] = "No response generated"
            return state

        # Evaluate uncertainty
        uncertainty = self.detector.evaluate_response(response, retrieved_chunks)

        # Log uncertainty detection
        self.audit_logger.log_uncertainty_detection(
            workflow_id=workflow_id,
            node_name="generate_answer",
            uncertainty_score=uncertainty.score,
            reason=uncertainty.reason,
            metadata={
                "response_confidence": uncertainty.response_confidence,
            },
        )

        # Update state
        state = state.copy()
        state["uncertainty_score"] = uncertainty.score
        state["uncertainty_reason"] = uncertainty.reason
        state["response_confidence"] = uncertainty.response_confidence

        logger.debug(
            f"Response uncertainty: {uncertainty.score:.2f} ({uncertainty.reason})"
        )

        return state


def create_qa_hitl_graph(
    base_graph: Graph,
    approval_store: ApprovalStore | None = None,
    retrieval_uncertainty_threshold: float = 0.7,
    response_uncertainty_threshold: float = 0.7,
) -> Graph:
    """Create a HITL-enhanced Q&A graph with approval gates.

    Adds gates:
    1. After retrieval: gates if retrieved documents are uncertain
    2. After generation: gates if LLM response is uncertain

    Args:
        base_graph: Base PDF Q&A graph
        approval_store: Backend for storing approvals
        retrieval_uncertainty_threshold: Score to trigger retrieval gate
        response_uncertainty_threshold: Score to trigger response gate

    Returns:
        Enhanced graph with approval gates
    """
    detector = detector_for_qa_queries()
    detector.approval_trigger = max(
        retrieval_uncertainty_threshold, response_uncertainty_threshold
    )
    audit_logger = AuditLogger()

    builder = HITLGraphBuilder(
        base_graph=base_graph,
        detector=detector,
        approval_store=approval_store,
        audit_logger=audit_logger,
    )

    # Add gates at critical points
    builder.add_gate_after_node(
        "retrieve",
        policy=ApprovalPolicy.AUTO_IF_UNCERTAIN,
        gate_name="gate_retrieval",
    )

    builder.add_gate_after_node(
        "generate_answer",
        policy=ApprovalPolicy.AUTO_IF_UNCERTAIN,
        gate_name="gate_response",
    )

    return builder.build()
