"""
Comprehensive HITL Workflow Resumption Example

This example demonstrates:
1. Creating a real LangGraph workflow with HITL support
2. Saving checkpoints at human intervention points
3. Pausing for human review and approval
4. Resuming workflow from checkpoint after modifications
5. Handling multiple scenarios and what-if analysis
6. State modification and audit trails
"""

from datetime import datetime
from typing import Any, Dict
import json

try:
    from langgraph.graph import StateGraph
except ImportError:
    # Fallback mock for environments without langgraph installed
    StateGraph = None

from ..state_manager import (
    HITLStateManager,
    HITLWorkflowState,
    WorkflowStatus,
    RecoveryStrategy,
)
from ..checkpoint_restorer import CheckpointRestorer


# ============================================================================
# WORKFLOW STATE AND NODES
# ============================================================================

class SalesWorkflowState(dict):
    """
    State dictionary for a sales approval workflow.

    Represents state of a deal that needs human approval at various stages.
    """

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)

    def __setitem__(self, key: str, value: Any) -> None:
        return super().__setitem__(key, value)


def extract_deal_info(state: SalesWorkflowState) -> SalesWorkflowState:
    """Extract and validate deal information from initial input."""
    print("=" * 60)
    print("STEP 1: Extracting Deal Information")
    print("=" * 60)

    state["deal_id"] = state.get("deal_id", f"DEAL_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    state["deal_amount"] = state.get("deal_amount", 100000)
    state["customer_name"] = state.get("customer_name", "Acme Corp")
    state["customer_credit_score"] = state.get("customer_credit_score", 750)
    state["extraction_complete"] = True
    state["extracted_at"] = datetime.utcnow().isoformat()

    print(f"Deal ID: {state['deal_id']}")
    print(f"Customer: {state['customer_name']}")
    print(f"Amount: ${state['deal_amount']:,.2f}")
    print(f"Credit Score: {state['customer_credit_score']}")
    print()

    return state


def analyze_risk(state: SalesWorkflowState) -> SalesWorkflowState:
    """Analyze financial risk of the deal."""
    print("=" * 60)
    print("STEP 2: Analyzing Risk")
    print("=" * 60)

    # Calculate risk score based on amount and credit
    amount = state.get("deal_amount", 0)
    credit = state.get("customer_credit_score", 0)

    # Simple risk model
    risk_score = 1.0 - (credit / 1000.0) + (amount / 500000.0)
    risk_score = max(0, min(1, risk_score))  # Clamp 0-1

    state["risk_score"] = round(risk_score, 3)
    state["risk_level"] = "HIGH" if risk_score > 0.7 else "MEDIUM" if risk_score > 0.4 else "LOW"
    state["analysis_complete"] = True
    state["analyzed_at"] = datetime.utcnow().isoformat()

    print(f"Risk Score: {state['risk_score']}")
    print(f"Risk Level: {state['risk_level']}")
    print()

    return state


def prepare_recommendation(state: SalesWorkflowState) -> SalesWorkflowState:
    """Prepare recommendation for human review."""
    print("=" * 60)
    print("STEP 3: Preparing Recommendation")
    print("=" * 60)

    risk_level = state.get("risk_level", "UNKNOWN")
    amount = state.get("deal_amount", 0)

    # Auto-recommend based on risk and amount
    if risk_level == "LOW" or (risk_level == "MEDIUM" and amount < 50000):
        recommendation = "APPROVE"
    elif risk_level == "HIGH" or amount > 500000:
        recommendation = "REJECT"
    else:
        recommendation = "REVIEW"  # Requires human review

    state["recommendation"] = recommendation
    state["recommendation_reason"] = (
        f"Risk level is {risk_level} for ${amount:,.0f} deal"
    )
    state["recommendation_prepared"] = True
    state["recommended_at"] = datetime.utcnow().isoformat()

    print(f"Recommendation: {recommendation}")
    print(f"Reason: {state['recommendation_reason']}")
    print()

    return state


def wait_for_human_review(state: SalesWorkflowState) -> SalesWorkflowState:
    """
    Pause workflow for human review.

    This is where the workflow pauses to wait for human intervention.
    The state is checkpointed here.
    """
    print("=" * 60)
    print("STEP 4: Waiting for Human Review")
    print("=" * 60)

    state["review_pending"] = True
    state["review_requested_at"] = datetime.utcnow().isoformat()

    print(f"Deal {state.get('deal_id')} is ready for human review")
    print(f"Recommendation: {state.get('recommendation')}")
    print("Workflow PAUSED - waiting for human decision")
    print()

    return state


def execute_approval(state: SalesWorkflowState) -> SalesWorkflowState:
    """Execute the approved decision."""
    print("=" * 60)
    print("STEP 5: Executing Approval Decision")
    print("=" * 60)

    decision = state.get("human_decision", "UNDECIDED")
    print(f"Human Decision: {decision}")
    print(f"Reviewer: {state.get('reviewed_by', 'unknown')}")
    print(f"Review Comments: {state.get('review_comments', 'none')}")
    print()

    state["decision_executed"] = True
    state["decision_executed_at"] = datetime.utcnow().isoformat()

    if decision == "APPROVE":
        state["approval_status"] = "APPROVED"
        state["approved_amount"] = state.get("deal_amount", 0)
        print(f"Deal approved for ${state['approved_amount']:,.2f}")
    elif decision == "REJECT":
        state["approval_status"] = "REJECTED"
        print("Deal rejected")
    else:
        state["approval_status"] = "PENDING"
        print("Decision pending")

    print()
    return state


def finalize_deal(state: SalesWorkflowState) -> SalesWorkflowState:
    """Finalize the deal processing."""
    print("=" * 60)
    print("STEP 6: Finalizing Deal")
    print("=" * 60)

    state["finalized"] = True
    state["finalized_at"] = datetime.utcnow().isoformat()

    print(f"Deal {state.get('deal_id')} finalized")
    print(f"Final Status: {state.get('approval_status')}")
    print()

    return state


def create_sales_workflow_graph() -> StateGraph:
    """
    Create a LangGraph workflow for sales deal approval with HITL support.

    Returns:
        StateGraph: The compiled workflow graph.
    """
    if StateGraph is None:
        raise ImportError(
            "langgraph is required. Install with: pip install langgraph"
        )

    # Define state graph
    workflow = StateGraph(SalesWorkflowState)

    # Add nodes
    workflow.add_node("extract", extract_deal_info)
    workflow.add_node("analyze", analyze_risk)
    workflow.add_node("prepare", prepare_recommendation)
    workflow.add_node("review", wait_for_human_review)
    workflow.add_node("execute", execute_approval)
    workflow.add_node("finalize", finalize_deal)

    # Add edges
    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "analyze")
    workflow.add_edge("analyze", "prepare")
    workflow.add_edge("prepare", "review")
    workflow.add_edge("review", "execute")
    workflow.add_edge("execute", "finalize")

    return workflow


