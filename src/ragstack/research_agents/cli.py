"""Command-line interface for the research agents system."""

import argparse
import json
import sys
from pathlib import Path

from .models import ResearchTask
from .supervisor import ResearchSupervisor


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Research System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple research task
  research-agents "What is prompt caching?" --depth medium

  # With output file
  research-agents "Latest AI trends" --output results.json --no-approval

  # Batch processing
  research-agents --batch tasks.json

  # Get audit report
  research-agents --audit task-abc123 --output audit.json
        """,
    )

    # Task input options
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "query",
        nargs="?",
        help="Research query (if not using --batch or --audit)",
    )
    input_group.add_argument(
        "--batch",
        type=Path,
        help="Path to JSON file with multiple tasks",
    )
    input_group.add_argument(
        "--audit",
        type=str,
        help="Get audit report for task ID",
    )

    # Task configuration
    parser.add_argument(
        "--depth",
        choices=["light", "medium", "deep"],
        default="medium",
        help="Research depth (default: medium)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=2,
        help="Maximum refinement iterations (default: 2)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.7,
        help="Confidence threshold for consensus (default: 0.7)",
    )

    # Workflow options
    parser.add_argument(
        "--model",
        default="claude-opus-5",
        help="Claude model to use (default: claude-opus-5)",
    )
    parser.add_argument(
        "--no-approval",
        action="store_true",
        help="Skip approval workflow",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Enable auto-approval for high-confidence outputs",
    )

    # Output options
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file for results (JSON format)",
    )
    parser.add_argument(
        "--compliance",
        action="store_true",
        help="Include compliance summary in output",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.query and not args.batch and not args.audit:
        parser.print_help()
        sys.exit(1)

    try:
        if args.audit:
            handle_audit_request(args)
        elif args.batch:
            handle_batch_processing(args)
        else:
            handle_single_task(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_single_task(args):
    """Handle a single research task."""
    print(f"\n{'='*80}")
    print("MULTI-AGENT RESEARCH SYSTEM")
    print(f"{'='*80}\n")

    # Create supervisor
    supervisor = ResearchSupervisor(
        model=args.model,
        max_iterations=args.iterations,
        confidence_threshold=args.confidence,
        enable_auto_approval=args.auto_approve,
    )

    # Create task
    task = ResearchTask(
        query=args.query,
        research_depth=args.depth,
        max_iterations=args.iterations,
    )

    if args.verbose:
        print(f"Query: {task.query}")
        print(f"Task ID: {task.task_id}")
        print(f"Depth: {args.depth}")
        print(f"Max Iterations: {args.iterations}\n")

    # Execute research
    state = supervisor.execute_research(task, require_approval=not args.no_approval)

    # Display results
    print(f"\n{'='*80}")
    print("RESULTS")
    print(f"{'='*80}\n")

    if state.writer_decision:
        print("RESEARCH OUTPUT:")
        print("-" * 80)
        print(state.writer_decision.content)
        print()

    print("METRICS:")
    print("-" * 80)
    print(f"Approval Status: {state.approval_status.value}")
    print(f"Iterations: {state.iteration + 1}")
    if state.supervisor_consensus:
        print(f"Consensus Score: {state.supervisor_consensus.confidence:.2%}")

    # Prepare output
    results = {
        "task_id": task.task_id,
        "query": task.query,
        "status": state.approval_status.value,
        "output": state.writer_decision.content if state.writer_decision else None,
        "metrics": {
            "consensus_score": (
                state.supervisor_consensus.confidence
                if state.supervisor_consensus
                else None
            ),
            "iterations": state.iteration + 1,
            "total_decisions": len(state.all_decisions),
        },
    }

    if args.compliance:
        results["compliance"] = supervisor.get_compliance_summary(task.task_id)

    # Save results if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Results saved to {args.output}")


def handle_batch_processing(args):
    """Handle batch processing of multiple tasks."""
    # Load tasks from file
    with open(args.batch, "r") as f:
        batch_data = json.load(f)

    tasks_data = batch_data if isinstance(batch_data, list) else batch_data.get("tasks", [])

    print(f"\n{'='*80}")
    print(f"BATCH PROCESSING ({len(tasks_data)} tasks)")
    print(f"{'='*80}\n")

    supervisor = ResearchSupervisor(
        model=args.model,
        max_iterations=args.iterations,
        confidence_threshold=args.confidence,
        enable_auto_approval=args.auto_approve,
    )

    results = []
    for i, task_data in enumerate(tasks_data, 1):
        print(f"\n[{i}/{len(tasks_data)}] Processing: {task_data.get('query', 'Untitled')[:60]}...")

        task = ResearchTask(
            query=task_data.get("query", ""),
            description=task_data.get("description"),
            research_depth=task_data.get("research_depth", "medium"),
        )

        try:
            state = supervisor.execute_research(
                task, require_approval=not args.no_approval
            )

            results.append(
                {
                    "task_id": task.task_id,
                    "query": task.query,
                    "status": state.approval_status.value,
                    "consensus": (
                        state.supervisor_consensus.confidence
                        if state.supervisor_consensus
                        else None
                    ),
                    "success": True,
                }
            )

            print(f"✓ Complete (Status: {state.approval_status.value})")

        except Exception as e:
            results.append(
                {
                    "task_id": task.task_id,
                    "query": task.query,
                    "error": str(e),
                    "success": False,
                }
            )
            print(f"✗ Error: {e}")

    # Display summary
    successful = sum(1 for r in results if r.get("success", False))
    print(f"\n{'='*80}")
    print(f"BATCH COMPLETE: {successful}/{len(results)} successful")
    print(f"{'='*80}\n")

    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"✓ Results saved to {args.output}")


def handle_audit_request(args):
    """Handle audit report request."""
    print(f"\n{'='*80}")
    print("AUDIT REPORT")
    print(f"{'='*80}\n")

    supervisor = ResearchSupervisor(model=args.model)

    # Get audit report
    report = supervisor.get_audit_report(args.audit)

    print(f"Task ID: {report['task_id']}")
    print(f"Total Actions: {report['total_actions']}")
    print(f"Timestamp: {report['timestamp']}\n")

    print("Actions by Type:")
    for action_type, count in sorted(report["actions_by_type"].items()):
        print(f"  {action_type}: {count}")

    print("\nActions by Actor:")
    for actor, count in sorted(report["actions_by_actor"].items()):
        print(f"  {actor}: {count}")

    if args.compliance:
        compliance = supervisor.get_compliance_summary(args.audit)
        print(f"\nCompliance Summary:")
        print(f"  Decisions: {compliance['total_decisions']}")
        print(f"  Approvals: {compliance['total_approvals']}")
        print(f"  Rejections: {compliance['total_rejections']}")
        if compliance["approvers"]:
            print(f"  Approvers: {', '.join(compliance['approvers'])}")

    # Save report if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n✓ Report saved to {args.output}")
    else:
        # Print full timeline if not saving to file
        print(f"\nTimeline ({len(report['timeline'])} entries):")
        for entry in report["timeline"][:5]:
            print(f"  [{entry['timestamp']}] {entry['action']} by {entry['actor']}")
        if len(report["timeline"]) > 5:
            print(f"  ... and {len(report['timeline']) - 5} more")


if __name__ == "__main__":
    main()
