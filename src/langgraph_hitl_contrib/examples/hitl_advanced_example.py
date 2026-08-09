"""
Advanced LangGraph HITL Workflow Examples

Demonstrates advanced features including:
1. Server crash recovery with automatic detection
2. State mutation and modification before resumption
3. Workflow replay capabilities
4. What-if scenario execution
5. Comprehensive audit trail tracking
6. State validation and deserialization
7. Checkpoint comparison and analysis

This example shows production-grade HITL workflow patterns.
"""

from datetime import datetime, timedelta
from typing import Any, Dict
import time

from langgraph.graph import StateGraph

from ..state_manager import (
    HITLStateManager,
    HITLWorkflowState,
    WorkflowStatus,
    RecoveryStrategy,
)
from ..checkpoint_restorer import CheckpointRestorer


# Example workflow state
class WorkflowStateDict(dict):
    """Example workflow state as a dictionary."""
    pass


def analyze_input_node(state: WorkflowStateDict) -> WorkflowStateDict:
    """Analyze input data."""
    print("  [Node] Analyzing input...")
    state['input_analyzed'] = True
    state['analysis_score'] = 0.75
    return state


def validate_input_node(state: WorkflowStateDict) -> WorkflowStateDict:
    """Validate analysis results."""
    print("  [Node] Validating input...")
    state['validation_passed'] = True
    return state


def decision_node(state: WorkflowStateDict) -> WorkflowStateDict:
    """Decision point - pauses for human review."""
    print("  [Node] Waiting for human decision...")
    state['awaiting_decision'] = True
    return state


def execute_node(state: WorkflowStateDict) -> WorkflowStateDict:
    """Execute approved decision."""
    print("  [Node] Executing approved decision...")
    state['execution_complete'] = True
    state['execution_time'] = datetime.utcnow().isoformat()
    return state


def finalize_node(state: WorkflowStateDict) -> WorkflowStateDict:
    """Finalize workflow."""
    print("  [Node] Finalizing workflow...")
    state['finalized'] = True
    return state


def create_workflow_graph() -> StateGraph:
    """Create a LangGraph workflow with HITL support."""
    workflow = StateGraph(WorkflowStateDict)

    workflow.add_node("analyze", analyze_input_node)
    workflow.add_node("validate", validate_input_node)
    workflow.add_node("decision", decision_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("finalize", finalize_node)

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "validate")
    workflow.add_edge("validate", "decision")
    workflow.add_edge("decision", "execute")
    workflow.add_edge("execute", "finalize")

    return workflow


def create_execution_hook():
    """Create an execution hook for logging events."""
    def hook(event_type: str, event_data: Dict[str, Any]):
        timestamp = datetime.utcnow().isoformat()
        print(f"  [Hook] {timestamp} - {event_type}: {event_data}")
    return hook


# ============================================================================
# EXAMPLE 1: Initial Execution with Checkpoint
# ============================================================================

def example1_initial_execution():
    """Example 1: Run workflow and create checkpoint at decision node."""
    print("\n" + "="*70)
    print("EXAMPLE 1: Initial Execution with Checkpoint")
    print("="*70)

    state_manager = HITLStateManager()
    restorer = CheckpointRestorer(state_manager)

    workflow_id = "workflow_crash_recovery_demo"
    initial_state = WorkflowStateDict(
        input="Process this critical data",
        input_type="transaction",
        priority="high"
    )

    print("\nExecuting initial workflow...")
    workflow_graph = create_workflow_graph()
    result = workflow_graph.invoke(initial_state)

    print("\nCreating checkpoint at decision node...")
    checkpoint = state_manager.create_checkpoint(
        workflow_id=workflow_id,
        node_name="decision",
        state_snapshot=dict(result),
        status=WorkflowStatus.PAUSED_FOR_HUMAN,
        metadata={
            "execution_id": "exec_001",
            "user_email": "reviewer@example.com",
        },
    )

    print(f"Checkpoint created: {checkpoint.checkpoint_id}")
    print(f"Workflow paused at node: {checkpoint.node_name}")
    print(f"State hash: {checkpoint.state_hash}")

    return workflow_id, checkpoint.checkpoint_id, state_manager, restorer