# ============================================================================
# EXAMPLE 1: Initial Execution with Checkpoint
# ============================================================================

def example_initial_execution():
    """Example 1: Run workflow and create checkpoint at review node."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Initial Execution with Checkpoint Creation")
    print("=" * 70)
    print()

    # Initialize managers
    state_manager = HITLStateManager()
    restorer = CheckpointRestorer(state_manager)

    # Create workflow graph
    try:
        graph = create_sales_workflow_graph().compile()
    except ImportError:
        print("langgraph not available - skipping workflow execution")
        return None

    # Initialize workflow
    workflow_id = "deal_initial_001"
    initial_state = SalesWorkflowState({
        "deal_id": "DEAL_20250101_001",
        "deal_amount": 150000,
        "customer_name": "TechStartup Inc",
        "customer_credit_score": 720,
    })

    # Create workflow state in manager
    workflow = HITLWorkflowState(
        workflow_id=workflow_id,
        status=WorkflowStatus.CREATED,
        current_node="extract",
        state_data=initial_state,
    )
    state_manager._workflows[workflow_id] = workflow

    # Execute workflow up to review node
    print("Starting workflow execution...")
    print()

    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        # Graph execution may not work without full langgraph setup
        result = initial_state
        result["extraction_complete"] = True
        result["analysis_complete"] = True
        result["recommendation_prepared"] = True
        result["review_pending"] = True

    # Update workflow status
    workflow.status = WorkflowStatus.RUNNING
    workflow.current_node = "review"
    workflow.state_data = result
    state_manager._workflows[workflow_id] = workflow

    # Create checkpoint at review node
    checkpoint = state_manager.create_checkpoint(
        workflow_id=workflow_id,
        node_name="review",
        state_snapshot=result.copy(),
        status=WorkflowStatus.PAUSED_FOR_HUMAN,
        metadata={
            "execution_stage": "awaiting_human_review",
            "risk_assessment": result.get("risk_level"),
        },
    )

    print(f"\nCheckpoint created: {checkpoint.checkpoint_id}")
    print(f"Workflow paused at node: {checkpoint.node_name}")
    print(f"Checkpoint status: {checkpoint.status.value}")
    print()

    return workflow_id, checkpoint.checkpoint_id, state_manager, restorer


# ============================================================================
# EXAMPLE 2: Human Review and State Modification
# ============================================================================

def example_human_review_and_modification(
    workflow_id: str,
    checkpoint_id: str,
    state_manager: HITLStateManager,
    restorer: CheckpointRestorer,
):
    """Example 2: Human reviews workflow and modifies state before resumption."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Human Review and State Modification")
    print("=" * 70)
    print()

    # Retrieve checkpoint for human review
    print(f"Retrieving checkpoint {checkpoint_id} for review...")

    try:
        state = restorer.restore_checkpoint_state(workflow_id, checkpoint_id)
        print("State snapshot retrieved successfully")
        print()
    except ValueError as e:
        print(f"Error restoring checkpoint: {e}")
        return

    # Display current state
    print("Current Deal State:")
    print("-" * 40)
    for key in ["deal_id", "deal_amount", "customer_name", "risk_score", "recommendation"]:
        if key in state:
            print(f"  {key}: {state[key]}")
    print()

    # Human review and decision
    print("Human Reviewer Analysis:")
    print("-" * 40)
    decision = "APPROVE"  # Simulating human decision
    comments = "Credit score is acceptable, deal meets our criteria"

    print(f"Decision: {decision}")
    print(f"Comments: {comments}")
    print()

    # Prepare state modifications
    modifications = {
        "human_decision": decision,
        "reviewed_by": "alice@company.com",
        "review_comments": comments,
        "review_confidence": 0.95,
        "reviewed_at": datetime.utcnow().isoformat(),
    }

    # Apply modifications and track them
    print("Applying state modifications...")
    modified_state, state_mods = restorer.restore_and_modify_state(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        modifications=modifications,
        applied_by="alice@company.com",
    )

    print(f"Applied {len(state_mods)} modifications:")
    for mod in state_mods:
        print(f"  - {mod.key}: {mod.old_value} -> {mod.new_value}")
    print()

    # Update workflow status
    print("Updating workflow status to HUMAN_APPROVED...")
    state_manager.update_workflow_status(
        workflow_id=workflow_id,
        status=WorkflowStatus.HUMAN_APPROVED,
        human_feedback=comments,
    )
    print()

    return modified_state


