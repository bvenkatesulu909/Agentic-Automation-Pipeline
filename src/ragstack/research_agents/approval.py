"""Human approval gate implementation."""

from abc import ABC, abstractmethod
from typing import Optional

from .models import ApprovalStatus, ResearchState


class ApprovalGate(ABC):
    """Abstract base class for approval gates."""

    @abstractmethod
    def request_approval(self, state: ResearchState) -> bool:
        """Request approval for research output.

        Args:
            state: Current research state

        Returns:
            True if approved, False if rejected
        """
        pass

    @abstractmethod
    def should_auto_approve(self, state: ResearchState) -> bool:
        """Determine if research should be auto-approved.

        Args:
            state: Current research state

        Returns:
            True if auto-approval criteria are met
        """
        pass


class HumanApprovalGate(ApprovalGate):
    """Interactive approval gate requiring human review."""

    def __init__(self, min_consensus_score: float = 0.85):
        """Initialize approval gate.

        Args:
            min_consensus_score: Minimum consensus score for auto-approval
        """
        self.min_consensus_score = min_consensus_score
        self.approval_history: list[dict] = []

    def request_approval(self, state: ResearchState) -> bool:
        """Request approval from user for research output."""
        if self.should_auto_approve(state):
            state.approval_status = ApprovalStatus.AUTO_APPROVED
            self._record_approval(state, approved=True, auto=True)
            return True

        # Display information for human review
        print("\n" + "=" * 80)
        print("APPROVAL REQUEST - RESEARCH OUTPUT REVIEW")
        print("=" * 80)

        self._display_research_summary(state)
        self._display_quality_metrics(state)

        # Get approval decision
        while True:
            response = input(
                "\nApprove this research output? (y/n/review): "
            ).lower().strip()

            if response == "y":
                state.approval_status = ApprovalStatus.APPROVED
                self._record_approval(state, approved=True, auto=False)
                print("✓ Research output approved.")
                return True

            elif response == "n":
                state.approval_status = ApprovalStatus.REJECTED
                feedback = input("Provide rejection feedback (optional): ").strip()
                self._record_approval(
                    state, approved=False, auto=False, feedback=feedback
                )
                print("✗ Research output rejected.")
                return False

            elif response == "review":
                self._display_detailed_review(state)

            else:
                print("Invalid response. Please enter 'y', 'n', or 'review'.")

    def should_auto_approve(self, state: ResearchState) -> bool:
        """Determine if research should be auto-approved.

        Auto-approval criteria:
        - Supervisor consensus exists
        - Consensus score >= min_consensus_score
        - No critical fact-checker issues
        """
        if not state.supervisor_consensus:
            return False

        consensus_score = state.supervisor_consensus.confidence
        if consensus_score < self.min_consensus_score:
            return False

        # Check for critical issues
        if state.fact_checker_decision:
            issues = state.fact_checker_decision.metadata.get("issues_found", [])
            critical_issues = [i for i in issues if "critical" in i.lower()]
            if critical_issues:
                return False

        return True

    def _display_research_summary(self, state: ResearchState) -> None:
        """Display summary of research findings."""
        print("\nRESEARCH SUMMARY")
        print("-" * 80)
        print(f"Query: {state.query}")
        print(f"Task ID: {state.task_id}")
        print(f"Iteration: {state.iteration}")

        if state.researcher_decision:
            print(f"\nResearcher Confidence: {state.researcher_decision.confidence:.2%}")
            print(f"Research Summary: {state.researcher_decision.content[:200]}...")

        if state.writer_decision:
            print(f"\nWriter Confidence: {state.writer_decision.confidence:.2%}")
            print(f"Output Preview: {state.writer_decision.content[:200]}...")

    def _display_quality_metrics(self, state: ResearchState) -> None:
        """Display quality metrics and consensus information."""
        print("\nQUALITY METRICS")
        print("-" * 80)

        if state.researcher_decision:
            print(
                f"Researcher Confidence: {state.researcher_decision.confidence:.2%} "
                f"({state.researcher_decision.reasoning})"
            )

        if state.writer_decision:
            print(
                f"Writer Confidence: {state.writer_decision.confidence:.2%} "
                f"({state.writer_decision.reasoning})"
            )

        if state.fact_checker_decision:
            print(
                f"Fact-Checker Confidence: {state.fact_checker_decision.confidence:.2%} "
                f"({state.fact_checker_decision.reasoning})"
            )
            issues = state.fact_checker_decision.metadata.get("issues_found", [])
            if issues:
                print(f"\nFact-Checker Issues ({len(issues)}):")
                for issue in issues[:3]:
                    print(f"  - {issue}")
                if len(issues) > 3:
                    print(f"  ... and {len(issues) - 3} more")

        if state.supervisor_consensus:
            print(
                f"\nSupervisor Consensus Score: {state.supervisor_consensus.confidence:.2%}"
            )
            print(
                f"Recommendation: {state.supervisor_consensus.reasoning[:100]}..."
            )

    def _display_detailed_review(self, state: ResearchState) -> None:
        """Display detailed review information."""
        print("\n" + "-" * 80)
        print("DETAILED REVIEW")
        print("-" * 80)

        if state.researcher_decision:
            print("\n[RESEARCHER FINDINGS]")
            print(state.researcher_decision.content)

        if state.writer_decision:
            print("\n[WRITTEN OUTPUT]")
            print(state.writer_decision.content)

        if state.fact_checker_decision:
            print("\n[FACT-CHECKER REPORT]")
            print(state.fact_checker_decision.content)

        if state.supervisor_consensus:
            print("\n[SUPERVISOR CONSENSUS]")
            print(state.supervisor_consensus.content)

    def _record_approval(
        self,
        state: ResearchState,
        approved: bool,
        auto: bool = False,
        feedback: str = "",
    ) -> None:
        """Record approval decision."""
        record = {
            "task_id": state.task_id,
            "approved": approved,
            "auto": auto,
            "feedback": feedback,
            "timestamp": state.updated_at.isoformat(),
        }
        self.approval_history.append(record)

    def get_approval_history(self) -> list[dict]:
        """Get history of all approval decisions."""
        return self.approval_history.copy()

    def add_rejection_reason(self, state: ResearchState, reason: str) -> None:
        """Add detailed rejection reason."""
        state.metadata = state.metadata or {}
        state.metadata["rejection_reasons"] = [reason]