# ============================================================================
# EXAMPLE 2: Server Crash Recovery
# ============================================================================

def example2_crash_recovery(workflow_id: str, checkpoint_id: str, state_manager,
                            restorer):
    """Example 2: Detect and recover from server crash."""
    print("\n" + "="*70)
    print("EXAMPLE 2: Server Crash Recovery")
    print("="*70)

    # Simulate server crash by setting old heartbeat
    print("\nSimulating server crash (no heartbeat for 6 minutes)...")
    workflow = state_manager.restore_workflow(workflow_id)
    workflow.last_heartbeat = datetime.utcnow() - timedelta(minutes=6)
    state_manager._workflows[workflow_id] = workflow

    print("Detecting crash...")
    recovery_record = state_manager.recover_from_crash(
        workflow_id=workflow_id,
        strategy=RecoveryStrategy.RESUME,
        execution_hook=create_execution_hook(),
    )

    if recovery_record:
        print(f"\nCrash Recovery Details:")
        print(f"  Recovery ID: {recovery_record.recovery_id}")
        print(f"  Strategy: {recovery_record.strategy.value}")
        print(f"  Success: {recovery_record.success}")
        print(f"  Checkpoint: {recovery_record.checkpoint_id}")
    else:
        print("No recovery needed")


# ============================================================================
# EXAMPLE 3: State Modification Before Resumption
# ============================================================================

def example3_state_mutation(workflow_id: str, checkpoint_id: str, state_manager,
                             restorer):
    """Example 3: Modify state before resumption."""
    print("\n" + "="*70)
    print("EXAMPLE 3: State Modification Before Resumption")
    print("="*70)

    print("\nSimulating human review and modification...")
    print("Reviewer: 'I'll approve, but with adjusted confidence score'")

    # Restore and modify state
    print("\nModifying state...")
    modified_state, modifications = restorer.restore_and_modify_state(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        modifications={
            'awaiting_decision': False,
            'human_approved': True,
            'analysis_score': 0.95,  # Upgraded confidence
            'reviewer_notes': 'Approved with adjustments',
        },
        applied_by="user:alice@example.com"
    )

    print(f"\nModifications applied: {len(modifications)}")
    for mod in modifications:
        print(f"  {mod.key}: {mod.old_value} -> {mod.new_value}")
        print(f"    Applied by: {mod.applied_by}")

    # Resume with modifications
    print("\nResuming workflow with modified state...")
    workflow_graph = create_workflow_graph()
    result = restorer.resume_workflow(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        graph=workflow_graph,
        execution_hook=create_execution_hook(),
    )

    print(f"Workflow resumed successfully")
    print(f"Result keys: {list(result.keys())}")


# ============================================================================
# EXAMPLE 4: Workflow Replay
# ============================================================================

def example4_workflow_replay(workflow_id: str, checkpoint_id: str, state_manager,
                             restorer):
    """Example 4: Replay workflow for testing/auditing."""
    print("\n" + "="*70)
    print("EXAMPLE 4: Workflow Replay")
    print("="*70)

    print("\nReplaying workflow for audit purposes...")
    workflow_graph = create_workflow_graph()

    result = state_manager.replay_workflow(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        graph=workflow_graph,
        execution_hook=create_execution_hook(),
    )

    print(f"Replay completed")
    print(f"Is replay flag: {result.get('_is_replay', False)}")


# ============================================================================
# EXAMPLE 5: What-If Scenarios
# ============================================================================