# ============================================================================
# EXAMPLE 3: Resume Workflow After Human Approval
# ============================================================================

def example_resume_workflow(
    workflow_id: str,
    checkpoint_id: str,
    state_manager: HITLStateManager,
):
    """Example 3: Resume workflow from checkpoint after human approval."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Resume Workflow After Human Approval")
    print("=" * 70)
    print()

    print("Resuming workflow from checkpoint...")
    print()

    # Create a simple mock graph for resumption
    class MockGraph:
        def invoke(self, state):
            # Simulate continuing workflow
            state["decision_executed"] = True
            state["approval_status"] = state.get("human_decision", "PENDING")
            state["finalized"] = True
            state["finalized_at"] = datetime.utcnow().isoformat()
            return state

    graph = MockGraph()

    try:
        result = state_manager.resume_from_checkpoint(
            workflow_id=workflow_id,
            checkpoint_id=checkpoint_id,
            graph=graph,
            state_modifications={
                "resumed_at": datetime.utcnow().isoformat(),
            },
        )

        print("Workflow resumed successfully!")
        print(f"Final Status: {result.get('approval_status')}")
        print(f"Deal Amount Approved: ${result.get('approved_amount', 0):,.2f}")
        print()
    except Exception as e:
        print(f"Error resuming workflow: {e}")


# ============================================================================
# EXAMPLE 4: Checkpoint Export and Analysis
# ============================================================================

def example_checkpoint_export_and_analysis(
    workflow_id: str,
    state_manager: HITLStateManager,
    restorer: CheckpointRestorer,
):
    """Example 4: Export and analyze checkpoints."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Checkpoint Export and Analysis")
    print("=" * 70)
    print()

    # Get workflow history
    try:
        history = state_manager.get_workflow_history(workflow_id)
    except ValueError:
        print(f"Workflow {workflow_id} not found")
        return

    print(f"Workflow History: {len(history)} checkpoints")
    print()

    # List checkpoint metadata
    print("Checkpoint Metadata:")
    print("-" * 60)
    for i, checkpoint in enumerate(history, 1):
        metadata = restorer.get_checkpoint_metadata(
            workflow_id=workflow_id,
            checkpoint_id=checkpoint.checkpoint_id,
        )

        print(f"\nCheckpoint {i}: {checkpoint.checkpoint_id}")
        print(f"  Node: {metadata['node_name']}")
        print(f"  Status: {metadata['status']}")
        print(f"  Timestamp: {metadata['timestamp']}")
        print(f"  State Keys: {', '.join(metadata['state_keys'][:5])}")
        print(f"  State Size: {metadata['state_size_bytes']} bytes")

    print()

    # Export latest checkpoint
    if history:
        latest = history[-1]
        print(f"Exporting latest checkpoint: {latest.checkpoint_id}")
        print("-" * 60)

        # Export as JSON
        json_export = restorer.export_checkpoint(
            workflow_id=workflow_id,
            checkpoint_id=latest.checkpoint_id,
            format="json",
        )

        print("JSON Export (first 300 chars):")
        print(json_export[:300] + "...")
        print()


