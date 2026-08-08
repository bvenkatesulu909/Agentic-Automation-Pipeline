"""Example usage of the Multi-Agent Research System."""

import json
from pathlib import Path

from .models import ResearchTask
from .supervisor import ResearchSupervisor


def example_research_task():
    """Run an example research task."""
    # Create supervisor
    supervisor = ResearchSupervisor(
        model="claude-opus-5",
        max_iterations=2,
        confidence_threshold=0.7,
        enable_auto_approval=False,
    )

    # Define research task
    task = ResearchTask(
        query="What are the latest advances in prompt optimization for LLMs?",
        description="Research recent breakthroughs and practical applications",
        required_sources=[
            "Academic papers",
            "Industry reports",
            "Technical blogs",
        ],
        research_depth="medium",
        max_iterations=2,
    )

    print("=" * 80)
    print("MULTI-AGENT RESEARCH SYSTEM EXAMPLE")
    print("=" * 80)
    print(f"\nResearch Query: {task.query}")
    print(f"Task ID: {task.task_id}\n")

    # Execute research workflow
    final_state = supervisor.execute_research(task, require_approval=True)

    # Display results
    print("\n" + "=" * 80)
    print("RESEARCH RESULTS")
    print("=" * 80)

    print("\n[FINAL OUTPUT]")
    if final_state.writer_decision:
        print(final_state.writer_decision.content)

    print("\n[APPROVAL STATUS]")
    print(f"Status: {final_state.approval_status.value}")
    print(f"Final Iteration: {final_state.iteration}")
    print(f"Total Decisions: {len(final_state.all_decisions)}")

    # Export audit report
    print("\n" + "=" * 80)
    print("AUDIT TRAIL")
    print("=" * 80)

    audit_report = supervisor.get_audit_report(task.task_id)
    print(f"\nTotal Actions Logged: {audit_report['total_actions']}")
    print(f"Actions by Type:")
    for action_type, count in audit_report["actions_by_type"].items():
        print(f"  - {action_type}: {count}")

    compliance_summary = supervisor.get_compliance_summary(task.task_id)
    print(f"\nCompliance Summary:")
    print(f"  - Total Decisions: {compliance_summary['total_decisions']}")
    print(f"  - Approvals: {compliance_summary['total_approvals']}")
    print(f"  - Rejections: {compliance_summary['total_rejections']}")
    if compliance_summary["approvers"]:
        print(f"  - Approvers: {', '.join(compliance_summary['approvers'])}")

    # Save results to file
    output_dir = Path("research_output")
    output_dir.mkdir(exist_ok=True)

    results = {
        "task": task.to_dict(),
        "final_state": final_state.to_dict(),
        "audit_report": audit_report,
        "compliance_summary": compliance_summary,
    }

    output_file = output_dir / f"research_{task.task_id}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Results saved to {output_file}")

    return final_state


def example_batch_research():
    """Run multiple research tasks with different configurations."""
    supervisor = ResearchSupervisor(
        model="claude-opus-5",
        max_iterations=1,
        confidence_threshold=0.75,
    )

    tasks = [
        ResearchTask(
            query="How are enterprises using Claude for RAG systems?",
            research_depth="light",
            max_iterations=1,
        ),
        ResearchTask(
            query="What are the best practices for prompt caching?",
            research_depth="medium",
            max_iterations=2,
        ),
    ]

    results = []
    for i, task in enumerate(tasks, 1):
        print(f"\n{'=' * 80}")
        print(f"Task {i}/{len(tasks)}")
        print(f"{'=' * 80}")

        state = supervisor.execute_research(task, require_approval=False)
        results.append(
            {
                "task": task.to_dict(),
                "approval_status": state.approval_status.value,
                "consensus_score": (
                    state.supervisor_consensus.confidence
                    if state.supervisor_consensus
                    else 0.0
                ),
            }
        )

    print(f"\n{'=' * 80}")
    print("BATCH PROCESSING COMPLETE")
    print(f"{'=' * 80}")
    print(f"Tasks Processed: {len(results)}")

    for i, result in enumerate(results, 1):
        print(f"\nTask {i}: {result['task']['query'][:50]}...")
        print(
            f"  Status: {result['approval_status']}, "
            f"Consensus: {result['consensus_score']:.2%}"
        )

    return results


if __name__ == "__main__":
    # Run example
    example_research_task()