def example5_whatif_scenarios(workflow_id: str, checkpoint_id: str, state_manager,
                               restorer):
    """Example 5: Test alternative execution paths."""
    print("\n" + "="*70)
    print("EXAMPLE 5: What-If Scenario Analysis")
    print("="*70)

    workflow_graph = create_workflow_graph()

    # Scenario 1: Conservative approach
    print("\nScenario 1: Conservative approval (high confidence threshold)...")
    scenario1 = state_manager.execute_what_if_scenario(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        graph=workflow_graph,
        scenario_name="conservative_approach",
        modifications={
            'analysis_score': 0.99,
            'approval_level': 'high',
        },
        execution_hook=create_execution_hook(),
    )
    print(f"  Success: {scenario1['success']}")
    print(f"  Execution time: {scenario1['execution_time']:.3f}s")

    # Scenario 2: Aggressive approach
    print("\nScenario 2: Aggressive approval (low confidence threshold)...")
    scenario2 = state_manager.execute_what_if_scenario(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        graph=workflow_graph,
        scenario_name="aggressive_approach",
        modifications={
            'analysis_score': 0.55,
            'approval_level': 'low',
        },
        execution_hook=create_execution_hook(),
    )
    print(f"  Success: {scenario2['success']}")
    print(f"  Execution time: {scenario2['execution_time']:.3f}s")

    # Scenario 3: Alternative path
    print("\nScenario 3: Alternative decision path...")
    scenario3 = state_manager.execute_what_if_scenario(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        graph=workflow_graph,
        scenario_name="alternative_path",
        modifications={
            'decision_override': 'manual_review',
            'escalate_to_manager': True,
        },
        execution_hook=create_execution_hook(),
    )
    print(f"  Success: {scenario3['success']}")
    print(f"  Execution time: {scenario3['execution_time']:.3f}s")


# ============================================================================
# EXAMPLE 6: Checkpoint Comparison and Analysis
# ============================================================================

def example6_checkpoint_analysis(workflow_id: str, checkpoint_id: str, state_manager,
                                  restorer):
    """Example 6: Compare and analyze checkpoints."""
    print("\n" + "="*70)
    print("EXAMPLE 6: Checkpoint Comparison & Analysis")
    print("="*70)

    history = state_manager.get_workflow_history(workflow_id)

    if len(history) >= 2:
        cp1 = history[0]
        cp2 = history[-1]

        print(f"\nComparing first and last checkpoint...")
        print(f"Checkpoint 1: {cp1.checkpoint_id} (node: {cp1.node_name})")
        print(f"Checkpoint 2: {cp2.checkpoint_id} (node: {cp2.node_name})")

        comparison = restorer.compare_checkpoints(cp1, cp2)

        print(f"\nComparison Results:")
        print(f"  Time elapsed: {comparison['time_difference']:.1f} seconds")
        print(f"  Status changed: {comparison['status_changed']}")
        print(f"  Node changed: {comparison['node_changed']}")
        print(f"  Keys added: {comparison['state_keys_added']}")
        print(f"  Keys removed: {comparison['state_keys_removed']}")
        print(f"  Total state changes: {comparison['total_changes']}")

        # Print diff summary
        print(f"\nDifference Summary:")
        summary = restorer.get_state_diff_summary(cp1, cp2)
        print(summary)


# ============================================================================
# EXAMPLE 7: State Serialization & Deserialization
# ============================================================================

def example7_state_serialization(workflow_id: str, checkpoint_id: str, state_manager,
                                  restorer):
    """Example 7: Serialize and deserialize state."""
    print("\n" + "="*70)
    print("EXAMPLE 7: State Serialization & Deserialization")
    print("="*70)

    # Export checkpoint
    print("\nExporting checkpoint to JSON...")
    json_export = restorer.export_checkpoint(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        format="json"
    )
    print(f"Exported {len(json_export)} bytes of JSON")

    # Export as text
    print("\nExporting checkpoint as text...")
    text_export = restorer.export_checkpoint(
        workflow_id=workflow_id,
        checkpoint_id=checkpoint_id,
        format="text"
    )
    print("Text export:")
    print(text_export[:500] + "..." if len(text_export) > 500 else text_export)

    # Get metadata only
    print("\nFetching checkpoint metadata...")
    metadata = restorer.get_checkpoint_metadata(workflow_id, checkpoint_id)
    print(f"Checkpoint metadata:")
    for key, value in metadata.items():
        if key != 'metadata':
            print(f"  {key}: {value}")