# ============================================================================
# EXAMPLE 5: What-If Scenario Analysis
# ============================================================================

def example_what_if_scenarios(
    workflow_id: str,
    checkpoint_id: str,
    state_manager: HITLStateManager,
):
    """Example 5: Execute what-if scenarios from checkpoint."""
    print("\n" + "=" * 70)
    print("EXAMPLE 5: What-If Scenario Analysis")
    print("=" * 70)
    print()

    # Mock graph for scenario execution
    class MockGraph:
        def invoke(self, state):
            # Just return the modified state
            return state

    graph = MockGraph()

    # Define scenarios
    scenarios = [
        {
            "name": "conservative_threshold",
            "modifications": {"deal_amount": 75000},
            "description": "Lower deal amount",
        },
        {
            "name": "better_credit_score",
            "modifications": {"customer_credit_score": 800},
            "description": "Better customer credit",
        },
        {
            "name": "higher_risk_tolerance",
            "modifications": {"risk_threshold": 0.8},
            "description": "Higher acceptable risk",
        },
    ]

    results = {}

    for scenario in scenarios:
        print(f"Executing scenario: {scenario['name']}")
        print(f"Description: {scenario['description']}")

        try:
            result = state_manager.execute_what_if_scenario(
                workflow_id=workflow_id,
                checkpoint_id=checkpoint_id,
                graph=graph,
                scenario_name=scenario["name"],
                modifications=scenario["modifications"],
            )

            results[scenario["name"]] = result

            print(f"Status: {'SUCCESS' if result['success'] else 'FAILED'}")
            print(f"Execution Time: {result['execution_time']:.3f}s")

            if result['success']:
                final_decision = result.get("result", {}).get("approval_status", "UNKNOWN")
                print(f"Outcome: {final_decision}")
            print()

        except Exception as e:
            print(f"Error: {e}")
            print()


# ============================================================================
# EXAMPLE 6: Crash Recovery
# ============================================================================

def example_crash_recovery(state_manager: HITLStateManager):
    """Example 6: Detect and recover from simulated server crash."""
    print("\n" + "=" * 70)
    print("EXAMPLE 6: Server Crash Detection and Recovery")
    print("=" * 70)
    print()

    # Create a workflow with an old heartbeat (simulating crash)
    workflow_id = "deal_crashed_001"

    from datetime import timedelta

    workflow = HITLWorkflowState(
        workflow_id=workflow_id,
        status=WorkflowStatus.RUNNING,
        current_node="review",
        state_data={"deal_amount": 100000},
    )

    # Set old heartbeat to simulate crash
    workflow.last_heartbeat = datetime.utcnow() - timedelta(seconds=400)
    state_manager._workflows[workflow_id] = workflow

    # Create checkpoint for recovery
    state_manager.create_checkpoint(
        workflow_id=workflow_id,
        node_name="review",
        state_snapshot=workflow.state_data.copy(),
    )

    print(f"Simulated crash for workflow {workflow_id}")
    print(f"Last heartbeat: {workflow.last_heartbeat.isoformat()}")
    print()

    # Attempt recovery
    print("Attempting crash recovery with RESUME strategy...")
    recovery = state_manager.recover_from_crash(
        workflow_id=workflow_id,
        strategy=RecoveryStrategy.RESUME,
    )

    if recovery:
        print(f"Recovery ID: {recovery.recovery_id}")
        print(f"Success: {recovery.success}")
        print(f"Strategy: {recovery.strategy.value}")
        print(f"Checkpoint: {recovery.checkpoint_id}")
        print()
    else:
        print("No recovery needed")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Run all examples."""
    print("\n" * 2)
    print("=" * 70)
    print("LangGraph HITL State Manager - Comprehensive Examples")
    print("=" * 70)

    # Example 1: Initial execution
    result = example_initial_execution()
    if result is None:
        print("\nSkipping examples due to missing dependencies")
        return

    workflow_id, checkpoint_id, state_manager, restorer = result

    # Example 2: Human review
    example_human_review_and_modification(
        workflow_id, checkpoint_id, state_manager, restorer
    )

    # Example 3: Resume
    example_resume_workflow(workflow_id, checkpoint_id, state_manager)

    # Example 4: Export and analysis
    example_checkpoint_export_and_analysis(workflow_id, state_manager, restorer)

    # Example 5: What-if scenarios
    example_what_if_scenarios(workflow_id, checkpoint_id, state_manager)

    # Example 6: Crash recovery
    example_crash_recovery(state_manager)

    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