# ============================================================================
# EXAMPLE 8: Audit Trail and Recovery Records
# ============================================================================

def example8_audit_trail(workflow_id: str, state_manager, restorer):
    """Example 8: View audit trail and recovery history."""
    print("\n" + "="*70)
    print("EXAMPLE 8: Audit Trail & Recovery History")
    print("="*70)

    workflow = state_manager.restore_workflow(workflow_id)

    # Display state modifications
    if workflow.state_modifications:
        print(f"\nState Modifications: {len(workflow.state_modifications)}")
        for i, mod in enumerate(workflow.state_modifications, 1):
            print(f"  {i}. {mod.key}: {mod.old_value} -> {mod.new_value}")
            print(f"     Applied by: {mod.applied_by}")
            print(f"     Reason: {mod.reason}")

    # Display recovery records
    if workflow.recovery_records:
        print(f"\nRecovery Records: {len(workflow.recovery_records)}")
        for i, record in enumerate(workflow.recovery_records, 1):
            print(f"  {i}. Recovery ID: {record.recovery_id}")
            print(f"     Strategy: {record.strategy.value}")
            print(f"     Success: {record.success}")
            if record.error_message:
                print(f"     Error: {record.error_message}")

    # Display checkpoint history
    history = state_manager.get_workflow_history(workflow_id)
    print(f"\nCheckpoint History: {len(history)} checkpoints")
    for i, cp in enumerate(history, 1):
        print(f"  {i}. {cp.checkpoint_id}")
        print(f"     Node: {cp.node_name}, Status: {cp.status.value}")
        print(f"     Time: {cp.timestamp.isoformat()}")


# ============================================================================
# EXAMPLE 9: Production Heartbeat Pattern
# ============================================================================

def example9_heartbeat_monitoring(workflow_id: str, state_manager):
    """Example 9: Implement production heartbeat monitoring."""
    print("\n" + "="*70)
    print("EXAMPLE 9: Heartbeat Monitoring for Crash Detection")
    print("="*70)

    print("\nSimulating active workflow execution with heartbeats...")

    # Simulate workflow execution with periodic heartbeats
    for i in range(3):
        print(f"\n  [Iteration {i+1}] Processing...")
        time.sleep(0.5)

        print(f"  [Iteration {i+1}] Sending heartbeat...")
        state_manager.update_heartbeat(workflow_id)

    # Check current status
    workflow = state_manager.restore_workflow(workflow_id)
    if workflow.last_heartbeat:
        age = (datetime.utcnow() - workflow.last_heartbeat).total_seconds()
        print(f"\nCurrent heartbeat age: {age:.1f} seconds")
        print(f"Workflow status: {workflow.status.value}")


# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Run all advanced examples."""
    print("\n" + "="*70)
    print("LangGraph HITL Advanced Workflow Examples")
    print("Demonstrating Production-Grade HITL Patterns")
    print("="*70)

    # Run examples in sequence
    workflow_id, checkpoint_id, state_manager, restorer = example1_initial_execution()

    example2_crash_recovery(workflow_id, checkpoint_id, state_manager, restorer)
    example3_state_mutation(workflow_id, checkpoint_id, state_manager, restorer)
    example4_workflow_replay(workflow_id, checkpoint_id, state_manager, restorer)
    example5_whatif_scenarios(workflow_id, checkpoint_id, state_manager, restorer)
    example6_checkpoint_analysis(workflow_id, checkpoint_id, state_manager, restorer)
    example7_state_serialization(workflow_id, checkpoint_id, state_manager, restorer)
    example8_audit_trail(workflow_id, state_manager, restorer)
    example9_heartbeat_monitoring(workflow_id, state_manager)

    print("\n" + "="*70)
    print("All examples completed successfully!")
    print("="*70)


if __name__ == "__main__":
    main()
